"""耐久成功查询证据表。

Revision ID: 0003_analytics_query_evidence
Revises: 0002_analytics_analysis_reports
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_analytics_query_evidence"
down_revision: str | Sequence[str] | None = "0002_analytics_analysis_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_query_evidence",
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("snapshot_bytes", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("principal_id", "thread_id", "run_id", "evidence_id", name="pk_analytics_query_evidence"),
        sa.CheckConstraint("snapshot_bytes >= 0", name="ck_analytics_query_evidence_snapshot_bytes"),
    )


def downgrade() -> None:
    op.drop_table("analytics_query_evidence")
