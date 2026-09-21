from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import DatasourceEngine, _require_trimmed

MAX_QUERY_ROWS = 10_000

_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


class QueryRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class QueryDecisionCode(StrEnum):
    APPROVED = "approved"
    EMPTY_SQL = "empty_sql"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    FORBIDDEN_OPERATION = "forbidden_operation"
    COMMENT_NOT_ALLOWED = "comment_not_allowed"
    WILDCARD_PROJECTION = "wildcard_projection"
    DANGEROUS_FUNCTION = "dangerous_function"
    OFFSET_NOT_ALLOWED = "offset_not_allowed"
    NON_LITERAL_LIMIT = "non_literal_limit"
    INVALID_LIMIT = "invalid_limit"
    UNBOUND_PARAMETER = "unbound_parameter"
    LIMIT_APPLIED = "limit_applied"
    LIMIT_REDUCED = "limit_reduced"
    COMPLEX_QUERY = "complex_query"


def _require_plain_int(value: object, field_name: str) -> None:
    """Reject non-integers and booleans masquerading as integers."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")


@dataclass(frozen=True, slots=True)
class QueryPolicyRequest:
    sql: str
    engine: DatasourceEngine
    max_rows: int = 1_000

    def __post_init__(self) -> None:
        if not isinstance(self.sql, str):
            raise ValueError("sql must be a string")
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        _require_plain_int(self.max_rows, "max_rows")
        if not 1 <= self.max_rows <= MAX_QUERY_ROWS:
            raise ValueError(f"max_rows must be between 1 and {MAX_QUERY_ROWS}")


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    sql: str
    engine: DatasourceEngine
    relations: tuple[str, ...]
    row_limit: int
    query_hash: str

    def __post_init__(self) -> None:
        _require_trimmed(self.sql, "sql")
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        if not isinstance(self.relations, tuple):
            raise ValueError("relations must be a tuple")
        for relation in self.relations:
            _require_trimmed(relation, "relations")
        if len(set(self.relations)) != len(self.relations):
            raise ValueError("relations must not contain duplicates")
        _require_plain_int(self.row_limit, "row_limit")
        if self.row_limit < 0:
            raise ValueError("row_limit must not be negative")
        if not isinstance(self.query_hash, str) or len(self.query_hash) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in self.query_hash):
            raise ValueError("query_hash must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class QueryPolicyDecision:
    allowed: bool
    risk: QueryRisk
    codes: tuple[QueryDecisionCode, ...]
    prepared: PreparedQuery | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ValueError("allowed must be a boolean")
        if not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be a QueryRisk")
        if not isinstance(self.codes, tuple) or not self.codes:
            raise ValueError("codes must be a non-empty tuple")
        for code in self.codes:
            if not isinstance(code, QueryDecisionCode):
                raise ValueError("codes must contain only QueryDecisionCode values")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError("codes must not contain duplicates")
        if self.prepared is not None and not isinstance(self.prepared, PreparedQuery):
            raise ValueError("prepared must be a PreparedQuery")
        if self.allowed:
            if self.risk is QueryRisk.BLOCKED:
                raise ValueError("an allowed decision cannot be blocked")
            if self.prepared is None:
                raise ValueError("an allowed decision requires a prepared query")
        elif self.prepared is not None:
            raise ValueError("a denied decision must not carry a prepared query")
