import re
from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed

_METRIC_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class MetricStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    owner_id: str
    name: str
    description: str
    expression: str
    dimensions: tuple[str, ...] = ()
    version: int = 1
    status: MetricStatus = MetricStatus.DRAFT

    def __post_init__(self) -> None:
        for field_name in ("owner_id", "name", "description", "expression"):
            _require_trimmed(getattr(self, field_name), field_name)
        if not isinstance(self.key, str) or _METRIC_KEY.fullmatch(self.key) is None:
            raise ValueError("key must match ^[a-z][a-z0-9_]{0,63}$")
        if not isinstance(self.status, MetricStatus):
            raise ValueError("status must be a MetricStatus")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.dimensions, tuple):
            raise ValueError("dimensions must be a tuple")
        for dimension in self.dimensions:
            _require_trimmed(dimension, "dimensions")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("dimensions must not contain duplicates")
