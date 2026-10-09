"""owner-scoped 管理用例（Phase 2C2 §5.1）。

只组合既有 repository 端口，不 import FastAPI/SQLAlchemy/Harness，因此 Phase 3 的 Agent Tool
可以复用同一批用例。

安全规则：

- `owner_id` 永远由调用方（认证上下文）给出，请求体里的同名字段在 HTTP 层就被拒绝；
- **owner 身份不产生查询权限**：管理用例只写 datasource/schema/policy，可访问读仍然要求
  存在与 principal 精确匹配的 policy 行；
- schema/policy 操作先确认 datasource 属于当前管理员，否则统一 `AnalyticsNotFoundError`
  （HTTP 层映射成 404，避免用 403 泄露"这个 ID 存在但不是你的"）；
- 物理删除不支持：停用语义是 `status=disabled`；
- repository/driver 失败被翻译成只带稳定 reason 的 `AnalyticsStorageError`，异常文本不外泄。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.analytics.application.persistence_ports import (
    AccessPolicyRepository,
    DatasourceAdminRepository,
    MetricRepository,
    PersistenceConflictError,
    PersistenceDataError,
    SchemaSnapshotRepository,
)
from app.analytics.domain import (
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    PrincipalAccessPolicy,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)

T = TypeVar("T")


class AnalyticsNotFoundError(Exception):
    """资源不存在或不属于当前管理员。调用方不得区分这两种情况。"""

    def __init__(self, reason: str = "analytics_resource_not_found") -> None:
        super().__init__(reason)
        self.reason = reason


class AnalyticsStorageError(Exception):
    """Analytics 应用库不可用或内容损坏。只携带稳定 reason。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AnalyticsAdministration:
    """datasource / schema / policy / metric 的管理用例。"""

    def __init__(
        self,
        *,
        datasources: DatasourceAdminRepository,
        schemas: SchemaSnapshotRepository,
        policies: AccessPolicyRepository,
        metrics: MetricRepository,
        id_issuer: Callable[[], str],
    ) -> None:
        self._datasources = datasources
        self._schemas = schemas
        self._policies = policies
        self._metrics = metrics
        self._id_issuer = id_issuer

    async def _guard(self, operation: Awaitable[T]) -> T:
        """把存储层失败翻译成稳定错误；冲突保持原样，损坏行 fail closed。"""

        try:
            return await operation
        except (PersistenceConflictError, AnalyticsNotFoundError):
            raise
        except PersistenceDataError as error:
            raise AnalyticsStorageError("analytics_storage_invalid") from error
        except Exception as error:  # noqa: BLE001 - 驱动异常文本可能含 DSN/表名，必须脱敏
            raise AnalyticsStorageError("analytics_storage_unavailable") from error

    async def _require_owned(self, *, owner_id: str, datasource_id: str) -> DatasourceDefinition:
        datasource = await self._guard(self._datasources.get_owned(owner_id=owner_id, datasource_id=datasource_id))
        if datasource is None:
            raise AnalyticsNotFoundError()
        return datasource

    # --- datasource ---------------------------------------------------------

    async def list_datasources(self, *, owner_id: str) -> tuple[DatasourceDefinition, ...]:
        return await self._guard(self._datasources.list_owned(owner_id=owner_id))

    async def get_datasource(self, *, owner_id: str, datasource_id: str) -> DatasourceDefinition | None:
        return await self._guard(self._datasources.get_owned(owner_id=owner_id, datasource_id=datasource_id))

    async def create_datasource(
        self,
        *,
        owner_id: str,
        name: str,
        engine: DatasourceEngine,
        secret_ref: str,
        default_schema: str | None = None,
    ) -> DatasourceDefinition:
        datasource = DatasourceDefinition(
            # ID 由服务端生成：客户端提交的 ID 在 HTTP 层就被拒绝。
            id=self._id_issuer(),
            owner_id=owner_id,
            name=name,
            engine=engine,
            secret_ref=secret_ref,
            default_schema=default_schema,
            status=DatasourceStatus.ACTIVE,
        )
        await self._guard(self._datasources.save(datasource))
        return datasource

    async def update_datasource(
        self,
        *,
        owner_id: str,
        datasource_id: str,
        name: str,
        secret_ref: str,
        default_schema: str | None,
        status: DatasourceStatus,
    ) -> DatasourceDefinition | None:
        current = await self._guard(self._datasources.get_owned(owner_id=owner_id, datasource_id=datasource_id))
        if current is None:
            return None
        updated = DatasourceDefinition(
            id=current.id,
            owner_id=current.owner_id,
            name=name,
            # engine 不随更新变化：换引擎等于换一个数据源，必须新建。
            engine=current.engine,
            secret_ref=secret_ref,
            default_schema=default_schema,
            status=status,
        )
        await self._guard(self._datasources.save(updated))
        return updated

    # --- schema -------------------------------------------------------------

    async def get_schema(self, *, owner_id: str, datasource_id: str) -> SchemaSnapshot | None:
        # 读路径用 None 表达"不存在或不属于你"，由 HTTP 层统一映射成 404；
        # 写路径用 AnalyticsNotFoundError，两者的对外表现一致。
        if await self._guard(self._datasources.get_owned(owner_id=owner_id, datasource_id=datasource_id)) is None:
            return None
        return await self._guard(self._schemas.get_current(datasource_id=datasource_id))

    async def replace_schema(
        self,
        *,
        owner_id: str,
        datasource_id: str,
        version: str,
        default_schema: str,
        relations: tuple[RelationSchema, ...],
        expected_version: str | None,
    ) -> SchemaSnapshot:
        datasource = await self._require_owned(owner_id=owner_id, datasource_id=datasource_id)
        # engine 从 datasource 派生，客户端不能提交。
        snapshot = SchemaSnapshot(datasource_id=datasource.id, engine=datasource.engine, version=version, default_schema=default_schema, relations=relations)
        await self._guard(self._schemas.replace(snapshot, expected_version=expected_version))
        return snapshot

    # --- policy -------------------------------------------------------------

    async def get_policy(self, *, owner_id: str, datasource_id: str, principal_id: str) -> PrincipalAccessPolicy | None:
        if await self._guard(self._datasources.get_owned(owner_id=owner_id, datasource_id=datasource_id)) is None:
            return None
        return await self._guard(self._policies.get_effective(principal_id=principal_id, datasource_id=datasource_id))

    async def replace_policy(
        self,
        *,
        owner_id: str,
        datasource_id: str,
        principal_id: str,
        version: str,
        relations: tuple[RelationAccessRule, ...],
        allowed_functions: tuple[str, ...],
        expected_version: str | None,
    ) -> PrincipalAccessPolicy:
        await self._require_owned(owner_id=owner_id, datasource_id=datasource_id)
        policy = PrincipalAccessPolicy(
            datasource_id=datasource_id,
            # principal 来自路径而 datasource 来自路径 + owner 校验：两者都不来自请求体。
            principal_id=principal_id,
            version=version,
            relations=relations,
            allowed_functions=allowed_functions,
        )
        await self._guard(self._policies.replace(policy, expected_version=expected_version))
        return policy

    async def remove_policy(self, *, owner_id: str, datasource_id: str, principal_id: str) -> None:
        await self._require_owned(owner_id=owner_id, datasource_id=datasource_id)
        await self._guard(self._policies.remove(datasource_id=datasource_id, principal_id=principal_id))

    # --- metric -------------------------------------------------------------

    async def list_metrics(self, *, owner_id: str) -> tuple[MetricDefinition, ...]:
        return await self._guard(self._metrics.list_owned(owner_id=owner_id))

    async def get_metric(self, *, owner_id: str, metric_key: str) -> MetricDefinition | None:
        return await self._guard(self._metrics.get_owned(owner_id=owner_id, metric_key=metric_key))

    async def _require_owned_metric(self, *, owner_id: str, metric_key: str) -> MetricDefinition:
        metric = await self._guard(self._metrics.get_owned(owner_id=owner_id, metric_key=metric_key))
        if metric is None:
            raise AnalyticsNotFoundError()
        return metric

    @staticmethod
    def _validate_grant_principal(principal_id: str) -> None:
        if not isinstance(principal_id, str) or not principal_id or len(principal_id) > 64 or principal_id != principal_id.strip() or any(unicodedata.category(character) == "Cc" for character in principal_id):
            raise ValueError("principal_id is invalid")

    async def list_metric_grants(self, *, owner_id: str, metric_key: str) -> tuple[str, ...]:
        await self._require_owned_metric(owner_id=owner_id, metric_key=metric_key)
        return await self._guard(self._metrics.list_grants(owner_id=owner_id, metric_key=metric_key))

    async def grant_metric(self, *, owner_id: str, metric_key: str, principal_id: str) -> None:
        await self._require_owned_metric(owner_id=owner_id, metric_key=metric_key)
        self._validate_grant_principal(principal_id)
        await self._guard(self._metrics.grant(owner_id=owner_id, metric_key=metric_key, principal_id=principal_id))

    async def revoke_metric_grant(self, *, owner_id: str, metric_key: str, principal_id: str) -> None:
        await self._require_owned_metric(owner_id=owner_id, metric_key=metric_key)
        self._validate_grant_principal(principal_id)
        await self._guard(self._metrics.revoke_grant(owner_id=owner_id, metric_key=metric_key, principal_id=principal_id))

    async def save_metric(self, *, owner_id: str, metric: MetricDefinition) -> MetricDefinition:
        if metric.owner_id != owner_id:
            # 调用方组装错误，而不是客户端输入错误：不可能通过修改请求变得合法。
            raise ValueError("metric owner must match the authenticated owner")
        await self._guard(self._metrics.save(metric))
        return metric

    async def retire_metric(self, *, owner_id: str, metric_key: str) -> None:
        await self._guard(self._metrics.retire(owner_id=owner_id, metric_key=metric_key))


__all__ = ["AnalyticsAdministration", "AnalyticsNotFoundError", "AnalyticsStorageError"]
