"""分析报告索引表（Phase 4 §6）。

Revision ID: 0002_analytics_analysis_reports
Revises: 0001_analytics_control_plane
Create Date: 2026-09-22

纯前向迁移：只新建 `analytics_analysis_reports`，不触碰 `0001` 建出的六张表，也不触碰 Harness
的链（那是另一条链、另一个版本表）。DDL 逐列镜像
`app/analytics/infrastructure/persistence/models.py::AnalysisReportRow`；两侧漂移由
`tests/test_analytics_persistence_migrations.py` 的逐列比对测试钉住。

这张表刻意**没有**指向 Harness `threads_meta` / `runs` 的外键：跨链外键是禁止的，而且报告索引
必须比会话活得更久。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_analytics_analysis_reports"
down_revision: str | Sequence[str] | None = "0001_analytics_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 `models.REPORT_STATUSES` 逐字一致。
_REPORT_STATUSES = "'published'"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("analytics_analysis_reports"):
        return

    op.create_table(
        "analytics_analysis_reports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("principal_id", "thread_id", "run_id", "artifact_path", name="uq_analytics_analysis_reports_identity"),
        sa.CheckConstraint(f"status IN ({_REPORT_STATUSES})", name="ck_analytics_analysis_reports_status"),
    )
    op.create_index("ix_analytics_analysis_reports_principal_created_at", "analytics_analysis_reports", ["principal_id", "created_at"])
    op.create_index("ix_analytics_analysis_reports_thread_id", "analytics_analysis_reports", ["thread_id"])
    op.create_index("ix_analytics_analysis_reports_run_id", "analytics_analysis_reports", ["run_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("analytics_analysis_reports"):
        return

    op.drop_index("ix_analytics_analysis_reports_run_id", table_name="analytics_analysis_reports")
    op.drop_index("ix_analytics_analysis_reports_thread_id", table_name="analytics_analysis_reports")
    op.drop_index("ix_analytics_analysis_reports_principal_created_at", table_name="analytics_analysis_reports")
    op.drop_table("analytics_analysis_reports")
