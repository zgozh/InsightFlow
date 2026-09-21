from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.application import (
    Clock,
    CreateQueryExecutionPlan,
    DatasourceQueryGateway,
    ExecuteQueryPlan,
    ExecutionPlanStore,
    PlanTokenIssuer,
    StoredExecutionPlan,
)
from app.analytics.domain import (
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    ColumnSchema,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    PreparedQuery,
    QueryAuthorizationDecision,
    QueryCostEstimate,
    QueryExecutionResult,
    QueryPlanReceipt,
    QueryRisk,
    RelationSchema,
    SchemaSnapshot,
)

_SQL = "SELECT id FROM orders LIMIT 10"
_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _prepared(**overrides):
    values = {
        "sql": _SQL,
        "engine": DatasourceEngine.POSTGRESQL,
        "relations": ("orders",),
        "row_limit": 10,
        "query_hash": "a" * 64,
    }
    values.update(overrides)
    return PreparedQuery(**values)


def _datasource(**overrides):
    values = {
        "id": "ds-1",
        "owner_id": "user-1",
        "name": "Warehouse",
        "engine": DatasourceEngine.POSTGRESQL,
        "secret_ref": "env://ANALYTICS_DS",
        "default_schema": "public",
        "status": DatasourceStatus.ACTIVE,
    }
    values.update(overrides)
    return DatasourceDefinition(**values)


def _authorized(**overrides):
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


def _limits(**overrides):
    values = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 10_000,
        "cancellation_grace_ms": 500,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 64,
        "max_result_rows": 10,
        "max_result_bytes": 4_194_304,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def _estimate(**overrides):
    values = {
        "engine": DatasourceEngine.POSTGRESQL,
        "estimated_rows": 10,
        "engine_cost": Decimal("12.5"),
        "plan_digest": "b" * 64,
    }
    values.update(overrides)
    return QueryCostEstimate(**values)


def _result(**overrides):
    values = {"columns": ("id",), "rows": ((1,),), "row_count": 1, "byte_count": 21, "truncated": False}
    values.update(overrides)
    return QueryExecutionResult(**values)


def _allowed_decision(spec):
    return QueryAuthorizationDecision(
        allowed=True,
        risk=spec.risk,
        codes=(AuthorizationDecisionCode.APPROVED,),
        authorized=spec,
    )


def _denied_decision():
    return QueryAuthorizationDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(AuthorizationDecisionCode.UNKNOWN_RELATION,),
    )


class _RecordingCatalog:
    def __init__(self, datasource, *, events, error=None, datasources=None):
        self._datasource = datasource
        self._datasources = datasources
        self._events = events
        self._error = error
        self._calls = 0

    async def list_accessible(self, *, principal_id):
        return ()

    async def get_accessible(self, *, principal_id, datasource_id):
        self._calls += 1
        self._events.append("datasource:first" if self._calls == 1 else "datasource:second")
        if self._error is not None:
            raise self._error
        if self._datasources is not None:
            return self._datasources[min(self._calls - 1, len(self._datasources) - 1)]
        return self._datasource


class _RecordingAuthorizer:
    def __init__(self, decision, *, events, error=None, decisions=None):
        self._decision = decision
        self._decisions = decisions
        self._events = events
        self._error = error
        self._calls = 0

    async def execute(self, *, principal_id, datasource_id, prepared):
        self._calls += 1
        self._events.append("authorize:first" if self._calls == 1 else "authorize:second")
        if self._error is not None:
            raise self._error
        if self._decisions is not None:
            return self._decisions[min(self._calls - 1, len(self._decisions) - 1)]
        return self._decision


class _RecordingGateway:
    def __init__(self, *, events, estimate=None, result=None, explain_error=None, execute_error=None):
        self._events = events
        self._estimate = estimate if estimate is not None else _estimate()
        self._result = result if result is not None else _result()
        self._explain_error = explain_error
        self._execute_error = execute_error

    async def explain(self, *, datasource, authorized, limits):
        self._events.append("explain")
        if self._explain_error is not None:
            raise self._explain_error
        return self._estimate

    async def execute(self, *, datasource, authorized, limits):
        self._events.append("execute")
        if self._execute_error is not None:
            raise self._execute_error
        return self._result


