"""Analytics 控制面首版 schema：六张表与索引。

Revision ID: 0001_analytics_control_plane
Revises:
Create Date: 2026-09-22

这是 Analytics bounded context 自己的迁移链起点。它只创建 `analytics_*` 表，
与 Harness 的链共用同一个应用数据库，但使用独立版本表 `analytics_alembic_version`。
DDL 逐列镜像 `app/analytics/infrastructure/persistence/models.py`；两侧漂移由
`tests/test_analytics_persistence_migrations.py` 的逐列比对测试钉住。

刻意不使用 `AnalyticsBase.metadata.create_all()` 作为首版实现：一条历史 revision 一旦
依赖"当前 ORM 元数据"，后续模型变更就会静默改写这条已经执行过的迁移。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_analytics_control_plane"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENGINES = "'mysql', 'postgresql'"
_STATUSES = "'active', 'disabled', 'unhealthy'"
_METRIC_STATUSES = "'draft', 'active', 'retired'"
_PHASES = "'policy', 'authorization', 'plan', 'execute'"
_AUDIT_STATUSES = "'started', 'completed'"
_RISKS = "'low', 'medium', 'high', 'blocked'"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("analytics_datasources"):
        op.create_table(
            "analytics_datasources",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("engine", sa.String(length=16), nullable=False),
            sa.Column("secret_ref", sa.String(length=512), nullable=False),
            sa.Column("default_schema", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_id", "name", name="uq_analytics_datasources_owner_name"),
            sa.CheckConstraint(f"engine IN ({_ENGINES})", name="ck_analytics_datasources_engine"),
            sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_analytics_datasources_status"),
        )

    if not inspector.has_table("analytics_schema_snapshots"):
        op.create_table(
            "analytics_schema_snapshots",
            sa.Column("datasource_id", sa.String(length=64), nullable=False),
            sa.Column("engine", sa.String(length=16), nullable=False),
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("default_schema", sa.String(length=255), nullable=False),
            sa.Column("relations_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("datasource_id"),
            sa.ForeignKeyConstraint(["datasource_id"], ["analytics_datasources.id"], name="fk_analytics_schema_snapshots_datasource"),
            sa.CheckConstraint(f"engine IN ({_ENGINES})", name="ck_analytics_schema_snapshots_engine"),
        )

    if not inspector.has_table("analytics_access_policies"):
        op.create_table(
            "analytics_access_policies",
            sa.Column("datasource_id", sa.String(length=64), nullable=False),
            sa.Column("principal_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("relations_json", sa.Text(), nullable=False),
            sa.Column("allowed_functions_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("datasource_id", "principal_id", name="pk_analytics_access_policies"),
            sa.ForeignKeyConstraint(["datasource_id"], ["analytics_datasources.id"], name="fk_analytics_access_policies_datasource"),
        )

    if not inspector.has_table("analytics_metrics"):
        op.create_table(
            "analytics_metrics",
            sa.Column("owner_id", sa.String(length=64), nullable=False),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("expression", sa.Text(), nullable=False),
            sa.Column("dimensions_json", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("owner_id", "key", name="pk_analytics_metrics"),
            sa.CheckConstraint(f"status IN ({_METRIC_STATUSES})", name="ck_analytics_metrics_status"),
        )

    if not inspector.has_table("analytics_execution_plans"):
        op.create_table(
            "analytics_execution_plans",
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("principal_id", sa.String(length=64), nullable=False),
            sa.Column("datasource_id", sa.String(length=64), nullable=False),
            sa.Column("payload_version", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("token_digest"),
            sa.ForeignKeyConstraint(["datasource_id"], ["analytics_datasources.id"], name="fk_analytics_execution_plans_datasource"),
            sa.CheckConstraint("expires_at > issued_at", name="ck_analytics_execution_plans_expiry"),
        )
        op.create_index("ix_analytics_execution_plans_expires_at", "analytics_execution_plans", ["expires_at"])
        op.create_index("ix_analytics_execution_plans_principal_expires_at", "analytics_execution_plans", ["principal_id", "expires_at"])
        op.create_index("ix_analytics_execution_plans_datasource_id", "analytics_execution_plans", ["datasource_id"])

    if not inspector.has_table("analytics_query_audits"):
        op.create_table(
            "analytics_query_audits",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("principal_id", sa.String(length=64), nullable=False),
            sa.Column("datasource_id", sa.String(length=64), nullable=True),
            sa.Column("phase", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("query_hash", sa.String(length=64), nullable=True),
            sa.Column("risk", sa.String(length=16), nullable=True),
            sa.Column("decision_code", sa.String(length=64), nullable=True),
            sa.Column("schema_version", sa.String(length=64), nullable=True),
            sa.Column("policy_version", sa.String(length=64), nullable=True),
            sa.Column("estimated_rows", sa.Integer(), nullable=True),
            sa.Column("engine_cost", sa.String(length=64), nullable=True),
            sa.Column("plan_digest", sa.String(length=64), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=True),
            sa.Column("byte_count", sa.Integer(), nullable=True),
            sa.Column("truncated", sa.Boolean(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            # 刻意没有指向 analytics_datasources 的外键：审计历史不得随数据源消失。
            sa.CheckConstraint(f"phase IN ({_PHASES})", name="ck_analytics_query_audits_phase"),
            sa.CheckConstraint(f"status IN ({_AUDIT_STATUSES})", name="ck_analytics_query_audits_status"),
            sa.CheckConstraint(f"risk IS NULL OR risk IN ({_RISKS})", name="ck_analytics_query_audits_risk"),
        )
        op.create_index("ix_analytics_query_audits_started_at", "analytics_query_audits", ["started_at"])
        op.create_index("ix_analytics_query_audits_principal_started_at", "analytics_query_audits", ["principal_id", "started_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("analytics_query_audits"):
        op.drop_index("ix_analytics_query_audits_principal_started_at", table_name="analytics_query_audits")
        op.drop_index("ix_analytics_query_audits_started_at", table_name="analytics_query_audits")
        op.drop_table("analytics_query_audits")

    if inspector.has_table("analytics_execution_plans"):
        op.drop_index("ix_analytics_execution_plans_datasource_id", table_name="analytics_execution_plans")
        op.drop_index("ix_analytics_execution_plans_principal_expires_at", table_name="analytics_execution_plans")
        op.drop_index("ix_analytics_execution_plans_expires_at", table_name="analytics_execution_plans")
        op.drop_table("analytics_execution_plans")

    if inspector.has_table("analytics_metrics"):
        op.drop_table("analytics_metrics")

    if inspector.has_table("analytics_access_policies"):
        op.drop_table("analytics_access_policies")

    if inspector.has_table("analytics_schema_snapshots"):
        op.drop_table("analytics_schema_snapshots")

    if inspector.has_table("analytics_datasources"):
        op.drop_table("analytics_datasources")
