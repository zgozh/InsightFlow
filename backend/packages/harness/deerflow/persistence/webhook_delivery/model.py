"""保留的 webhook schema ORM 映射。

历史迁移仍要求该表与 ORM 保持一致；当前仓库没有对应的 webhook 写入服务。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class WebhookDeliveryRow(Base):
    __tablename__ = "webhook_deliveries"

    # Keep the historical composite key (channel, workspace_id, chat_id, message_id).
    # Using the four columns
    # directly avoids any string-joined surrogate key — important because the
    # components can contain characters (e.g. NUL) that are illegal in a single
    # Postgres TEXT column, and keeps the ON CONFLICT target natural.
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(512), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(512), nullable=False)
    message_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("channel", "workspace_id", "chat_id", "message_id", name="pk_webhook_deliveries"),
        Index("ix_webhook_deliveries_first_seen", "first_seen"),
    )
