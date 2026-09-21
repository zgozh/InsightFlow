"""SQL 单次 plan store 测试（Phase 2C1 任务 5）。

关键不变量：

- `claim` 是**单条数据库原子语句** `DELETE ... RETURNING`，绝不允许 SELECT-then-DELETE，
  也不允许用 `asyncio.Lock` 或 dict 模拟数据库原子性；
- 摘要匹配即消费：错 principal、已过期、载荷损坏、未知 payload 版本都已被删除，
  对外统一返回 `None`；
- 原始 token 永不落库，任何列都不含它；
- 容量与过期清理在同一个短事务内完成，且事务不包围任何业务数据库网络 I/O。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import ExecutionPlanStoreError, StoredExecutionPlan
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionLimits,
    PreparedQuery,
    QueryCostEstimate,
    QueryRisk,
)
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.codec import PLAN_PAYLOAD_VERSION
from app.analytics.infrastructure.persistence.plan_store import SqlExecutionPlanStore

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64


def _plan(*, digest=_DIGEST, principal_id="user-1", issued_at=_NOW, ttl_seconds=60):
    return StoredExecutionPlan(
        token_digest=digest,
        principal_id=principal_id,
        datasource=DatasourceDefinition(
            id="ds-1",
            owner_id="user-1",
            name="Warehouse",
            engine=DatasourceEngine.POSTGRESQL,
            secret_ref="env://ANALYTICS_DS",
            default_schema="public",
            status=DatasourceStatus.ACTIVE,
        ),
        authorized=AuthorizedQuerySpec(
            prepared=PreparedQuery(sql="SELECT id FROM orders LIMIT 10", engine=DatasourceEngine.POSTGRESQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
            datasource_id="ds-1",
            principal_id="user-1",
            schema_version="s1",
            policy_version="p1",
            relations=("public.orders",),
            columns=("public.orders.id",),
            functions=(),
            risk=QueryRisk.LOW,
        ),
        estimate=QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64),
        limits=ExecutionLimits(
            connect_timeout_ms=5_000,
            statement_timeout_ms=10_000,
            cancellation_grace_ms=500,
            max_estimated_rows=100_000,
            max_engine_cost=Decimal("10000"),
            max_explain_bytes=1_048_576,
            max_result_columns=64,
            max_result_rows=10,
            max_result_bytes=4_194_304,
            plan_ttl_seconds=60,
        ),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False)


@contextmanager
def _record_statements(engine):
    """记录真实发到数据库的语句，用来证明 claim 不是 SELECT-then-DELETE。"""

    statements: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)


@pytest_asyncio.fixture
async def engine(tmp_path):
    instance = _engine(tmp_path / "plan-store.db")
    try:
        await bootstrap_analytics_schema(instance, backend="sqlite")
        yield instance
    finally:
        await instance.dispose()


@pytest_asyncio.fixture
async def sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _store(sessions, *, max_entries=8):
    return SqlExecutionPlanStore(sessions, max_entries=max_entries)


async def _seed_datasource(sessions) -> None:
    """plan 表对 datasource 有外键；SQLite 默认不强制外键，所以这里显式建一行。

    时间用字面量字符串而不是绑定 datetime：原生 `text()` 绑定会走 sqlite3 已弃用的默认
    datetime adapter，污染测试输出的告警。
    """

    async with sessions() as session:
        await session.execute(
            text(
                "INSERT INTO analytics_datasources (id, owner_id, name, engine, secret_ref, default_schema, status, created_at, updated_at) "
                "VALUES ('ds-1', 'user-1', 'Warehouse', 'postgresql', 'env://ANALYTICS_DS', 'public', 'active', '2026-09-22 12:00:00.000000', '2026-09-22 12:00:00.000000')"
            )
        )
        await session.commit()


# --- 基本行为 ---------------------------------------------------------------


def test_the_store_requires_a_positive_capacity(sessions):
    with pytest.raises(ValueError):
        _store(sessions, max_entries=0)
    with pytest.raises(ValueError):
        _store(sessions, max_entries=True)


@pytest.mark.asyncio
async def test_a_plan_round_trips_and_is_consumed_once(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())

    claimed = await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW)

    assert claimed == _plan()
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_only_the_token_digest_is_persisted(sessions):
    await _seed_datasource(sessions)
    await _store(sessions).put(_plan())

    async with sessions() as session:
        payload = (await session.execute(text("SELECT payload_json FROM analytics_execution_plans"))).scalar_one()
        columns = (await session.execute(text("SELECT token_digest, payload_version FROM analytics_execution_plans"))).one()

    assert columns[0] == _DIGEST
    assert columns[1] == PLAN_PAYLOAD_VERSION
    # payload 里只有 canonical SQL 与 opaque secret_ref，没有原始 token。
    assert "fixed-plan-token" not in payload
    assert "env://ANALYTICS_DS" in payload


@pytest.mark.asyncio
async def test_a_digest_collision_is_a_stable_error(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())

    with pytest.raises(ExecutionPlanStoreError) as error:
        await store.put(_plan())

    assert error.value.reason == "digest_conflict"


@pytest.mark.asyncio
async def test_capacity_is_enforced_and_purged_expired_entries_free_slots(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions, max_entries=1)
    await store.put(_plan(digest="a" * 64, issued_at=_NOW, ttl_seconds=60))

    with pytest.raises(ExecutionPlanStoreError) as error:
        await store.put(_plan(digest="b" * 64, issued_at=_NOW, ttl_seconds=60))
    assert error.value.reason == "capacity_exceeded"

    # 过期记录必须在容量判断之前被清理，否则过期条目会长期占用容量。
    later = _NOW + timedelta(seconds=61)
    await store.put(_plan(digest="c" * 64, issued_at=later, ttl_seconds=60))

    assert await store.claim(token_digest="a" * 64, principal_id="user-1", now=later) is None
    assert await store.claim(token_digest="c" * 64, principal_id="user-1", now=later) is not None


@pytest.mark.asyncio
async def test_purge_expired_is_public_and_idempotent(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan(ttl_seconds=60))

    await store.purge_expired(now=_NOW + timedelta(seconds=60))
    await store.purge_expired(now=_NOW + timedelta(seconds=60))

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_revoke_removes_the_plan_and_is_idempotent(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())

    await store.revoke(token_digest=_DIGEST)
    await store.revoke(token_digest=_DIGEST)

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


# --- 统一不可用：任何不匹配都消费 token -------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_digest_returns_none(sessions):
    assert await _store(sessions).claim(token_digest="f" * 64, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_a_wrong_principal_consumes_the_token(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())

    assert await store.claim(token_digest=_DIGEST, principal_id="user-2", now=_NOW) is None
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_an_expired_token_is_consumed(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan(ttl_seconds=60))
    later = _NOW + timedelta(seconds=120)

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=later) is None
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=later) is None


@pytest.mark.asyncio
async def test_a_corrupt_payload_is_consumed_without_raising(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())
    async with sessions() as session:
        await session.execute(text("UPDATE analytics_execution_plans SET payload_json = '{not json'"))
        await session.commit()

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_an_unknown_payload_version_is_consumed_without_raising(sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())
    async with sessions() as session:
        await session.execute(text("UPDATE analytics_execution_plans SET payload_version = 99"))
        await session.commit()

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


# --- 原子性证据 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_issues_exactly_one_delete_returning(engine, sessions):
    await _seed_datasource(sessions)
    store = _store(sessions)
    await store.put(_plan())

    with _record_statements(engine) as statements:
        await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW)

    deletes = [statement for statement in statements if statement.strip().upper().startswith("DELETE")]
    selects = [statement for statement in statements if statement.strip().upper().startswith("SELECT")]
    assert len(deletes) == 1
    assert "RETURNING" in deletes[0].upper()
    assert selects == [], "claim must not read before deleting"


@pytest.mark.asyncio
async def test_two_independent_stores_racing_for_one_token_yield_exactly_one_winner(tmp_path):
    path = tmp_path / "race.db"
    first_engine = _engine(path)
    second_engine = _engine(path)
    try:
        await bootstrap_analytics_schema(first_engine, backend="sqlite")
        first = SqlExecutionPlanStore(async_sessionmaker(first_engine, expire_on_commit=False), max_entries=8)
        second = SqlExecutionPlanStore(async_sessionmaker(second_engine, expire_on_commit=False), max_entries=8)
        await _seed_datasource(async_sessionmaker(first_engine, expire_on_commit=False))
        await first.put(_plan())

        import asyncio

        results = await asyncio.gather(
            first.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW),
            second.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW),
        )
    finally:
        await first_engine.dispose()
        await second_engine.dispose()

    assert sum(result is not None for result in results) == 1


def test_the_sql_adapter_uses_no_in_process_lock():
    """按 AST 判定：进程内锁在第二个 worker 上完全失效，是本阶段必须消除的实现。

    文本子串会被 docstring 里"禁止 asyncio.Lock"这类说明误伤，所以检查 import 与调用名。
    """

    import ast

    source = (Path(__file__).resolve().parents[1] / "app/analytics/infrastructure/persistence/plan_store.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "asyncio" not in imported
    assert "threading" not in imported

    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "Lock" not in attributes
