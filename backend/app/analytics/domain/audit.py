"""查询审计的领域值对象（Phase 2C1）。

审计是访问真实业务数据库之前的**安全门禁**，不是尽力而为的日志。因此这里的值对象只承载
稳定元数据（阶段、状态、决定码、schema/policy 版本、成本与结果计数），绝不承载：

- 原始或规范化 SQL；
- plan token 与 token digest；
- secret ref、DSN、用户名与口令；
- 驱动异常文本、原始 EXPLAIN JSON 与查询结果单元格。

`QueryAuditStart` 与 `QueryAuditCompletion` 是不可变值：任何字段越界都在构造时拒绝，
而不是留到写库时才失败。
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed
from app.analytics.domain.query import QueryRisk, _require_plain_int

_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


class QueryAuditPhase(StrEnum):
    POLICY = "policy"
    AUTHORIZATION = "authorization"
    PLAN = "plan"
    EXECUTE = "execute"


class QueryAuditStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _require_optional_digest(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"{field_name} must be None or 64 lowercase hexadecimal characters")


def _require_optional_measurement(value: object, field_name: str) -> None:
    if value is None:
        return
    _require_plain_int(value, field_name)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{field_name} must not be negative")


def _require_optional_cost(value: object, field_name: str) -> None:
    # 只接受 Decimal：float 的二进制误差会让审计里的成本与门禁判定的成本对不上。
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be None or a finite non-negative Decimal")


def _require_optional_bool(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field_name} must be None or a boolean")


@dataclass(frozen=True, slots=True)
class QueryAuditStart:
    """一条 `started` 审计记录：真实业务数据库 I/O 之前必须先写入它。"""

    principal_id: str
    datasource_id: str | None
    phase: QueryAuditPhase
    started_at: datetime
    query_hash: str | None = None
    risk: QueryRisk | None = None
    schema_version: str | None = None
    policy_version: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.principal_id, "principal_id")
        if self.datasource_id is not None:
            _require_trimmed(self.datasource_id, "datasource_id")
        if not isinstance(self.phase, QueryAuditPhase):
            raise ValueError("phase must be a QueryAuditPhase")
        _require_aware_datetime(self.started_at, "started_at")
        _require_optional_digest(self.query_hash, "query_hash")
        if self.risk is not None and not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be None or a QueryRisk")
        # schema/policy 版本要么一起给，要么都不给：只写一半会让审计无法判断授权依据。
        if (self.schema_version is None) != (self.policy_version is None):
            raise ValueError("schema_version and policy_version must be provided together")
        if self.schema_version is not None:
            _require_trimmed(self.schema_version, "schema_version")
            _require_trimmed(self.policy_version, "policy_version")


@dataclass(frozen=True, slots=True)
class QueryAuditCompletion:
    """一条审计的终态更新：只允许携带稳定决定码与有界测量值。"""

    audit_id: str
    decision_code: str
    finished_at: datetime
    risk: QueryRisk | None = None
    estimated_rows: int | None = None
    engine_cost: Decimal | None = None
    plan_digest: str | None = None
    row_count: int | None = None
    byte_count: int | None = None
    truncated: bool | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.audit_id, "audit_id")
        _require_trimmed(self.decision_code, "decision_code")
        _require_aware_datetime(self.finished_at, "finished_at")
        if self.risk is not None and not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be None or a QueryRisk")
        for field_name in ("estimated_rows", "row_count", "byte_count", "latency_ms"):
            _require_optional_measurement(getattr(self, field_name), field_name)
        _require_optional_cost(self.engine_cost, "engine_cost")
        _require_optional_digest(self.plan_digest, "plan_digest")
        _require_optional_bool(self.truncated, "truncated")


@dataclass(frozen=True, slots=True)
class QueryAuditRecord:
    """审计表的只读投影：字段与表结构一一对应，不多一个。

    读取侧与写入侧共用同一份"安全元数据"定义：这里没有 SQL、token/digest、secret ref、
    DSN、账号口令、驱动异常文本、原始 EXPLAIN 或结果值，因此任何序列化路径都不可能把它们
    带出去。
    """

    id: str
    principal_id: str
    datasource_id: str | None
    phase: QueryAuditPhase
    status: QueryAuditStatus
    started_at: datetime
    query_hash: str | None = None
    risk: QueryRisk | None = None
    decision_code: str | None = None
    schema_version: str | None = None
    policy_version: str | None = None
    estimated_rows: int | None = None
    engine_cost: Decimal | None = None
    plan_digest: str | None = None
    row_count: int | None = None
    byte_count: int | None = None
    truncated: bool | None = None
    latency_ms: int | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.id, "id")
        _require_trimmed(self.principal_id, "principal_id")
        if self.datasource_id is not None:
            _require_trimmed(self.datasource_id, "datasource_id")
        if not isinstance(self.phase, QueryAuditPhase):
            raise ValueError("phase must be a QueryAuditPhase")
        if not isinstance(self.status, QueryAuditStatus):
            raise ValueError("status must be a QueryAuditStatus")
        _require_aware_datetime(self.started_at, "started_at")
        if self.finished_at is not None:
            _require_aware_datetime(self.finished_at, "finished_at")
        _require_optional_digest(self.query_hash, "query_hash")
        _require_optional_digest(self.plan_digest, "plan_digest")
        if self.risk is not None and not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be None or a QueryRisk")
        if self.decision_code is not None:
            _require_trimmed(self.decision_code, "decision_code")
        if (self.schema_version is None) != (self.policy_version is None):
            raise ValueError("schema_version and policy_version must be provided together")
        if self.schema_version is not None:
            _require_trimmed(self.schema_version, "schema_version")
            _require_trimmed(self.policy_version, "policy_version")
        for field_name in ("estimated_rows", "row_count", "byte_count", "latency_ms"):
            _require_optional_measurement(getattr(self, field_name), field_name)
        _require_optional_cost(self.engine_cost, "engine_cost")
        _require_optional_bool(self.truncated, "truncated")
