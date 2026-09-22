"""Analytics 的 App 自有配置解析（Phase 2C2）。

`analytics:` 是 `AppConfig(extra="allow")` 上的 App 扩展块。Harness 不认识它，也不新增
业务域配置类型；由本模块严格解析成不可变值，再交给既有领域类型校验边界。

为什么严格：

- 未知字段一律拒绝——配置里的拼写错误如果被静默忽略，运行时会用默认限额处理生产查询；
- `bool` 是 `int` 的子类，必须显式排除，否则 `enabled: true` 写在整数键上会被当成 1；
- 成本只能是十进制精确值（字符串或整数），`float` 在解析阶段就已经丢失精度；
- 本模块**不复制** `ExecutionLimits` 的阈值，只把值装进去让它校验，避免两套边界漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.analytics.domain import MAX_QUERY_ROWS, ExecutionLimits

#: 审计分页的服务端硬上限；`audit_page_size` 是默认值，客户端只能向下请求。
MAX_AUDIT_PAGE_SIZE = 100

_BOOL_FIELDS = ("enabled",)
_INT_FIELDS = (
    "query_max_rows",
    "connect_timeout_ms",
    "statement_timeout_ms",
    "cancellation_grace_ms",
    "max_estimated_rows",
    "max_explain_bytes",
    "max_result_columns",
    "max_result_rows",
    "max_result_bytes",
    "plan_ttl_seconds",
    "audit_page_size",
)
_DECIMAL_FIELDS = ("max_engine_cost",)
_KNOWN_FIELDS = frozenset(_BOOL_FIELDS + _INT_FIELDS + _DECIMAL_FIELDS)


class AnalyticsConfigError(RuntimeError):
    """配置不可用。只携带稳定 reason（可以包含字段名），不含任何凭证。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _parse_cost(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise AnalyticsConfigError(f"analytics_config_invalid_decimal:{name}")
    if isinstance(value, float):
        # float 已经丢失十进制精度，绝不接受。
        raise AnalyticsConfigError(f"analytics_config_invalid_decimal:{name}")
    if isinstance(value, int):
        return Decimal(value)
    if not isinstance(value, str) or not value.strip():
        raise AnalyticsConfigError(f"analytics_config_invalid_decimal:{name}")
    try:
        parsed = Decimal(value.strip())
    except InvalidOperation as error:
        raise AnalyticsConfigError(f"analytics_config_invalid_decimal:{name}") from error
    if not parsed.is_finite() or parsed <= 0:
        raise AnalyticsConfigError(f"analytics_config_invalid_decimal:{name}")
    return parsed


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    """冻结的 Analytics 配置；启动时解析一次，修改需要重启。"""

    enabled: bool = True
    query_max_rows: int = 1_000
    connect_timeout_ms: int = 3_000
    statement_timeout_ms: int = 5_000
    cancellation_grace_ms: int = 500
    max_estimated_rows: int = 100_000
    max_engine_cost: Decimal = Decimal("100000")
    max_explain_bytes: int = 1_048_576
    max_result_columns: int = 128
    max_result_rows: int = 1_000
    max_result_bytes: int = 1_048_576
    plan_ttl_seconds: int = 60
    audit_page_size: int = 50

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        for field_name in _INT_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{field_name} must be an integer")
        if not isinstance(self.max_engine_cost, Decimal) or not self.max_engine_cost.is_finite() or self.max_engine_cost <= 0:
            raise ValueError("max_engine_cost must be a positive finite Decimal")

        if self.query_max_rows > MAX_QUERY_ROWS:
            raise ValueError(f"query_max_rows must be between 1 and {MAX_QUERY_ROWS}")
        if self.max_result_rows > MAX_QUERY_ROWS:
            raise ValueError(f"max_result_rows must be between 1 and {MAX_QUERY_ROWS}")
        # SQL 层 row_limit 是授权值的一部分：传输上限高于它等于放宽授权义务。
        if self.max_result_rows > self.query_max_rows:
            raise ValueError("max_result_rows must not exceed query_max_rows")
        if not 1 <= self.audit_page_size <= MAX_AUDIT_PAGE_SIZE:
            raise ValueError(f"audit_page_size must be between 1 and {MAX_AUDIT_PAGE_SIZE}")

        # 其余传输边界由领域类型唯一负责，这里不复制阈值。
        self.execution_limits()

    @classmethod
    def from_app_config(cls, config: object) -> AnalyticsConfig:
        """从 `AppConfig`（或任何带 `analytics` 属性的对象）解析。"""

        raw = getattr(config, "analytics", None)
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise AnalyticsConfigError("analytics_config_not_a_mapping")

        unknown = sorted(set(raw) - _KNOWN_FIELDS)
        if unknown:
            raise AnalyticsConfigError(f"analytics_config_unknown_field:{unknown[0]}")

        values: dict[str, object] = {}
        for field_name in _BOOL_FIELDS:
            if field_name in raw:
                value = raw[field_name]
                if not isinstance(value, bool):
                    raise AnalyticsConfigError(f"analytics_config_invalid_bool:{field_name}")
                values[field_name] = value
        for field_name in _INT_FIELDS:
            if field_name in raw:
                value = raw[field_name]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise AnalyticsConfigError(f"analytics_config_invalid_int:{field_name}")
                values[field_name] = value
        for field_name in _DECIMAL_FIELDS:
            if field_name in raw:
                values[field_name] = _parse_cost(raw[field_name], field_name)

        try:
            return cls(**values)  # type: ignore[arg-type]
        except ValueError as error:
            raise AnalyticsConfigError(f"analytics_config_invalid_value:{error}") from error

    def execution_limits(self) -> ExecutionLimits:
        """构造执行限额。API 不接受任何客户端覆盖，限额只来自这里。"""

        return ExecutionLimits(
            connect_timeout_ms=self.connect_timeout_ms,
            statement_timeout_ms=self.statement_timeout_ms,
            cancellation_grace_ms=self.cancellation_grace_ms,
            max_estimated_rows=self.max_estimated_rows,
            max_engine_cost=self.max_engine_cost,
            max_explain_bytes=self.max_explain_bytes,
            max_result_columns=self.max_result_columns,
            max_result_rows=self.max_result_rows,
            max_result_bytes=self.max_result_bytes,
            plan_ttl_seconds=self.plan_ttl_seconds,
        )
