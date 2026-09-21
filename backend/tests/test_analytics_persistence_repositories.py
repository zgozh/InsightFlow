"""principal 隔离的 SQL catalog 测试（Phase 2C1 任务 4）。

这些测试全部跑在临时 SQLite 上（普通离线测试不得依赖 Docker）：

- datasource 的「可访问」读必须存在与 principal **精确匹配**的 policy 行，owner 本身不放行；
- owner 侧读只认精确 owner，绝不用 `None` 表示跨用户；
- schema/policy 的 `replace` 需要 `expected_version`：完全相等幂等、同版本漂移拒绝、
  stale expected 稳定冲突；
- metric 是 exact-owner scope，版本只能前进；
- 任何一行解码失败都抛 `PersistenceDataError`，绝不返回部分值。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import PersistenceConflictError, PersistenceDataError
from app.analytics.domain import (
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    MetricStatus,
    PrincipalAccessPolicy,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
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


def _datasource(*, id="ds-1", owner_id="user-1", name="Warehouse", status=DatasourceStatus.ACTIVE, engine=DatasourceEngine.POSTGRESQL):
    return DatasourceDefinition(id=id, owner_id=owner_id, name=name, engine=engine, secret_ref="env://ANALYTICS_DS", default_schema="public", status=status)


def _snapshot(*, datasource_id="ds-1", version="s1", engine=DatasourceEngine.POSTGRESQL, column="id"):
    return SchemaSnapshot(
        datasource_id=datasource_id,
        engine=engine,
        version=version,
        default_schema="public",
        relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name=column, data_type="integer"),)),),
    )


def _policy(*, datasource_id="ds-1", principal_id="user-1", version="p1", column="id", access=ColumnAccess.ALLOW):
    return PrincipalAccessPolicy(
        datasource_id=datasource_id,
        principal_id=principal_id,
        version=version,
        relations=(RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name=column, access=access),)),),
        allowed_functions=("count",),
    )


def _metric(*, key="revenue", owner_id="user-1", version=1, status=MetricStatus.DRAFT, dimensions=("region",)):
    return MetricDefinition(
        key=key,
        owner_id=owner_id,
        name="Revenue",
        description="Total revenue",
        expression="sum(amount)",
        dimensions=dimensions,
        version=version,
        status=status,
    )


class _Fixture:
    def __init__(self, engine):
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    def datasources(self):
        return SqlDatasourceRepository(self.sessions)

    def schemas(self):
        return SqlSchemaSnapshotRepository(self.sessions)

    def policies(self):
        return SqlAccessPolicyRepository(self.sessions)

    def metrics(self):
        return SqlMetricRepository(self.sessions)


@pytest_asyncio.fixture
async def fixture(tmp_path):
    engine = _engine(tmp_path / "repositories.db")
    try:
        await bootstrap_analytics_schema(engine, backend="sqlite")
        yield _Fixture(engine)
    finally:
        await engine.dispose()


# --- datasource：管理归属 vs 查询权限 ---------------------------------------


@pytest.mark.asyncio
async def test_datasource_save_round_trips_for_the_exact_owner(fixture):
    repository = fixture.datasources()
    await repository.save(_datasource())

    owned = await repository.get_owned(owner_id="user-1", datasource_id="ds-1")

    assert owned == _datasource()
    assert await repository.get_owned(owner_id="user-2", datasource_id="ds-1") is None


@pytest.mark.asyncio
async def test_datasource_save_is_idempotent(fixture):
    repository = fixture.datasources()
    await repository.save(_datasource())
    await repository.save(_datasource())

    assert await repository.list_owned(owner_id="user-1") == (_datasource(),)


@pytest.mark.asyncio
async def test_owned_listing_is_ordered_by_name_then_id(fixture):
    repository = fixture.datasources()
    # (owner_id, name) 唯一，所以同一 owner 下不能重名；这里验证 name 排序。
    for datasource in (_datasource(id="ds-b", name="beta"), _datasource(id="ds-c", name="zeta"), _datasource(id="ds-a", name="alpha")):
        await repository.save(datasource)

    listed = await repository.list_owned(owner_id="user-1")

    assert [item.id for item in listed] == ["ds-a", "ds-b", "ds-c"]


@pytest.mark.asyncio
async def test_a_duplicate_owner_and_name_is_a_stable_conflict(fixture):
    repository = fixture.datasources()
    await repository.save(_datasource(id="ds-1", name="Warehouse"))

    with pytest.raises(PersistenceConflictError) as error:
        await repository.save(_datasource(id="ds-2", name="Warehouse"))

    assert error.value.reason == "datasource_identity_conflict"


@pytest.mark.asyncio
async def test_the_owner_alone_grants_no_query_access(fixture):
    await fixture.datasources().save(_datasource())

    assert await fixture.datasources().get_accessible(principal_id="user-1", datasource_id="ds-1") is None
    assert await fixture.datasources().list_accessible(principal_id="user-1") == ()


@pytest.mark.asyncio
async def test_an_exact_policy_row_grants_access_only_to_that_principal(fixture):
    await fixture.datasources().save(_datasource())
    await fixture.policies().replace(_policy(principal_id="user-1"), expected_version=None)

    assert await fixture.datasources().get_accessible(principal_id="user-1", datasource_id="ds-1") == _datasource()
    # 另一个 principal 即使能读到同一数据源的管理元数据，也不能查询；owner 身份也不放行。
    assert await fixture.datasources().get_accessible(principal_id="user-2", datasource_id="ds-1") is None
    assert await fixture.datasources().get_accessible(principal_id="", datasource_id="ds-1") is None


@pytest.mark.asyncio
async def test_a_disabled_datasource_is_denied_even_with_a_policy(fixture):
    await fixture.datasources().save(_datasource(status=DatasourceStatus.DISABLED))
    await fixture.policies().replace(_policy(), expected_version=None)

    assert await fixture.datasources().get_accessible(principal_id="user-1", datasource_id="ds-1") is None
    assert await fixture.datasources().list_accessible(principal_id="user-1") == ()


@pytest.mark.asyncio
async def test_accessible_listing_is_scoped_and_ordered(fixture):
    datasources = fixture.datasources()
    policies = fixture.policies()
    # 同名的两个数据源分属不同 owner —— 唯一约束只覆盖 (owner_id, name)，
    # 因此「按 (name, id) 排序」的 id 兜底在这里才真正生效。
    for datasource in (_datasource(id="ds-a", name="alpha"), _datasource(id="ds-c", name="zeta"), _datasource(id="ds-b", owner_id="user-2", name="alpha")):
        await datasources.save(datasource)
        await policies.replace(_policy(datasource_id=datasource.id, principal_id="user-1"), expected_version=None)
    # 没有 policy 的数据源对 user-1 不可见。
    await datasources.save(_datasource(id="ds-x", owner_id="user-3", name="beta"))

    listed = await datasources.list_accessible(principal_id="user-1")

    assert [item.id for item in listed] == ["ds-a", "ds-b", "ds-c"]


# --- schema snapshot：版本纪律 ----------------------------------------------


@pytest.mark.asyncio
async def test_schema_replace_requires_an_existing_datasource(fixture):
    with pytest.raises(PersistenceConflictError) as error:
        await fixture.schemas().replace(_snapshot(), expected_version=None)

    assert error.value.reason == "datasource_missing"


@pytest.mark.asyncio
async def test_schema_replace_rejects_an_engine_that_disagrees_with_the_datasource(fixture):
    await fixture.datasources().save(_datasource(engine=DatasourceEngine.POSTGRESQL))

    with pytest.raises(PersistenceConflictError) as error:
        await fixture.schemas().replace(_snapshot(engine=DatasourceEngine.MYSQL), expected_version=None)

    assert error.value.reason == "engine_mismatch"


@pytest.mark.asyncio
async def test_schema_replace_is_idempotent_when_the_value_is_identical(fixture):
    await fixture.datasources().save(_datasource())
    schemas = fixture.schemas()
    await schemas.replace(_snapshot(), expected_version=None)

    await schemas.replace(_snapshot(), expected_version="s1")

    assert await schemas.get_current(datasource_id="ds-1") == _snapshot()


@pytest.mark.asyncio
async def test_schema_replace_rejects_content_drift_at_the_same_version(fixture):
    await fixture.datasources().save(_datasource())
    schemas = fixture.schemas()
    await schemas.replace(_snapshot(), expected_version=None)

    with pytest.raises(PersistenceConflictError) as error:
        await schemas.replace(_snapshot(column="customer"), expected_version="s1")

    assert error.value.reason == "version_drift"
    assert await schemas.get_current(datasource_id="ds-1") == _snapshot()


@pytest.mark.asyncio
async def test_schema_replace_rejects_a_stale_expected_version(fixture):
    await fixture.datasources().save(_datasource())
    schemas = fixture.schemas()
    await schemas.replace(_snapshot(version="s1"), expected_version=None)

    with pytest.raises(PersistenceConflictError) as error:
        await schemas.replace(_snapshot(version="s3", column="customer"), expected_version="s2")

    assert error.value.reason == "stale_expected_version"
    assert await schemas.get_current(datasource_id="ds-1") == _snapshot()


@pytest.mark.asyncio
async def test_schema_replace_advances_the_version_when_expected_matches(fixture):
    await fixture.datasources().save(_datasource())
    schemas = fixture.schemas()
    await schemas.replace(_snapshot(version="s1"), expected_version=None)

    await schemas.replace(_snapshot(version="s2", column="customer"), expected_version="s1")

    assert await schemas.get_current(datasource_id="ds-1") == _snapshot(version="s2", column="customer")


@pytest.mark.asyncio
async def test_schema_get_current_returns_none_for_an_unknown_datasource(fixture):
    assert await fixture.schemas().get_current(datasource_id="ds-missing") is None


# --- access policy：版本纪律与移除 ------------------------------------------


@pytest.mark.asyncio
async def test_policy_replace_requires_an_existing_datasource(fixture):
    with pytest.raises(PersistenceConflictError):
        await fixture.policies().replace(_policy(), expected_version=None)


@pytest.mark.asyncio
async def test_policy_replace_is_idempotent_and_rejects_drift(fixture):
    await fixture.datasources().save(_datasource())
    policies = fixture.policies()
    await policies.replace(_policy(), expected_version=None)

    await policies.replace(_policy(), expected_version="p1")
    with pytest.raises(PersistenceConflictError) as error:
        await policies.replace(_policy(access=ColumnAccess.DENY), expected_version="p1")

    assert error.value.reason == "version_drift"
    assert await policies.get_effective(principal_id="user-1", datasource_id="ds-1") == _policy()


@pytest.mark.asyncio
async def test_policy_replace_rejects_a_stale_expected_version(fixture):
    await fixture.datasources().save(_datasource())
    policies = fixture.policies()
    await policies.replace(_policy(version="p1"), expected_version=None)

    with pytest.raises(PersistenceConflictError) as error:
        await policies.replace(_policy(version="p3", column="amount"), expected_version="p2")

    assert error.value.reason == "stale_expected_version"


@pytest.mark.asyncio
async def test_policy_removal_is_exact_and_idempotent(fixture):
    await fixture.datasources().save(_datasource())
    policies = fixture.policies()
    await policies.replace(_policy(principal_id="user-1"), expected_version=None)
    await policies.replace(_policy(principal_id="user-2"), expected_version=None)

    await policies.remove(datasource_id="ds-1", principal_id="user-1")
    await policies.remove(datasource_id="ds-1", principal_id="user-1")

    assert await policies.get_effective(principal_id="user-1", datasource_id="ds-1") is None
    assert await policies.get_effective(principal_id="user-2", datasource_id="ds-1") == _policy(principal_id="user-2")


@pytest.mark.asyncio
async def test_policies_are_isolated_per_principal_and_per_datasource(fixture):
    await fixture.datasources().save(_datasource(id="ds-1"))
    await fixture.datasources().save(_datasource(id="ds-2", name="Other"))
    policies = fixture.policies()
    await policies.replace(_policy(datasource_id="ds-1", principal_id="user-1"), expected_version=None)
    await policies.replace(_policy(datasource_id="ds-2", principal_id="user-1", version="p9"), expected_version=None)

    assert await policies.get_effective(principal_id="user-1", datasource_id="ds-1") == _policy(datasource_id="ds-1")
    assert await policies.get_effective(principal_id="user-1", datasource_id="ds-2") == _policy(datasource_id="ds-2", version="p9")
    assert await policies.get_effective(principal_id="user-2", datasource_id="ds-1") is None


# --- metric：exact-owner scope 与只能前进的版本 -----------------------------


@pytest.mark.asyncio
async def test_metric_save_round_trips_for_the_exact_owner(fixture):
    metrics = fixture.metrics()
    await metrics.save(_metric())

    assert await metrics.get_accessible(principal_id="user-1", metric_key="revenue") == _metric()
    assert await metrics.get_accessible(principal_id="user-2", metric_key="revenue") is None
    assert await metrics.list_accessible(principal_id="user-2") == ()


@pytest.mark.asyncio
async def test_metric_listing_is_ordered_by_key_then_version(fixture):
    metrics = fixture.metrics()
    await metrics.save(_metric(key="zeta", version=1))
    await metrics.save(_metric(key="alpha", version=1))
    await metrics.save(_metric(key="alpha", version=2, dimensions=("day",)))
    # 另一个 owner 的同名 metric 绝不出现。
    await metrics.save(_metric(key="alpha", owner_id="user-2"))

    listed = await metrics.list_accessible(principal_id="user-1")

    assert [(item.key, item.version, item.owner_id) for item in listed] == [("alpha", 2, "user-1"), ("zeta", 1, "user-1")]


@pytest.mark.asyncio
async def test_metric_save_is_idempotent_and_rejects_a_non_increasing_version(fixture):
    metrics = fixture.metrics()
    await metrics.save(_metric(version=2))
    await metrics.save(_metric(version=2))

    with pytest.raises(PersistenceConflictError) as error:
        await metrics.save(_metric(version=2, dimensions=("day",)))
    assert error.value.reason == "metric_version_conflict"

    with pytest.raises(PersistenceConflictError):
        await metrics.save(_metric(version=1))
    assert await metrics.get_accessible(principal_id="user-1", metric_key="revenue") == _metric(version=2)


@pytest.mark.asyncio
async def test_a_higher_metric_version_replaces_the_row(fixture):
    metrics = fixture.metrics()
    await metrics.save(_metric(version=1))
    await metrics.save(_metric(version=3, dimensions=("day",), status=MetricStatus.ACTIVE))

    stored = await metrics.get_accessible(principal_id="user-1", metric_key="revenue")

    assert stored == _metric(version=3, dimensions=("day",), status=MetricStatus.ACTIVE)


@pytest.mark.asyncio
async def test_metric_retire_is_exact_and_idempotent(fixture):
    metrics = fixture.metrics()
    await metrics.save(_metric(key="revenue"))
    await metrics.save(_metric(key="margin"))

    await metrics.retire(owner_id="user-1", metric_key="revenue")
    await metrics.retire(owner_id="user-1", metric_key="revenue")
    await metrics.retire(owner_id="user-1", metric_key="missing")

    assert (await metrics.get_accessible(principal_id="user-1", metric_key="revenue")).status is MetricStatus.RETIRED
    assert (await metrics.get_accessible(principal_id="user-1", metric_key="margin")).status is MetricStatus.DRAFT


# --- 损坏行与异常文本 -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_corrupt_schema_row_raises_a_data_error_without_returning_a_partial_value(fixture):
    await fixture.datasources().save(_datasource())
    await fixture.schemas().replace(_snapshot(), expected_version=None)
    async with fixture.sessions() as session:
        await session.execute(sa_text("UPDATE analytics_schema_snapshots SET relations_json = '{not json'"))
        await session.commit()

    with pytest.raises(PersistenceDataError) as error:
        await fixture.schemas().get_current(datasource_id="ds-1")

    assert "not json" not in str(error.value)
    assert " " not in error.value.reason


@pytest.mark.asyncio
async def test_a_corrupt_datasource_row_raises_a_data_error(fixture):
    await fixture.datasources().save(_datasource())
    async with fixture.sessions() as session:
        # 破坏行内不变量而不是 enum：enum 会被 CHECK constraint 提前挡住，测不到解码路径。
        await session.execute(sa_text("UPDATE analytics_datasources SET secret_ref = ''"))
        await session.commit()

    with pytest.raises(PersistenceDataError):
        await fixture.datasources().get_owned(owner_id="user-1", datasource_id="ds-1")


@pytest.mark.asyncio
async def test_repository_errors_never_carry_driver_text(fixture):
    await fixture.datasources().save(_datasource())

    with pytest.raises(PersistenceConflictError) as error:
        await fixture.datasources().save(_datasource(id="ds-2", name="Warehouse"))

    assert "sqlite" not in str(error.value)
    assert "INSERT" not in str(error.value)
