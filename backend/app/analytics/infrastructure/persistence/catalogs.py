"""principal 隔离的 SQL catalog 适配器（Phase 2C1）。

职责划分：本模块只做「catalog 读写 + 版本纪律 + 行解码」，不实现 plan store、审计或迁移。

安全与一致性规则（架构规格 §4、§10）：

- **owner ≠ 查询权限**：`get_accessible` / `list_accessible` 必须存在与 principal 精确匹配的
  `analytics_access_policies` 行，而且 datasource 必须 `active`；owner 身份本身不放行。
- 所有读写都用调用方传入的**精确** owner/principal，绝不用 `None` 表示跨用户。
- schema/policy 的 `replace` 在同一事务内加行锁、读取旧值并按 `expected_version` 判定：
  完全相等幂等、内容不同但版本相同拒绝、当前版本不等于 expected 拒绝。
- 仓库不缓存权限或 schema；任何解码失败都抛 `PersistenceDataError`，绝不返回部分值。
- 仓库异常只携带稳定 reason，绝不携带驱动异常文本。

`with_for_update()` 在 SQLite 上是空操作、在 PostgreSQL 上是真正的行锁；SQLite 只用于
单 worker 本地开发，多 worker 由现有全局门禁要求 PostgreSQL。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import PersistenceConflictError, PersistenceDataError
from app.analytics.domain import (
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    MetricStatus,
    PrincipalAccessPolicy,
    SchemaSnapshot,
)
from app.analytics.infrastructure.persistence.codec import (
    decode_access_policy,
    decode_dimensions,
    decode_schema_snapshot,
    encode_access_policy,
    encode_dimensions,
    encode_schema_snapshot,
)
from app.analytics.infrastructure.persistence.models import AccessPolicyRow, DatasourceRow, MetricRow, SchemaSnapshotRow


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_datasource(row: DatasourceRow) -> DatasourceDefinition:
    try:
        return DatasourceDefinition(
            id=row.id,
            owner_id=row.owner_id,
            name=row.name,
            engine=DatasourceEngine(row.engine),
            secret_ref=row.secret_ref,
            default_schema=row.default_schema,
            status=DatasourceStatus(row.status),
        )
    except PersistenceDataError:
        raise
    except (ValueError, TypeError) as error:
        raise PersistenceDataError("row_invalid_datasource") from error


def _row_to_snapshot(row: SchemaSnapshotRow) -> SchemaSnapshot:
    snapshot = decode_schema_snapshot(row.relations_json)
    # payload 与行键必须自洽：不一致说明行被改写，不能让调用方拿到"半个对象"。
    if snapshot.datasource_id != row.datasource_id:
        raise PersistenceDataError("row_snapshot_identity_mismatch")
    return snapshot


def _row_to_policy(row: AccessPolicyRow) -> PrincipalAccessPolicy:
    policy = decode_access_policy(row.relations_json)
    if policy.datasource_id != row.datasource_id or policy.principal_id != row.principal_id:
        raise PersistenceDataError("row_policy_identity_mismatch")
    return policy


def _row_to_metric(row: MetricRow) -> MetricDefinition:
    try:
        return MetricDefinition(
            key=row.key,
            owner_id=row.owner_id,
            name=row.name,
            description=row.description,
            expression=row.expression,
            dimensions=decode_dimensions(row.dimensions_json),
            version=row.version,
            status=MetricStatus(row.status),
        )
    except PersistenceDataError:
        raise
    except (ValueError, TypeError) as error:
        raise PersistenceDataError("row_invalid_metric") from error


class SqlDatasourceRepository:
    """datasource 的读写适配器：管理侧按 owner，查询侧按精确 policy。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_owned(self, *, owner_id: str, datasource_id: str) -> DatasourceDefinition | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(DatasourceRow).where(DatasourceRow.owner_id == owner_id, DatasourceRow.id == datasource_id))).scalar_one_or_none()
        return None if row is None else _row_to_datasource(row)

    async def list_owned(self, *, owner_id: str) -> tuple[DatasourceDefinition, ...]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(DatasourceRow).where(DatasourceRow.owner_id == owner_id).order_by(DatasourceRow.name, DatasourceRow.id))).scalars().all()
        return tuple(_row_to_datasource(row) for row in rows)

    async def save(self, datasource: DatasourceDefinition) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(DatasourceRow, datasource.id)
                timestamp = _now()
                if row is None:
                    session.add(
                        DatasourceRow(
                            id=datasource.id,
                            owner_id=datasource.owner_id,
                            name=datasource.name,
                            engine=datasource.engine.value,
                            secret_ref=datasource.secret_ref,
                            default_schema=datasource.default_schema,
                            status=datasource.status.value,
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
                    try:
                        await session.flush()
                    except IntegrityError as error:
                        raise PersistenceConflictError("datasource_identity_conflict") from error
                    return
                taken = (
                    await session.execute(
                        select(DatasourceRow.id).where(
                            DatasourceRow.owner_id == datasource.owner_id,
                            DatasourceRow.name == datasource.name,
                            DatasourceRow.id != datasource.id,
                        )
                    )
                ).first()
                if taken is not None:
                    raise PersistenceConflictError("datasource_identity_conflict")
                row.owner_id = datasource.owner_id
                row.name = datasource.name
                row.engine = datasource.engine.value
                row.secret_ref = datasource.secret_ref
                row.default_schema = datasource.default_schema
                row.status = datasource.status.value
                row.updated_at = timestamp

    async def get_accessible(self, *, principal_id: str, datasource_id: str) -> DatasourceDefinition | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(DatasourceRow)
                    .join(AccessPolicyRow, AccessPolicyRow.datasource_id == DatasourceRow.id)
                    .where(
                        AccessPolicyRow.principal_id == principal_id,
                        DatasourceRow.id == datasource_id,
                        DatasourceRow.status == DatasourceStatus.ACTIVE.value,
                    )
                )
            ).scalar_one_or_none()
        return None if row is None else _row_to_datasource(row)

    async def list_accessible(self, *, principal_id: str) -> tuple[DatasourceDefinition, ...]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DatasourceRow)
                        .join(AccessPolicyRow, AccessPolicyRow.datasource_id == DatasourceRow.id)
                        .where(AccessPolicyRow.principal_id == principal_id, DatasourceRow.status == DatasourceStatus.ACTIVE.value)
                        .order_by(DatasourceRow.name, DatasourceRow.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(_row_to_datasource(row) for row in rows)


class SqlSchemaSnapshotRepository:
    """每个 datasource 只保存一个 current snapshot，替换必须携带 `expected_version`。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_current(self, *, datasource_id: str) -> SchemaSnapshot | None:
        async with self._session_factory() as session:
            row = await session.get(SchemaSnapshotRow, datasource_id)
        return None if row is None else _row_to_snapshot(row)

    async def replace(self, snapshot: SchemaSnapshot, *, expected_version: str | None) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                datasource = await session.get(DatasourceRow, snapshot.datasource_id)
                if datasource is None:
                    raise PersistenceConflictError("datasource_missing")
                if datasource.engine != snapshot.engine.value:
                    # 规格要求 snapshot.engine 与 datasource 精确一致；不一致会让后续授权
                    # 在一个引擎的 schema 上做另一个引擎的判断。
                    raise PersistenceConflictError("engine_mismatch")

                row = (await session.execute(select(SchemaSnapshotRow).where(SchemaSnapshotRow.datasource_id == snapshot.datasource_id).with_for_update())).scalar_one_or_none()
                timestamp = _now()
                if row is None:
                    if expected_version is not None:
                        raise PersistenceConflictError("stale_expected_version")
                    session.add(
                        SchemaSnapshotRow(
                            datasource_id=snapshot.datasource_id,
                            engine=snapshot.engine.value,
                            version=snapshot.version,
                            default_schema=snapshot.default_schema,
                            relations_json=encode_schema_snapshot(snapshot),
                            updated_at=timestamp,
                        )
                    )
                    return

                current = _row_to_snapshot(row)
                if current == snapshot:
                    return
                if current.version == snapshot.version:
                    raise PersistenceConflictError("version_drift")
                if current.version != expected_version:
                    raise PersistenceConflictError("stale_expected_version")

                row.engine = snapshot.engine.value
                row.version = snapshot.version
                row.default_schema = snapshot.default_schema
                row.relations_json = encode_schema_snapshot(snapshot)
                row.updated_at = timestamp


class SqlAccessPolicyRepository:
    """principal 精确匹配的访问策略仓库。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_effective(self, *, principal_id: str, datasource_id: str) -> PrincipalAccessPolicy | None:
        async with self._session_factory() as session:
            row = await session.get(AccessPolicyRow, (datasource_id, principal_id))
        return None if row is None else _row_to_policy(row)

    async def replace(self, policy: PrincipalAccessPolicy, *, expected_version: str | None) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                datasource = await session.get(DatasourceRow, policy.datasource_id)
                if datasource is None:
                    raise PersistenceConflictError("datasource_missing")

                key = (policy.datasource_id, policy.principal_id)
                row = (await session.execute(select(AccessPolicyRow).where(AccessPolicyRow.datasource_id == key[0], AccessPolicyRow.principal_id == key[1]).with_for_update())).scalar_one_or_none()
                timestamp = _now()
                if row is None:
                    if expected_version is not None:
                        raise PersistenceConflictError("stale_expected_version")
                    session.add(
                        AccessPolicyRow(
                            datasource_id=policy.datasource_id,
                            principal_id=policy.principal_id,
                            version=policy.version,
                            relations_json=encode_access_policy(policy),
                            allowed_functions_json=encode_dimensions(policy.allowed_functions),
                            updated_at=timestamp,
                        )
                    )
                    return

                current = _row_to_policy(row)
                if current == policy:
                    return
                if current.version == policy.version:
                    raise PersistenceConflictError("version_drift")
                if current.version != expected_version:
                    raise PersistenceConflictError("stale_expected_version")

                row.version = policy.version
                row.relations_json = encode_access_policy(policy)
                row.allowed_functions_json = encode_dimensions(policy.allowed_functions)
                row.updated_at = timestamp

    async def remove(self, *, datasource_id: str, principal_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                # 精确到 (datasource, principal)，且天然幂等：删不存在的行不是错误。
                await session.execute(delete(AccessPolicyRow).where(AccessPolicyRow.datasource_id == datasource_id, AccessPolicyRow.principal_id == principal_id))


class SqlMetricRepository:
    """V1 的 metric 是 exact-owner scoped，不引入组织、租户或共享目录。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_accessible(self, *, principal_id: str, metric_key: str) -> MetricDefinition | None:
        async with self._session_factory() as session:
            row = await session.get(MetricRow, (principal_id, metric_key))
        return None if row is None else _row_to_metric(row)

    async def list_accessible(self, *, principal_id: str) -> tuple[MetricDefinition, ...]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(MetricRow).where(MetricRow.owner_id == principal_id).order_by(MetricRow.key, MetricRow.version))).scalars().all()
        return tuple(_row_to_metric(row) for row in rows)

    async def save(self, metric: MetricDefinition) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                key = (metric.owner_id, metric.key)
                row = await session.get(MetricRow, key)
                timestamp = _now()
                if row is None:
                    session.add(
                        MetricRow(
                            owner_id=metric.owner_id,
                            key=metric.key,
                            name=metric.name,
                            description=metric.description,
                            expression=metric.expression,
                            dimensions_json=encode_dimensions(metric.dimensions),
                            version=metric.version,
                            status=metric.status.value,
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
                    return

                current = _row_to_metric(row)
                if current == metric:
                    return
                if metric.version <= current.version:
                    # 版本只能前进：同版本改内容或回退版本都会让已消费的版本号失去意义。
                    raise PersistenceConflictError("metric_version_conflict")

                row.name = metric.name
                row.description = metric.description
                row.expression = metric.expression
                row.dimensions_json = encode_dimensions(metric.dimensions)
                row.version = metric.version
                row.status = metric.status.value
                row.updated_at = timestamp

    async def retire(self, *, owner_id: str, metric_key: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(MetricRow, (owner_id, metric_key))
                if row is None or row.status == MetricStatus.RETIRED.value:
                    return
                row.status = MetricStatus.RETIRED.value
                row.updated_at = _now()
