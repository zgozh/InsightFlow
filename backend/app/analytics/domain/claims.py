"""受证据单元格约束的数字引用与固定十进制算式。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, DecimalException, localcontext
from enum import StrEnum

from app.analytics.domain.evidence import (
    MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES,
    AnalyticsQueryEvidence,
    AnalyticsQueryToolResult,
    validate_successful_query_result,
)

MAX_NUMERIC_CLAIMS = 50
MAX_NUMERIC_CLAIM_SNAPSHOTS = 20
MAX_NUMERIC_CLAIM_ID_CHARACTERS = 64
MAX_NUMERIC_CLAIM_COLUMN_CHARACTERS = 256
MAX_NUMERIC_CLAIM_LABEL_CHARACTERS = 128
MAX_NUMERIC_CLAIM_DECIMAL_CHARACTERS = 256
MAX_NUMERIC_CLAIM_DECIMAL_DIGITS = 100
MAX_NUMERIC_CLAIM_DECIMAL_EXPONENT = 100

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CLAIM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_ARITHMETIC_PRECISION = 512
_MAX_RESULT_ADJUSTED_EXPONENT = 202
_ERROR_REASONS = frozenset(
    {
        "numeric_claims_invalid",
        "numeric_claim_snapshot_unavailable",
        "numeric_claim_reference_unavailable",
        "numeric_claim_value_invalid",
        "numeric_claim_value_mismatch",
        "numeric_claim_computation_invalid",
    }
)


class NumericClaimError(RuntimeError):
    """数字引用整体无法验证；reason 稳定且不携带查询或单元格内容。"""

    def __init__(self, reason: str) -> None:
        stable_reason = reason if isinstance(reason, str) and reason in _ERROR_REASONS else "numeric_claims_invalid"
        super().__init__(stable_reason)
        self.reason = stable_reason


class NumericClaimOperation(StrEnum):
    CELL = "cell"
    SUM = "sum"
    DIFFERENCE = "difference"
    RATIO = "ratio"
    PERCENTAGE = "percentage"
    MEAN = "mean"
    CHANGE_PERCENTAGE = "change_percentage"


@dataclass(frozen=True, slots=True)
class EvidenceCellReference:
    evidence_id: str
    row_index: int
    column_name: str

    def __post_init__(self) -> None:
        _validate_reference(self)


@dataclass(frozen=True, slots=True)
class NumericClaim:
    id: str
    operation: NumericClaimOperation
    operands: tuple[EvidenceCellReference, ...]
    value: str
    decimal_places: int
    unit_reference: EvidenceCellReference | None = None
    period_reference: EvidenceCellReference | None = None

    def __post_init__(self) -> None:
        _validate_claim(self)


@dataclass(frozen=True, slots=True)
class NumericClaimPlan:
    id: str
    operation: NumericClaimOperation
    operands: tuple[EvidenceCellReference, ...]
    decimal_places: int
    unit_reference: EvidenceCellReference | None = None
    period_reference: EvidenceCellReference | None = None

    def __post_init__(self) -> None:
        _validate_claim_plan(self)


@dataclass(frozen=True, slots=True)
class VerifiedNumericClaim:
    id: str
    operation: NumericClaimOperation
    source_references: tuple[EvidenceCellReference, ...]
    calculated_value: str
    rounded: bool
    references_truncated_snapshot: bool
    unit: str | None
    period: str | None
    unit_reference: EvidenceCellReference | None
    period_reference: EvidenceCellReference | None


def _validate_reference(reference: object) -> None:
    if type(reference) is not EvidenceCellReference:
        raise ValueError("reference must be an EvidenceCellReference")
    if not isinstance(reference.evidence_id, str) or not _DIGEST.fullmatch(reference.evidence_id):
        raise ValueError("evidence_id must be 64 lowercase hexadecimal characters")
    if not isinstance(reference.row_index, int) or isinstance(reference.row_index, bool) or reference.row_index < 0:
        raise ValueError("row_index must be a non-negative integer")
    if (
        not isinstance(reference.column_name, str)
        or not reference.column_name
        or len(reference.column_name) > MAX_NUMERIC_CLAIM_COLUMN_CHARACTERS
        or reference.column_name != reference.column_name.strip()
        or not all(character.isprintable() for character in reference.column_name)
    ):
        raise ValueError("column_name must be a bounded printable result label")


def _validate_claim_structure(claim: object) -> None:
    if type(claim) not in {NumericClaim, NumericClaimPlan}:
        raise ValueError("claim must be a NumericClaim or NumericClaimPlan")
    if not isinstance(claim.id, str) or len(claim.id) > MAX_NUMERIC_CLAIM_ID_CHARACTERS or not _CLAIM_ID.fullmatch(claim.id):
        raise ValueError("id must be a bounded lowercase slug")
    if not isinstance(claim.operation, NumericClaimOperation):
        raise ValueError("operation must be a NumericClaimOperation")
    if type(claim.operands) is not tuple:
        raise ValueError("operands must be a tuple")
    for reference in claim.operands:
        _validate_reference(reference)
    operand_count = len(claim.operands)
    if claim.operation is NumericClaimOperation.CELL and operand_count != 1:
        raise ValueError("cell requires one operand")
    if (
        claim.operation
        in {
            NumericClaimOperation.DIFFERENCE,
            NumericClaimOperation.RATIO,
            NumericClaimOperation.PERCENTAGE,
            NumericClaimOperation.CHANGE_PERCENTAGE,
        }
        and operand_count != 2
    ):
        raise ValueError("operation requires two operands")
    if claim.operation in {NumericClaimOperation.SUM, NumericClaimOperation.MEAN} and not 1 <= operand_count <= MAX_NUMERIC_CLAIMS:
        raise ValueError("sum and mean require one to fifty operands")
    if not isinstance(claim.decimal_places, int) or isinstance(claim.decimal_places, bool) or not 0 <= claim.decimal_places <= 12:
        raise ValueError("decimal_places must be an integer from zero to twelve")
    for reference in (claim.unit_reference, claim.period_reference):
        if reference is not None:
            _validate_reference(reference)


def _validate_claim(claim: object) -> None:
    if type(claim) is not NumericClaim:
        raise ValueError("claim must be a NumericClaim")
    _validate_claim_structure(claim)
    _parse_decimal_text(claim.value)


def _validate_claim_plan(plan: object) -> None:
    if type(plan) is not NumericClaimPlan:
        raise ValueError("plan must be a NumericClaimPlan")
    _validate_claim_structure(plan)


def _check_decimal_bounds(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    decimal_tuple = value.as_tuple()
    if len(decimal_tuple.digits) > MAX_NUMERIC_CLAIM_DECIMAL_DIGITS:
        raise ValueError("decimal has too many digits")
    if not isinstance(decimal_tuple.exponent, int) or abs(decimal_tuple.exponent) > MAX_NUMERIC_CLAIM_DECIMAL_EXPONENT:
        raise ValueError("decimal exponent is out of bounds")
    if value != 0 and abs(value.adjusted()) > MAX_NUMERIC_CLAIM_DECIMAL_EXPONENT:
        raise ValueError("decimal magnitude is out of bounds")
    return value


def _parse_decimal_text(value: object) -> Decimal:
    if type(value) is not str or len(value) > MAX_NUMERIC_CLAIM_DECIMAL_CHARACTERS or not _DECIMAL_TEXT.fullmatch(value):
        raise ValueError("value must be a bounded plain decimal string")
    return _check_decimal_bounds(Decimal(value))


def _parse_numeric_cell(value: object) -> Decimal:
    if type(value) is int:
        if value.bit_length() > 334:
            raise ValueError("integer magnitude is out of bounds")
        return _check_decimal_bounds(Decimal(value))
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("float must be finite")
        return _check_decimal_bounds(Decimal(str(value)))
    if type(value) is str:
        if len(value) > MAX_NUMERIC_CLAIM_DECIMAL_CHARACTERS:
            raise ValueError("numeric text is too long")
        return _parse_decimal_text(value)
    raise ValueError("cell is not a supported numeric value")


def _resolve_cell(
    reference: EvidenceCellReference,
    evidence_index: dict[str, tuple[AnalyticsQueryToolResult, dict[str, int | None]]],
) -> tuple[object, bool]:
    _validate_reference(reference)
    entry = evidence_index.get(reference.evidence_id)
    if entry is None:
        raise NumericClaimError("numeric_claim_reference_unavailable")
    snapshot, columns = entry
    column_index = columns.get(reference.column_name)
    if column_index is None or reference.row_index >= len(snapshot.rows):
        raise NumericClaimError("numeric_claim_reference_unavailable")
    return snapshot.rows[reference.row_index][column_index], snapshot.truncated


def _resolve_label(
    reference: EvidenceCellReference | None,
    *,
    evidence_index: dict[str, tuple[AnalyticsQueryToolResult, dict[str, int | None]]],
    field_name: str,
) -> tuple[str | None, bool]:
    if reference is None:
        return None, False
    value, truncated = _resolve_cell(reference, evidence_index)
    # 期间整数只接受公历年份范围，避免把任意数字改写成标签。
    if field_name == "period" and type(value) is int and 1 <= value <= 9999:
        return str(value), truncated
    if type(value) is not str or not value or len(value) > MAX_NUMERIC_CLAIM_LABEL_CHARACTERS or value != value.strip() or not all(character.isprintable() for character in value):
        raise NumericClaimError("numeric_claim_reference_unavailable")
    return value, truncated


def _calculate(operation: NumericClaimOperation, values: tuple[Decimal, ...]) -> Decimal:
    if operation is NumericClaimOperation.CELL:
        return values[0]
    if operation is NumericClaimOperation.SUM:
        return sum(values, Decimal(0))
    if operation is NumericClaimOperation.DIFFERENCE:
        return values[0] - values[1]
    if operation in {NumericClaimOperation.RATIO, NumericClaimOperation.PERCENTAGE}:
        denominator = values[1]
        if denominator == 0:
            raise NumericClaimError("numeric_claim_computation_invalid")
        quotient = values[0] / denominator
        return quotient * Decimal(100) if operation is NumericClaimOperation.PERCENTAGE else quotient
    if operation is NumericClaimOperation.MEAN:
        return sum(values, Decimal(0)) / Decimal(len(values))
    if operation is NumericClaimOperation.CHANGE_PERCENTAGE:
        denominator = values[1]
        if denominator == 0:
            raise NumericClaimError("numeric_claim_computation_invalid")
        return (values[0] - denominator) / denominator * Decimal(100)
    raise NumericClaimError("numeric_claims_invalid")


def _format_result(value: Decimal, decimal_places: int) -> tuple[str, bool, Decimal]:
    if not value.is_finite() or (value != 0 and abs(value.adjusted()) > _MAX_RESULT_ADJUSTED_EXPONENT):
        raise NumericClaimError("numeric_claim_computation_invalid")
    quantum = Decimal((0, (1,), -decimal_places))
    rounded_value = value.quantize(quantum, rounding=ROUND_HALF_UP)
    result_text = format(rounded_value, "f")
    if len(result_text) > MAX_NUMERIC_CLAIM_DECIMAL_CHARACTERS:
        raise NumericClaimError("numeric_claim_computation_invalid")
    return result_text, value != rounded_value, rounded_value


def _calculate_numeric_claims(
    claims: tuple[NumericClaim | NumericClaimPlan, ...],
    snapshots: tuple[AnalyticsQueryToolResult, ...],
    *,
    claim_type: type[NumericClaim] | type[NumericClaimPlan],
) -> tuple[VerifiedNumericClaim, ...]:
    """执行共享的快照、引用与 Decimal 计算边界。"""

    if type(claims) is not tuple or len(claims) > MAX_NUMERIC_CLAIMS or type(snapshots) is not tuple or len(snapshots) > MAX_NUMERIC_CLAIM_SNAPSHOTS:
        raise NumericClaimError("numeric_claims_invalid")

    evidence_index: dict[str, tuple[AnalyticsQueryToolResult, dict[str, int | None]]] = {}
    snapshot_bytes = 0
    for snapshot in snapshots:
        if type(snapshot) is not AnalyticsQueryToolResult or type(snapshot.evidence) is not AnalyticsQueryEvidence:
            raise NumericClaimError("numeric_claim_snapshot_unavailable")
        try:
            snapshot_bytes += validate_successful_query_result(snapshot)
        except Exception:
            raise NumericClaimError("numeric_claim_snapshot_unavailable") from None
        evidence_id = snapshot.evidence.evidence_id
        if evidence_id in evidence_index:
            raise NumericClaimError("numeric_claim_snapshot_unavailable")
        columns: dict[str, int | None] = {}
        for index, name in enumerate(snapshot.columns):
            columns[name] = None if name in columns else index
        evidence_index[evidence_id] = (snapshot, columns)
    if snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
        raise NumericClaimError("numeric_claim_snapshot_unavailable")

    seen_ids: set[str] = set()
    verified: list[VerifiedNumericClaim] = []
    for claim in claims:
        try:
            if type(claim) is not claim_type:
                raise ValueError("claim type is invalid")
            if claim_type is NumericClaim:
                _validate_claim(claim)
            else:
                _validate_claim_plan(claim)
        except Exception:
            raise NumericClaimError("numeric_claims_invalid") from None
        if claim.id in seen_ids:
            raise NumericClaimError("numeric_claims_invalid")
        seen_ids.add(claim.id)

        try:
            resolved = tuple(_resolve_cell(reference, evidence_index) for reference in claim.operands)
            decimal_values = tuple(_parse_numeric_cell(value) for value, _ in resolved)
            unit, unit_truncated = _resolve_label(claim.unit_reference, evidence_index=evidence_index, field_name="unit")
            period, period_truncated = _resolve_label(claim.period_reference, evidence_index=evidence_index, field_name="period")
        except NumericClaimError:
            raise
        except Exception:
            raise NumericClaimError("numeric_claim_value_invalid") from None

        try:
            with localcontext(
                Context(
                    prec=_ARITHMETIC_PRECISION,
                    rounding=ROUND_HALF_UP,
                    Emax=999_999,
                    Emin=-999_999,
                )
            ):
                calculated = _calculate(claim.operation, decimal_values)
                calculated_text, rounded, rounded_value = _format_result(calculated, claim.decimal_places)
        except NumericClaimError:
            raise
        except (DecimalException, ArithmeticError, ValueError):
            raise NumericClaimError("numeric_claim_computation_invalid") from None

        if claim_type is NumericClaim:
            try:
                asserted_value = _parse_decimal_text(claim.value)
            except Exception:
                raise NumericClaimError("numeric_claim_value_invalid") from None
            if asserted_value != rounded_value:
                raise NumericClaimError("numeric_claim_value_mismatch")

        truncated = unit_truncated or period_truncated or any(was_truncated for _, was_truncated in resolved)
        verified.append(
            VerifiedNumericClaim(
                id=claim.id,
                operation=claim.operation,
                source_references=claim.operands,
                calculated_value=calculated_text,
                rounded=rounded,
                references_truncated_snapshot=truncated,
                unit=unit,
                period=period,
                unit_reference=claim.unit_reference,
                period_reference=claim.period_reference,
            )
        )
    return tuple(verified)


def verify_numeric_claims(
    claims: tuple[NumericClaim, ...],
    snapshots: tuple[AnalyticsQueryToolResult, ...],
) -> tuple[VerifiedNumericClaim, ...]:
    """按 exact evidence 复核模型断言值；模型值必须等于服务器结果。"""

    return _calculate_numeric_claims(claims, snapshots, claim_type=NumericClaim)


def calculate_numeric_claim_plans(
    plans: tuple[NumericClaimPlan, ...],
    snapshots: tuple[AnalyticsQueryToolResult, ...],
) -> tuple[VerifiedNumericClaim, ...]:
    """从无值运算计划与 exact evidence 计算服务端可信数字。"""

    return _calculate_numeric_claims(plans, snapshots, claim_type=NumericClaimPlan)
