"""Shared inbound webhook dedupe table (issue #4120).

ORM model only. Phase 5 删除了 Channels/IM 产品面，写入方
``app.channels.dedupe_store.PostgresInboundDedupeStore`` 已删除；表本身保留，
因为它必须与 Alembic 历史链（0009_webhook_dedupe）保持一致。
"""
