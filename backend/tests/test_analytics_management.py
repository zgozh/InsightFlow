"""owner-scoped 管理用例测试（Phase 2C2 任务 2）。

管理用例只组合既有 repository 端口，不 import HTTP/SQLAlchemy：

- 服务端生成 datasource ID，`owner_id` 只从调用方（认证上下文）来；
- schema/policy 操作必须先确认 datasource 属于当前管理员，否则统一 `AnalyticsNotFoundError`；
- metric 是 exact-owner scope；
- owner 身份本身不产生查询权限；
- repository/driver 失败被翻译成稳定错误，异常文本不外泄。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import (
    PersistenceConflictError,
    PersistenceDataError,
)
from app.analytics.application.management import (
    AnalyticsAdministration,
    AnalyticsNotFoundError,
    AnalyticsStorageError,
)
from app.analytics.domain import (
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    MetricStatus,
    RelationAccessRule,
    RelationSchema,
)
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.catalogs import (
    SqlAccessPolicyRepository,
    SqlDatasourceRepository,
    SqlMetricRepository,
    SqlSchemaSnapshotRepository,
)


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False)


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = _engine(tmp_path / "management.db")
    try:
        await bootstrap_analytics_schema(engine, backend="sqlite")
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def admin(sessions):
    counter = {"n": 0}

    def issue() -> str:
        counter["n"] += 1
        return f"ds-{counter['n']:04d}"

    return AnalyticsAdministration(
        datasources=SqlDatasourceRepository(sessions),
        schemas=SqlSchemaSnapshotRepository(sessions),
        policies=SqlAccessPolicyRepository(sessions),
        metrics=SqlMetricRepository(sessions),
        id_issuer=issue,
    )


def _relations(column="id", access=ColumnAccess.ALLOW):
    return (RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name=column, access=access),)),)


def _metric(*, key="revenue", owner_id="user-1", version=1, status=MetricStatus.DRAFT):
    return MetricDefinition(key=key, owner_id=owner_id, name="Revenue", description="Total revenue", expression="sum(amount)", dimensions=("region",), version=version, status=status)


def _columns(column="id"):
    return (RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name=column, data_type="integer"),)),)


# --- datasource 管理 --------------------------------------------------------


@pytest.mark.asyncio
async def test_create_datasource_generates_the_id_and_keeps_the_owner(admin):
    created = await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public")

    assert created.id == "ds-0001"
    assert created.owner_id == "user-1"
    assert created.status is DatasourceStatus.ACTIVE
    assert await admin.get_datasource(owner_id="user-1", datasource_id="ds-0001") == created


@pytest.mark.asyncio
async def test_datasource_reads_are_owner_exact(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")

    assert await admin.get_datasource(owner_id="user-2", datasource_id="ds-0001") is None
    assert await admin.list_datasources(owner_id="user-2") == ()
    assert len(await admin.list_datasources(owner_id="user-1")) == 1


@pytest.mark.asyncio
async def test_update_datasource_is_exact_and_absent_for_a_foreign_owner(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")

    updated = await admin.update_datasource(owner_id="user-1", datasource_id="ds-0001", name="Renamed", secret_ref="env://OTHER", default_schema=None, status=DatasourceStatus.DISABLED)

    assert updated is not None and updated.name == "Renamed" and updated.status is DatasourceStatus.DISABLED
    assert updated.default_schema is None
    assert await admin.update_datasource(owner_id="user-2", datasource_id="ds-0001", name="Stolen", secret_ref="env://X", default_schema=None, status=DatasourceStatus.ACTIVE) is None


@pytest.mark.asyncio
async def test_deactivate_keeps_the_row_and_removes_query_access(admin, sessions):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")
    await admin.replace_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-1", version="p1", relations=_relations(), allowed_functions=(), expected_version=None)

    accessible = SqlDatasourceRepository(sessions)
    assert await accessible.get_accessible(principal_id="user-1", datasource_id="ds-0001") is not None

    await admin.update_datasource(owner_id="user-1", datasource_id="ds-0001", name="Warehouse", secret_ref="env://ANALYTICS_DS", default_schema=None, status=DatasourceStatus.DISABLED)

    assert await admin.get_datasource(owner_id="user-1", datasource_id="ds-0001") is not None
    assert await accessible.get_accessible(principal_id="user-1", datasource_id="ds-0001") is None


# --- schema -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_requires_an_owned_datasource(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")

    with pytest.raises(AnalyticsNotFoundError):
        await admin.replace_schema(owner_id="user-2", datasource_id="ds-0001", version="s1", default_schema="public", relations=_columns(), expected_version=None)

    assert await admin.get_schema(owner_id="user-2", datasource_id="ds-0001") is None


@pytest.mark.asyncio
async def test_schema_replace_derives_the_engine_from_the_datasource(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.MYSQL, secret_ref="env://ANALYTICS_DS")

    stored = await admin.replace_schema(owner_id="user-1", datasource_id="ds-0001", version="s1", default_schema="analytics_test", relations=_columns(), expected_version=None)

    assert stored.engine is DatasourceEngine.MYSQL
    assert await admin.get_schema(owner_id="user-1", datasource_id="ds-0001") == stored


@pytest.mark.asyncio
async def test_schema_replace_enforces_expected_version(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")
    await admin.replace_schema(owner_id="user-1", datasource_id="ds-0001", version="s1", default_schema="public", relations=_columns(), expected_version=None)

    with pytest.raises(PersistenceConflictError):
        await admin.replace_schema(owner_id="user-1", datasource_id="ds-0001", version="s2", default_schema="public", relations=_columns(column="customer"), expected_version="stale")

    advanced = await admin.replace_schema(owner_id="user-1", datasource_id="ds-0001", version="s2", default_schema="public", relations=_columns(column="customer"), expected_version="s1")
    assert advanced.version == "s2"


# --- policy -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_requires_an_owned_datasource(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")

    with pytest.raises(AnalyticsNotFoundError):
        await admin.replace_policy(owner_id="user-2", datasource_id="ds-0001", principal_id="user-1", version="p1", relations=_relations(), allowed_functions=(), expected_version=None)


@pytest.mark.asyncio
async def test_policy_is_exact_principal_and_removable(admin):
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")
    stored = await admin.replace_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-9", version="p1", relations=_relations(), allowed_functions=("count",), expected_version=None)

    assert stored.principal_id == "user-9"
    assert stored.allowed_functions == ("count",)
    assert await admin.get_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-9") == stored
    assert await admin.get_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-1") is None

    await admin.remove_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-9")

    assert await admin.get_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-9") is None


@pytest.mark.asyncio
async def test_owner_identity_grants_no_query_permission(admin, sessions):
    # 管理员建了数据源并给自己写了策略以外的东西：访问读仍然只能靠精确 policy。
    await admin.create_datasource(owner_id="user-1", name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS")
    await admin.replace_policy(owner_id="user-1", datasource_id="ds-0001", principal_id="user-2", version="p1", relations=_relations(), allowed_functions=(), expected_version=None)

    accessible = SqlDatasourceRepository(sessions)

    assert await accessible.get_accessible(principal_id="user-1", datasource_id="ds-0001") is None
    assert await accessible.get_accessible(principal_id="user-2", datasource_id="ds-0001") is not None


# --- metric -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_metric_is_exact_owner_scoped(admin):
    saved = await admin.save_metric(owner_id="user-1", metric=_metric())

    assert saved.owner_id == "user-1"
    assert await admin.get_metric(owner_id="user-1", metric_key="revenue") == saved
    assert await admin.get_metric(owner_id="user-2", metric_key="revenue") is None
    assert await admin.list_metrics(owner_id="user-2") == ()


@pytest.mark.asyncio
async def test_metric_owner_must_match_the_authenticated_owner(admin):
    with pytest.raises(ValueError):
        await admin.save_metric(owner_id="user-1", metric=_metric(owner_id="user-2"))


@pytest.mark.asyncio
async def test_metric_version_can_only_advance_and_retire_is_idempotent(admin):
    await admin.save_metric(owner_id="user-1", metric=_metric(version=1))
    await admin.save_metric(owner_id="user-1", metric=_metric(version=2, status=MetricStatus.ACTIVE))

    with pytest.raises(PersistenceConflictError):
        await admin.save_metric(owner_id="user-1", metric=_metric(version=1))

    await admin.retire_metric(owner_id="user-1", metric_key="revenue")
    await admin.retire_metric(owner_id="user-1", metric_key="revenue")
    await admin.retire_metric(owner_id="user-1", metric_key="missing")

    stored = await admin.get_metric(owner_id="user-1", metric_key="revenue")
    assert stored.status is MetricStatus.RETIRED


# --- 存储失败翻译 -----------------------------------------------------------


class _ExplodingRepository:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    async def list_owned(self, *, owner_id):
        raise self._error

    async def get_owned(self, *, owner_id, datasource_id):
        raise self._error

    async def save(self, datasource):
        raise self._error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RuntimeError("dsn=postgres://user:pw@host/db"), PersistenceDataError("row_invalid_datasource")],
)
async def test_storage_failures_are_translated_without_leaking_text(sessions, error):
    admin = AnalyticsAdministration(
        datasources=_ExplodingRepository(error),
        schemas=SqlSchemaSnapshotRepository(sessions),
        policies=SqlAccessPolicyRepository(sessions),
        metrics=SqlMetricRepository(sessions),
        id_issuer=lambda: "ds-0001",
    )

    with pytest.raises(AnalyticsStorageError) as raised:
        await admin.list_datasources(owner_id="user-1")

    assert "postgres://" not in str(raised.value)
    assert " " not in raised.value.reason


@pytest.mark.asyncio
async def test_conflicts_are_not_masked_as_storage_failures(sessions):
    admin = AnalyticsAdministration(
        datasources=_ExplodingRepository(PersistenceConflictError("datasource_identity_conflict")),
        schemas=SqlSchemaSnapshotRepository(sessions),
        policies=SqlAccessPolicyRepository(sessions),
        metrics=SqlMetricRepository(sessions),
        id_issuer=lambda: "ds-0001",
    )

    with pytest.raises(PersistenceConflictError):
        await admin.list_datasources(owner_id="user-1")
