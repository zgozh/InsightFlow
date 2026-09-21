from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.domain import (
    MAX_QUERY_ROWS,
    DatasourceEngine,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryCostEstimate,
    QueryExecutionDecision,
    QueryExecutionResult,
    QueryPlanDecision,
    QueryPlanReceipt,
    QueryRisk,
)


def _limits(**overrides):
    values = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 10_000,
        "cancellation_grace_ms": 500,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 64,
        "max_result_rows": 1_000,
        "max_result_bytes": 4_194_304,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def _estimate(**overrides):
    values = {
        "engine": DatasourceEngine.POSTGRESQL,
        "estimated_rows": 42,
        "engine_cost": Decimal("12.5"),
        "plan_digest": "a" * 64,
    }
    values.update(overrides)
    return QueryCostEstimate(**values)


def _receipt(**overrides):
    values = {
        "plan_id": "token-value",
        "expires_at": datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
        "estimate": _estimate(),
    }
    values.update(overrides)
    return QueryPlanReceipt(**values)


def _result(**overrides):
    values = {
        "columns": ("id",),
        "rows": ((1,),),
        "row_count": 1,
        "byte_count": 21,
        "truncated": False,
    }
    values.update(overrides)
    return QueryExecutionResult(**values)


def test_execution_limits_accepts_the_documented_bounds():
    limits = _limits(connect_timeout_ms=100, statement_timeout_ms=60_000, cancellation_grace_ms=50, plan_ttl_seconds=5)

    assert limits.connect_timeout_ms == 100
    assert limits.max_result_rows == 1_000


def test_execution_limits_is_frozen_and_slotted():
    limits = _limits()

    assert not hasattr(limits, "__dict__")
    with pytest.raises(FrozenInstanceError):
        limits.statement_timeout_ms = 1  # type: ignore[misc]


def test_execution_limits_reject_boolean_integer():
    with pytest.raises(ValueError):
        _limits(statement_timeout_ms=True)


@pytest.mark.parametrize(
    "field_name",
    [
        "connect_timeout_ms",
        "statement_timeout_ms",
        "cancellation_grace_ms",
        "max_estimated_rows",
        "max_explain_bytes",
        "max_result_columns",
        "max_result_rows",
        "max_result_bytes",
        "plan_ttl_seconds",
    ],
)
@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "1", None])
def test_execution_limits_reject_non_positive_integers(field_name, bad):
    with pytest.raises(ValueError):
        _limits(**{field_name: bad})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("connect_timeout_ms", 99),
        ("connect_timeout_ms", 30_001),
        ("statement_timeout_ms", 99),
        ("statement_timeout_ms", 60_001),
        ("cancellation_grace_ms", 49),
        ("cancellation_grace_ms", 5_001),
        ("max_result_columns", 257),
        ("max_result_bytes", 16 * 1024 * 1024 + 1),
        ("max_explain_bytes", 4 * 1024 * 1024 + 1),
        ("plan_ttl_seconds", 4),
        ("plan_ttl_seconds", 301),
        ("max_result_rows", MAX_QUERY_ROWS + 1),
    ],
)
def test_execution_limits_enforce_their_hard_ranges(field_name, value):
    with pytest.raises(ValueError):
        _limits(**{field_name: value})


@pytest.mark.parametrize("cost", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.5, "1", None])
def test_execution_limits_require_a_finite_positive_decimal_cost(cost):
    with pytest.raises(ValueError):
        _limits(max_engine_cost=cost)


def test_execution_limits_accept_a_non_negative_result_row_budget():
    assert _limits(max_result_rows=MAX_QUERY_ROWS).max_result_rows == MAX_QUERY_ROWS
    assert _limits(max_result_rows=1).max_result_rows == 1


def test_cost_estimate_is_frozen_and_slotted():
    estimate = _estimate()

    assert not hasattr(estimate, "__dict__")
    with pytest.raises(FrozenInstanceError):
        estimate.estimated_rows = 1  # type: ignore[misc]


