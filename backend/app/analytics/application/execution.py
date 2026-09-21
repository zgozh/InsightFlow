import hashlib
from datetime import timedelta

from app.analytics.application.authorization import AuthorizePreparedQuery
from app.analytics.application.execution_ports import (
    Clock,
    DatasourceQueryError,
    DatasourceQueryGateway,
    ExecutionPlanStore,
    ExecutionPlanStoreError,
    PlanTokenIssuer,
    StoredExecutionPlan,
)
from app.analytics.application.ports import DatasourceCatalog
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryExecutionDecision,
    QueryPlanDecision,
    QueryPlanReceipt,
)


class _Denied(Exception):
    """内部拒绝载体：只携带稳定决定码，避免把异常文本带到调用方。"""

    def __init__(self, code: ExecutionDecisionCode) -> None:
        super().__init__(code.value)
        self.code = code


def _plan_failure(code: ExecutionDecisionCode) -> QueryPlanDecision:
    return QueryPlanDecision(code=code)


def _execution_failure(code: ExecutionDecisionCode) -> QueryExecutionDecision:
    return QueryExecutionDecision(code=code)


class _ExecutionUseCaseBase:
    def __init__(
        self,
        *,
        datasource_catalog: DatasourceCatalog,
        authorize_prepared_query: AuthorizePreparedQuery,
        gateway: DatasourceQueryGateway,
        plan_store: ExecutionPlanStore,
        clock: Clock,
    ) -> None:
        self._datasource_catalog = datasource_catalog
        self._authorize_prepared_query = authorize_prepared_query
        self._gateway = gateway
        self._plan_store = plan_store
        self._clock = clock

    async def _load_active_datasource(self, principal_id: str, datasource_id: str) -> DatasourceDefinition:
        try:
            datasource = await self._datasource_catalog.get_accessible(principal_id=principal_id, datasource_id=datasource_id)
        except Exception as error:  # noqa: BLE001 - 任何 catalog 失败都必须默认拒绝
            raise _Denied(ExecutionDecisionCode.DATASOURCE_UNAVAILABLE) from error
        if datasource is None or datasource.status is not DatasourceStatus.ACTIVE:
            raise _Denied(ExecutionDecisionCode.DATASOURCE_UNAVAILABLE)
        return datasource

    async def _authorization_matches(
        self,
        principal_id: str,
        datasource_id: str,
        authorized: AuthorizedQuerySpec,
    ) -> bool:
        """重跑完整 Phase 2B1，并要求新的授权值与计划内的值 dataclass 精确相等。

        只比较 version 是不够的：schema/policy 内容可能在版本号未变时漂移。
        """

        try:
            decision = await self._authorize_prepared_query.execute(
                principal_id=principal_id,
                datasource_id=datasource_id,
                prepared=authorized.prepared,
            )
        except Exception as error:  # noqa: BLE001 - 授权链失败不得降级为放行
            raise _Denied(ExecutionDecisionCode.DATABASE_UNAVAILABLE) from error
        return decision.allowed and decision.authorized == authorized