class _RecordingStore:
    def __init__(self, *, events, plan=None, put_error=None):
        self._events = events
        self._plan = plan
        self._put_error = put_error
        self.plans: list[StoredExecutionPlan] = []
        self.claims: list[dict] = []

    async def put(self, plan):
        self._events.append("store:put")
        if self._put_error is not None:
            raise self._put_error
        self.plans.append(plan)

    async def claim(self, *, token_digest, principal_id, now):
        self._events.append("store:claim")
        self.claims.append({"token_digest": token_digest, "principal_id": principal_id, "now": now})
        return self._plan

    async def purge_expired(self, *, now):
        self._events.append("store:purge")


class _FixedClock:
    def __init__(self, now=_NOW):
        self._now = now

    def now(self):
        return self._now


class _FixedTokenIssuer:
    def __init__(self, token="fixed-plan-token"):
        self._token = token
        self.calls = 0

    def issue(self):
        self.calls += 1
        return self._token


def _create_use_case(*, catalog, authorizer, gateway, store, clock=None, issuer=None):
    return CreateQueryExecutionPlan(
        datasource_catalog=catalog,
        authorize_prepared_query=authorizer,
        gateway=gateway,
        plan_store=store,
        clock=clock or _FixedClock(),
        token_issuer=issuer or _FixedTokenIssuer(),
    )


def _execute_use_case(*, catalog, authorizer, gateway, store, clock=None):
    return ExecuteQueryPlan(
        datasource_catalog=catalog,
        authorize_prepared_query=authorizer,
        gateway=gateway,
        plan_store=store,
        clock=clock or _FixedClock(),
    )


def _stored_plan(*, authorized=None, datasource=None, limits=None):
    return StoredExecutionPlan(
        token_digest="d" * 64,
        principal_id="user-1",
        datasource=datasource or _datasource(),
        authorized=authorized or _authorized(),
        estimate=_estimate(),
        limits=limits or _limits(),
        issued_at=_NOW,
        expires_at=_NOW + timedelta(seconds=60),
    )


# --- 创建 plan --------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_plan_runs_the_documented_sequence():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.PLAN_CREATED
    assert events == [
        "datasource:first",
        "authorize:first",
        "explain",
        "datasource:second",
        "authorize:second",
        "store:put",
    ]


@pytest.mark.asyncio
async def test_create_plan_stores_only_the_token_digest_and_returns_the_raw_token():
    import hashlib

    events: list[str] = []
    authorized = _authorized()
    store = _RecordingStore(events=events)
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=store,
        issuer=_FixedTokenIssuer("raw-token-value"),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.receipt is not None
    assert decision.receipt.plan_id == "raw-token-value"
    assert decision.receipt.expires_at == _NOW + timedelta(seconds=60)
    assert len(store.plans) == 1
    assert store.plans[0].token_digest == hashlib.sha256(b"raw-token-value").hexdigest()
    assert "raw-token-value" not in repr(store.plans[0])


@pytest.mark.asyncio
async def test_create_plan_rejects_a_mismatched_principal():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-2", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert events == []


@pytest.mark.asyncio
async def test_create_plan_rejects_a_mismatched_datasource_id():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-2", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert events == []


@pytest.mark.asyncio
async def test_create_plan_rejects_limits_that_exceed_the_prepared_row_limit():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(
        principal_id="user-1",
        datasource_id="ds-1",
        authorized=authorized,
        limits=_limits(max_result_rows=11),
    )

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert events == []


@pytest.mark.asyncio
async def test_create_plan_returns_authorization_stale_when_current_authorization_denies():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_denied_decision(), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert "explain" not in events


@pytest.mark.asyncio
async def test_create_plan_returns_authorization_stale_when_the_authorization_value_differs():
    events: list[str] = []
    authorized = _authorized()
    drifted = _authorized(policy_version="p2")
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(drifted), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert "explain" not in events