@pytest.mark.parametrize("engine", ["postgres", "POSTGRESQL", None, 1])
def test_cost_estimate_rejects_non_enum_engine(engine):
    with pytest.raises(ValueError):
        _estimate(engine=engine)


@pytest.mark.parametrize("rows", [-1, True, 1.5, "1", None])
def test_cost_estimate_rejects_invalid_row_counts(rows):
    with pytest.raises(ValueError):
        _estimate(estimated_rows=rows)


def test_cost_estimate_accepts_zero_rows_and_zero_cost():
    estimate = _estimate(estimated_rows=0, engine_cost=Decimal("0"))

    assert estimate.estimated_rows == 0


@pytest.mark.parametrize("cost", [Decimal("-1"), Decimal("NaN"), Decimal("-Infinity"), 1.5, "1", None])
def test_cost_estimate_rejects_invalid_costs(cost):
    with pytest.raises(ValueError):
        _estimate(engine_cost=cost)


@pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "A" * 64, "z" * 64, None])
def test_cost_estimate_rejects_invalid_digests(digest):
    with pytest.raises(ValueError):
        _estimate(plan_digest=digest)


def test_cost_estimate_has_no_raw_plan_field():
    assert {field.name for field in fields(QueryCostEstimate)} == {"engine", "estimated_rows", "engine_cost", "plan_digest"}


def test_plan_receipt_has_no_sql_or_secret():
    names = {field.name for field in fields(QueryPlanReceipt)}
    assert names == {"plan_id", "expires_at", "estimate"}


def test_plan_receipt_is_frozen():
    receipt = _receipt()

    with pytest.raises(FrozenInstanceError):
        receipt.plan_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("plan_id", ["", "   ", " token ", None, 1])
def test_plan_receipt_requires_a_trimmed_plan_id(plan_id):
    with pytest.raises(ValueError):
        _receipt(plan_id=plan_id)


@pytest.mark.parametrize("expires_at", [datetime(2026, 9, 21, 12, 0), "2026-09-21T12:00:00Z", None, 1])
def test_plan_receipt_requires_a_timezone_aware_expiry(expires_at):
    with pytest.raises(ValueError):
        _receipt(expires_at=expires_at)


def test_plan_receipt_requires_a_cost_estimate():
    with pytest.raises(ValueError):
        _receipt(estimate={"estimated_rows": 1})


def test_result_preserves_duplicate_columns():
    result = QueryExecutionResult(
        columns=("id", "id"),
        rows=((1, 2),),
        row_count=1,
        byte_count=17,
        truncated=False,
    )
    assert result.columns == ("id", "id")


def test_result_is_frozen_and_slotted():
    result = _result()

    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.truncated = True  # type: ignore[misc]


@pytest.mark.parametrize("columns", [["id"], ("",), (" id ",), (1,), None])
def test_result_rejects_invalid_columns(columns):
    with pytest.raises(ValueError):
        _result(columns=columns, rows=(), row_count=0)


def test_result_rejects_row_width_mismatch():
    with pytest.raises(ValueError):
        _result(columns=("a", "b"), rows=((1,),), row_count=1)


def test_result_rejects_row_count_mismatch():
    with pytest.raises(ValueError):
        _result(columns=("a",), rows=((1,), (2,)), row_count=1)


@pytest.mark.parametrize("rows", [["x"], ((1,), "x"), None])
def test_result_requires_tuple_rows(rows):
    with pytest.raises(ValueError):
        _result(rows=rows, row_count=len(rows) if isinstance(rows, (tuple, list)) else 0)


def test_result_accepts_only_json_scalars():
    result = _result(
        columns=("a", "b", "c", "d", "e"),
        rows=((None, True, 3, 1.5, "text"),),
        row_count=1,
        byte_count=64,
    )

    assert result.rows == ((None, True, 3, 1.5, "text"),)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), Decimal("1.5"), b"bytes", bytearray(b"x"), datetime(2026, 9, 21), {"a": 1}])
def test_result_rejects_non_json_scalar_cells(value):
    with pytest.raises(ValueError):
        _result(columns=("a",), rows=((value,),), row_count=1)


