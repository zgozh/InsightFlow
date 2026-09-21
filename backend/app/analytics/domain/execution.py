import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.analytics.domain.datasource import DatasourceEngine, _require_trimmed
from app.analytics.domain.query import MAX_QUERY_ROWS, _require_plain_int

# 结果与计划的字节上限是硬边界：超过即拒绝，不做截断式放宽。
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_EXPLAIN_BYTES = 4 * 1024 * 1024
_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")

# 允许穿透到调用方的标量类型；驱动私有对象一律不进入结果。
JsonScalar = None | bool | int | float | str


class ExecutionDecisionCode(StrEnum):
    PLAN_CREATED = "plan_created"
    PLAN_UNAVAILABLE = "plan_unavailable"
    PLAN_STORE_UNAVAILABLE = "plan_store_unavailable"
    AUTHORIZATION_STALE = "authorization_stale"
    DATASOURCE_UNAVAILABLE = "datasource_unavailable"
    SECRET_UNAVAILABLE = "secret_unavailable"
    EXPLAIN_REJECTED = "explain_rejected"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    UNSUPPORTED_IDENTIFIER_MODE = "unsupported_identifier_mode"
    EXECUTION_TIMEOUT = "execution_timeout"
    RESULT_LIMIT_REACHED = "result_limit_reached"
    UNSUPPORTED_RESULT_TYPE = "unsupported_result_type"
    DATABASE_UNAVAILABLE = "database_unavailable"
    EXECUTED = "executed"


def _require_bounded_int(value: object, field_name: str, *, minimum: int, maximum: int) -> None:
    _require_plain_int(value, field_name)
    if not minimum <= value <= maximum:  # type: ignore[operator]
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")


def _require_decimal(value: object, field_name: str, *, allow_zero: bool) -> None:
    # 只接受 Decimal：float 的二进制误差会让成本门禁在边界上出现不可解释的抖动。
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{field_name} must be a positive Decimal")


def _require_digest(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _require_json_scalar(value: object) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        # NaN/Infinity 无法稳定 JSON 序列化，必须在领域边界拒绝。
        if not math.isfinite(value):
            raise ValueError("rows must contain only finite floats")
        return
    raise ValueError("rows must contain only JSON scalars")


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    connect_timeout_ms: int
    statement_timeout_ms: int
    cancellation_grace_ms: int
    max_estimated_rows: int
    max_engine_cost: Decimal
    max_explain_bytes: int
    max_result_columns: int
    max_result_rows: int
    max_result_bytes: int
    plan_ttl_seconds: int

    def __post_init__(self) -> None:
        _require_bounded_int(self.connect_timeout_ms, "connect_timeout_ms", minimum=100, maximum=30_000)
        _require_bounded_int(self.statement_timeout_ms, "statement_timeout_ms", minimum=100, maximum=60_000)
        _require_bounded_int(self.cancellation_grace_ms, "cancellation_grace_ms", minimum=50, maximum=5_000)
        _require_bounded_int(self.max_estimated_rows, "max_estimated_rows", minimum=1, maximum=10**12)
        _require_decimal(self.max_engine_cost, "max_engine_cost", allow_zero=False)
        _require_bounded_int(self.max_explain_bytes, "max_explain_bytes", minimum=1, maximum=_MAX_EXPLAIN_BYTES)
        _require_bounded_int(self.max_result_columns, "max_result_columns", minimum=1, maximum=256)
        # max_result_rows 是传输层上限；它还必须不超过 SQL 层的 row_limit（由用例校验）。
        _require_bounded_int(self.max_result_rows, "max_result_rows", minimum=1, maximum=MAX_QUERY_ROWS)
        _require_bounded_int(self.max_result_bytes, "max_result_bytes", minimum=1, maximum=_MAX_RESULT_BYTES)
        _require_bounded_int(self.plan_ttl_seconds, "plan_ttl_seconds", minimum=5, maximum=300)


@dataclass(frozen=True, slots=True)
class QueryCostEstimate:
    engine: DatasourceEngine
    estimated_rows: int
    engine_cost: Decimal
    plan_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        if not isinstance(self.estimated_rows, int) or isinstance(self.estimated_rows, bool) or self.estimated_rows < 0:
            raise ValueError("estimated_rows must be a non-negative integer")
        _require_decimal(self.engine_cost, "engine_cost", allow_zero=True)
        _require_digest(self.plan_digest, "plan_digest")


@dataclass(frozen=True, slots=True)
class QueryPlanReceipt:
    plan_id: str
    expires_at: datetime
    estimate: QueryCostEstimate

    def __post_init__(self) -> None:
        _require_trimmed(self.plan_id, "plan_id")
        _require_aware_datetime(self.expires_at, "expires_at")
        if not isinstance(self.estimate, QueryCostEstimate):
            raise ValueError("estimate must be a QueryCostEstimate")


@dataclass(frozen=True, slots=True)
class QueryExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[JsonScalar, ...], ...]
    row_count: int
    byte_count: int
    truncated: bool

    def __post_init__(self) -> None:
        if not isinstance(self.columns, tuple):
            raise ValueError("columns must be a tuple")
        for column in self.columns:
            _require_trimmed(column, "columns")
        if not isinstance(self.rows, tuple):
            raise ValueError("rows must be a tuple")
        for row in self.rows:
            if not isinstance(row, tuple):
                raise ValueError("each row must be a tuple")
            if len(row) != len(self.columns):
                raise ValueError("each row must have one cell per column")
            for cell in row:
                _require_json_scalar(cell)
        _require_plain_int(self.row_count, "row_count")
        if self.row_count != len(self.rows):
            raise ValueError("row_count must match the number of rows")
        _require_plain_int(self.byte_count, "byte_count")
        if self.byte_count < 0:
            raise ValueError("byte_count must not be negative")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a boolean")


@dataclass(frozen=True, slots=True)
class QueryPlanDecision:
    code: ExecutionDecisionCode
    receipt: QueryPlanReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ExecutionDecisionCode):
            raise ValueError("code must be an ExecutionDecisionCode")
        if self.receipt is not None and not isinstance(self.receipt, QueryPlanReceipt):
            raise ValueError("receipt must be a QueryPlanReceipt")
        if self.code is ExecutionDecisionCode.PLAN_CREATED:
            if self.receipt is None:
                raise ValueError("a created plan requires a receipt")
        elif self.receipt is not None:
            raise ValueError("only a created plan may carry a receipt")


@dataclass(frozen=True, slots=True)
class QueryExecutionDecision:
    code: ExecutionDecisionCode
    result: QueryExecutionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ExecutionDecisionCode):
            raise ValueError("code must be an ExecutionDecisionCode")
        if self.result is not None and not isinstance(self.result, QueryExecutionResult):
            raise ValueError("result must be a QueryExecutionResult")
        if self.code in (ExecutionDecisionCode.EXECUTED, ExecutionDecisionCode.RESULT_LIMIT_REACHED):
            if self.result is None:
                raise ValueError("an executed or truncated outcome requires a result")
            return
        if self.code is ExecutionDecisionCode.PLAN_CREATED:
            raise ValueError("plan creation is not an execution decision")
        if self.result is not None:
            raise ValueError("a failed execution must not carry a result")