@pytest.mark.asyncio
async def test_create_plan_returns_authorization_stale_when_the_datasource_changes_after_explain():
    events: list[str] = []
    authorized = _authorized()
    changed = _datasource(name="Renamed warehouse")
    use_case = _create_use_case(
        catalog=_RecordingCatalog(None, events=events, datasources=[_datasource(), changed]),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert events[-1] == "datasource:second"


@pytest.mark.asyncio
async def test_create_plan_returns_authorization_stale_when_authorization_changes_after_explain():
    events: list[str] = []
    authorized = _authorized()
    drifted = _authorized(policy_version="p2")
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(None, events=events, decisions=[_allowed_decision(authorized), _allowed_decision(drifted)]),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert "store:put" not in events


@pytest.mark.asyncio
async def test_create_plan_returns_datasource_unavailable_for_a_missing_or_inactive_datasource():
    events: list[str] = []
    authorized = _authorized()
    for datasource in (None, _datasource(status=DatasourceStatus.DISABLED), _datasource(status=DatasourceStatus.UNHEALTHY)):
        events.clear()
        use_case = _create_use_case(
            catalog=_RecordingCatalog(datasource, events=events),
            authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
            gateway=_RecordingGateway(events=events),
            store=_RecordingStore(events=events),
        )
        decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())
        assert decision.code is ExecutionDecisionCode.DATASOURCE_UNAVAILABLE


@pytest.mark.asyncio
async def test_create_plan_maps_catalog_failures_without_leaking():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events, error=RuntimeError("dsn=postgres://user:pw@host/db")),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.DATASOURCE_UNAVAILABLE
    assert "postgres://" not in repr(decision)


@pytest.mark.asyncio
async def test_create_plan_rejects_an_estimate_above_the_estimated_row_cap():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events, estimate=_estimate(estimated_rows=100_001)),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.COST_LIMIT_EXCEEDED
    assert "store:put" not in events


@pytest.mark.asyncio
async def test_create_plan_rejects_an_estimate_above_the_engine_cost_cap():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events, estimate=_estimate(engine_cost=Decimal("10000.01"))),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.COST_LIMIT_EXCEEDED


@pytest.mark.asyncio
async def test_create_plan_accepts_an_estimate_exactly_at_both_caps():
    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events, estimate=_estimate(estimated_rows=100_000, engine_cost=Decimal("10000"))),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.PLAN_CREATED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        ExecutionDecisionCode.SECRET_UNAVAILABLE,
        ExecutionDecisionCode.EXPLAIN_REJECTED,
        ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE,
        ExecutionDecisionCode.DATABASE_UNAVAILABLE,
    ],
)
async def test_create_plan_maps_gateway_failures_to_stable_codes(code):
    from app.analytics.application import DatasourceQueryError

    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events, explain_error=DatasourceQueryError(code)),
        store=_RecordingStore(events=events),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is code
    assert decision.receipt is None


@pytest.mark.asyncio
async def test_create_plan_returns_store_unavailable_when_the_store_rejects():
    from app.analytics.application import ExecutionPlanStoreError

    events: list[str] = []
    authorized = _authorized()
    use_case = _create_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, put_error=ExecutionPlanStoreError("capacity")),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=authorized, limits=_limits())

    assert decision.code is ExecutionDecisionCode.PLAN_STORE_UNAVAILABLE
    assert decision.receipt is None


# --- 执行 plan --------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_plan_claims_before_any_external_work():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.EXECUTED
    assert events == ["store:claim", "datasource:first", "authorize:first", "execute"]


@pytest.mark.asyncio
async def test_execute_plan_passes_only_the_token_digest_to_the_store():
    import hashlib

    events: list[str] = []
    plan = _stored_plan()
    store = _RecordingStore(events=events, plan=plan)
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=store,
    )

    await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert store.claims[0]["token_digest"] == hashlib.sha256(b"raw-token").hexdigest()
    assert store.claims[0]["principal_id"] == "user-1"
    assert store.claims[0]["now"] == _NOW


@pytest.mark.asyncio
async def test_execute_plan_returns_plan_unavailable_when_the_claim_fails():
    events: list[str] = []
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_denied_decision(), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=None),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="stale-token")

    assert decision.code is ExecutionDecisionCode.PLAN_UNAVAILABLE
    assert decision.result is None
    assert events == ["store:claim"]


