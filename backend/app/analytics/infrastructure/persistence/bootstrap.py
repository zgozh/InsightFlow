"""Analytics 独立迁移链的 fail-closed bootstrap（Phase 2C1）。

设计要点：

- **只前进，不重建**：空库直接 `upgrade head`（不使用 `create_all + stamp head` 捷径）；
  版本表里是未知 revision、空表、多版本行，或有 `analytics_*` 表却没有版本表，一律拒绝启动。
  bootstrap 绝不自动 stamp 一个它不认识的 revision。
- **并发安全**：PostgreSQL 使用与 Harness 不同的固定 advisory lock（跨进程真串行）；
  SQLite 用每 engine 的 `asyncio.Lock` 保证同进程串行，并设置 30 秒 `PRAGMA busy_timeout`
  让跨进程写入等待文件锁而不是立刻失败。多 worker 部署仍要求 PostgreSQL。
- **不在 DSN 上另建 engine**：迁移通过调用方注入的已有连接执行，因此自定义 PostgreSQL
  schema 的 search path、事务与锁都落在同一个会话语义里。

错误保持致命且脱敏：失败只抛出稳定 reason 的 `AnalyticsSchemaBootstrapError`，
原始异常用 `raise ... from` 保留在内部调试链上。
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from functools import partial
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.analytics.infrastructure.persistence.models import VERSION_TABLE_NAME

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_TABLE_PREFIX = "analytics_"
_SUPPORTED_BACKENDS = ("postgres", "sqlite")

# 与 Harness 的 `_PG_LOCK_KEY` 不同：两条链可以同时各自启动而互不阻塞，
# 也不会因为共用同一把锁而在 bootstrap 之间形成意外的顺序依赖。
_PG_LOCK_KEY = 0x1F10_2C10_5A11_7E01

_HEAD_REVISION: str | None = None


class AnalyticsSchemaBootstrapError(RuntimeError):
    """Analytics schema bootstrap 的稳定失败。只携带稳定 reason，不含 DSN 或驱动文本。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _build_alembic_config() -> AlembicConfig:
    config = AlembicConfig()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return config


def _get_known_revisions() -> tuple[str, frozenset[str]]:
    """从磁盘脚本树读出 head 与全部已知 revision；无 head 视为仓库损坏。"""

    global _HEAD_REVISION
    script = ScriptDirectory.from_config(_build_alembic_config())
    known = frozenset(revision.revision for revision in script.walk_revisions())
    if _HEAD_REVISION is None:
        head = script.get_current_head()
        if head is None:
            raise AnalyticsSchemaBootstrapError("analytics_schema_has_no_head_revision")
        _HEAD_REVISION = head
    return _HEAD_REVISION, known


def _reflect_state(sync_conn) -> dict:
    """读取数据库侧状态：Analytics 表集合与版本表内容。"""

    inspector = sa_inspect(sync_conn)
    names = set(inspector.get_table_names())
    tables = sorted(name for name in names if name.startswith(_TABLE_PREFIX))
    has_version_table = VERSION_TABLE_NAME in names
    revisions: list[str] = []
    if has_version_table:
        # 表名是仓库常量，不是外部输入。
        revisions = [str(value) for value in sync_conn.execute(text(f"SELECT version_num FROM {VERSION_TABLE_NAME}")).scalars()]
    return {"analytics_tables": tables, "has_version_table": has_version_table, "version_rows": revisions}


def _validate_state(state: dict, *, known: frozenset[str]) -> str | None:
    """fail-closed 判定：只有「全新空库」与「已知单版本」两种状态允许继续。"""

    revisions = state["version_rows"]
    if not state["has_version_table"]:
        if state["analytics_tables"]:
            # 有表却没有版本表：来源不明的 schema，绝不自动 stamp。
            raise AnalyticsSchemaBootstrapError("analytics_schema_has_tables_without_version_table")
        return None
    if not revisions:
        # 版本表存在但为空：可能是被清空或被中断的初始化，不能当新库处理。
        raise AnalyticsSchemaBootstrapError("analytics_schema_version_table_empty")
    if len(revisions) != 1:
        raise AnalyticsSchemaBootstrapError("analytics_schema_has_multiple_versions")
    revision = revisions[0]
    if revision not in known:
        raise AnalyticsSchemaBootstrapError("analytics_schema_revision_unknown")
    return revision


