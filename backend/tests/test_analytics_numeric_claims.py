from dataclasses import replace
from decimal import ROUND_DOWN, Decimal, getcontext, setcontext

import pytest

import app.analytics.domain.claims as claims_module
from app.analytics.domain import (
    EvidenceCellReference,
    NumericClaim,
    NumericClaimError,
    NumericClaimOperation,
    NumericClaimPlan,
    calculate_numeric_claim_plans,
    verify_numeric_claims,
)
from app.analytics.domain.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json
from app.analytics.domain.execution import ExecutionDecisionCode, QueryExecutionResult
from app.analytics.domain.query import QueryRisk


def _snapshot(
    columns: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
    *,
    truncated: bool = False,
) -> AnalyticsQueryToolResult:
    code = ExecutionDecisionCode.RESULT_LIMIT_REACHED.value if truncated else ExecutionDecisionCode.EXECUTED.value
    byte_count = len(canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8"))
    result = QueryExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        byte_count=byte_count,
        truncated=truncated,
    )
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="datasource",
        query_hash="a" * 64,
        risk=QueryRisk.LOW,
        schema_version="schema-1",
        policy_version="policy-1",
        plan_digest="b" * 64,
        estimated_rows=len(rows),
        engine_cost=Decimal(0),
        result=result,
        decision_code=code,
    )
    return AnalyticsQueryToolResult(code=code, columns=columns, rows=rows, truncated=truncated, evidence=evidence)


def _ref(snapshot: AnalyticsQueryToolResult, column: str, row: int = 0) -> EvidenceCellReference:
    assert snapshot.evidence is not None
    return EvidenceCellReference(snapshot.evidence.evidence_id, row, column)


def _claim(
    claim_id: str,
    operation: NumericClaimOperation,
    operands: tuple[EvidenceCellReference, ...],
    value: str,
    places: int = 2,
    *,
    unit: EvidenceCellReference | None = None,
    period: EvidenceCellReference | None = None,
) -> NumericClaim:
    return NumericClaim(claim_id, operation, operands, value, places, unit, period)


def _plan(
    plan_id: str,
    operation: NumericClaimOperation,
    operands: tuple[EvidenceCellReference, ...],
    places: int = 2,
    *,
    unit: EvidenceCellReference | None = None,
    period: EvidenceCellReference | None = None,
) -> NumericClaimPlan:
    return NumericClaimPlan(plan_id, operation, operands, places, unit, period)


def _expect_claim_error(reason: str, claims: tuple[NumericClaim, ...], snapshots: tuple[AnalyticsQueryToolResult, ...]) -> None:
    with pytest.raises(NumericClaimError) as error:
        verify_numeric_claims(claims, snapshots)
    assert error.value.reason == reason
    assert str(error.value) == reason


def _expect_plan_error(reason: str, plans: tuple[NumericClaimPlan, ...], snapshots: tuple[AnalyticsQueryToolResult, ...]) -> None:
    with pytest.raises(NumericClaimError) as error:
        calculate_numeric_claim_plans(plans, snapshots)
    assert error.value.reason == reason
    assert str(error.value) == reason


def test_server_calculates_march_cell_and_sum_from_the_same_exact_snapshot():
    snapshot = _snapshot(
        ("period", "amount", "currency"),
        (("2026-03", "1200.75", "CNY"), ("2026-03", "2700.50", "CNY")),
    )
    plans = (
        _plan(
            "march-first-cell",
            NumericClaimOperation.CELL,
            (_ref(snapshot, "amount", 0),),
            2,
            unit=_ref(snapshot, "currency", 0),
            period=_ref(snapshot, "period", 0),
        ),
        _plan("march-total", NumericClaimOperation.SUM, (_ref(snapshot, "amount", 0), _ref(snapshot, "amount", 1)), 2),
    )

    verified = calculate_numeric_claim_plans(plans, (snapshot,))

    assert tuple(claim.calculated_value for claim in verified) == ("1200.75", "3901.25")
    assert (verified[0].unit, verified[0].period) == ("CNY", "2026-03")
    assert verified[0].source_references == plans[0].operands
    assert not hasattr(plans[0], "value")
    with pytest.raises(NumericClaimError) as asserted_claim_rejected:
        verify_numeric_claims((plans[0],), (snapshot,))  # type: ignore[arg-type]
    assert asserted_claim_rejected.value.reason == "numeric_claims_invalid"


