from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import DatasourceEngine, _require_trimmed


class ColumnSensitivity(StrEnum):
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    PII = "pii"


def _relation_key(catalog: str | None, schema: str, name: str) -> str:
    return ".".join(part for part in (catalog, schema, name) if part)


def _require_columns(columns: object) -> None:
    if not isinstance(columns, tuple):
        raise ValueError("columns must be a tuple")
    names: set[str] = set()
    for column in columns:
        if not isinstance(column, ColumnSchema):
            raise ValueError("columns must contain only ColumnSchema values")
        if column.name in names:
            raise ValueError("columns must not contain duplicate names")
        names.add(column.name)


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    data_type: str
    sensitivity: ColumnSensitivity = ColumnSensitivity.STANDARD

    def __post_init__(self) -> None:
        _require_trimmed(self.name, "name")
        _require_trimmed(self.data_type, "data_type")
        if not isinstance(self.sensitivity, ColumnSensitivity):
            raise ValueError("sensitivity must be a ColumnSensitivity")


@dataclass(frozen=True, slots=True)
class RelationSchema:
    name: str
    schema: str
    columns: tuple[ColumnSchema, ...]
    catalog: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.name, "name")
        _require_trimmed(self.schema, "schema")
        if self.catalog is not None:
            _require_trimmed(self.catalog, "catalog")
        _require_columns(self.columns)


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    datasource_id: str
    engine: DatasourceEngine
    version: str
    default_schema: str
    relations: tuple[RelationSchema, ...]

    def __post_init__(self) -> None:
        _require_trimmed(self.datasource_id, "datasource_id")
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        _require_trimmed(self.version, "version")
        _require_trimmed(self.default_schema, "default_schema")
        if not isinstance(self.relations, tuple):
            raise ValueError("relations must be a tuple")
        keys: set[str] = set()
        for relation in self.relations:
            if not isinstance(relation, RelationSchema):
                raise ValueError("relations must contain only RelationSchema values")
            key = _relation_key(relation.catalog, relation.schema, relation.name)
            if key in keys:
                raise ValueError("relations must not contain duplicate keys")
            keys.add(key)
