"""PostgreSQL 16 上的持久化控制面集成测试（Phase 2C1 任务 7）。

只在 `ANALYTICS_TEST_POSTGRESQL=1` 时运行（由 `scripts/test_analytics_databases.py` 注入），
普通 pytest 收集时整体跳过，因此离线套件不依赖 Docker。

为什么必须是真实 PostgreSQL：

- `DELETE ... RETURNING` 的原子性、`pg_advisory_xact_lock` 的容量串行化、`SELECT ... FOR UPDATE`
  的行锁竞争，都无法用 SQLite 或 mock 证明；
- 这些正是"两个独立 Gateway worker"场景的正确性来源。

隔离方式：每个测试自建一个临时 schema，测完 `DROP SCHEMA ... CASCADE`。schema 生命周期用
compose 栈的初始化超级用户完成（等价于 compose 用管理员建库建角色的既有做法），
**被测连接一律使用普通用户 `analytics_tester`**，因此权限问题不会被管理员身份掩盖。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import (
    CreateQueryExecutionPlan,
    ExecuteQueryPlan,
    PersistenceConflictError,
    StoredExecutionPlan,
)
from app.analytics.domain import (
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryAuthorizationDecision,
    QueryCostEstimate,
    QueryExecutionResult,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)
from app.analytics.infrastructure import SecurePlanTokenIssuer, SystemClock
from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver
from app.analytics.infrastructure.persistence import (
    SqlAccessPolicyRepository,
    SqlDatasourceRepository,
    SqlExecutionPlanStore,
    SqlQueryAuditLog,
    SqlSchemaSnapshotRepository,
    bootstrap_analytics_schema,
)

_INTEGRATION_ENV = "ANALYTICS_TEST_POSTGRESQL"
_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_CREDENTIAL"
_ADMIN_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_ADMIN_CREDENTIAL"
_SCHEMA_PREFIX = "analytics_p2c1_"


def _integration_enabled() -> bool:
    return os.environ.get(_INTEGRATION_ENV, "").strip() == "1"


def _credential(variable: str):
    """`secret_ref` 的唯一合法形式是 `env://NAME`；解析逻辑与生产完全一致。"""

    datasource = DatasourceDefinition(id="ds-p2c1", owner_id="user-1", name="Persistence gate", engine=DatasourceEngine.POSTGRESQL, secret_ref=f"env://{variable}")
    return EnvironmentDatasourceSecretResolver().resolve(datasource=datasource)


def _tester_username() -> str:
    return str(json.loads(os.environ[_CREDENTIAL_ENV])["username"])


def _engine(variable: str, *, schema: str | None = None):
    credential = _credential(variable)
    connect_args: dict = {}
    if schema is not None:
        # 把临时 schema 钉在 search_path 首位：Analytics 链的 DDL 与版本表都落在它里面。
        connect_args["server_settings"] = {"search_path": f'"{schema}"'}
    return create_async_engine(credential.url, poolclass=NullPool, echo=False, connect_args=connect_args)


async def _provision_schema(admin_engine, schema: str, role: str) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{role}"'))


async def _drop_schema(admin_engine, schema: str) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest_asyncio.fixture
async def environment():
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = _engine(_ADMIN_CREDENTIAL_ENV)
    first = _engine(_CREDENTIAL_ENV, schema=schema)
    second = _engine(_CREDENTIAL_ENV, schema=schema)
    try:
        await _provision_schema(admin, schema, _tester_username())
        await bootstrap_analytics_schema(first, backend="postgres")
        yield SimpleNamespace(
            schema=schema,
            admin=admin,
            first=first,
            second=second,
            first_sessions=async_sessionmaker(first, expire_on_commit=False),
            second_sessions=async_sessionmaker(second, expire_on_commit=False),
        )
    finally:
        try:
            await _drop_schema(admin, schema)
        finally:
            await asyncio.gather(admin.dispose(), first.dispose(), second.dispose())


# --- 测试数据 ---------------------------------------------------------------


def _datasource(*, id="ds-1", owner_id="user-1", name="Warehouse", status=DatasourceStatus.ACTIVE):
    return DatasourceDefinition(id=id, owner_id=owner_id, name=name, engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public", status=status)


def _snapshot(*, version="s1", column="id"):
    return SchemaSnapshot(
        datasource_id="ds-1",
        engine=DatasourceEngine.POSTGRESQL,
        version=version,
        default_schema="public",
        relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name=column, data_type="integer"),)),),
    )


def _policy(*, version="p1", access=ColumnAccess.ALLOW):
    return PrincipalAccessPolicy(
        datasource_id="ds-1",
        principal_id="user-1",
        version=version,
        relations=(RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name="id", access=access),)),),
        allowed_functions=("count",),
    )


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


def _authorized():
    return AuthorizedQuerySpec(
        prepared=PreparedQuery(sql="SELECT id FROM orders LIMIT 10", engine=DatasourceEngine.POSTGRESQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
        datasource_id="ds-1",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=("public.orders",),
        columns=("public.orders.id",),
        functions=("count",),
        risk=QueryRisk.LOW,
    )


def _plan(*, digest, ttl_seconds=60):
    now = SystemClock().now()

    return StoredExecutionPlan(
        token_digest=digest,
        principal_id="user-1",
        datasource=_datasource(),
        authorized=_authorized(),
        estimate=QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64),
        limits=_limits(),
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


class _CountingGateway:
    def __init__(self):
        self.explain_calls = 0
        self.execute_calls = 0

    async def explain(self, *, datasource, authorized, limits):
        self.explain_calls += 1
        return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)

    async def execute(self, *, datasource, authorized, limits):
        self.execute_calls += 1
        return QueryExecutionResult(columns=("id",), rows=((1,),), row_count=1, byte_count=21, truncated=False)


class _AllowedAuthorizer:
    async def execute(self, *, principal_id, datasource_id, prepared):
        spec = _authorized()
        return QueryAuthorizationDecision(allowed=True, risk=spec.risk, codes=(AuthorizationDecisionCode.APPROVED,), authorized=spec)


class _AuditLog:
    """可注入 start/finish 失败的审计替身；成功时把记录写进真实数据库。"""

    def __init__(self, delegate, *, fail_start=False, fail_finish=False):
        self._delegate = delegate
        self._fail_start = fail_start
        self._fail_finish = fail_finish

    async def start(self, entry):
        if self._fail_start:
            raise RuntimeError("audit store down")
        return await self._delegate.start(entry)

    async def finish(self, completion):
        if self._fail_finish:
            raise RuntimeError("audit store down")
        await self._delegate.finish(completion)


async def _seed(sessions):
    datasources = SqlDatasourceRepository(sessions)
    await datasources.save(_datasource())
    await SqlSchemaSnapshotRepository(sessions).replace(_snapshot(), expected_version=None)
    await SqlAccessPolicyRepository(sessions).replace(_policy(), expected_version=None)
    return datasources


@pytest.mark.integration
@pytest.mark.skipif(not _integration_enabled(), reason=f"set {_INTEGRATION_ENV}=1 (see scripts/test_analytics_databases.py)")
class TestPostgreSQLPersistenceControlPlane:
    pytestmark = pytest.mark.asyncio

    async def test_bootstrap_is_repeatable_and_owns_only_the_analytics_tables(self, environment):
        await bootstrap_analytics_schema(environment.first, backend="postgres")

        async with environment.first.connect() as conn:
            revision = (await conn.execute(text("SELECT version_num FROM analytics_alembic_version"))).scalar_one()
            tables = set((await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"), {"schema": environment.schema})).scalars())

        assert revision == "0002_analytics_analysis_reports"
        assert tables == {
            "analytics_alembic_version",
            "analytics_analysis_reports",
            "analytics_access_policies",
            "analytics_datasources",
            "analytics_execution_plans",
            "analytics_metrics",
            "analytics_query_audits",
            "analytics_schema_snapshots",
        }

    async def test_two_independent_engines_racing_for_one_token_yield_exactly_one_winner(self, environment):
        await _seed(environment.first_sessions)
        digest = "a" * 64
        await SqlExecutionPlanStore(environment.first_sessions, max_entries=8).put(_plan(digest=digest))
        first = SqlExecutionPlanStore(environment.first_sessions, max_entries=8)
        second = SqlExecutionPlanStore(environment.second_sessions, max_entries=8)
        now = SystemClock().now()

        results = await asyncio.gather(
            first.claim(token_digest=digest, principal_id="user-1", now=now),
            second.claim(token_digest=digest, principal_id="user-1", now=now),
        )

        assert sum(result is not None for result in results) == 1

    async def test_concurrent_capacity_checks_never_exceed_max_entries(self, environment):
        await _seed(environment.first_sessions)
        first = SqlExecutionPlanStore(environment.first_sessions, max_entries=1)
        second = SqlExecutionPlanStore(environment.second_sessions, max_entries=1)

        results = await asyncio.gather(
            first.put(_plan(digest="1" * 64)),
            second.put(_plan(digest="2" * 64)),
            first.put(_plan(digest="3" * 64)),
            second.put(_plan(digest="4" * 64)),
            return_exceptions=True,
        )

        stored = sum(1 for result in results if result is None)
        rejected = [result for result in results if isinstance(result, Exception)]
        assert stored == 1
        assert len(rejected) == 3
        assert all(getattr(result, "reason", None) in {"capacity_exceeded", "digest_conflict"} for result in rejected)

        async with environment.first.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM analytics_execution_plans"))).scalar_one() == 1

    async def test_a_stale_expected_version_conflicts_without_losing_data(self, environment):
        datasources = await _seed(environment.first_sessions)
        schemas_first = SqlSchemaSnapshotRepository(environment.first_sessions)
        schemas_second = SqlSchemaSnapshotRepository(environment.second_sessions)

        results = await asyncio.gather(
            schemas_first.replace(_snapshot(version="s2", column="customer"), expected_version="s1"),
            schemas_second.replace(_snapshot(version="s3", column="amount"), expected_version="s1"),
            return_exceptions=True,
        )

        assert sum(1 for result in results if result is None) == 1
        conflicts = [result for result in results if isinstance(result, PersistenceConflictError)]
        assert len(conflicts) == 1
        assert conflicts[0].reason == "stale_expected_version"

        stored = await SqlSchemaSnapshotRepository(environment.first_sessions).get_current(datasource_id="ds-1")
        assert stored.version in {"s2", "s3"}
        # 数据源本身没有被并发替换波及。
        assert await datasources.get_owned(owner_id="user-1", datasource_id="ds-1") == _datasource()

    async def test_audit_start_failure_prevents_the_business_gateway_from_being_called(self, environment):
        await _seed(environment.first_sessions)
        gateway = _CountingGateway()
        use_case = CreateQueryExecutionPlan(
            datasource_catalog=SqlDatasourceRepository(environment.first_sessions),
            authorize_prepared_query=_AllowedAuthorizer(),
            gateway=gateway,
            plan_store=SqlExecutionPlanStore(environment.first_sessions, max_entries=8),
            audit_log=_AuditLog(SqlQueryAuditLog(environment.first_sessions), fail_start=True),
            clock=SystemClock(),
            token_issuer=SecurePlanTokenIssuer(),
        )

        decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", authorized=_authorized(), limits=_limits())

        assert decision.code is ExecutionDecisionCode.AUDIT_UNAVAILABLE
        assert decision.receipt is None
        assert gateway.explain_calls == 0
        async with environment.first.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM analytics_execution_plans"))).scalar_one() == 0

    async def test_audit_finish_failure_suppresses_the_result_and_keeps_the_row_started(self, environment):
        await _seed(environment.first_sessions)
        gateway = _CountingGateway()
        real_audit = SqlQueryAuditLog(environment.first_sessions)
        use_case = ExecuteQueryPlan(
            datasource_catalog=SqlDatasourceRepository(environment.first_sessions),
            authorize_prepared_query=_AllowedAuthorizer(),
            gateway=gateway,
            plan_store=SqlExecutionPlanStore(environment.first_sessions, max_entries=8),
            audit_log=_AuditLog(real_audit, fail_finish=True),
            clock=SystemClock(),
        )
        token = SecurePlanTokenIssuer().issue()
        await SqlExecutionPlanStore(environment.first_sessions, max_entries=8).put(_plan(digest=hashlib.sha256(token.encode()).hexdigest()))

        decision = await use_case.execute(principal_id="user-1", plan_id=token)

        assert decision.code is ExecutionDecisionCode.AUDIT_UNAVAILABLE
        assert decision.result is None
        assert gateway.execute_calls == 1
        async with environment.first.connect() as conn:
            rows = (await conn.execute(text("SELECT status, finished_at FROM analytics_query_audits"))).all()
        assert len(rows) == 1
        assert rows[0][0] == "started" and rows[0][1] is None

    async def test_a_real_plan_and_execute_cycle_completes_both_audit_phases(self, environment):
        await _seed(environment.first_sessions)
        gateway = _CountingGateway()
        store = SqlExecutionPlanStore(environment.first_sessions, max_entries=8)
        audit = SqlQueryAuditLog(environment.first_sessions)
        create = CreateQueryExecutionPlan(
            datasource_catalog=SqlDatasourceRepository(environment.first_sessions),
            authorize_prepared_query=_AllowedAuthorizer(),
            gateway=gateway,
            plan_store=store,
            audit_log=audit,
            clock=SystemClock(),
            token_issuer=SecurePlanTokenIssuer(),
        )
        execute = ExecuteQueryPlan(
            datasource_catalog=SqlDatasourceRepository(environment.first_sessions),
            authorize_prepared_query=_AllowedAuthorizer(),
            gateway=gateway,
            plan_store=store,
            audit_log=audit,
            clock=SystemClock(),
        )

        planned = await create.execute(principal_id="user-1", datasource_id="ds-1", authorized=_authorized(), limits=_limits())
        assert planned.code is ExecutionDecisionCode.PLAN_CREATED
        executed = await execute.execute(principal_id="user-1", plan_id=planned.receipt.plan_id)

        assert executed.code is ExecutionDecisionCode.EXECUTED
        assert executed.result is not None and executed.result.row_count == 1
        async with environment.first.connect() as conn:
            phases = sorted((await conn.execute(text("SELECT phase, status FROM analytics_query_audits"))).all())
            remaining = (await conn.execute(text("SELECT count(*) FROM analytics_execution_plans"))).scalar_one()
        assert phases == [("execute", "completed"), ("plan", "completed")]
        # plan 在 claim 时被删除，不留在数据库里。
        assert remaining == 0