def test_server_calculation_keeps_half_up_rounding_and_rejects_bad_plan_references():
    snapshot = _snapshot(("amount", "unit"), ((1.005, "CNY"), (2.678, "CNY")))
    rounded = calculate_numeric_claim_plans(
        (_plan("sum", NumericClaimOperation.SUM, (_ref(snapshot, "amount", 0), _ref(snapshot, "amount", 1))),),
        (snapshot,),
    )[0]
    assert rounded.calculated_value == "3.68"
    assert rounded.rounded is True

    missing = EvidenceCellReference("f" * 64, 0, "amount")
    _expect_plan_error("numeric_claim_reference_unavailable", (_plan("missing", NumericClaimOperation.CELL, (missing,)),), (snapshot,))
    _expect_plan_error(
        "numeric_claim_reference_unavailable",
        (_plan("wrong-unit", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), unit=_ref(snapshot, "amount")),),
        (snapshot,),
    )
    duplicate = _plan("duplicate", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),))
    _expect_plan_error("numeric_claims_invalid", (duplicate, duplicate), (snapshot,))
    zero_snapshot = _snapshot(("numerator", "denominator"), ((1, 0),))
    _expect_plan_error(
        "numeric_claim_computation_invalid",
        (_plan("zero-divisor", NumericClaimOperation.RATIO, (_ref(zero_snapshot, "numerator"), _ref(zero_snapshot, "denominator"))),),
        (zero_snapshot,),
    )


@pytest.mark.parametrize("source", (True, None, "NaN", "Infinity", "1e3", 10**101, 1e101, 1e-101, "1" * 257))
def test_server_calculation_rejects_nonfinite_and_oversized_source_values(source: object):
    snapshot = _snapshot(("amount",), ((source,),))
    plan = _plan("bounded", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),))

    _expect_plan_error("numeric_claim_value_invalid", (plan,), (snapshot,))


def test_all_fixed_operations_resolve_exact_cells_and_round_deterministically():
    first = _snapshot(("a", "b", "currency", "year"), ((4.5, 2, "USD", 2025),))
    second = _snapshot(("c",), ((6,),))
    a, b, c = _ref(first, "a"), _ref(first, "b"), _ref(second, "c")

    claims = (
        _claim("cell", NumericClaimOperation.CELL, (a,), "4.50"),
        _claim("sum", NumericClaimOperation.SUM, (a, b, c), "12.5", 1),
        _claim("difference", NumericClaimOperation.DIFFERENCE, (a, b), "2.50"),
        _claim("ratio", NumericClaimOperation.RATIO, (a, b), "2.25"),
        _claim("percentage", NumericClaimOperation.PERCENTAGE, (a, b), "225.00"),
        _claim("mean", NumericClaimOperation.MEAN, (a, b, c), "4.17"),
        _claim("change", NumericClaimOperation.CHANGE_PERCENTAGE, (a, b), "125.00"),
    )

    verified = verify_numeric_claims(claims, (first, second))

    assert tuple(item.calculated_value for item in verified) == ("4.50", "12.5", "2.50", "2.25", "225.00", "4.17", "125.00")
    assert tuple(item.id for item in verified) == tuple(claim.id for claim in claims)
    assert verified[0].source_references == (a,)
    assert all(item.unit is None and item.period is None for item in verified)


@pytest.mark.parametrize(
    ("source", "expected", "rounded"),
    (("-1.235", "-1.24", True), ("0.005", "0.01", True), (0, "0.00", False), (-2, "-2.00", False)),
)
def test_cell_claims_cover_zero_negative_values_and_half_up_boundaries(source: object, expected: str, rounded: bool):
    snapshot = _snapshot(("amount",), ((source,),))
    verified = verify_numeric_claims((_claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), expected),), (snapshot,))[0]

    assert verified.calculated_value == expected
    assert verified.rounded is rounded