@pytest.mark.parametrize("byte_count", [-1, True, 1.5, "1", None])
def test_result_rejects_invalid_byte_counts(byte_count):
    with pytest.raises(ValueError):
        _result(byte_count=byte_count)


@pytest.mark.parametrize("truncated", [0, 1, "yes", None])
def test_result_requires_a_boolean_truncated_flag(truncated):
    with pytest.raises(ValueError):
        _result(truncated=truncated)


def test_execution_decision_code_values_are_stable_storage_contracts():
    assert ExecutionDecisionCode.PLAN_CREATED.value == "plan_created"
    assert ExecutionDecisionCode.PLAN_UNAVAILABLE.value == "plan_unavailable"
    assert ExecutionDecisionCode.PLAN_STORE_UNAVAILABLE.value == "plan_store_unavailable"
    assert ExecutionDecisionCode.AUTHORIZATION_STALE.value == "authorization_stale"
    assert ExecutionDecisionCode.DATASOURCE_UNAVAILABLE.value == "datasource_unavailable"
    assert ExecutionDecisionCode.SECRET_UNAVAILABLE.value == "secret_unavailable"
    assert ExecutionDecisionCode.EXPLAIN_REJECTED.value == "explain_rejected"
    assert ExecutionDecisionCode.COST_LIMIT_EXCEEDED.value == "cost_limit_exceeded"
    assert ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE.value == "unsupported_identifier_mode"
    assert ExecutionDecisionCode.EXECUTION_TIMEOUT.value == "execution_timeout"
    assert ExecutionDecisionCode.RESULT_LIMIT_REACHED.value == "result_limit_reached"
    assert ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE.value == "unsupported_result_type"
    assert ExecutionDecisionCode.DATABASE_UNAVAILABLE.value == "database_unavailable"
    assert ExecutionDecisionCode.EXECUTED.value == "executed"


def test_plan_decision_requires_a_receipt_only_when_created():
    created = QueryPlanDecision(code=ExecutionDecisionCode.PLAN_CREATED, receipt=_receipt())

    assert created.receipt is not None
    with pytest.raises(ValueError):
        QueryPlanDecision(code=ExecutionDecisionCode.PLAN_CREATED)
    with pytest.raises(ValueError):
        QueryPlanDecision(code=ExecutionDecisionCode.PLAN_UNAVAILABLE, receipt=_receipt())


def test_plan_decision_rejects_non_enum_codes():
    with pytest.raises(ValueError):
        QueryPlanDecision(code="plan_created", receipt=_receipt())


def test_plan_decision_is_frozen():
    decision = QueryPlanDecision(code=ExecutionDecisionCode.PLAN_UNAVAILABLE)

    with pytest.raises(FrozenInstanceError):
        decision.receipt = _receipt()  # type: ignore[misc]


def test_execution_decision_carries_a_result_for_executed_and_truncated_outcomes():
    executed = QueryExecutionDecision(code=ExecutionDecisionCode.EXECUTED, result=_result())
    truncated = QueryExecutionDecision(code=ExecutionDecisionCode.RESULT_LIMIT_REACHED, result=_result(truncated=True))

    assert executed.result is not None
    assert truncated.result is not None


def test_execution_decision_forbids_a_result_for_failures():
    with pytest.raises(ValueError):
        QueryExecutionDecision(code=ExecutionDecisionCode.EXECUTION_TIMEOUT, result=_result())
    with pytest.raises(ValueError):
        QueryExecutionDecision(code=ExecutionDecisionCode.EXECUTED)


def test_execution_decision_rejects_a_plan_created_code():
    with pytest.raises(ValueError):
        QueryExecutionDecision(code=ExecutionDecisionCode.PLAN_CREATED, result=_result())


def test_execution_values_carry_no_timing_or_row_risk_dependency():
    # 执行决策不重新定义风险等级：HIGH 永远不可执行由 2B1 与 plan 流程保证。
    assert QueryRisk.HIGH.value == "high"
    assert _receipt().expires_at - datetime(2026, 9, 21, 11, 59, tzinfo=UTC) == timedelta(minutes=1)
