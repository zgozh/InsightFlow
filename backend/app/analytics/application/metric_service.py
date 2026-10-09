"""按当前 principal 读取并校验只读的 active 指标目录快照。"""

from __future__ import annotations

from app.analytics.application.ports import MetricCatalog
from app.analytics.domain.metric import MetricDefinition, MetricStatus

MAX_ACTIVE_METRICS = 50


class MetricServiceError(RuntimeError):
    """指标目录无法作为可信快照使用时的稳定应用错误。"""

    def __init__(self) -> None:
        super().__init__("metric_catalog_unavailable")


class MetricService:
    """复用既有授权目录，不缓存 principal 的权限结果。"""

    __slots__ = ("_catalog",)

    def __init__(self, catalog: MetricCatalog) -> None:
        self._catalog = catalog

    async def list_active_for_principal(self, *, principal_id: str) -> tuple[MetricDefinition, ...]:
        if type(principal_id) is not str or not principal_id or principal_id != principal_id.strip() or principal_id == "default":
            raise MetricServiceError
        try:
            metrics = await self._catalog.list_accessible(principal_id=principal_id)
        except Exception:
            raise MetricServiceError from None
        if type(metrics) is not tuple or len(metrics) > MAX_ACTIVE_METRICS:
            raise MetricServiceError

        seen_keys: set[str] = set()
        for metric in metrics:
            if type(metric) is not MetricDefinition or metric.status is not MetricStatus.ACTIVE or metric.key in seen_keys:
                raise MetricServiceError
            seen_keys.add(metric.key)
        return tuple(sorted(metrics, key=lambda metric: metric.key))
