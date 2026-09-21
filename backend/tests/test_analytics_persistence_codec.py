"""显式版本化 codec 的往返与损坏拒绝测试（Phase 2C1 任务 2）。

规则：JSON 只承载经过显式字段校验的有界数据。任何未知字段、缺失字段、非法 enum、
naive 时间、非有限 Decimal、重复 relation/column 与超限 payload 都必须 fail closed，
且错误只携带稳定 reason —— 绝不回显 payload，否则损坏内容会经由异常进入日志。
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.analytics.application import PersistenceDataError, StoredExecutionPlan
from app.analytics.application.persistence_ports import PersistenceDataError as _PersistenceDataError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    ColumnSensitivity,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionLimits,
    MetricStatus,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryCostEstimate,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)
from app.analytics.infrastructure.persistence.codec import (
    MAX_PLAN_PAYLOAD_BYTES,
    PLAN_PAYLOAD_VERSION,
    decode_access_policy,
    decode_dimensions,
    decode_schema_snapshot,
    decode_stored_plan,
    encode_access_policy,
    encode_dimensions,
    encode_schema_snapshot,
    encode_stored_plan,
)

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_CST = timezone(timedelta(hours=8))
_PG = DatasourceEngine.POSTGRESQL


def _snapshot(**overrides) -> SchemaSnapshot:
    values = {
        "datasource_id": "ds-1",
        "engine": _PG,
        "version": "s1",
        "default_schema": "public",
        "relations": (
            RelationSchema(
                name="orders",
                schema="public",
                columns=(
                    ColumnSchema(name="id", data_type="integer"),
                    ColumnSchema(name="customer", data_type="text", sensitivity=ColumnSensitivity.PII),
                ),
            ),
            RelationSchema(
                name="订单",
                schema="sales",
                catalog="warehouse",
                columns=(ColumnSchema(name="total", data_type="numeric(12,2)", sensitivity=ColumnSensitivity.SENSITIVE),),
            ),
        ),
    }
    values.update(overrides)
    return SchemaSnapshot(**values)


def _policy(**overrides) -> PrincipalAccessPolicy:
    values = {
        "datasource_id": "ds-1",
        "principal_id": "user-1",
        "version": "p1",
        "relations": (
            RelationAccessRule(
                name="orders",
                schema="public",
                columns=(ColumnAccessRule(name="id", access=ColumnAccess.ALLOW), ColumnAccessRule(name="amount", access=ColumnAccess.AGGREGATE_ONLY)),
            ),
        ),
        "allowed_functions": ("count", "sum"),
    }
    values.update(overrides)
    return PrincipalAccessPolicy(**values)


def _datasource(**overrides) -> DatasourceDefinition:
    values = {
        "id": "ds-1",
        "owner_id": "user-1",
        "name": "Warehouse",
        "engine": _PG,
        "secret_ref": "env://ANALYTICS_DS",
        "default_schema": "public",
        "status": DatasourceStatus.ACTIVE,
    }
    values.update(overrides)
    return DatasourceDefinition(**values)


def _limits(**overrides) -> ExecutionLimits:
    values = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 10_000,
        "cancellation_grace_ms": 500,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 64,
        "max_result_rows": 10,
        "max_result_bytes": 4_194_304,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def _plan(**overrides) -> StoredExecutionPlan:
    values = {
        "token_digest": "a" * 64,
        "principal_id": "user-1",
        "datasource": _datasource(),
        "authorized": AuthorizedQuerySpec(
            prepared=PreparedQuery(
                sql="SELECT id FROM orders LIMIT 10",
                engine=_PG,
                relations=("orders",),
                row_limit=10,
                query_hash="b" * 64,
            ),
            datasource_id="ds-1",
            principal_id="user-1",
            schema_version="s1",
            policy_version="p1",
            relations=("public.orders",),
            columns=("public.orders.id",),
            functions=("count",),
            risk=QueryRisk.LOW,
        ),
        "estimate": QueryCostEstimate(engine=_PG, estimated_rows=10, engine_cost=Decimal("12.50"), plan_digest="c" * 64),
        "limits": _limits(),
        "issued_at": _NOW,
        "expires_at": _NOW + timedelta(seconds=60),
    }
    values.update(overrides)
    return StoredExecutionPlan(**values)


# --- 往返 -------------------------------------------------------------------


def test_schema_snapshot_round_trips_with_exact_tuple_restoration():
    value = _snapshot()

    decoded = decode_schema_snapshot(encode_schema_snapshot(value))

    assert decoded == value
    assert isinstance(decoded.relations, tuple)
    assert all(isinstance(relation.columns, tuple) for relation in decoded.relations)
    assert decoded.engine is _PG
    assert decoded.relations[1].columns[0].sensitivity is ColumnSensitivity.SENSITIVE


def test_access_policy_round_trips_including_nested_access_and_functions():
    value = _policy()

    decoded = decode_access_policy(encode_access_policy(value))

    assert decoded == value
    assert isinstance(decoded.relations, tuple)
    assert isinstance(decoded.relations[0].columns, tuple)
    assert isinstance(decoded.allowed_functions, tuple)
    assert decoded.relations[0].columns[1].access is ColumnAccess.AGGREGATE_ONLY


def test_dimensions_round_trip_preserves_order_and_tuple_type():
    value = ("region", "channel", "day")

    decoded = decode_dimensions(encode_dimensions(value))

    assert decoded == value
    assert isinstance(decoded, tuple)


def test_stored_plan_round_trips_with_every_nested_value():
    value = _plan()

    decoded = decode_stored_plan(encode_stored_plan(value), payload_version=PLAN_PAYLOAD_VERSION)

    assert decoded == value
    assert decoded.datasource == value.datasource
    assert decoded.authorized == value.authorized
    assert decoded.estimate == value.estimate
    assert decoded.limits == value.limits
    assert isinstance(decoded.limits.max_engine_cost, Decimal)
    assert decoded.limits.max_engine_cost == Decimal("10000")
    assert decoded.issued_at == value.issued_at and decoded.expires_at == value.expires_at


def test_mysql_values_round_trip_too():
    value = _snapshot(engine=DatasourceEngine.MYSQL, default_schema="analytics_test")
    plan = _plan(datasource=_datasource(engine=DatasourceEngine.MYSQL))

    assert decode_schema_snapshot(encode_schema_snapshot(value)) == value
    assert decode_stored_plan(encode_stored_plan(plan), payload_version=PLAN_PAYLOAD_VERSION) == plan


# --- 规范化 ----------------------------------------------------------------


def test_encoding_is_deterministic_compact_and_utf8_preserving():
    first = encode_schema_snapshot(_snapshot())
    second = encode_schema_snapshot(_snapshot())

    assert first == second
    # 紧凑分隔符：没有为了可读性插入的空格。
    assert ", " not in first and '": ' not in first
    # ensure_ascii=False：中文标识符按真实字符编码，而不是 \uXXXX。
    assert "订单" in first
    assert "\\u" not in first
    assert json.loads(first)["version"] == "s1"


def test_encoding_uses_sorted_keys():
    payload = encode_access_policy(_policy())

    assert payload.startswith('{"allowed_functions":')


def test_decimals_use_a_canonical_non_exponent_string():
    plan = _plan(estimate=QueryCostEstimate(engine=_PG, estimated_rows=10, engine_cost=Decimal("1E+2"), plan_digest="c" * 64))

    payload = json.loads(encode_stored_plan(plan))

    assert payload["estimate"]["engine_cost"] == "100"
    decoded = decode_stored_plan(encode_stored_plan(plan), payload_version=PLAN_PAYLOAD_VERSION)
    assert decoded.estimate.engine_cost == Decimal("100")


def test_datetimes_are_normalized_to_utc_on_decode():
    plan = _plan(issued_at=datetime(2026, 9, 22, 20, 0, tzinfo=_CST), expires_at=datetime(2026, 9, 22, 20, 1, tzinfo=_CST))
    payload = json.loads(encode_stored_plan(plan))

    decoded = decode_stored_plan(encode_stored_plan(plan), payload_version=PLAN_PAYLOAD_VERSION)

    assert payload["issued_at"].endswith("+00:00")
    assert decoded.issued_at == datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    assert decoded.issued_at.utcoffset() == timedelta(0)


# --- 损坏与越界拒绝 ---------------------------------------------------------


def _snapshot_payload(**mutations) -> str:
    payload = json.loads(encode_schema_snapshot(_snapshot()))
    payload.update(mutations)
    return json.dumps(payload)


def test_an_unknown_plan_payload_version_is_rejected():
    with pytest.raises(PersistenceDataError) as error:
        decode_stored_plan(encode_stored_plan(_plan()), payload_version=PLAN_PAYLOAD_VERSION + 1)

    assert "version" in error.value.reason


@pytest.mark.parametrize("payload", ["not json", "[]", '"text"', "42", "null", ""])
def test_a_snapshot_payload_that_is_not_a_json_object_is_rejected(payload):
    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(payload)


def test_a_missing_key_is_rejected():
    payload = json.loads(encode_schema_snapshot(_snapshot()))
    del payload["version"]

    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(json.dumps(payload))


def test_an_unknown_key_is_rejected():
    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(_snapshot_payload(extra="surprise"))


def test_an_unknown_enum_value_is_rejected():
    payload = json.loads(encode_schema_snapshot(_snapshot()))
    payload["relations"][0]["columns"][0]["sensitivity"] = "top_secret"

    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(json.dumps(payload))


def test_a_duplicate_relation_is_rejected():
    payload = json.loads(encode_schema_snapshot(_snapshot()))
    payload["relations"].append(payload["relations"][0])

    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(json.dumps(payload))


def test_a_duplicate_column_is_rejected():
    payload = json.loads(encode_schema_snapshot(_snapshot()))
    payload["relations"][0]["columns"].append(payload["relations"][0]["columns"][0])

    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot(json.dumps(payload))


def test_a_naive_datetime_is_rejected():
    payload = json.loads(encode_stored_plan(_plan()))
    payload["issued_at"] = "2026-09-22T12:00:00"

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


def test_a_non_iso_datetime_is_rejected():
    payload = json.loads(encode_stored_plan(_plan()))
    payload["issued_at"] = "yesterday"

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e5", "12,5", 12.5, True])
def test_a_non_canonical_decimal_is_rejected(value):
    payload = json.loads(encode_stored_plan(_plan()))
    payload["estimate"]["engine_cost"] = value

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


@pytest.mark.parametrize("value", ["10", 10.5, True, None])
def test_a_non_integer_for_an_integer_field_is_rejected(value):
    payload = json.loads(encode_stored_plan(_plan()))
    payload["estimate"]["estimated_rows"] = value

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


def test_an_unknown_nested_shape_is_rejected():
    payload = json.loads(encode_stored_plan(_plan()))
    payload["authorized"]["prepared"]["relations"] = [{"name": "orders"}]

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


def test_an_untrimmed_string_is_rejected_by_re_constructed_domain_invariants():
    payload = json.loads(encode_stored_plan(_plan()))
    payload["principal_id"] = " user-1"

    with pytest.raises(PersistenceDataError):
        decode_stored_plan(json.dumps(payload), payload_version=PLAN_PAYLOAD_VERSION)


def test_a_payload_larger_than_one_mibibyte_is_rejected_on_encode():
    oversized = _snapshot(relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="x" * (MAX_PLAN_PAYLOAD_BYTES + 1)),)),))

    with pytest.raises(PersistenceDataError) as error:
        encode_schema_snapshot(oversized)

    assert "large" in error.value.reason or "size" in error.value.reason


def test_a_payload_larger_than_one_mibibyte_is_rejected_on_decode():
    with pytest.raises(PersistenceDataError):
        decode_schema_snapshot('{"version":"' + "x" * (MAX_PLAN_PAYLOAD_BYTES + 1) + '"}')


def test_error_messages_never_echo_the_payload():
    corrupt = '{"version":"s1","secret":"postgres://user:pw@host/db"'

    with pytest.raises(PersistenceDataError) as error:
        decode_schema_snapshot(corrupt)

    assert "postgres://" not in str(error.value)
    assert error.value.reason == error.value.reason.strip()
    assert " " not in error.value.reason


def test_persistence_data_error_is_the_application_port_error():
    # infrastructure 抛出的必须是应用端口声明的同一个异常类型，否则上层无法稳定捕获。
    assert PersistenceDataError is _PersistenceDataError


# --- 源码级禁令 -------------------------------------------------------------


def test_codec_source_has_no_pickle_dynamic_import_or_repr_fallback():
    """源码级禁令按 AST 判定，而不是按文本子串。

    文本子串会被 docstring 里"禁止 pickle"这类说明误伤，也会漏掉 `import pickle as p`；
    直接检查 import 名与实际调用名才是精确的。
    """

    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/analytics/infrastructure/persistence/codec.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "pickle" not in imported
    assert "importlib" not in imported
    assert "dataclasses" not in imported

    banned_calls = {"eval", "exec", "__import__", "repr", "asdict"}
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not (called & banned_calls), f"codec must not call {sorted(called & banned_calls)}"


def test_metrics_status_enum_is_still_available_for_codec_consumers():
    assert MetricStatus.ACTIVE.value == "active"
