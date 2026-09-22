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
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import PersistenceConflictError, PersistenceDataError
from app.analytics.domain import (
    QueryAuditCompletion,
    QueryAuditPhase,
    QueryAuditRecord,
    QueryAuditStart,
    QueryAuditStatus,
    QueryRisk,
)
from app.analytics.infrastructure.persistence.codec import _render_decimal
from app.analytics.infrastructure.persistence.models import QueryAuditRow

#: 单页硬上限。默认值来自 `AnalyticsConfig.audit_page_size`，客户端只能向下请求。
MAX_AUDIT_PAGE_SIZE = 100


def _as_utc(value: datetime) -> datetime:
    """审计时间统一按 UTC 落库：SQLite 不保存偏移，混用 naive/aware 无法比较。"""

    if value.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise PersistenceDataError("row_invalid_audit_cost") from error
    if not parsed.is_finite():
        raise PersistenceDataError("row_invalid_audit_cost")
    return parsed


def _row_to_record(row: QueryAuditRow) -> QueryAuditRecord:
    """损坏行整体失败：读取接口绝不返回"部分正确"的审计证据。"""

    try:
        started_at = row.started_at if row.started_at.tzinfo is not None else row.started_at.replace(tzinfo=UTC)
        finished_at = row.finished_at
        if finished_at is not None and finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=UTC)
        return QueryAuditRecord(
            id=row.id,
            principal_id=row.principal_id,
            datasource_id=row.datasource_id,
            phase=QueryAuditPhase(row.phase),
            status=QueryAuditStatus(row.status),
            started_at=started_at,
            query_hash=row.query_hash,
            risk=None if row.risk is None else QueryRisk(row.risk),
            decision_code=row.decision_code,
            schema_version=row.schema_version,
            policy_version=row.policy_version,
            estimated_rows=row.estimated_rows,
            engine_cost=_optional_decimal(row.engine_cost),
            plan_digest=row.plan_digest,
            row_count=row.row_count,
            byte_count=row.byte_count,
            truncated=row.truncated,
            latency_ms=row.latency_ms,
            finished_at=finished_at,
        )
    except PersistenceDataError:
        raise
    except (ValueError, TypeError) as error:
        raise PersistenceDataError("row_invalid_audit_record") from error


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

    async def list_for_principal(
        self,
        *,
        principal_id: str,
        limit: int,
        before_started_at: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[QueryAuditRecord, ...]:
        """按 `(started_at DESC, id DESC)` 的 keyset 分页读取一个 principal 的审计。

        keyset 而非 OFFSET：审计是持续追加的，OFFSET 在新行插入后会重复或漏掉记录。
        游标两个字段要么都给、要么都不给——只用其一无法表达"严格更早"。
        """

        if not isinstance(principal_id, str) or not principal_id.strip() or principal_id != principal_id.strip():
            raise ValueError("principal_id must be a non-empty trimmed string")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_AUDIT_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_AUDIT_PAGE_SIZE}")
        if (before_started_at is None) != (before_id is None):
            raise ValueError("before_started_at and before_id must be provided together")

        statement = select(QueryAuditRow).where(QueryAuditRow.principal_id == principal_id)
        if before_started_at is not None and before_id is not None:
            cursor = _as_utc(before_started_at)
            if not isinstance(before_id, str) or not before_id.strip() or before_id != before_id.strip():
                raise ValueError("before_id must be a non-empty trimmed string")
            # 行值比较 (started_at, id) < (cursor) 的等价显式写法，避免依赖方言的 row value 支持。
            statement = statement.where(
                or_(
                    QueryAuditRow.started_at < cursor,
                    and_(QueryAuditRow.started_at == cursor, QueryAuditRow.id < before_id),
                )
            )
        statement = statement.order_by(QueryAuditRow.started_at.desc(), QueryAuditRow.id.desc()).limit(limit)

        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(_row_to_record(row) for row in rows)
