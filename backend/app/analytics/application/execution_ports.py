from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryCostEstimate,
    QueryExecutionResult,
)

_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


class DatasourceQueryError(Exception):
    """数据库网关的稳定失败。

    只携带决定码：驱动异常文本可能包含 DSN、用户名、地址或 SQL 片段，绝不能向上穿透。
    需要调试链时用 `raise ... from error` 保留在内部，外发文本保持稳定。
    """

    def __init__(self, code: ExecutionDecisionCode) -> None:
        super().__init__(code.value)
        self.code = code


class ExecutionPlanStoreError(Exception):
    """plan store 拒绝写入（摘要冲突或容量溢出）。

    文本保持固定原因，不含 token、摘要或任何凭证信息。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class StoredExecutionPlan:
    """store 内部保存的 plan：只绑定能力摘要与当次授权快照。

    这里保存的是 token 的 SHA-256 摘要，不是原始 token；原始 token 只在创建时返回一次。
    """

    token_digest: str
    principal_id: str
    datasource: DatasourceDefinition
    authorized: AuthorizedQuerySpec
    estimate: QueryCostEstimate
    limits: ExecutionLimits
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.token_digest, str) or len(self.token_digest) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in self.token_digest):
            raise ValueError("token_digest must be 64 lowercase hexadecimal characters")
        if not isinstance(self.principal_id, str) or not self.principal_id.strip() or self.principal_id != self.principal_id.strip():
            raise ValueError("principal_id must be a non-empty trimmed string")
        if not isinstance(self.datasource, DatasourceDefinition):
            raise ValueError("datasource must be a DatasourceDefinition")
        if not isinstance(self.authorized, AuthorizedQuerySpec):
            raise ValueError("authorized must be an AuthorizedQuerySpec")
        if not isinstance(self.estimate, QueryCostEstimate):
            raise ValueError("estimate must be a QueryCostEstimate")
        if not isinstance(self.limits, ExecutionLimits):
            raise ValueError("limits must be ExecutionLimits")
        for field_name in ("issued_at", "expires_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValueError(f"{field_name} must be a timezone-aware datetime")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")


@runtime_checkable
class DatasourceQueryGateway(Protocol):
    async def explain(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryCostEstimate: ...

    async def execute(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryExecutionResult: ...


@runtime_checkable
class ExecutionPlanStore(Protocol):
    async def put(self, plan: StoredExecutionPlan) -> None: ...

    async def claim(self, *, token_digest: str, principal_id: str, now: datetime) -> StoredExecutionPlan | None: ...

    async def purge_expired(self, *, now: datetime) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class PlanTokenIssuer(Protocol):
    def issue(self) -> str: ...