def test_text_numeric_cells_and_source_bound_unit_period_labels_are_supported():
    snapshot = _snapshot(("amount", "currency", "year"), (("12.50", "CNY", 2024),))
    claim = _claim(
        "revenue",
        NumericClaimOperation.CELL,
        (_ref(snapshot, "amount"),),
        "12.50",
        unit=_ref(snapshot, "currency"),
        period=_ref(snapshot, "year"),
    )

    verified = verify_numeric_claims((claim,), (snapshot,))[0]

    assert (verified.unit, verified.period) == ("CNY", "2024")
    assert verified.unit_reference == claim.unit_reference
    assert verified.period_reference == claim.period_reference


def test_column_labels_are_literal_exact_keys_even_when_they_contain_spaces_or_sql_punctuation():
    snapshot = _snapshot(("total revenue", "SUM(amount)"), ((10, 3),))
    claims = (
        _claim("revenue", NumericClaimOperation.CELL, (_ref(snapshot, "total revenue"),), "10"),
        _claim("aggregate-label", NumericClaimOperation.CELL, (_ref(snapshot, "SUM(amount)"),), "3"),
    )

    verified = verify_numeric_claims(claims, (snapshot,))

    assert tuple(item.calculated_value for item in verified) == ("10.00", "3.00")


def test_missing_unit_and_period_sources_are_not_guessed_and_truncation_is_preserved():
    snapshot = _snapshot(("amount",), ((7,),), truncated=True)
    verified = verify_numeric_claims((_claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "7.00"),), (snapshot,))[0]

    assert verified.unit is None
    assert verified.period is None
    assert verified.references_truncated_snapshot is True


@pytest.mark.parametrize("operation", (NumericClaimOperation.RATIO, NumericClaimOperation.CHANGE_PERCENTAGE))
def test_zero_denominator_rejects_the_whole_claim_batch(operation: NumericClaimOperation):
    snapshot = _snapshot(("numerator", "denominator"), ((1, 0),))
    claim = _claim("zero-divisor", operation, (_ref(snapshot, "numerator"), _ref(snapshot, "denominator")), "0")

    _expect_claim_error("numeric_claim_computation_invalid", (claim,), (snapshot,))


def test_asserted_value_must_equal_the_server_rounded_result_exactly():
    snapshot = _snapshot(("amount",), ((1.234,),))
    claim = _claim("wrong-amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1.24")

    _expect_claim_error("numeric_claim_value_mismatch", (claim,), (snapshot,))


def test_references_must_match_one_exact_evidence_row_and_column():
    snapshot = _snapshot(("amount", "other"), ((5, 5),))
    wrong_column = EvidenceCellReference(snapshot.evidence.evidence_id, 0, "missing")  # type: ignore[union-attr]
    wrong_row = EvidenceCellReference(snapshot.evidence.evidence_id, 1, "amount")  # type: ignore[union-attr]

    for reference in (wrong_column, wrong_row):
        claim = _claim("wrong-reference", NumericClaimOperation.CELL, (reference,), "5")
        _expect_claim_error("numeric_claim_reference_unavailable", (claim,), (snapshot,))


def test_matching_a_number_elsewhere_does_not_satisfy_a_wrong_column_reference():
    snapshot = _snapshot(("actual",), ((5,),))
    reference = EvidenceCellReference(snapshot.evidence.evidence_id, 0, "expected")  # type: ignore[union-attr]
    claim = _claim("wrong-column", NumericClaimOperation.CELL, (reference,), "5")

    _expect_claim_error("numeric_claim_reference_unavailable", (claim,), (snapshot,))


def test_duplicate_columns_are_ambiguous_only_when_referenced():
    snapshot = _snapshot(("amount", "amount"), ((5, 5),))
    claim = _claim("ambiguous-column", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "5")

    _expect_claim_error("numeric_claim_reference_unavailable", (claim,), (snapshot,))


def test_duplicate_evidence_and_claim_ids_are_rejected_as_whole_batches():
    snapshot = _snapshot(("amount",), ((5,),))
    claim = _claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "5")

    _expect_claim_error("numeric_claim_snapshot_unavailable", (claim,), (snapshot, snapshot))
    _expect_claim_error("numeric_claims_invalid", (claim, claim), (snapshot,))


