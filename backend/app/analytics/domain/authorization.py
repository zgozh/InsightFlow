from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed
from app.analytics.domain.query import PreparedQuery, QueryRisk


class AuthorizationDecisionCode(StrEnum):
    APPROVED = "approved"
    DATASOURCE_NOT_ACCESSIBLE = "datasource_not_accessible"
    SCHEMA_UNAVAILABLE = "schema_unavailable"
    POLICY_UNAVAILABLE = "policy_unavailable"
    PREPARED_QUERY_MISMATCH = "prepared_query_mismatch"
    ANALYSIS_ERROR = "analysis_error"
    CORRELATED_SUBQUERY_NOT_ALLOWED = "correlated_subquery_not_allowed"
    UNKNOWN_RELATION = "unknown_relation"
    RELATION_NOT_ALLOWED = "relation_not_allowed"
    UNKNOWN_COLUMN = "unknown_column"
    COLUMN_NOT_ALLOWED = "column_not_allowed"
    FUNCTION_NOT_ALLOWED = "function_not_allowed"
    SENSITIVE_COLUMN = "sensitive_column"
    CROSS_SCHEMA = "cross_schema"
    CARTESIAN_JOIN = "cartesian_join"
    APPROVAL_REQUIRED = "approval_required"


def _require_inventory(values: object, field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    seen: set[str] = set()
    for value in values:
        _require_trimmed(value, field_name)
        if value in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(value)


@dataclass(frozen=True, slots=True)
class AuthorizedQuerySpec:
    prepared: PreparedQuery
    datasource_id: str
    principal_id: str
    schema_version: str
    policy_version: str
    relations: tuple[str, ...]
    columns: tuple[str, ...]
    functions: tuple[str, ...]
    risk: QueryRisk

    def __post_init__(self) -> None:
        if not isinstance(self.prepared, PreparedQuery):
            raise ValueError("prepared must be a PreparedQuery")
        for field_name in ("datasource_id", "principal_id", "schema_version", "policy_version"):
            _require_trimmed(getattr(self, field_name), field_name)
        for field_name in ("relations", "columns", "functions"):
            _require_inventory(getattr(self, field_name), field_name)
        if not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be a QueryRisk")
        if self.risk not in (QueryRisk.LOW, QueryRisk.MEDIUM):
            raise ValueError("risk must be LOW or MEDIUM for an authorized query spec")


@dataclass(frozen=True, slots=True)
class QueryAuthorizationDecision:
    allowed: bool
    risk: QueryRisk
    codes: tuple[AuthorizationDecisionCode, ...]
    authorized: AuthorizedQuerySpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise ValueError("allowed must be a boolean")
        if not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be a QueryRisk")
        if not isinstance(self.codes, tuple) or not self.codes:
            raise ValueError("codes must be a non-empty tuple")
        for code in self.codes:
            if not isinstance(code, AuthorizationDecisionCode):
                raise ValueError("codes must contain only AuthorizationDecisionCode values")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError("codes must not contain duplicates")
        if self.authorized is not None and not isinstance(self.authorized, AuthorizedQuerySpec):
            raise ValueError("authorized must be an AuthorizedQuerySpec")
        if self.allowed:
            if self.risk not in (QueryRisk.LOW, QueryRisk.MEDIUM):
                raise ValueError("an allowed decision must be LOW or MEDIUM risk")
            if self.authorized is None:
                raise ValueError("an allowed decision requires an authorized query spec")
            if self.authorized.risk is not self.risk:
                raise ValueError("an allowed decision must match its authorized query spec risk")
            return
        if self.authorized is not None:
            raise ValueError("a denied decision must not carry an authorized query spec")
        if self.risk is QueryRisk.HIGH:
            if self.codes[-1] is not AuthorizationDecisionCode.APPROVAL_REQUIRED:
                raise ValueError("a denied HIGH decision must end with APPROVAL_REQUIRED")
        elif self.codes[-1] is AuthorizationDecisionCode.APPROVAL_REQUIRED:
            raise ValueError("only a denied HIGH decision may end with APPROVAL_REQUIRED")
