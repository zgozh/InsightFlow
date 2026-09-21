from typing import Protocol, runtime_checkable

from app.analytics.domain import DatasourceDefinition, MetricDefinition


@runtime_checkable
class DatasourceCatalog(Protocol):
    async def list_accessible(self, *, principal_id: str) -> tuple[DatasourceDefinition, ...]: ...

    async def get_accessible(self, *, principal_id: str, datasource_id: str) -> DatasourceDefinition | None: ...


@runtime_checkable
class MetricCatalog(Protocol):
    async def list_accessible(self, *, principal_id: str) -> tuple[MetricDefinition, ...]: ...

    async def get_accessible(self, *, principal_id: str, metric_key: str) -> MetricDefinition | None: ...
