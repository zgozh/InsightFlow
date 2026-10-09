"""显式指标授权表。

Revision ID: 0004_metric_grants
Revises: 0003_analytics_query_evidence
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_metric_grants"
down_revision: str | Sequence[str] | None = "0003_analytics_query_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_metric_grants",
        sa.Column("metric_owner_id", sa.String(length=64), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("metric_owner_id", "metric_key", "principal_id", name="pk_analytics_metric_grants"),
        sa.ForeignKeyConstraint(
            ["metric_owner_id", "metric_key"],
            ["analytics_metrics.owner_id", "analytics_metrics.key"],
            name="fk_analytics_metric_grants_metric",
        ),
    )
    op.create_index("ix_analytics_metric_grants_principal_id", "analytics_metric_grants", ["principal_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analytics_metric_grants_principal_id", table_name="analytics_metric_grants")
    op.drop_table("analytics_metric_grants")
