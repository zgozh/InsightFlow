from dataclasses import dataclass
from enum import StrEnum


class DatasourceEngine(StrEnum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class DatasourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"


def _require_trimmed(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class DatasourceDefinition:
    id: str
    owner_id: str
    name: str
    engine: DatasourceEngine
    secret_ref: str
    default_schema: str | None = None
    status: DatasourceStatus = DatasourceStatus.ACTIVE

    def __post_init__(self) -> None:
        for field_name in ("id", "owner_id", "name", "secret_ref"):
            _require_trimmed(getattr(self, field_name), field_name)
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        if not isinstance(self.status, DatasourceStatus):
            raise ValueError("status must be a DatasourceStatus")
        if self.default_schema is not None:
            _require_trimmed(self.default_schema, "default_schema")
