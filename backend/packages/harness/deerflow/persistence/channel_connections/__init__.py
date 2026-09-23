"""User-owned IM channel connection persistence — ORM models only.

Phase 5 删除了 Channels/IM 产品面：repository 与凭据加密器随之删除，只保留 ORM
model 以维持 `Base.metadata` 与 Alembic 历史链一致。
"""

from deerflow.persistence.channel_connections.model import (
    ChannelConnectionRow,
    ChannelConversationRow,
    ChannelCredentialRow,
    ChannelOAuthStateRow,
)

__all__ = [
    "ChannelConnectionRow",
    "ChannelConversationRow",
    "ChannelCredentialRow",
    "ChannelOAuthStateRow",
]