@pytest.mark.asyncio
async def test_execute_plan_returns_datasource_unavailable_when_the_datasource_is_gone():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(None, events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.DATASOURCE_UNAVAILABLE
    assert "execute" not in events


@pytest.mark.asyncio
async def test_execute_plan_returns_authorization_stale_when_the_datasource_snapshot_drifted():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(name="Renamed"), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert "execute" not in events


@pytest.mark.asyncio
async def test_execute_plan_returns_authorization_stale_when_the_authorization_drifted():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(replace(plan.authorized, policy_version="p2")), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE
    assert "execute" not in events


@pytest.mark.asyncio
async def test_execute_plan_returns_authorization_stale_when_authorization_now_denies():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_denied_decision(), events=events),
        gateway=_RecordingGateway(events=events),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.AUTHORIZATION_STALE


@pytest.mark.asyncio
async def test_execute_plan_returns_the_result_on_success():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events, result=_result(columns=("id",), rows=((1,), (2,)), row_count=2, byte_count=42)),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.EXECUTED
    assert decision.result is not None
    assert decision.result.row_count == 2
    assert decision.result.truncated is False


@pytest.mark.asyncio
async def test_execute_plan_reports_result_limit_reached_when_truncated():
    events: list[str] = []
    plan = _stored_plan()
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events, result=_result(truncated=True)),
        store=_RecordingStore(events=events, plan=plan),
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is ExecutionDecisionCode.RESULT_LIMIT_REACHED
    assert decision.result is not None
    assert decision.result.truncated is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        ExecutionDecisionCode.EXECUTION_TIMEOUT,
        ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE,
        ExecutionDecisionCode.DATABASE_UNAVAILABLE,
        ExecutionDecisionCode.SECRET_UNAVAILABLE,
    ],
)
async def test_execute_plan_maps_gateway_failures_and_never_restores_the_plan(code):
    from app.analytics.application import DatasourceQueryError

    events: list[str] = []
    plan = _stored_plan()
    store = _RecordingStore(events=events, plan=plan)
    use_case = _execute_use_case(
        catalog=_RecordingCatalog(_datasource(), events=events),
        authorizer=_RecordingAuthorizer(_allowed_decision(plan.authorized), events=events),
        gateway=_RecordingGateway(events=events, execute_error=DatasourceQueryError(code)),
        store=store,
    )

    decision = await use_case.execute(principal_id="user-1", plan_id="raw-token")

    assert decision.code is code
    assert decision.result is None
    # claim 已经消费 token；失败不恢复，避免重放与重复成本。
    assert events.count("store:claim") == 1
    assert "store:put" not in events


# --- 运行时端口契约 ---------------------------------------------------------


def test_execution_ports_are_runtime_checkable_protocols():
    assert getattr(DatasourceQueryGateway, "_is_runtime_protocol", False)
    assert getattr(ExecutionPlanStore, "_is_runtime_protocol", False)
    assert getattr(Clock, "_is_runtime_protocol", False)
    assert getattr(PlanTokenIssuer, "_is_runtime_protocol", False)
    assert isinstance(_FixedClock(), Clock)
    assert isinstance(_FixedTokenIssuer(), PlanTokenIssuer)


def test_receipts_and_decisions_never_carry_sql_or_secret_text():
    decision = QueryAuthorizationDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=(AuthorizationDecisionCode.UNKNOWN_RELATION,))
    receipt = QueryPlanReceipt(plan_id="token-value", expires_at=_NOW, estimate=_estimate())

    assert "SELECT" not in repr(decision)
    assert _SQL not in repr(receipt)
    assert "env://" not in repr(receipt)


def test_authorized_spec_still_has_no_execution_authority():
    spec = _authorized()
    assert not hasattr(spec, "plan_id")
    assert not hasattr(spec, "execute")
    assert not hasattr(_prepared(), "execute")


def test_schema_snapshot_is_not_part_of_a_stored_plan():
    # plan 只绑定授权值与数据源快照；schema/policy 细节留在授权值内。
    assert {field for field in StoredExecutionPlan.__dataclass_fields__} == {
        "token_digest",
        "principal_id",
        "datasource",
        "authorized",
        "estimate",
        "limits",
        "issued_at",
        "expires_at",
    }
    assert RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="INT"),)).name == "orders"
    assert SchemaSnapshot.__name__ == "SchemaSnapshot"
