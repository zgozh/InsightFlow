"""Analytics bounded context 自己的 ORM metadata 与六张持久化表（Phase 2C1）。

为什么**不**继承 Harness 的 `deerflow.persistence.base.Base`：

1. `app.analytics` 是 App 拥有的业务域，Harness 不得反向 import App；
2. 依赖 import 副作用把 App 模型塞进 Harness 的 `create_all()`，会让空库、Alembic
   autogenerate 与独立测试的表集合发生漂移；
3. 独立 metadata + 独立迁移链让表所有权、回滚和边界测试清晰，同时仍然复用同一个物理
   应用数据库，不增加部署复杂度。

因此这里所有表统一使用 `analytics_` 前缀，版本表是 `analytics_alembic_version`，
Harness 的迁移过滤器显式排除该前缀。

**跨链外键是禁止的**：Analytics 表绝不引用 Harness 表（`users` / `threads_meta` 等）。
Analytics 内部引用使用具名外键，但审计历史不得被级联删除，所以
`analytics_query_audits.datasource_id` 刻意**不加**外键——审计必须比数据源活得更久。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 与领域枚举逐字对应的字面量：check constraint 用它们构造，避免两处独立维护。
DATASOURCE_ENGINES = ("mysql", "postgresql")
DATASOURCE_STATUSES = ("active", "disabled", "unhealthy")
METRIC_STATUSES = ("draft", "active", "retired")
AUDIT_PHASES = ("policy", "authorization", "plan", "execute")
AUDIT_STATUSES = ("started", "completed")
RISK_LEVELS = ("low", "medium", "high", "blocked")

VERSION_TABLE_NAME = "analytics_alembic_version"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class AnalyticsBase(DeclarativeBase):
    """Analytics 专属 metadata 根：绝不注册到 Harness 的 `Base.metadata`。"""


class DatasourceRow(AnalyticsBase):
    __tablename__ = "analytics_datasources"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_analytics_datasources_owner_name"),
        CheckConstraint(f"engine IN ({_quoted(DATASOURCE_ENGINES)})", name="ck_analytics_datasources_engine"),
        CheckConstraint(f"status IN ({_quoted(DATASOURCE_STATUSES)})", name="ck_analytics_datasources_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
    # 只保存 opaque reference；真实 DSN 与口令属于凭证解析器，绝不入库。
    secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    default_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchemaSnapshotRow(AnalyticsBase):
    __tablename__ = "analytics_schema_snapshots"
    __table_args__ = (CheckConstraint(f"engine IN ({_quoted(DATASOURCE_ENGINES)})", name="ck_analytics_schema_snapshots_engine"),)

    datasource_id: Mapped[str] = mapped_column(String(64), ForeignKey("analytics_datasources.id", name="fk_analytics_schema_snapshots_datasource"), primary_key=True)
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    default_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    relations_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccessPolicyRow(AnalyticsBase):
    __tablename__ = "analytics_access_policies"
    __table_args__ = (PrimaryKeyConstraint("datasource_id", "principal_id", name="pk_analytics_access_policies"),)

    datasource_id: Mapped[str] = mapped_column(String(64), ForeignKey("analytics_datasources.id", name="fk_analytics_access_policies_datasource"))
    principal_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    relations_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_functions_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetricRow(AnalyticsBase):
    __tablename__ = "analytics_metrics"
    __table_args__ = (
        PrimaryKeyConstraint("owner_id", "key", name="pk_analytics_metrics"),
        CheckConstraint(f"status IN ({_quoted(METRIC_STATUSES)})", name="ck_analytics_metrics_status"),
    )

    owner_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # V1 的 expression 只是业务定义文本，绝不进入 SQL 执行器。
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExecutionPlanRow(AnalyticsBase):
    __tablename__ = "analytics_execution_plans"
    __table_args__ = (
        CheckConstraint("expires_at > issued_at", name="ck_analytics_execution_plans_expiry"),
        Index("ix_analytics_execution_plans_expires_at", "expires_at"),
        Index("ix_analytics_execution_plans_principal_expires_at", "principal_id", "expires_at"),
        Index("ix_analytics_execution_plans_datasource_id", "datasource_id"),
    )

    # 只存 SHA-256 摘要；原始 token 永不落库。
    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    datasource_id: Mapped[str] = mapped_column(String(64), ForeignKey("analytics_datasources.id", name="fk_analytics_execution_plans_datasource"), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueryAuditRow(AnalyticsBase):
    __tablename__ = "analytics_query_audits"
    __table_args__ = (
        CheckConstraint(f"phase IN ({_quoted(AUDIT_PHASES)})", name="ck_analytics_query_audits_phase"),
        CheckConstraint(f"status IN ({_quoted(AUDIT_STATUSES)})", name="ck_analytics_query_audits_status"),
        CheckConstraint(f"risk IS NULL OR risk IN ({_quoted(RISK_LEVELS)})", name="ck_analytics_query_audits_risk"),
        Index("ix_analytics_query_audits_started_at", "started_at"),
        Index("ix_analytics_query_audits_principal_started_at", "principal_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 审计必须比数据源活得更久，因此这里没有外键，也不参与级联删除。
    datasource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    query_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # canonical decimal 以字符串保存：SQLite 的 NUMERIC 会退化成 float，二进制误差不可接受。
    engine_cost: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 长期停留在 started 表示 worker 崩溃或终态写入失败；读取接口不得把它伪装成成功。
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
