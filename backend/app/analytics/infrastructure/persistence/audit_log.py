"""SQL 审计账本适配器（Phase 2C1）。

审计是安全门禁，不是尽力而为的日志：`start()` 必须在任何真实业务数据库 I/O 之前成功，
`finish()` 只更新恰好一条 `started` 行。

这里刻意不接受任意 dict，也不接受"顺带带上 SQL/结果做调试"的做法——审计表结构本身就不含
这些字段（见 `models.QueryAuditRow`），因此这条约束在数据库层也有兜底。

`started` 长期未完成表示 worker 崩溃或终态写入失败，是有价值的保守证据，读取接口不得把它
伪装成成功；本阶段不做自动删除，保留策略留给部署验收阶段配置。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import PersistenceConflictError
from app.analytics.domain import QueryAuditCompletion, QueryAuditStart, QueryAuditStatus
from app.analytics.infrastructure.persistence.codec import _render_decimal
from app.analytics.infrastructure.persistence.models import QueryAuditRow


def _as_utc(value: datetime) -> datetime:
    """审计时间统一按 UTC 落库：SQLite 不保存偏移，混用 naive/aware 无法比较。"""

    if value.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    return value.astimezone(UTC)


class SqlQueryAuditLog:
    """`QueryAuditLog` 端口的持久化实现。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def start(self, entry: QueryAuditStart) -> str:
        audit_id = str(uuid.uuid4())
        async with self._session_factory() as session:
            session.add(
                QueryAuditRow(
                    id=audit_id,
                    principal_id=entry.principal_id,
                    datasource_id=entry.datasource_id,
                    phase=entry.phase.value,
                    status=QueryAuditStatus.STARTED.value,
                    query_hash=entry.query_hash,
                    risk=None if entry.risk is None else entry.risk.value,
                    schema_version=entry.schema_version,
                    policy_version=entry.policy_version,
                    started_at=_as_utc(entry.started_at),
                )
            )
            await session.commit()
        return audit_id

    async def finish(self, completion: QueryAuditCompletion) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                update(QueryAuditRow)
                .where(QueryAuditRow.id == completion.audit_id, QueryAuditRow.status == QueryAuditStatus.STARTED.value)
                .values(
                    status=QueryAuditStatus.COMPLETED.value,
                    decision_code=completion.decision_code,
                    risk=None if completion.risk is None else completion.risk.value,
                    estimated_rows=completion.estimated_rows,
                    # 与 plan payload 共用同一条 canonical decimal 规则，避免两处漂移。
                    engine_cost=None if completion.engine_cost is None else _render_decimal(completion.engine_cost),
                    plan_digest=completion.plan_digest,
                    row_count=completion.row_count,
                    byte_count=completion.byte_count,
                    truncated=completion.truncated,
                    latency_ms=completion.latency_ms,
                    finished_at=_as_utc(completion.finished_at),
                )
            )
            if result.rowcount != 1:
                # 0 行（未知 ID 或已经 completed）与多行都不是可以忽略的状态：
                # 前者会让"审计已终态"变成假象，必须显式失败。
                await session.rollback()
                raise PersistenceConflictError("audit_record_not_completable")
            await session.commit()