@pytest.mark.parametrize("source", (True, None, "NaN", "Infinity", "1e3", "01.2", " 1.2"))
def test_boolean_null_nonfinite_and_noncanonical_numeric_cells_are_rejected(source: object):
    snapshot = _snapshot(("amount",), ((source,),))
    claim = _claim("bad-number", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1")

    _expect_claim_error("numeric_claim_value_invalid", (claim,), (snapshot,))


@pytest.mark.parametrize("source", (10**101, 1e101, 1e-101, "1" * 257))
def test_excessively_large_numeric_cells_are_rejected_without_unbounded_arithmetic(source: object):
    snapshot = _snapshot(("amount",), ((source,),))
    claim = _claim("large-number", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1")

    _expect_claim_error("numeric_claim_value_invalid", (claim,), (snapshot,))


def test_invalid_digest_and_failed_snapshots_are_rejected_before_reference_resolution():
    snapshot = _snapshot(("amount",), ((5,),))
    assert snapshot.evidence is not None
    broken = replace(snapshot, evidence=replace(snapshot.evidence, result_digest="0" * 64))
    claim = _claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "5")
    failed = AnalyticsQueryToolResult(code="query_failed")

    _expect_claim_error("numeric_claim_snapshot_unavailable", (claim,), (broken,))
    _expect_claim_error("numeric_claim_snapshot_unavailable", (claim,), (failed,))
    nonfinite = replace(snapshot, rows=((float("inf"),),))
    _expect_claim_error("numeric_claim_snapshot_unavailable", (claim,), (nonfinite,))


def test_aggregate_snapshot_byte_budget_is_enforced(monkeypatch: pytest.MonkeyPatch):
    first = _snapshot(("amount",), ((1,),))
    second = _snapshot(("amount",), ((2,),))
    monkeypatch.setattr(claims_module, "MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES", 1)
    claim = _claim("sum", NumericClaimOperation.SUM, (_ref(first, "amount"), _ref(second, "amount")), "3")

    _expect_claim_error("numeric_claim_snapshot_unavailable", (claim,), (first, second))


def test_claim_and_snapshot_count_limits_are_enforced_before_processing():
    snapshot = _snapshot(("amount",), ((1,),))
    claim = _claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1")

    _expect_claim_error("numeric_claims_invalid", (claim,) * 51, (snapshot,))
    _expect_claim_error("numeric_claims_invalid", (claim,), (snapshot,) * 21)


def test_claim_constructors_reject_unbounded_or_controlled_reference_input():
    with pytest.raises(ValueError):
        EvidenceCellReference("A" * 64, 0, "amount")
    with pytest.raises(ValueError):
        EvidenceCellReference("a" * 64, True, "amount")
    with pytest.raises(ValueError):
        EvidenceCellReference("a" * 64, 0, "amount\n")
    with pytest.raises(ValueError):
        EvidenceCellReference("a" * 64, 0, "x" * 257)
    with pytest.raises(ValueError):
        _claim("bad-id", NumericClaimOperation.CELL, (EvidenceCellReference("a" * 64, 0, "amount"),), "1e2")
    with pytest.raises(ValueError):
        NumericClaim("bad-places", NumericClaimOperation.CELL, (EvidenceCellReference("a" * 64, 0, "amount"),), "1", True)
    with pytest.raises(ValueError):
        NumericClaimPlan("bad-operation", "median", (EvidenceCellReference("a" * 64, 0, "amount"),), 2)  # type: ignore[arg-type]


def test_control_characters_in_source_labels_are_rejected():
    snapshot = _snapshot(("amount", "unit"), ((1, "USD\n"),))
    claim = _claim(
        "label",
        NumericClaimOperation.CELL,
        (_ref(snapshot, "amount"),),
        "1",
        unit=_ref(snapshot, "unit"),
    )

    _expect_claim_error("numeric_claim_reference_unavailable", (claim,), (snapshot,))


def test_verification_does_not_modify_the_process_decimal_context():
    context = getcontext()
    original = context.copy()
    context.prec = 7
    context.rounding = ROUND_DOWN
    snapshot = _snapshot(("amount",), ((1.235,),))
    expected = (context.prec, context.rounding, context.Emax, context.Emin, dict(context.traps), dict(context.flags))
    try:
        verify_numeric_claims((_claim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1.24"),), (snapshot,))
        planned = calculate_numeric_claim_plans((_plan("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),)),), (snapshot,))
        assert planned[0].calculated_value == "1.24"
        assert (context.prec, context.rounding, context.Emax, context.Emin, dict(context.traps), dict(context.flags)) == expected
    finally:
        setcontext(original)
