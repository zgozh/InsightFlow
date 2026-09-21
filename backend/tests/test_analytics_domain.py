from dataclasses import FrozenInstanceError

import pytest

from app.analytics.domain import (
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    MetricStatus,
)


def test_datasource_definition_is_immutable_and_contains_only_secret_reference():
    datasource = DatasourceDefinition(
        id="sales-primary",
        owner_id="user-1",
        name="Sales warehouse",
        engine=DatasourceEngine.POSTGRESQL,
        secret_ref="env:SALES_DATABASE_SECRET",
        default_schema="analytics",
    )

    assert datasource.status is DatasourceStatus.ACTIVE
    assert datasource.secret_ref == "env:SALES_DATABASE_SECRET"
    assert not hasattr(datasource, "password")
    assert not hasattr(datasource, "dsn")
    with pytest.raises(FrozenInstanceError):
        datasource.name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize("field", ["id", "owner_id", "name", "secret_ref"])
def test_datasource_definition_rejects_blank_required_values(field: str):
    values = {
        "id": "sales-primary",
        "owner_id": "user-1",
        "name": "Sales warehouse",
        "engine": DatasourceEngine.MYSQL,
        "secret_ref": "env:SALES_DATABASE_SECRET",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        DatasourceDefinition(**values)


def test_datasource_definition_rejects_untrimmed_schema():
    with pytest.raises(ValueError, match="default_schema"):
        DatasourceDefinition(
            id="sales-primary",
            owner_id="user-1",
            name="Sales warehouse",
            engine=DatasourceEngine.MYSQL,
            secret_ref="env:SALES_DATABASE_SECRET",
            default_schema=" analytics ",
        )


def test_datasource_engine_values_are_stable_storage_contracts():
    assert DatasourceEngine.MYSQL.value == "mysql"
    assert DatasourceEngine.POSTGRESQL.value == "postgresql"


def test_metric_definition_is_immutable_and_keeps_tuple_dimensions():
    metric = MetricDefinition(
        key="gross_revenue",
        owner_id="user-1",
        name="Gross revenue",
        description="Booked revenue before deductions",
        expression="sum(order_amount)",
        dimensions=("region", "channel"),
        version=2,
        status=MetricStatus.ACTIVE,
    )

    assert metric.dimensions == ("region", "channel")
    with pytest.raises(FrozenInstanceError):
        metric.version = 3  # type: ignore[misc]


@pytest.mark.parametrize("key", ["", " GrossRevenue", "gross-revenue", "1st_metric"])
def test_metric_definition_rejects_invalid_machine_key(key: str):
    with pytest.raises(ValueError, match="key"):
        MetricDefinition(
            key=key,
            owner_id="user-1",
            name="Gross revenue",
            description="Booked revenue before deductions",
            expression="sum(order_amount)",
        )


def test_metric_definition_rejects_duplicate_or_blank_dimensions():
    base = {
        "key": "gross_revenue",
        "owner_id": "user-1",
        "name": "Gross revenue",
        "description": "Booked revenue before deductions",
        "expression": "sum(order_amount)",
    }

    with pytest.raises(ValueError, match="dimensions"):
        MetricDefinition(**base, dimensions=("region", "region"))
    with pytest.raises(ValueError, match="dimensions"):
        MetricDefinition(**base, dimensions=("region", " "))


def test_metric_definition_rejects_non_positive_version():
    with pytest.raises(ValueError, match="version"):
        MetricDefinition(
            key="gross_revenue",
            owner_id="user-1",
            name="Gross revenue",
            description="Booked revenue before deductions",
            expression="sum(order_amount)",
            version=0,
        )
