"""raw SQL 交付编排（Phase 2C2 §5.2、§5.3）。

这是系统里**唯一**接受原始 SQL 的入口，也是 HTTP 层与 Phase 3 Agent Tool 共用的应用服务：

```text
可访问 datasource -> Phase 2A policy -> Phase 2B1 authorization -> CreateQueryExecutionPlan
```

边界：

- 只接受认证 `principal_id`、客户端 `datasource_id` 与短生命周期 `raw_sql`；限额来自服务端
  配置，授权值来自服务端重跑，两者都不接受客户端输入；
- 返回的是**窄的交付决定**：一个稳定 `code`（可能来自 policy、authorization 或执行决定码）
  加上成功时的 plan receipt；绝不返回 raw SQL、`PreparedQuery` 或 `AuthorizedQuerySpec`；
- policy/authorization 拒绝会写对应阶段的审计；审计 start 或 finish 失败统一
  `AUDIT_UNAVAILABLE` 并停止后续步骤；
- raw SQL 只以 Phase 2A 的 SHA-256 `query_hash` 进入审计，异常文本一律不外发。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.analytics.application.authorization import AuthorizePreparedQuery
from app.analytics.application.execution import CreateQueryExecutionPlan, ExecuteQueryPlan
from app.analytics.application.execution_ports import Clock
from app.analytics.application.persistence_ports import QueryAuditLog
from app.analytics.application.ports import DatasourceCatalog
from app.analytics.application.query_policy import QueryPolicy
from app.analytics.config import AnalyticsConfig
from app.analytics.domain import (
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryAuditCompletion,
    QueryAuditPhase,
    QueryAuditStart,
    QueryExecutionResult,
    QueryPlanReceipt,
    QueryPolicyRequest,
    QueryRisk,
)


@dataclass(frozen=True, slots=True)
class QueryPlanDeliveryMetadata:
    """plan 阶段产出的**安全**元数据，供 Phase 3 evidence 使用。

    只含审计表里本就有的字段：datasource、Phase 2A 的 `query_hash`、风险级别与 schema/policy
    版本。没有 SQL、token、secret 或凭证；HTTP DTO 不会顺带暴露它。
    """

    datasource_id: str
    query_hash: str
    risk: QueryRisk
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        for field_name in ("datasource_id", "schema_version", "policy_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{field_name} must be a non-empty trimmed string")
        if not isinstance(self.query_hash, str) or len(self.query_hash) != 64 or any(character not in "0123456789abcdef" for character in self.query_hash):
            raise ValueError("query_hash must be 64 lowercase hexadecimal characters")
        if not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be a QueryRisk")


@dataclass(frozen=True, slots=True)
class QueryPlanDelivery:
    """plan 交付结果：稳定码 + 成功时的一次性 plan receipt + 安全元数据。"""

    code: str
    receipt: QueryPlanReceipt | None = None
    metadata: QueryPlanDeliveryMetadata | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip() or self.code != self.code.strip():
            raise ValueError("code must be a non-empty trimmed string")
        if self.receipt is not None and not isinstance(self.receipt, QueryPlanReceipt):
            raise ValueError("receipt must be a QueryPlanReceipt")
        if self.metadata is not None and not isinstance(self.metadata, QueryPlanDeliveryMetadata):
            raise ValueError("metadata must be a QueryPlanDeliveryMetadata")
        if (self.code == ExecutionDecisionCode.PLAN_CREATED.value) != (self.receipt is not None):
            raise ValueError("only a created plan may carry a receipt")
        # receipt 与 metadata 同时产出：只有它们都存在时 Phase 3 才可能构造 evidence。
        if (self.receipt is not None) != (self.metadata is not None):
            raise ValueError("a receipt and its metadata must be provided together")


@dataclass(frozen=True, slots=True)
class QueryExecutionDelivery:
    """执行交付结果：稳定码 + 有界结果（只有成功/截断才带结果）。"""

    code: str
    result: QueryExecutionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip() or self.code != self.code.strip():
            raise ValueError("code must be a non-empty trimmed string")
        if self.result is not None and not isinstance(self.result, QueryExecutionResult):
            raise ValueError("result must be a QueryExecutionResult")
        carries_result = self.code in (ExecutionDecisionCode.EXECUTED.value, ExecutionDecisionCode.RESULT_LIMIT_REACHED.value)
        if carries_result != (self.result is not None):
            raise ValueError("only an executed or truncated outcome may carry a result")


class PlanAnalyticsQuery:
    """raw SQL → 一次性 plan 的交付编排。"""

    def __init__(
        self,
        *,
        config: AnalyticsConfig,
        datasource_catalog: DatasourceCatalog,
        query_policy: QueryPolicy,
        authorize_prepared_query: AuthorizePreparedQuery,
        create_plan: CreateQueryExecutionPlan,
        audit_log: QueryAuditLog,
        clock: Clock,
    ) -> None:
        self._config = config
        self._datasource_catalog = datasource_catalog
        self._query_policy = query_policy
        self._authorize_prepared_query = authorize_prepared_query
        self._create_plan = create_plan
        self._audit_log = audit_log
        self._clock = clock

    async def _record_denial(
        self,
        *,
        phase: QueryAuditPhase,
        code: str,
        principal_id: str,
        datasource_id: str,
        query_hash: str | None,
        risk: QueryRisk | None,
    ) -> bool:
        """写入一次拒绝审计；任何失败都返回 False（调用方 fail closed）。"""

        started_at = self._clock.now()
        try:
            audit_id = await self._audit_log.start(
                QueryAuditStart(
                    principal_id=principal_id,
                    datasource_id=datasource_id,
                    phase=phase,
                    started_at=started_at,
                    query_hash=query_hash,
                    risk=risk,
                )
            )
        except Exception:  # noqa: BLE001 - 审计写不进去就不能继续
            return False

        finished_at = self._clock.now()
        try:
            await self._audit_log.finish(
                QueryAuditCompletion(
                    audit_id=audit_id,
                    decision_code=code,
                    finished_at=finished_at,
                    risk=risk,
                    latency_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
                )
            )
        except Exception:  # noqa: BLE001 - 终态写不进去同样按不可用处理
            return False
        return True

    def _plan_limits(self, authorized: AuthorizedQuerySpec) -> ExecutionLimits:
        """为本次计划派生执行限额：只把传输行上限向下收紧到授权查询的 row_limit。

        `max_result_rows` 是**全局服务器上限**，不是每条查询必须达到的下限——否则
        `SELECT ... LIMIT 10` 会因为 1000 > 10 被判 `authorization_stale`。这里取
        `min(配置上限, prepared.row_limit)`：客户端仍然无法提交或覆盖任何限额，结果上限只可能
        变小而不可能变大，其余字段继续固定来自启动配置。`CreateQueryExecutionPlan` 里
        `limits.max_result_rows <= prepared.row_limit` 的校验保留为纵深防御。
        """

        configured = self._config.execution_limits()
        effective = min(configured.max_result_rows, authorized.prepared.row_limit)
        if effective == configured.max_result_rows:
            return configured
        # `replace` 会重跑 ExecutionLimits 的不变量校验，收紧后的值仍然必须自洽。
        return replace(configured, max_result_rows=effective)

    async def execute(self, *, principal_id: str, datasource_id: str, raw_sql: str) -> QueryPlanDelivery:
        try:
            datasource = await self._datasource_catalog.get_accessible(principal_id=principal_id, datasource_id=datasource_id)
        except Exception:  # noqa: BLE001 - catalog 失败必须默认拒绝且不泄漏文本
            return QueryPlanDelivery(code=ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value)
        if datasource is None or datasource.status is not DatasourceStatus.ACTIVE:
            return QueryPlanDelivery(code=ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value)

        try:
            policy_decision = self._query_policy.evaluate(
                QueryPolicyRequest(sql=raw_sql, engine=datasource.engine, max_rows=self._config.query_max_rows),
            )
        except Exception:  # noqa: BLE001 - 分析失败不得降级为放行
            return QueryPlanDelivery(code=AuthorizationDecisionCode.ANALYSIS_ERROR.value)

        if not policy_decision.allowed:
            code = policy_decision.codes[0].value
            written = await self._record_denial(
                phase=QueryAuditPhase.POLICY,
                code=code,
                principal_id=principal_id,
                datasource_id=datasource_id,
                query_hash=None,
                risk=policy_decision.risk,
            )
            if not written:
                return QueryPlanDelivery(code=ExecutionDecisionCode.AUDIT_UNAVAILABLE.value)
            return QueryPlanDelivery(code=code)

        prepared = policy_decision.prepared
        if prepared is None:  # pragma: no cover - 领域不变量保证 allowed 必有 prepared
            return QueryPlanDelivery(code=AuthorizationDecisionCode.ANALYSIS_ERROR.value)

        try:
            authorization = await self._authorize_prepared_query.execute(principal_id=principal_id, datasource_id=datasource_id, prepared=prepared)
        except Exception:  # noqa: BLE001 - 授权链失败不得降级为放行
            return QueryPlanDelivery(code=ExecutionDecisionCode.DATABASE_UNAVAILABLE.value)

        if not authorization.allowed:
            code = authorization.codes[0].value
            written = await self._record_denial(
                phase=QueryAuditPhase.AUTHORIZATION,
                code=code,
                principal_id=principal_id,
                datasource_id=datasource_id,
                # 只有 Phase 2A 产生的摘要进审计；prepared.sql 本身绝不落库。
                query_hash=prepared.query_hash,
                risk=authorization.risk,
            )
            if not written:
                return QueryPlanDelivery(code=ExecutionDecisionCode.AUDIT_UNAVAILABLE.value)
            return QueryPlanDelivery(code=code)

        authorized = authorization.authorized
        if authorized is None:  # pragma: no cover - 领域不变量保证 allowed 必有 authorized
            return QueryPlanDelivery(code=AuthorizationDecisionCode.ANALYSIS_ERROR.value)

        try:
            plan_decision = await self._create_plan.execute(
                principal_id=principal_id,
                datasource_id=datasource_id,
                authorized=authorized,
                limits=self._plan_limits(authorized),
            )
        except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏文本
            return QueryPlanDelivery(code=ExecutionDecisionCode.DATABASE_UNAVAILABLE.value)

        return QueryPlanDelivery(
            code=plan_decision.code.value,
            receipt=plan_decision.receipt,
            # 只有签发成功才带安全元数据：拒绝路径没有可引用的 authorized 值。
            metadata=None
            if plan_decision.receipt is None
            else QueryPlanDeliveryMetadata(
                datasource_id=authorized.datasource_id,
                query_hash=authorized.prepared.query_hash,
                risk=authorized.risk,
                schema_version=authorized.schema_version,
                policy_version=authorized.policy_version,
            ),
        )


class ExecuteAnalyticsQuery:
    """一次性 plan → 结果的薄入口；HTTP 与 Phase 3 Agent Tool 共用。"""

    def __init__(self, *, execute_plan: ExecuteQueryPlan) -> None:
        self._execute_plan = execute_plan

    async def execute(self, *, principal_id: str, plan_id: str) -> QueryExecutionDelivery:
        decision = await self._execute_plan.execute(principal_id=principal_id, plan_id=plan_id)
        return QueryExecutionDelivery(code=decision.code.value, result=decision.result)


__all__ = ["ExecuteAnalyticsQuery", "PlanAnalyticsQuery", "QueryExecutionDelivery", "QueryPlanDelivery"]
