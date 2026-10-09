"""Analytics composition root 测试（Phase 2C2 任务 4）。

Composition 只接收**已经注入**的 engine/session factory 与配置：

- `enabled=false` 或 `database.backend=memory` 返回 `None` 且**不**运行迁移；
- enabled 且 SQL backend 时复用精确的注入对象，配置/engine/session/迁移失败都阻止启动；
- 装配出来的服务能在 SQLite 上跑完管理 → plan → execute（业务数据库 gateway 用替身），
  并且用的是持久化 plan store 与真实审计，而不是内存实现。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics import composition
from app.analytics.composition import AnalyticsCompositionError, AnalyticsServices, build_analytics_services
from app.analytics.config import AnalyticsConfigError
from app.analytics.domain import (
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceEngine,
    ExecutionDecisionCode,
    QueryCostEstimate,
    QueryExecutionResult,
    RelationAccessRule,
    RelationSchema,
)


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False)


def _config(block=None):
    return SimpleNamespace(analytics=block, database=SimpleNamespace(backend="sqlite"))


class _StubGateway:
    """业务数据库 gateway 替身：只记录调用并返回固定估算/结果。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.explain_calls = 0
        self.execute_calls = 0

    async def explain(self, *, datasource, authorized, limits):
        self.explain_calls += 1
        return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)

    async def execute(self, *, datasource, authorized, limits):
        self.execute_calls += 1
        return QueryExecutionResult(columns=("id",), rows=((1,),), row_count=1, byte_count=21, truncated=False)


class _BootstrapSpy:
    def __init__(self, *, error=None):
        self.calls: list[tuple] = []
        self._error = error

    async def __call__(self, engine, *, backend):
        self.calls.append((engine, backend))
        if self._error is not None:
            raise self._error


# --- disabled / memory ------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_returns_none_without_migrating(tmp_path, monkeypatch):
    spy = _BootstrapSpy()
    monkeypatch.setattr(composition, "bootstrap_analytics_schema", spy)
    engine = _engine(tmp_path / "disabled.db")
    try:
        services = await build_analytics_services(config=_config({"enabled": False}), engine=engine, session_factory=async_sessionmaker(engine), backend="sqlite")
    finally:
        await engine.dispose()

    assert services is None
    assert spy.calls == []


@pytest.mark.asyncio
async def test_memory_backend_returns_none_without_migrating(tmp_path, monkeypatch):
    spy = _BootstrapSpy()
    monkeypatch.setattr(composition, "bootstrap_analytics_schema", spy)
    engine = _engine(tmp_path / "memory.db")
    try:
        services = await build_analytics_services(config=_config(), engine=None, session_factory=None, backend="memory")
    finally:
        await engine.dispose()

    assert services is None
    assert spy.calls == []


@pytest.mark.asyncio
async def test_memory_backend_never_gets_an_in_memory_plan_store(tmp_path):
    # 内存 backend 是"没有持久化能力"，不是"换一种 store"。
    engine = _engine(tmp_path / "memory-only.db")
    try:
        services = await build_analytics_services(config=_config(), engine=None, session_factory=None, backend="memory")
    finally:
        await engine.dispose()

    assert services is None


# --- 启动失败 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_enabled_sql_requires_an_engine_and_session_factory():
    with pytest.raises(AnalyticsCompositionError):
        await build_analytics_services(config=_config(), engine=None, session_factory=None, backend="sqlite")


@pytest.mark.asyncio
async def test_a_migration_failure_stops_startup(tmp_path, monkeypatch):
    engine = _engine(tmp_path / "boom.db")
    monkeypatch.setattr(composition, "bootstrap_analytics_schema", _BootstrapSpy(error=RuntimeError("migration failed")))
    try:
        with pytest.raises(RuntimeError, match="migration failed"):
            await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine), backend="sqlite")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_invalid_config_stops_startup(tmp_path):
    engine = _engine(tmp_path / "badcfg.db")
    try:
        with pytest.raises(AnalyticsConfigError):
            await build_analytics_services(config=_config({"bogus": 1}), engine=engine, session_factory=async_sessionmaker(engine), backend="sqlite")
    finally:
        await engine.dispose()


