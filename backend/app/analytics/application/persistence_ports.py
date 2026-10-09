"""持久化侧的应用端口（Phase 2C1）。

设计约束：

- 端口只暴露不可变领域值与 keyword-only 身份参数，绝不暴露 SQLAlchemy session；
- 绝不出现"返回任意 dict"的万能 repository；
- 仓库异常只携带稳定 reason，不携带数据库异常文本或序列化 payload。

只读端口（`DatasourceCatalog` / `MetricCatalog` / `SchemaCatalog` / `AccessPolicyCatalog`）
在 Phase 2B1 已定义；这里的写侧端口显式继承它们，保证同一次注入同时满足读写两侧。
"""

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.analytics.application.authorization import AccessPolicyCatalog, SchemaCatalog
from app.analytics.application.ports import MetricCatalog
from app.analytics.domain import (
    DatasourceDefinition,
    MetricDefinition,
    PrincipalAccessPolicy,
    QueryAuditCompletion,
    QueryAuditRecord,
    QueryAuditStart,
    SchemaSnapshot,
)


class PersistenceConflictError(Exception):
    """写入被版本或唯一性规则拒绝。

    文本是固定 reason（例如 `version_drift` / `stale_expected_version`），不含行内容、
    SQL 或驱动异常文本。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PersistenceDataError(Exception):
    """已存 payload 无法安全解码。

    只携带稳定错误类别；绝不回显 payload，否则损坏的 JSON 会经由异常进入日志。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class DatasourceAdminRepository(Protocol):
    """数据源的管理侧端口：`owner_id` 只决定管理归属，不隐含查询权限。"""

    async def get_owned(self, *, owner_id: str, datasource_id: str) -> DatasourceDefinition | None: ...

    async def list_owned(self, *, owner_id: str) -> tuple[DatasourceDefinition, ...]: ...

    async def save(self, datasource: DatasourceDefinition) -> None: ...


@runtime_checkable
class SchemaSnapshotRepository(SchemaCatalog, Protocol):
    async def replace(self, snapshot: SchemaSnapshot, *, expected_version: str | None) -> None: ...


@runtime_checkable
class AccessPolicyRepository(AccessPolicyCatalog, Protocol):
    async def replace(self, policy: PrincipalAccessPolicy, *, expected_version: str | None) -> None: ...

    async def remove(self, *, datasource_id: str, principal_id: str) -> None: ...


@runtime_checkable
class MetricRepository(MetricCatalog, Protocol):
    async def get_owned(self, *, owner_id: str, metric_key: str) -> MetricDefinition | None: ...

    async def list_owned(self, *, owner_id: str) -> tuple[MetricDefinition, ...]: ...

    async def list_grants(self, *, owner_id: str, metric_key: str) -> tuple[str, ...]: ...

    async def grant(self, *, owner_id: str, metric_key: str, principal_id: str) -> None: ...

    async def revoke_grant(self, *, owner_id: str, metric_key: str, principal_id: str) -> None: ...

    async def save(self, metric: MetricDefinition) -> None: ...

    async def retire(self, *, owner_id: str, metric_key: str) -> None: ...


@runtime_checkable
class QueryAuditReader(Protocol):
    """只读审计端口：按 principal 精确过滤的 `(started_at, id)` keyset 分页。

    没有"全部租户"的读法：跨用户列表只能由调用方对每个 principal 单独查询。
    """

    async def list_for_principal(
        self,
        *,
        principal_id: str,
        limit: int,
        before_started_at: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[QueryAuditRecord, ...]: ...


@runtime_checkable
class QueryAuditLog(QueryAuditReader, Protocol):
    """审计门禁端口：`start` 返回审计 ID，`finish` 只更新一条 `started` 记录。"""

    async def start(self, entry: QueryAuditStart) -> str: ...

    async def finish(self, completion: QueryAuditCompletion) -> None: ...
