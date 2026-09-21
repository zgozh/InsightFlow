"""基于应用数据库的单次 plan store（Phase 2C1）。

`InMemoryExecutionPlanStore` 只在一个进程里有效；本模块用应用数据库提供跨进程、跨重启的
原子能力消费。四个方法都只做数据库操作，不发起任何业务数据库 I/O。

原子性来源（架构规格 §6）：

- `claim()` 只用**一条** `DELETE ... RETURNING`：先删除再在 adapter 内校验 principal、过期与
  payload。两个独立 worker 竞争同一 token 时数据库本身保证最多一个拿到行；不存在、过期、
  已领取、principal 不匹配与 payload 损坏对上层统一表现为 `None`（→ `PLAN_UNAVAILABLE`）。
  失败后绝不恢复 token，避免重放与重复成本。
- 禁止 SELECT-then-DELETE、禁止 dict、禁止 `asyncio.Lock`：进程内锁在第二个 worker 上
  完全失效，这正是 2B2 内存实现必须被替换的原因。
- `put()` 的容量判定在同一个短事务里完成，并且**不包围任何业务数据库网络 I/O**：
  PostgreSQL 用固定的 transaction-scoped advisory lock，SQLite 用 `BEGIN IMMEDIATE`
  获得数据库级写串行化。

只保存 token 的 SHA-256 摘要；原始 token 永不落库，摘要也永不写日志。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import ExecutionPlanStoreError, StoredExecutionPlan
from app.analytics.infrastructure.persistence.codec import PLAN_PAYLOAD_VERSION, decode_stored_plan, encode_stored_plan
from app.analytics.infrastructure.persistence.models import ExecutionPlanRow

# 与 bootstrap 使用同一把 Analytics 专用 key：capacity 事务之间互斥，但不与 Harness 的
# bootstrap 锁或 analytics bootstrap 锁互相阻塞（transaction-scoped，随事务释放）。
_CAPACITY_ADVISORY_LOCK_KEY = 0x1F10_2C10_5A11_7E02


def _as_utc(value: datetime) -> datetime:
    """统一到 UTC。

    两个原因：SQLite 不保存时区偏移，naive 值与 aware 值比较会直接抛 TypeError；
    而且只有全部按 UTC 落库，字符串排序才等价于时间排序。
    """

    if value.tzinfo is None:
        raise ValueError("plan store timestamps must be timezone-aware")
    return value.astimezone(UTC)


class SqlExecutionPlanStore:
    """`ExecutionPlanStore` 的持久化实现。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, max_entries: int) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self._session_factory = session_factory
        self._max_entries = max_entries

    async def _begin_capacity_transaction(self, session: AsyncSession) -> None:
        """在容量判定事务开始时取得写串行化。

        PostgreSQL 用固定的 transaction-scoped advisory lock（随 commit/rollback 自动释放）；
        SQLite 用 `BEGIN IMMEDIATE`：默认的 deferred 事务直到第一条写语句才占写锁，那样
        "先计数后插入"会在两个连接之间超额。SQLite 只用于单 worker 本地开发。
        """

        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CAPACITY_ADVISORY_LOCK_KEY})
        elif dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))

    async def put(self, plan: StoredExecutionPlan) -> None:
        async with self._session_factory() as session:
            await self._begin_capacity_transaction(session)
            try:
                issued_at = _as_utc(plan.issued_at)
                # 容量判断前先清理过期记录：否则过期条目会长期占用容量。
                await session.execute(delete(ExecutionPlanRow).where(ExecutionPlanRow.expires_at <= issued_at))

                taken = (await session.execute(select(ExecutionPlanRow.token_digest).where(ExecutionPlanRow.token_digest == plan.token_digest))).first()
                if taken is not None:
                    raise ExecutionPlanStoreError("digest_conflict")

                current = (await session.execute(select(func.count()).select_from(ExecutionPlanRow))).scalar_one()
                if current >= self._max_entries:
                    raise ExecutionPlanStoreError("capacity_exceeded")

                await session.execute(
                    insert(ExecutionPlanRow).values(
                        token_digest=plan.token_digest,
                        principal_id=plan.principal_id,
                        datasource_id=plan.datasource.id,
                        payload_version=PLAN_PAYLOAD_VERSION,
                        payload_json=encode_stored_plan(plan),
                        issued_at=issued_at,
                        expires_at=_as_utc(plan.expires_at),
                    )
                )
            except Exception:
                await session.rollback()
                raise
            await session.commit()

    async def claim(self, *, token_digest: str, principal_id: str, now: datetime) -> StoredExecutionPlan | None:
        async with self._session_factory() as session:
            # 单条语句完成「取出并删除」；删除先发生，因此任何后续校验失败都已经消费了 token。
            row = (
                await session.execute(
                    delete(ExecutionPlanRow)
                    .where(ExecutionPlanRow.token_digest == token_digest)
                    .returning(
                        ExecutionPlanRow.principal_id,
                        ExecutionPlanRow.payload_version,
                        ExecutionPlanRow.payload_json,
                        ExecutionPlanRow.expires_at,
                    )
                )
            ).first()
            await session.commit()

        if row is None:
            return None
        expires_at = row.expires_at if row.expires_at.tzinfo is not None else row.expires_at.replace(tzinfo=UTC)
        if row.principal_id != principal_id or expires_at <= _as_utc(now):
            return None
        try:
            return decode_stored_plan(row.payload_json, payload_version=row.payload_version)
        except Exception:  # noqa: BLE001 - 损坏 payload 已消费，统一表现为不可用
            return None

    async def purge_expired(self, *, now: datetime) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(ExecutionPlanRow).where(ExecutionPlanRow.expires_at <= _as_utc(now)))
            await session.commit()

    async def revoke(self, *, token_digest: str) -> None:
        """作废一个已签发但不可交付的 plan（审计 finish 失败时必须调用）。幂等。"""

        async with self._session_factory() as session:
            await session.execute(delete(ExecutionPlanRow).where(ExecutionPlanRow.token_digest == token_digest))
            await session.commit()
