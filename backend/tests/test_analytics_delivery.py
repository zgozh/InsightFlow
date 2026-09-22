"""raw SQL 交付编排测试（Phase 2C2 任务 3）。

`PlanAnalyticsQuery` 是唯一的 raw SQL 入口，它只接受认证主体、客户端 datasource ID 与短
生命周期 SQL，然后把**服务端派生**的授权值与**服务端配置**的执行限额交给 2C1 的
`CreateQueryExecutionPlan`。

这里固定的是顺序与脱敏：

- 可访问 datasource → policy → authorization → plan；
- policy/authorization 拒绝会写对应的审计并返回稳定码；
- 审计 start/finish 失败统一 `AUDIT_UNAVAILABLE`，且不继续后续步骤；
- raw SQL 只以 Phase 2A 的 SHA-256 query_hash 进入审计，绝不进入返回对象或异常文本。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analytics.application.delivery import (
    ExecuteAnalyticsQuery,
    PlanAnalyticsQuery,
    QueryExecutionDelivery,
    QueryPlanDelivery,
)
from app.analytics.config import AnalyticsConfig
from app.analytics.domain import (
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionDecisionCode,
    PreparedQuery,
    QueryAuthorizationDecision,
    QueryCostEstimate,
    QueryDecisionCode,
    QueryExecutionDecision,
    QueryExecutionResult,
    QueryPlanDecision,
    QueryPlanReceipt,
    QueryPolicyDecision,
    QueryPolicyRequest,
    QueryRisk,
)
from app.analytics.domain import (
    ExecutionDecisionCode as ExecutionCode,
)

_SQL = "SELECT id FROM orders LIMIT 10"
_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_HASH = "b" * 64


def _datasource(**overrides) -> DatasourceDefinition:
    values = {"id": "ds-1", "owner_id": "user-1", "name": "Warehouse", "engine": DatasourceEngine.POSTGRESQL, "secret_ref": "env://ANALYTICS_DS", "default_schema": "public", "status": DatasourceStatus.ACTIVE}
    values.update(overrides)
    return DatasourceDefinition(**values)


def _prepared(**overrides) -> PreparedQuery:
    values = {"sql": _SQL, "engine": DatasourceEngine.POSTGRESQL, "relations": ("orders",), "row_limit": 10, "query_hash": _HASH}
    values.update(overrides)
    return PreparedQuery(**values)


def _authorized(**overrides) -> AuthorizedQuerySpec:
    values = {
        "prepared": _prepared(),
        "datasource_id": "ds-1",
        "principal_id": "user-1",
        "schema_version": "s1",
        "policy_version": "p1",
        "relations": ("public.orders",),
        "columns": ("public.orders.id",),
        "functions": (),
        "risk": QueryRisk.LOW,
    }
    values.update(overrides)
    return AuthorizedQuerySpec(**values)


class _Catalog:
    def __init__(self, datasource, *, events, error=None):
        self._datasource = datasource
        self._error = error
        self._events = events

    async def list_accessible(self, *, principal_id):
        return ()

    async def get_accessible(self, *, principal_id, datasource_id):
        self._events.append("datasource")
        if self._error is not None:
            raise self._error
        return self._datasource


class _Policy:
    def __init__(self, decision=None, *, events, error=None):
        self._decision = decision
        self._error = error
        self._events = events
        self.requests: list[QueryPolicyRequest] = []

    def evaluate(self, request):
        self._events.append("policy")
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._decision


class _Authorizer:
    def __init__(self, decision=None, *, events, error=None):
        self._decision = decision
        self._error = error
        self._events = events
        self.calls: list[PreparedQuery] = []

    async def execute(self, *, principal_id, datasource_id, prepared):
        self._events.append("authorization")
        self.calls.append(prepared)
        if self._error is not None:
            raise self._error
        return self._decision


class _CreatePlan:
    def __init__(self, decision=None, *, events, error=None):
        self._decision = decision
        self._error = error
        self._events = events
        self.calls: list[dict] = []

    async def execute(self, *, principal_id, datasource_id, authorized, limits):
        self._events.append("plan")
        self.calls.append({"principal_id": principal_id, "datasource_id": datasource_id, "authorized": authorized, "limits": limits})
        if self._error is not None:
            raise self._error
        return self._decision


class _ExecutePlan:
    def __init__(self, decision=None, *, events, error=None):
        self._decision = decision
        self._error = error
        self._events = events
        self.calls: list[dict] = []

    async def execute(self, *, principal_id, plan_id):
        self._events.append("execute")
        self.calls.append({"principal_id": principal_id, "plan_id": plan_id})
        if self._error is not None:
            raise self._error
        return self._decision


class _Audit:
    def __init__(self, *, events, start_error=None, finish_error=None):
        self._events = events
        self._start_error = start_error
        self._finish_error = finish_error
        self.started: list = []
        self.finished: list = []

    async def start(self, entry):
        self._events.append("audit:start")
        if self._start_error is not None:
            raise self._start_error
        self.started.append(entry)
        return f"audit-{len(self.started)}"

    async def finish(self, completion):
        self._events.append("audit:finish")
        if self._finish_error is not None:
            raise self._finish_error
        self.finished.append(completion)


class _Clock:
    def now(self):
        return _NOW


def _allow_policy(*, prepared=None) -> QueryPolicyDecision:
    return QueryPolicyDecision(allowed=True, risk=QueryRisk.LOW, codes=(QueryDecisionCode.APPROVED,), prepared=prepared or _prepared())


def _deny_policy(code=QueryDecisionCode.FORBIDDEN_OPERATION) -> QueryPolicyDecision:
    return QueryPolicyDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=(code,))


def _allow_authorization(spec=None) -> QueryAuthorizationDecision:
    authorized = spec or _authorized()
    return QueryAuthorizationDecision(allowed=True, risk=authorized.risk, codes=(AuthorizationDecisionCode.APPROVED,), authorized=authorized)


def _deny_authorization(code=AuthorizationDecisionCode.RELATION_NOT_ALLOWED, *, risk=QueryRisk.BLOCKED) -> QueryAuthorizationDecision:
    return QueryAuthorizationDecision(allowed=False, risk=risk, codes=(code,))


def _plan_created() -> QueryPlanDecision:
    return QueryPlanDecision(
        code=ExecutionDecisionCode.PLAN_CREATED,
        receipt=QueryPlanReceipt(plan_id="raw-token", expires_at=_NOW, estimate=QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)),
    )


def _use_case(*, catalog, policy, authorizer, create_plan, audit, config=None):
    return PlanAnalyticsQuery(
        config=config or AnalyticsConfig(),
        datasource_catalog=catalog,
        query_policy=policy,
        authorize_prepared_query=authorizer,
        create_plan=create_plan,
        audit_log=audit,
        clock=_Clock(),
    )


# --- 顺序 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_documented_sequence_runs_and_returns_the_plan_receipt():
    events: list[str] = []
    policy = _Policy(_allow_policy(), events=events)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(catalog=_Catalog(_datasource(), events=events), policy=policy, authorizer=_Authorizer(_allow_authorization(), events=events), create_plan=create_plan, audit=_Audit(events=events))

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=ExecutionDecisionCode.PLAN_CREATED.value, receipt=_plan_created().receipt)
    assert events == ["datasource", "policy", "authorization", "plan"]
    # 成功路径没有额外的 policy/authorization 审计：plan 阶段由 2C1 用例自己写。
    assert policy.requests[0].max_rows == AnalyticsConfig().query_max_rows
    assert policy.requests[0].engine is DatasourceEngine.POSTGRESQL
    assert policy.requests[0].sql == _SQL


@pytest.mark.asyncio
async def test_the_plan_use_case_receives_only_server_derived_values():
    events: list[str] = []
    authorized = _authorized()
    config = AnalyticsConfig.from_app_config(type("C", (), {"analytics": {"query_max_rows": 321, "max_result_rows": 300}})())
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    call = create_plan.calls[0]
    assert call["authorized"] is authorized
    # 限额来自服务端配置，唯一的变化是把传输行上限向下收紧到该查询的 row_limit。
    configured = config.execution_limits()
    assert configured.max_result_rows == 300 and authorized.prepared.row_limit == 10
    assert call["limits"] == replace(configured, max_result_rows=10)
    assert (call["principal_id"], call["datasource_id"]) == ("user-1", "ds-1")


# --- 拒绝与审计 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_policy_denial_writes_a_policy_audit_and_stops():
    events: list[str] = []
    audit = _Audit(events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events), policy=_Policy(_deny_policy(), events=events), authorizer=_Authorizer(_allow_authorization(), events=events), create_plan=_CreatePlan(_plan_created(), events=events), audit=audit
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=QueryDecisionCode.FORBIDDEN_OPERATION.value)
    assert events == ["datasource", "policy", "audit:start", "audit:finish"]
    assert audit.started[0].phase.value == "policy"
    assert audit.finished[0].decision_code == QueryDecisionCode.FORBIDDEN_OPERATION.value


@pytest.mark.asyncio
async def test_an_authorization_denial_writes_an_authorization_audit_and_stops():
    events: list[str] = []
    audit = _Audit(events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events), policy=_Policy(_allow_policy(), events=events), authorizer=_Authorizer(_deny_authorization(), events=events), create_plan=_CreatePlan(_plan_created(), events=events), audit=audit
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=AuthorizationDecisionCode.RELATION_NOT_ALLOWED.value)
    assert events == ["datasource", "policy", "authorization", "audit:start", "audit:finish"]
    assert audit.started[0].phase.value == "authorization"
    # 拒绝路径没有 prepared 授权值，但 Phase 2A 的 query_hash 仍然要写进审计。
    assert audit.started[0].query_hash == _HASH


@pytest.mark.asyncio
async def test_high_risk_denial_is_never_executed_and_has_no_approval_path():
    events: list[str] = []
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(), events=events),
        authorizer=_Authorizer(_deny_authorization(AuthorizationDecisionCode.APPROVAL_REQUIRED, risk=QueryRisk.HIGH), events=events),
        create_plan=_CreatePlan(_plan_created(), events=events),
        audit=_Audit(events=events),
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery.code == AuthorizationDecisionCode.APPROVAL_REQUIRED.value
    assert delivery.receipt is None
    assert "plan" not in events


@pytest.mark.asyncio
async def test_an_audit_start_failure_stops_before_the_denial_continues():
    events: list[str] = []
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_deny_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(), events=events),
        create_plan=_CreatePlan(_plan_created(), events=events),
        audit=_Audit(events=events, start_error=RuntimeError("audit store down")),
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=ExecutionDecisionCode.AUDIT_UNAVAILABLE.value)
    assert events == ["datasource", "policy", "audit:start"]


@pytest.mark.asyncio
async def test_an_audit_finish_failure_returns_audit_unavailable_instead_of_the_denial():
    events: list[str] = []
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_deny_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(), events=events),
        create_plan=_CreatePlan(_plan_created(), events=events),
        audit=_Audit(events=events, finish_error=RuntimeError("audit store down")),
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=ExecutionDecisionCode.AUDIT_UNAVAILABLE.value)


# --- 默认拒绝与脱敏 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_an_missing_or_inactive_datasource_is_denied_without_audit():
    for datasource in (None, _datasource(status=DatasourceStatus.DISABLED)):
        events: list[str] = []
        use_case = _use_case(
            catalog=_Catalog(datasource, events=events),
            policy=_Policy(_allow_policy(), events=events),
            authorizer=_Authorizer(_allow_authorization(), events=events),
            create_plan=_CreatePlan(_plan_created(), events=events),
            audit=_Audit(events=events),
        )

        delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

        assert delivery == QueryPlanDelivery(code=ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value)
        assert events == ["datasource"]


@pytest.mark.asyncio
async def test_catalog_driver_policy_and_authorizer_failures_are_denied_without_leaking_text():
    dsn = "postgres://user:pw@host/db"

    cases = [
        ({"catalog": _Catalog(_datasource(), events=[], error=RuntimeError(dsn))}, ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value),
        ({"policy": _Policy(None, events=[], error=RuntimeError(dsn))}, AuthorizationDecisionCode.ANALYSIS_ERROR.value),
        ({"authorizer": _Authorizer(None, events=[], error=RuntimeError(dsn))}, ExecutionDecisionCode.DATABASE_UNAVAILABLE.value),
    ]

    for overrides, expected in cases:
        events: list[str] = []
        use_case = _use_case(
            catalog=overrides.get("catalog", _Catalog(_datasource(), events=events)),
            policy=overrides.get("policy", _Policy(_allow_policy(), events=events)),
            authorizer=overrides.get("authorizer", _Authorizer(_allow_authorization(), events=events)),
            create_plan=_CreatePlan(_plan_created(), events=events),
            audit=_Audit(events=events),
        )
        delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

        assert delivery.code == expected
        assert dsn not in repr(delivery)
        assert "plan" not in events


@pytest.mark.asyncio
async def test_a_plan_use_case_failure_is_mapped_without_leaking_text():
    events: list[str] = []
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(), events=events),
        create_plan=_CreatePlan(None, events=events, error=RuntimeError("dsn=postgres://user:pw@host/db")),
        audit=_Audit(events=events),
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert delivery == QueryPlanDelivery(code=ExecutionDecisionCode.DATABASE_UNAVAILABLE.value)
    assert "postgres://" not in repr(delivery)


# --- 脱敏证据 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_raw_sql_only_reaches_the_audit_as_a_query_hash():
    # policy 阶段还没有 prepared，所以审计里连摘要都没有；raw SQL 本身永远不出现。
    events: list[str] = []
    policy_audit = _Audit(events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_deny_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(), events=events),
        create_plan=_CreatePlan(_plan_created(), events=events),
        audit=policy_audit,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert policy_audit.started[0].query_hash is None
    for value in (policy_audit.started[0], policy_audit.finished[0]):
        rendered = repr(value)
        assert _SQL not in rendered
        assert "SELECT" not in rendered

    # authorization 阶段才有 Phase 2A 摘要：raw SQL 只以 SHA-256 形式进入审计。
    events = []
    authorization_audit = _Audit(events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(), events=events),
        authorizer=_Authorizer(_deny_authorization(), events=events),
        create_plan=_CreatePlan(_plan_created(), events=events),
        audit=authorization_audit,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SQL)

    assert authorization_audit.started[0].query_hash == _HASH
    for value in (authorization_audit.started[0], authorization_audit.finished[0]):
        rendered = repr(value)
        assert _SQL not in rendered
        assert "SELECT" not in rendered


def test_delivery_values_never_carry_sql_or_authorization_objects():
    assert set(QueryPlanDelivery.__dataclass_fields__) == {"code", "receipt"}
    assert set(QueryExecutionDelivery.__dataclass_fields__) == {"code", "result"}


# --- execute 入口 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_forwards_only_the_authenticated_principal_and_the_token():
    events: list[str] = []
    result = QueryExecutionResult(columns=("id",), rows=((1,),), row_count=1, byte_count=21, truncated=False)
    decision = QueryExecutionDecision(code=ExecutionCode.EXECUTED, result=result)
    execute_plan = _ExecutePlan(decision, events=events)
    use_case = ExecuteAnalyticsQuery(execute_plan=execute_plan)

    delivery = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert execute_plan.calls == [{"principal_id": "user-1", "plan_id": "raw-token"}]
    assert delivery.code == ExecutionCode.EXECUTED.value
    assert delivery.result is result
    # 交付值不带 token 本体，也不带授权对象。
    assert "raw-token" not in repr(delivery)
    assert "authorized" not in repr(delivery)


@pytest.mark.asyncio
async def test_execute_maps_a_plan_unavailable_decision_without_a_result():
    events: list[str] = []
    execute_plan = _ExecutePlan(QueryExecutionDecision(code=ExecutionCode.PLAN_UNAVAILABLE), events=events)
    use_case = ExecuteAnalyticsQuery(execute_plan=execute_plan)

    delivery = await use_case.execute(principal_id="user-1", plan_id="stale-token")

    assert delivery == QueryExecutionDelivery(code=ExecutionCode.PLAN_UNAVAILABLE.value)
    assert delivery.result is None


_SMALL_LIMIT_SQL = "SELECT id FROM orders LIMIT 10"


def _config(**overrides):
    return AnalyticsConfig.from_app_config(type("C", (), {"analytics": overrides or None})())


def _authorized_with_row_limit(row_limit):
    prepared = _prepared(sql=_SMALL_LIMIT_SQL, row_limit=row_limit)
    return prepared, _authorized(prepared=prepared)


@pytest.mark.asyncio
async def test_a_small_query_limit_clamps_the_transport_row_cap_and_still_creates_a_plan():
    """配置上限 1000、查询 LIMIT 10：传给 plan use case 的上限被收紧为 10。"""

    events: list[str] = []
    config = AnalyticsConfig()
    assert config.max_result_rows == 1_000
    prepared, authorized = _authorized_with_row_limit(10)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(prepared=prepared), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SMALL_LIMIT_SQL)

    assert delivery.code == ExecutionDecisionCode.PLAN_CREATED.value
    assert delivery.receipt is not None
    assert create_plan.calls[0]["limits"].max_result_rows == 10


@pytest.mark.asyncio
async def test_a_query_limit_above_the_cap_keeps_the_configured_cap():
    """查询 row_limit 高于配置上限时，仍然使用配置上限。"""

    events: list[str] = []
    config = _config(max_result_rows=100)
    prepared, authorized = _authorized_with_row_limit(5_000)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(prepared=prepared), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SMALL_LIMIT_SQL)

    assert create_plan.calls[0]["limits"].max_result_rows == 100


@pytest.mark.asyncio
async def test_a_query_without_a_limit_uses_the_smaller_of_the_two_server_values():
    """没有显式 LIMIT 时 Phase 2A 会套用 query_max_rows，取两者较小值。"""

    events: list[str] = []
    config = _config(query_max_rows=1_000, max_result_rows=250)
    prepared, authorized = _authorized_with_row_limit(1_000)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(prepared=prepared), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql="SELECT id FROM orders")

    assert create_plan.calls[0]["limits"].max_result_rows == 250


@pytest.mark.asyncio
async def test_only_the_result_row_cap_is_clamped_and_everything_else_matches_the_config():
    events: list[str] = []
    config = AnalyticsConfig()
    prepared, authorized = _authorized_with_row_limit(10)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(prepared=prepared), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SMALL_LIMIT_SQL)

    configured = config.execution_limits()
    delivered = create_plan.calls[0]["limits"]
    assert delivered.max_result_rows == 10
    for field_name in configured.__dataclass_fields__:
        if field_name == "max_result_rows":
            continue
        assert getattr(delivered, field_name) == getattr(configured, field_name), field_name


@pytest.mark.asyncio
async def test_the_row_cap_is_left_untouched_when_no_clamping_is_needed():
    """相等时不做无谓的复制：传下去的仍是配置生成的那个值。"""

    events: list[str] = []
    config = AnalyticsConfig()
    prepared, authorized = _authorized_with_row_limit(config.max_result_rows)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_allow_policy(prepared=prepared), events=events),
        authorizer=_Authorizer(_allow_authorization(authorized), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=config,
    )

    await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SMALL_LIMIT_SQL)

    assert create_plan.calls[0]["limits"] == config.execution_limits()


@pytest.mark.asyncio
async def test_a_denied_policy_still_never_reaches_the_plan_use_case():
    """收紧只发生在授权通过之后：拒绝路径的行为完全不变。"""

    events: list[str] = []
    prepared, _authorized_spec = _authorized_with_row_limit(10)
    create_plan = _CreatePlan(_plan_created(), events=events)
    use_case = _use_case(
        catalog=_Catalog(_datasource(), events=events),
        policy=_Policy(_deny_policy(), events=events),
        authorizer=_Authorizer(_allow_authorization(), events=events),
        create_plan=create_plan,
        audit=_Audit(events=events),
        config=AnalyticsConfig(),
    )

    delivery = await use_case.execute(principal_id="user-1", datasource_id="ds-1", raw_sql=_SMALL_LIMIT_SQL)

    assert delivery.receipt is None
    assert create_plan.calls == []
    assert prepared.row_limit == 10