def _upgrade_to_head(sync_conn, *, alembic_config: AlembicConfig, backend: str) -> None:
    """在调用方注入的连接上执行 `upgrade head`。"""

    if backend == "sqlite":
        # SQLite 的 busy timeout 是每连接属性，必须在真正写入的那条连接上设置。
        sync_conn.exec_driver_sql("PRAGMA busy_timeout=30000")
    alembic_config.attributes["connection"] = sync_conn
    try:
        alembic_command.upgrade(alembic_config, "head")
    except AnalyticsSchemaBootstrapError:
        raise
    except Exception as error:  # noqa: BLE001 - 迁移失败必须致命，且外发文本保持稳定
        raise AnalyticsSchemaBootstrapError("analytics_schema_migration_failed") from error


_SQLITE_LOCKS: weakref.WeakKeyDictionary[AsyncEngine, asyncio.Lock] = weakref.WeakKeyDictionary()


def _sqlite_lock(engine: AsyncEngine) -> asyncio.Lock:
    """每 engine 一把锁：`asyncio.Lock` 绑定首次使用它的事件循环，按 id(engine) 缓存会在
    地址复用后把已死循环的锁交给新 engine。"""

    lock = _SQLITE_LOCKS.get(engine)
    if lock is None:
        lock = asyncio.Lock()
        _SQLITE_LOCKS[engine] = lock
    return lock


async def _bootstrap_postgres(engine: AsyncEngine, *, known: frozenset[str], alembic_config: AlembicConfig) -> None:
    async with engine.connect() as lock_conn:
        # 被托管的 PostgreSQL 常带 idle_in_transaction_session_timeout；锁是会话级的，
        # 会话被宿主杀掉会静默释放锁，另一实例就会并发跑 DDL。
        await lock_conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
        await lock_conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _PG_LOCK_KEY})
        try:
            state = await lock_conn.run_sync(_reflect_state)
            _validate_state(state, known=known)
            # PostgreSQL 支持事务性 DDL，Alembic 自己会开启并提交迁移事务，
            # 因此这里用 connect() 而不是 begin()，避免与 Alembic 的事务嵌套。
            async with engine.connect() as conn:
                await conn.run_sync(partial(_upgrade_to_head, alembic_config=alembic_config, backend="postgres"))
        finally:
            try:
                await lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _PG_LOCK_KEY})
            except Exception:  # noqa: BLE001 - 连接关闭本身会释放会话锁
                logger.warning("analytics bootstrap: pg_advisory_unlock raised; session close will release", exc_info=True)


async def _bootstrap_sqlite(engine: AsyncEngine, *, known: frozenset[str], alembic_config: AlembicConfig) -> None:
    async with _sqlite_lock(engine):
        async with engine.connect() as conn:
            state = await conn.run_sync(_reflect_state)
            _validate_state(state, known=known)
        # SQLite 的 `transactional_ddl` 为 False：Alembic 不会自己开启或提交迁移事务，
        # 版本表写入必须由调用方提交，否则表建好了却没有任何 revision 记录。
        async with engine.begin() as conn:
            await conn.run_sync(partial(_upgrade_to_head, alembic_config=alembic_config, backend="sqlite"))


async def bootstrap_analytics_schema(engine: AsyncEngine, *, backend: str) -> None:
    """把 Analytics schema 带到 head。

    只接受调用方已经建立好的应用数据库 engine；`backend` 决定加锁策略，不做自动探测 ——
    猜错后端会静默降级成"没有跨进程保护"。
    """

    if backend not in _SUPPORTED_BACKENDS:
        raise ValueError(f"analytics bootstrap: unsupported backend {backend!r}")

    _, known = await asyncio.to_thread(_get_known_revisions)
    alembic_config = _build_alembic_config()

    if backend == "postgres":
        await _bootstrap_postgres(engine, known=known, alembic_config=alembic_config)
    else:
        await _bootstrap_sqlite(engine, known=known, alembic_config=alembic_config)

    logger.info("analytics bootstrap: complete (backend=%s)", backend)