class CreateQueryExecutionPlan(_ExecutionUseCaseBase):
    def __init__(
        self,
        *,
        datasource_catalog: DatasourceCatalog,
        authorize_prepared_query: AuthorizePreparedQuery,
        gateway: DatasourceQueryGateway,
        plan_store: ExecutionPlanStore,
        clock: Clock,
        token_issuer: PlanTokenIssuer,
    ) -> None:
        super().__init__(
            datasource_catalog=datasource_catalog,
            authorize_prepared_query=authorize_prepared_query,
            gateway=gateway,
            plan_store=plan_store,
            clock=clock,
        )
        self._token_issuer = token_issuer

    async def execute(
        self,
        *,
        principal_id: str,
        datasource_id: str,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryPlanDecision:
        try:
            return await self._create(principal_id=principal_id, datasource_id=datasource_id, authorized=authorized, limits=limits)
        except _Denied as denial:
            return _plan_failure(denial.code)

    async def _create(
        self,
        *,
        principal_id: str,
        datasource_id: str,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryPlanDecision:
        # 输入身份必须自洽：plan 只能绑定它自己声明的主体与数据源。
        if authorized.principal_id != principal_id or authorized.datasource_id != datasource_id:
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)
        # 传输层上限不得高于 SQL 层 row_limit，否则等于放宽授权值的义务。
        if limits.max_result_rows > authorized.prepared.row_limit:
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)

        before_explain = await self._load_active_datasource(principal_id, datasource_id)
        if not await self._authorization_matches(principal_id, datasource_id, authorized):
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)

        try:
            estimate = await self._gateway.explain(datasource=before_explain, authorized=authorized, limits=limits)
        except DatasourceQueryError as error:
            return _plan_failure(error.code)
        except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏文本
            return _plan_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE)

        if estimate.estimated_rows > limits.max_estimated_rows or estimate.engine_cost > limits.max_engine_cost:
            return _plan_failure(ExecutionDecisionCode.COST_LIMIT_EXCEEDED)

        # EXPLAIN 之后必须重做数据源与授权复验：两者之间可能已经漂移。
        after_explain = await self._load_active_datasource(principal_id, datasource_id)
        if after_explain != before_explain:
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)
        if not await self._authorization_matches(principal_id, datasource_id, authorized):
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)

        token = self._token_issuer.issue()
        issued_at = self._clock.now()
        expires_at = issued_at + timedelta(seconds=limits.plan_ttl_seconds)
        plan = StoredExecutionPlan(
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
            principal_id=principal_id,
            datasource=after_explain,
            authorized=authorized,
            estimate=estimate,
            limits=limits,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        try:
            await self._plan_store.put(plan)
        except ExecutionPlanStoreError:
            return _plan_failure(ExecutionDecisionCode.PLAN_STORE_UNAVAILABLE)
        except Exception:  # noqa: BLE001 - store 失败不得降级为签发
            return _plan_failure(ExecutionDecisionCode.PLAN_STORE_UNAVAILABLE)

        return QueryPlanDecision(
            code=ExecutionDecisionCode.PLAN_CREATED,
            receipt=QueryPlanReceipt(plan_id=token, expires_at=expires_at, estimate=estimate),
        )


class ExecuteQueryPlan(_ExecutionUseCaseBase):
    async def execute(self, *, principal_id: str, plan_id: str) -> QueryExecutionDecision:
        try:
            return await self._execute(principal_id=principal_id, plan_id=plan_id)
        except _Denied as denial:
            return _execution_failure(denial.code)

    async def _execute(self, *, principal_id: str, plan_id: str) -> QueryExecutionDecision:
        # claim 必须先于任何外部 I/O：同一 token 的并发请求只能有一个进入数据库。
        digest = hashlib.sha256(plan_id.encode()).hexdigest()
        try:
            plan = await self._plan_store.claim(
                token_digest=digest,
                principal_id=principal_id,
                now=self._clock.now(),
            )
        except Exception:  # noqa: BLE001 - store 不可用时不能把未知状态当成可用 plan
            return _execution_failure(ExecutionDecisionCode.PLAN_UNAVAILABLE)
        if plan is None:
            # 不存在、过期、已领取、principal 不匹配统一返回同一码，防止枚举。
            return _execution_failure(ExecutionDecisionCode.PLAN_UNAVAILABLE)

        # 从这里开始 token 已经消费；任何失败都不恢复，避免重放和重复成本。
        datasource = await self._load_active_datasource(principal_id, plan.datasource.id)
        if datasource != plan.datasource:
            raise _Denied(ExecutionDecisionCode.AUTHORIZATION_STALE)
        if not await self._authorization_matches(principal_id, plan.datasource.id, plan.authorized):
            raise _Denied(ExecutionDecisionCode.AUTHORIZATION_STALE)

        try:
            result = await self._gateway.execute(datasource=datasource, authorized=plan.authorized, limits=plan.limits)
        except DatasourceQueryError as error:
            return _execution_failure(error.code)
        except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏文本
            return _execution_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE)

        code = ExecutionDecisionCode.RESULT_LIMIT_REACHED if result.truncated else ExecutionDecisionCode.EXECUTED
        return QueryExecutionDecision(code=code, result=result)
