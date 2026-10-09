from __future__ import annotations

import pytest

from app.analytics.application.metric_service import MetricService, MetricServiceError
from app.analytics.domain.metric import MetricDefinition, MetricStatus


def _metric(key: str, *, status: MetricStatus = MetricStatus.ACTIVE) -> MetricDefinition:
    return MetricDefinition(
        key=key,
        owner_id="owner-secret",
        name=f"Metric {key}",
        description="Registered business definition",
        expression="sum(amount)",
        version=2,
        status=status,
    )


class _Catalog:
    def __init__(self, result):
        self.result = result
        self.principals: list[str] = []

    async def list_accessible(self, *, principal_id):
        self.principals.append(principal_id)
        return self.result


@pytest.mark.asyncio
async def test_metric_service_returns_a_sorted_immutable_authorized_snapshot_once():
    catalog = _Catalog((_metric("z_revenue"), _metric("a_cost")))

    snapshot = await MetricService(catalog).list_active_for_principal(principal_id="user-1")

    assert type(snapshot) is tuple
    assert tuple(metric.key for metric in snapshot) == ("a_cost", "z_revenue")
    assert catalog.principals == ["user-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        [_metric("revenue")],
        (_metric("revenue"), _metric("revenue")),
        (_metric("draft", status=MetricStatus.DRAFT),),
        (_metric("retired", status=MetricStatus.RETIRED),),
        tuple(_metric(f"metric_{index}") for index in range(51)),
        (object(),),
    ],
)
async def test_metric_service_rejects_invalid_or_ambiguous_catalog_snapshots(result):
    service = MetricService(_Catalog(result))

    with pytest.raises(MetricServiceError, match="^metric_catalog_unavailable$"):
        await service.list_active_for_principal(principal_id="user-1")


@pytest.mark.asyncio
async def test_metric_service_does_not_turn_catalog_failure_text_into_a_public_error():
    class FailingCatalog:
        async def list_accessible(self, *, principal_id):
            raise RuntimeError("dsn=postgres://owner:secret@db")

    with pytest.raises(MetricServiceError, match="^metric_catalog_unavailable$"):
        await MetricService(FailingCatalog()).list_active_for_principal(principal_id="user-1")
