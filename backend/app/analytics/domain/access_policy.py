from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed


class ColumnAccess(StrEnum):
    ALLOW = "allow"
    AGGREGATE_ONLY = "aggregate_only"
    DENY = "deny"


def _relation_key(catalog: str | None, schema: str, name: str) -> str:
    return ".".join(part for part in (catalog, schema, name) if part)


@dataclass(frozen=True, slots=True)
class ColumnAccessRule:
    name: str
    access: ColumnAccess

    def __post_init__(self) -> None:
        _require_trimmed(self.name, "name")
        if not isinstance(self.access, ColumnAccess):
            raise ValueError("access must be a ColumnAccess")


@dataclass(frozen=True, slots=True)
class RelationAccessRule:
    name: str
    schema: str
    columns: tuple[ColumnAccessRule, ...]
    catalog: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.name, "name")
        _require_trimmed(self.schema, "schema")
        if self.catalog is not None:
            _require_trimmed(self.catalog, "catalog")
        if not isinstance(self.columns, tuple):
            raise ValueError("columns must be a tuple")
        names: set[str] = set()
        for rule in self.columns:
            if not isinstance(rule, ColumnAccessRule):
                raise ValueError("columns must contain only ColumnAccessRule values")
            if rule.name in names:
                raise ValueError("columns must not contain duplicate names")
            names.add(rule.name)


@dataclass(frozen=True, slots=True)
class PrincipalAccessPolicy:
    datasource_id: str
    principal_id: str
    version: str
    relations: tuple[RelationAccessRule, ...]
    allowed_functions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_trimmed(self.datasource_id, "datasource_id")
        _require_trimmed(self.principal_id, "principal_id")
        _require_trimmed(self.version, "version")
        if not isinstance(self.relations, tuple):
            raise ValueError("relations must be a tuple")
        keys: set[str] = set()
        for relation in self.relations:
            if not isinstance(relation, RelationAccessRule):
                raise ValueError("relations must contain only RelationAccessRule values")
            key = _relation_key(relation.catalog, relation.schema, relation.name)
            if key in keys:
                raise ValueError("relations must not contain duplicate keys")
            keys.add(key)
        if not isinstance(self.allowed_functions, tuple):
            raise ValueError("allowed_functions must be a tuple")
        folded: list[str] = []
        seen: set[str] = set()
        for function in self.allowed_functions:
            _require_trimmed(function, "allowed_functions")
            name = function.casefold()
            if name in seen:
                raise ValueError("allowed_functions must not contain duplicates")
            seen.add(name)
            folded.append(name)
        object.__setattr__(self, "allowed_functions", tuple(folded))