# --- 装配 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_bundle_is_frozen_and_exposes_only_service_entry_points(tmp_path):
    engine = _engine(tmp_path / "bundle.db")
    try:
        services = await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
    finally:
        await engine.dispose()

    assert services is not None
    assert set(AnalyticsServices.__dataclass_fields__) == {"config", "datasources", "metrics", "administration", "plan_query", "execute_query", "audit_reader", "publish_report", "list_reports", "analysis_evidence_repository"}
    assert services.analysis_evidence_repository is not None
    with pytest.raises(FrozenInstanceError):
        services.config = None  # type: ignore[misc]
    assert isinstance(services.config, composition.AnalyticsConfig)
    # 交付用例只持有应用服务，不透出 gateway/plan store。
    assert not hasattr(services, "gateway")
    assert not hasattr(services, "plan_store")


@pytest.mark.asyncio
async def test_an_unknown_backend_is_rejected(tmp_path):
    engine = _engine(tmp_path / "weird.db")
    try:
        with pytest.raises(AnalyticsCompositionError):
            await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine), backend="oracle")
    finally:
        await engine.dispose()


# --- 端到端（业务 gateway 替身） --------------------------------------------


@pytest.mark.asyncio
async def test_management_plan_and_execute_run_end_to_end_on_sqlite(tmp_path, monkeypatch):
    created: list[_StubGateway] = []

    def _factory(**kwargs):
        gateway = _StubGateway(**kwargs)
        created.append(gateway)
        return gateway

    monkeypatch.setattr(composition, "SQLAlchemyDatasourceQueryGateway", _factory)
    engine = _engine(tmp_path / "end-to-end.db")
    try:
        # 与 2B2 的行上限不变量保持一致：传输上限不得超过 SQL 授权值里的 row_limit，
        # 所以这里显式把 max_result_rows 配成与查询 LIMIT 相同的值。
        services = await build_analytics_services(config=_config({"max_result_rows": 10}), engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
        assert services is not None

        datasource = await services.administration.create_datasource(owner_id="owner-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public")
        await services.administration.replace_schema(
            owner_id="owner-1",
            datasource_id=datasource.id,
            version="s1",
            default_schema="public",
            relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="integer"),)),),
            expected_version=None,
        )
        await services.administration.replace_policy(
            owner_id="owner-1",
            datasource_id=datasource.id,
            principal_id="user-9",
            version="p1",
            relations=(RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),)),),
            allowed_functions=(),
            expected_version=None,
        )

        planned = await services.plan_query.execute(principal_id="user-9", datasource_id=datasource.id, raw_sql="SELECT id FROM orders LIMIT 10")
        assert planned.code == ExecutionDecisionCode.PLAN_CREATED.value
        assert planned.receipt is not None

        executed = await services.execute_query.execute(principal_id="user-9", plan_id=planned.receipt.plan_id)
        assert executed.code == ExecutionDecisionCode.EXECUTED.value
        assert executed.result is not None and executed.result.row_count == 1

        # 一次性 token：同一个 plan 不能被执行两次。
        assert (await services.execute_query.execute(principal_id="user-9", plan_id=planned.receipt.plan_id)).code == ExecutionDecisionCode.PLAN_UNAVAILABLE.value

        gateway = created[0]
        assert (gateway.explain_calls, gateway.execute_calls) == (1, 1)

        audits = await services.audit_reader.list_for_principal(principal_id="user-9", limit=10)
        assert sorted(record.phase.value for record in audits) == ["execute", "plan"]
        assert all(record.status.value == "completed" for record in audits)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_query_limit_below_the_transport_cap_is_clamped_not_rejected(tmp_path, monkeypatch):
    """配置的 `max_result_rows` 是全局服务器上限，不是每条查询必须达到的下限。

    Phase 2C2 Fix 01：服务端为每条计划取 `min(配置上限, prepared.row_limit)`，所以默认
    `max_result_rows=1000` 时 `LIMIT 10` 的查询会正常建出 plan，而不是被判 `authorization_stale`。
    收紧只向下发生，且 2B2 那条"传输上限大于授权 row_limit 直接拒绝"的校验原样保留为纵深防御。
    """

    monkeypatch.setattr(composition, "SQLAlchemyDatasourceQueryGateway", lambda **kwargs: _StubGateway(**kwargs))
    engine = _engine(tmp_path / "stale-row-bound.db")
    try:
        services = await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
        datasource = await services.administration.create_datasource(owner_id="owner-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")
        await services.administration.replace_schema(
            owner_id="owner-1",
            datasource_id=datasource.id,
            version="s1",
            default_schema="public",
            relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="integer"),)),),
            expected_version=None,
        )
        await services.administration.replace_policy(
            owner_id="owner-1",
            datasource_id=datasource.id,
            principal_id="user-9",
            version="p1",
            relations=(RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),)),),
            allowed_functions=(),
            expected_version=None,
        )

        delivery = await services.plan_query.execute(principal_id="user-9", datasource_id=datasource.id, raw_sql="SELECT id FROM orders LIMIT 10")

        assert delivery.code == ExecutionDecisionCode.PLAN_CREATED.value
        assert delivery.receipt is not None
        # 配置上限仍是 1000（未被服务端改写），收紧只作用于本次计划。
        assert services.config.max_result_rows == 1_000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_owner_without_a_policy_cannot_query(tmp_path, monkeypatch):
    monkeypatch.setattr(composition, "SQLAlchemyDatasourceQueryGateway", lambda **kwargs: _StubGateway(**kwargs))
    engine = _engine(tmp_path / "owner-denied.db")
    try:
        services = await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
        datasource = await services.administration.create_datasource(owner_id="owner-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")

        delivery = await services.plan_query.execute(principal_id="owner-1", datasource_id=datasource.id, raw_sql="SELECT id FROM orders LIMIT 10")

        assert delivery.code == ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value
        assert delivery.receipt is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_migrated_schema_belongs_to_the_analytics_chain(tmp_path):
    engine = _engine(tmp_path / "chain.db")
    try:
        await build_analytics_services(config=_config(), engine=engine, session_factory=async_sessionmaker(engine), backend="sqlite")
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: set(sa_inspect(sync_conn).get_table_names()))
    finally:
        await engine.dispose()

    assert "analytics_alembic_version" in tables
    assert "analytics_execution_plans" in tables
    # 绝不在 Gateway 自己那条链上动手。
    assert "alembic_version" not in tables


@pytest.mark.asyncio
async def test_the_configured_limits_reach_the_plan_use_case(tmp_path, monkeypatch):
    monkeypatch.setattr(composition, "SQLAlchemyDatasourceQueryGateway", lambda **kwargs: _StubGateway(**kwargs))
    engine = _engine(tmp_path / "limits.db")
    try:
        services = await build_analytics_services(config=_config({"query_max_rows": 250, "max_result_rows": 200, "plan_ttl_seconds": 30}), engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
        assert services.config.query_max_rows == 250
        limits = services.config.execution_limits()
        assert limits.max_result_rows == 200 and limits.plan_ttl_seconds == 30
    finally:
        await engine.dispose()


def test_the_plan_store_capacity_is_a_server_side_constant():
    # 预算是服务端常量，客户端没有任何覆盖入口。
    assert composition.PLAN_STORE_MAX_ENTRIES >= 1
    assert timedelta(seconds=composition.AnalyticsConfig().plan_ttl_seconds).total_seconds() == 60
