"""受控执行的用例（Phase 2B2 + Phase 2C1 审计门禁）。

Phase 2C1 把审计从"尽力而为的日志"提升为**访问真实业务数据库之前的安全门禁**：

```text
plan:    audit:start -> datasource -> authorize -> explain -> datasource -> authorize
         -> store:put -> audit:finish -> 返回 PLAN_CREATED
execute: store:claim -> audit:start -> datasource -> authorize -> gateway:execute
         -> audit:finish -> 返回结果
```

规则：

- 审计 start 失败立即返回 `AUDIT_UNAVAILABLE`，并且**不发起任何后续业务数据库调用**；
- plan 的审计 finish 失败必须作废已插入的 plan（`revoke`）且绝不返回 token；
- execute 的审计 finish 失败不返回查询结果，审计行保持在 `started`——已经发生的外部查询
  无法用分布式事务回滚，`started` 就是"执行结果未知"的保守证据；
- 取消继续传播 `asyncio.CancelledError`，但在有界 shield 中尽力把审计标记为稳定失败；
- 纯本地的输入自洽检查（身份/上限不匹配）不写审计：它们既不是策略判定也不触碰数据库。

权限与一次性语义（Phase 2B2）保持不变：完整语义授权重跑三次并要求 `AuthorizedQuerySpec`
精确相等；`claim()` 发生在所有外部 I/O 之前，失败后不恢复 token；HIGH 永不执行。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta

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
from app.analytics.application.persistence_ports import QueryAuditLog
from app.analytics.application.ports import DatasourceCatalog
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryAuditCompletion,
    QueryAuditPhase,
    QueryAuditStart,
    QueryExecutionDecision,
    QueryPlanDecision,
    QueryPlanReceipt,
    QueryRisk,
)

logger = logging.getLogger(__name__)

# 终态写入必须有限：取消路径上的清理不能无限阻塞取消传播。
_AUDIT_FINISH_TIMEOUT_SECONDS = 5.0
# 取消导致的中断没有专属决定码（本阶段只新增 AUDIT_UNAVAILABLE），统一映射为保守失败。
_CANCELLED_CODE = ExecutionDecisionCode.DATABASE_UNAVAILABLE


class _Denied(Exception):
    """内部拒绝载体：只携带稳定决定码，避免把异常文本带到调用方。"""

    def __init__(self, code: ExecutionDecisionCode) -> None:
        super().__init__(code.value)
        self.code = code


def _plan_failure(code: ExecutionDecisionCode) -> QueryPlanDecision:
    return QueryPlanDecision(code=code)


def _execution_failure(code: ExecutionDecisionCode) -> QueryExecutionDecision:
    return QueryExecutionDecision(code=code)


def _latency_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


class _ExecutionUseCaseBase:
    def __init__(
        self,
        *,
        datasource_catalog: DatasourceCatalog,
        authorize_prepared_query: AuthorizePreparedQuery,
        gateway: DatasourceQueryGateway,
        plan_store: ExecutionPlanStore,
        audit_log: QueryAuditLog,
        clock: Clock,
    ) -> None:
        self._datasource_catalog = datasource_catalog
        self._authorize_prepared_query = authorize_prepared_query
        self._gateway = gateway
        self._plan_store = plan_store
        self._audit_log = audit_log
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

    async def _start_audit(
        self,
        *,
        principal_id: str,
        datasource_id: str | None,
        phase: QueryAuditPhase,
        started_at: datetime,
        query_hash: str | None,
        risk: QueryRisk | None,
        schema_version: str | None,
        policy_version: str | None,
    ) -> str | None:
        """写入 `started` 记录；任何失败都返回 None（调用方必须 fail closed）。"""

        try:
            return await self._audit_log.start(
                QueryAuditStart(
                    principal_id=principal_id,
                    datasource_id=datasource_id,
                    phase=phase,
                    started_at=started_at,
                    query_hash=query_hash,
                    risk=risk,
                    schema_version=schema_version,
                    policy_version=policy_version,
                )
            )
        except Exception:  # noqa: BLE001 - 审计不可用时不得触碰业务数据库
            logger.warning("analytics: audit start failed; refusing to touch the business database")
            return None

    async def _bounded_finish(self, completion: QueryAuditCompletion) -> bool:
        """有界地尝试写入终态；失败只返回 False。取消异常不被吞掉。"""

        try:
            async with asyncio.timeout(_AUDIT_FINISH_TIMEOUT_SECONDS):
                await self._audit_log.finish(completion)
        except TimeoutError:
            logger.warning("analytics: audit finish timed out; the record stays started")
            return False
        except Exception:  # noqa: BLE001 - 终态写入失败必须让调用方 fail closed
            logger.warning("analytics: audit finish failed; the record stays started")
            return False
        return True

    async def _finish_after_cancellation(self, completion: QueryAuditCompletion) -> None:
        """取消传播中尽力写终态：有界、不吞取消、不无限阻塞。"""

        task = asyncio.ensure_future(self._bounded_finish(completion))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # 取消正在传播；清理已经交给 shield 保护的任务，继续抛出原取消。
            pass

    def _completion(
        self,
        *,
        audit_id: str,
        code: ExecutionDecisionCode,
        started_at: datetime,
        risk: QueryRisk | None,
        receipt: QueryPlanReceipt | None = None,
        result: object | None = None,
    ) -> QueryAuditCompletion:
        finished_at = self._clock.now()
        estimate = None if receipt is None else receipt.estimate
        return QueryAuditCompletion(
            audit_id=audit_id,
            decision_code=code.value,
            finished_at=finished_at,
            risk=risk,
            estimated_rows=None if estimate is None else estimate.estimated_rows,
            engine_cost=None if estimate is None else estimate.engine_cost,
            plan_digest=None if estimate is None else estimate.plan_digest,
            row_count=None if result is None else result.row_count,
            byte_count=None if result is None else result.byte_count,
            truncated=None if result is None else result.truncated,
            latency_ms=_latency_ms(started_at, finished_at),
        )


class CreateQueryExecutionPlan(_ExecutionUseCaseBase):
    def __init__(
        self,
        *,
        datasource_catalog: DatasourceCatalog,
        authorize_prepared_query: AuthorizePreparedQuery,
        gateway: DatasourceQueryGateway,
        plan_store: ExecutionPlanStore,
        audit_log: QueryAuditLog,
        clock: Clock,
        token_issuer: PlanTokenIssuer,
    ) -> None:
        super().__init__(
            datasource_catalog=datasource_catalog,
            authorize_prepared_query=authorize_prepared_query,
            gateway=gateway,
            plan_store=plan_store,
            audit_log=audit_log,
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
        # 输入身份必须自洽：plan 只能绑定它自己声明的主体与数据源。
        if authorized.principal_id != principal_id or authorized.datasource_id != datasource_id:
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)
        # 传输层上限不得高于 SQL 层 row_limit，否则等于放宽授权值的义务。
        if limits.max_result_rows > authorized.prepared.row_limit:
            return _plan_failure(ExecutionDecisionCode.AUTHORIZATION_STALE)

        started_at = self._clock.now()
        audit_id = await self._start_audit(
            principal_id=principal_id,
            datasource_id=datasource_id,
            phase=QueryAuditPhase.PLAN,
            started_at=started_at,
            query_hash=authorized.prepared.query_hash,
            risk=authorized.risk,
            schema_version=authorized.schema_version,
            policy_version=authorized.policy_version,
        )
        if audit_id is None:
            return _plan_failure(ExecutionDecisionCode.AUDIT_UNAVAILABLE)

        try:
            decision = await self._create_after_audit(principal_id=principal_id, datasource_id=datasource_id, authorized=authorized, limits=limits)
        except asyncio.CancelledError:
            await self._finish_after_cancellation(
                self._completion(audit_id=audit_id, code=_CANCELLED_CODE, started_at=started_at, risk=authorized.risk),
            )
            raise
        except _Denied as denial:
            decision = _plan_failure(denial.code)
        except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏文本
            decision = _plan_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE)

        completion = self._completion(audit_id=audit_id, code=decision.code, started_at=started_at, risk=authorized.risk, receipt=decision.receipt)
        if not await self._bounded_finish(completion):
            await self._revoke_plan(decision)
            return _plan_failure(ExecutionDecisionCode.AUDIT_UNAVAILABLE)
        return decision

    async def _revoke_plan(self, decision: QueryPlanDecision) -> None:
        """审计 finish 失败时作废已插入的 plan：绝不返回可执行 token。"""

        receipt = decision.receipt
        if receipt is None:
            return
        digest = hashlib.sha256(receipt.plan_id.encode()).hexdigest()
        try:
            await self._plan_store.revoke(token_digest=digest)
        except Exception:  # noqa: BLE001
            # token 从未返回给调用方，因此即使 revoke 失败也不存在可被使用的能力；
            # 这里只保留一条不含摘要的告警。
            logger.warning("analytics: failed to revoke an undeliverable plan; the token was never returned")

    async def _create_after_audit(
        self,
        *,
        principal_id: str,
        datasource_id: str,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryPlanDecision:
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
        started_at = self._clock.now()
        risk = plan.authorized.risk
        audit_id = await self._start_audit(
            principal_id=principal_id,
            datasource_id=plan.datasource.id,
            phase=QueryAuditPhase.EXECUTE,
            started_at=started_at,
            query_hash=plan.authorized.prepared.query_hash,
            risk=risk,
            schema_version=plan.authorized.schema_version,
            policy_version=plan.authorized.policy_version,
        )
        if audit_id is None:
            # token 保持已消费；审计写不进去就绝不访问业务数据库。
            return _execution_failure(ExecutionDecisionCode.AUDIT_UNAVAILABLE)

        try:
            decision = await self._execute_after_audit(principal_id=principal_id, plan=plan)
        except asyncio.CancelledError:
            await self._finish_after_cancellation(self._completion(audit_id=audit_id, code=_CANCELLED_CODE, started_at=started_at, risk=risk))
            raise
        except _Denied as denial:
            decision = _execution_failure(denial.code)
        except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏文本
            decision = _execution_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE)

        completion = self._completion(audit_id=audit_id, code=decision.code, started_at=started_at, risk=risk, result=decision.result)
        if not await self._bounded_finish(completion):
            # 审计没能写下终态：结果不得返回，记录停留在 started 作为"结果未知"的证据。
            return _execution_failure(ExecutionDecisionCode.AUDIT_UNAVAILABLE)
        return decision

    async def _execute_after_audit(self, *, principal_id: str, plan: StoredExecutionPlan) -> QueryExecutionDecision:
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
