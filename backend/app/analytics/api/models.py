"""Analytics API 的严格 DTO（Phase 2C2 §6）。

请求模型一律 `extra="forbid"`：客户端提交 `principal_id`、`owner_id`、prepared/authorized
对象、执行限额、schema/policy 版本或 credential 都会被 422 拒绝，而不是被静默忽略。

raw SQL 与 plan token 用 `SecretStr` 承载：它们的 `repr` 永远不出现原值，因此日志、异常提示
和调试输出都不会带出敏感内容。真正的"验证错误不回显原值"由 `router.install_request_error_handler`
折叠 `/api/analytics` 下的 422 响应体保证。

响应模型只暴露审计表与目录里本就安全的字段：普通用户的 datasource 视图没有 `owner_id` 与
`secret_ref`，任何响应都不含解析后的凭证。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.analytics.domain import (
    ColumnAccess,
    ColumnSensitivity,
    DatasourceEngine,
    DatasourceStatus,
    MetricStatus,
    QueryAuditPhase,
    QueryAuditStatus,
    QueryRisk,
)

#: 原始 SQL 与 plan token 的长度上限。它们只是拒绝异常膨胀的输入，不是业务限额。
MAX_SQL_CHARACTERS = 20_000
MAX_PLAN_ID_CHARACTERS = 512

_STRICT = ConfigDict(extra="forbid")
# `schema` 是领域字段名但也是 Pydantic v1 的保留方法名；用别名承载并按名填充。
_STRICT_ALIASED = ConfigDict(extra="forbid", populate_by_name=True)


# --- 请求：管理员 -----------------------------------------------------------


class DatasourceCreateRequest(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=255)
    engine: DatasourceEngine
    secret_ref: str = Field(min_length=1, max_length=512)
    default_schema: str | None = Field(default=None, max_length=255)


class DatasourceUpdateRequest(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=255)
    secret_ref: str = Field(min_length=1, max_length=512)
    default_schema: str | None = Field(default=None, max_length=255)
    status: DatasourceStatus


class ColumnSchemaPayload(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=255)
    data_type: str = Field(min_length=1, max_length=128)
    sensitivity: ColumnSensitivity = ColumnSensitivity.STANDARD


class RelationSchemaPayload(BaseModel):
    model_config = _STRICT_ALIASED

    name: str = Field(min_length=1, max_length=255)
    schema_: str = Field(alias="schema", min_length=1, max_length=255)
    catalog: str | None = Field(default=None, max_length=255)
    columns: tuple[ColumnSchemaPayload, ...]


class SchemaSnapshotRequest(BaseModel):
    model_config = _STRICT

    version: str = Field(min_length=1, max_length=64)
    # 必须显式携带；首次创建写 null。
    expected_version: str | None
    default_schema: str = Field(min_length=1, max_length=255)
    relations: tuple[RelationSchemaPayload, ...]


class ColumnAccessRulePayload(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=255)
    access: ColumnAccess


class RelationAccessRulePayload(BaseModel):
    model_config = _STRICT_ALIASED

    name: str = Field(min_length=1, max_length=255)
    schema_: str = Field(alias="schema", min_length=1, max_length=255)
    catalog: str | None = Field(default=None, max_length=255)
    columns: tuple[ColumnAccessRulePayload, ...]


class AccessPolicyRequest(BaseModel):
    model_config = _STRICT

    version: str = Field(min_length=1, max_length=64)
    expected_version: str | None
    relations: tuple[RelationAccessRulePayload, ...]
    allowed_functions: tuple[str, ...] = ()


class MetricCreateRequest(BaseModel):
    model_config = _STRICT

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    expression: str = Field(min_length=1, max_length=2_000)
    dimensions: tuple[str, ...] = ()
    version: int = Field(ge=1)
    status: MetricStatus


class MetricUpdateRequest(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2_000)
    expression: str = Field(min_length=1, max_length=2_000)
    dimensions: tuple[str, ...] = ()
    version: int = Field(ge=1)
    status: MetricStatus


# --- 请求：用户 -------------------------------------------------------------


class QueryPlanRequest(BaseModel):
    model_config = _STRICT

    datasource_id: str = Field(min_length=1, max_length=64)
    sql: SecretStr


class QueryExecutionRequest(BaseModel):
    model_config = _STRICT

    plan_id: SecretStr


# --- 响应：目录 -------------------------------------------------------------


class DatasourceView(BaseModel):
    """普通用户视图：没有 owner，也没有 secret_ref。"""

    id: str
    name: str
    engine: DatasourceEngine
    default_schema: str | None
    status: DatasourceStatus


class DatasourceListResponse(BaseModel):
    datasources: tuple[DatasourceView, ...]


class AdminDatasourceView(BaseModel):
    """管理员视图：可以看到自己数据源的 opaque reference，但永远看不到解析后的凭证。"""

    id: str
    owner_id: str
    name: str
    engine: DatasourceEngine
    secret_ref: str
    default_schema: str | None
    status: DatasourceStatus


class AdminDatasourceListResponse(BaseModel):
    datasources: tuple[AdminDatasourceView, ...]


class MetricView(BaseModel):
    key: str
    name: str
    description: str
    expression: str
    dimensions: tuple[str, ...]
    version: int
    status: MetricStatus


class MetricListResponse(BaseModel):
    metrics: tuple[MetricView, ...]


class ColumnSchemaView(BaseModel):
    name: str
    data_type: str
    sensitivity: ColumnSensitivity


class RelationSchemaView(BaseModel):
    name: str
    schema_: str = Field(serialization_alias="schema")
    catalog: str | None
    columns: tuple[ColumnSchemaView, ...]


class SchemaSnapshotView(BaseModel):
    datasource_id: str
    engine: DatasourceEngine
    version: str
    default_schema: str
    relations: tuple[RelationSchemaView, ...]


class ColumnAccessRuleView(BaseModel):
    name: str
    access: ColumnAccess


class RelationAccessRuleView(BaseModel):
    name: str
    schema_: str = Field(serialization_alias="schema")
    catalog: str | None
    columns: tuple[ColumnAccessRuleView, ...]


class AccessPolicyView(BaseModel):
    datasource_id: str
    principal_id: str
    version: str
    relations: tuple[RelationAccessRuleView, ...]
    allowed_functions: tuple[str, ...]


# --- 响应：查询 -------------------------------------------------------------


class QueryPlanResponse(BaseModel):
    code: str
    plan_id: str | None = None
    expires_at: datetime | None = None
    estimated_rows: int | None = None
    engine_cost: Decimal | None = None
    plan_digest: str | None = None


class QueryResultView(BaseModel):
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    byte_count: int
    truncated: bool


class QueryExecutionResponse(BaseModel):
    code: str
    result: QueryResultView | None = None


# --- 响应：审计 -------------------------------------------------------------


class QueryAuditView(BaseModel):
    id: str
    principal_id: str
    datasource_id: str | None
    phase: QueryAuditPhase
    status: QueryAuditStatus
    query_hash: str | None
    risk: QueryRisk | None
    decision_code: str | None
    schema_version: str | None
    policy_version: str | None
    estimated_rows: int | None
    engine_cost: Decimal | None
    plan_digest: str | None
    row_count: int | None
    byte_count: int | None
    truncated: bool | None
    latency_ms: int | None
    started_at: datetime
    finished_at: datetime | None


class QueryAuditPageResponse(BaseModel):
    audits: tuple[QueryAuditView, ...]
    has_more: bool
    next_before_started_at: datetime | None = None
    next_before_id: str | None = None


class AnalyticsErrorResponse(BaseModel):
    code: str
