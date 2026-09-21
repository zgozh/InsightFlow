"""SQL 审计账本适配器测试（Phase 2C1 任务 6 的 adapter 部分）。

审计不是"尽力而为的日志"，而是访问真实业务数据库前的门禁。因此这里的断言集中在：

- `start()` 只插入 `started` 行并返回审计 ID（不接受、也不生成任何 payload/dict）；
- `finish()` 只更新**恰好一条** `started` 行，0 行或多行都是稳定持久化错误；
- 表结构里不存在 SQL、token/digest、secret ref、DSN、口令、驱动异常与结果值字段。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import PersistenceConflictError
from app.analytics.domain import (
    ExecutionDecisionCode,
    QueryAuditCompletion,
    QueryAuditPhase,
    QueryAuditStart,
    QueryAuditStatus,
    QueryRisk,
)
from app.analytics.infrastructure.persistence.audit_log import SqlQueryAuditLog
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.models import QueryAuditRow

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_BANNED_COLUMN_FRAGMENTS = ("sql", "token", "secret", "dsn", "password", "credential", "result", "explain")


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False)


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = _engine(tmp_path / "audit.db")
    try:
        await bootstrap_analytics_schema(engine, backend="sqlite")
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _start(**overrides) -> QueryAuditStart:
    values = {
        "principal_id": "user-1",
        "datasource_id": "ds-1",
        "phase": QueryAuditPhase.PLAN,
        "started_at": _NOW,
        "query_hash": "a" * 64,
        "risk": QueryRisk.LOW,
        "schema_version": "s1",
        "policy_version": "p1",
    }
    values.update(overrides)
    return QueryAuditStart(**values)


def _completion(**overrides) -> QueryAuditCompletion:
    values = {
        "audit_id": "unused",
        "decision_code": ExecutionDecisionCode.PLAN_CREATED.value,
        "finished_at": _NOW + timedelta(milliseconds=42),
        "risk": QueryRisk.LOW,
        "estimated_rows": 10,
        "engine_cost": Decimal("12.5"),
        "plan_digest": "b" * 64,
        "row_count": 3,
        "byte_count": 128,
        "truncated": False,
        "latency_ms": 42,
    }
    values.update(overrides)
    return QueryAuditCompletion(**values)


async def _rows(sessions):
    async with sessions() as session:
        return (await session.execute(select(QueryAuditRow))).scalars().all()


# --- start ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_inserts_a_started_row_and_returns_only_an_id(sessions):
    log = SqlQueryAuditLog(sessions)

    audit_id = await log.start(_start())

    assert isinstance(audit_id, str) and audit_id
    rows = await _rows(sessions)
    assert len(rows) == 1
    row = rows[0]
    assert row.id == audit_id
    assert row.status == QueryAuditStatus.STARTED.value
    assert row.phase == QueryAuditPhase.PLAN.value
    assert row.principal_id == "user-1"
    assert row.datasource_id == "ds-1"
    assert row.query_hash == "a" * 64
    assert row.risk == QueryRisk.LOW.value
    assert row.schema_version == "s1"
    assert row.policy_version == "p1"
    # started 记录可以尚未有最终决定。
    assert row.decision_code is None
    assert row.finished_at is None


@pytest.mark.asyncio
async def test_start_returns_distinct_ids(sessions):
    log = SqlQueryAuditLog(sessions)

    first = await log.start(_start())
    second = await log.start(_start())

    assert first != second
    assert len(await _rows(sessions)) == 2


@pytest.mark.asyncio
async def test_start_accepts_a_minimal_entry_without_datasource_or_metadata(sessions):
    log = SqlQueryAuditLog(sessions)

    await log.start(QueryAuditStart(principal_id="user-1", datasource_id=None, phase=QueryAuditPhase.POLICY, started_at=_NOW))

    row = (await _rows(sessions))[0]
    assert row.datasource_id is None
    assert row.query_hash is None
    assert row.schema_version is None


# --- finish -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_finish_updates_exactly_one_started_row(sessions):
    log = SqlQueryAuditLog(sessions)
    audit_id = await log.start(_start())

    await log.finish(_completion(audit_id=audit_id))

    row = (await _rows(sessions))[0]
    assert row.status == QueryAuditStatus.COMPLETED.value
    assert row.decision_code == ExecutionDecisionCode.PLAN_CREATED.value
    assert row.estimated_rows == 10
    assert row.engine_cost == "12.5"
    assert row.plan_digest == "b" * 64
    assert row.row_count == 3
    assert row.byte_count == 128
    assert row.truncated is False
    assert row.latency_ms == 42
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_finish_accepts_an_unknown_audit_id_as_a_stable_error(sessions):
    log = SqlQueryAuditLog(sessions)

    with pytest.raises(PersistenceConflictError) as error:
        await log.finish(_completion(audit_id="does-not-exist"))

    assert error.value.reason == "audit_record_not_completable"


@pytest.mark.asyncio
async def test_finish_refuses_to_overwrite_an_already_completed_row(sessions):
    log = SqlQueryAuditLog(sessions)
    audit_id = await log.start(_start())
    await log.finish(_completion(audit_id=audit_id))

    with pytest.raises(PersistenceConflictError):
        await log.finish(_completion(audit_id=audit_id, row_count=999))

    row = (await _rows(sessions))[0]
    assert row.row_count == 3


@pytest.mark.asyncio
async def test_finish_carries_only_the_supplied_metadata(sessions):
    log = SqlQueryAuditLog(sessions)
    audit_id = await log.start(_start())

    await log.finish(QueryAuditCompletion(audit_id=audit_id, decision_code=ExecutionDecisionCode.PLAN_UNAVAILABLE.value, finished_at=_NOW))

    row = (await _rows(sessions))[0]
    assert row.decision_code == ExecutionDecisionCode.PLAN_UNAVAILABLE.value
    assert row.estimated_rows is None and row.engine_cost is None and row.plan_digest is None
    assert row.row_count is None and row.byte_count is None and row.truncated is None and row.latency_ms is None


@pytest.mark.asyncio
async def test_a_started_row_that_never_finishes_stays_visible_as_started(sessions):
    """worker 崩溃或终态写入失败会留下 started —— 这本身就是有价值的保守证据。"""

    log = SqlQueryAuditLog(sessions)
    await log.start(_start())

    row = (await _rows(sessions))[0]
    assert row.status == QueryAuditStatus.STARTED.value
    assert row.finished_at is None


# --- 表结构：敏感字段边界 ---------------------------------------------------


def test_the_audit_table_has_no_sensitive_columns():
    columns = set(QueryAuditRow.__table__.columns.keys())

    for fragment in _BANNED_COLUMN_FRAGMENTS:
        offenders = sorted(name for name in columns if fragment in name.lower())
        assert offenders == [], f"audit schema must not carry {fragment!r}: {offenders}"

    # 字段集合本身也钉死：机械扩字段是最容易把敏感值带进审计的方式。
    assert columns == {
        "id",
        "principal_id",
        "datasource_id",
        "phase",
        "status",
        "query_hash",
        "risk",
        "decision_code",
        "schema_version",
        "policy_version",
        "estimated_rows",
        "engine_cost",
        "plan_digest",
        "row_count",
        "byte_count",
        "truncated",
        "latency_ms",
        "started_at",
        "finished_at",
    }


@pytest.mark.asyncio
async def test_no_audit_value_contains_sql_or_credentials(sessions):
    log = SqlQueryAuditLog(sessions)
    audit_id = await log.start(_start())
    await log.finish(_completion(audit_id=audit_id))

    async with sessions() as session:
        dumped = (
            await session.execute(
                text(
                    "SELECT id || '|' || principal_id || '|' || coalesce(datasource_id, '') || '|' || phase || '|' || status || '|' || "
                    "coalesce(query_hash, '') || '|' || coalesce(decision_code, '') || '|' || coalesce(schema_version, '') || '|' || "
                    "coalesce(policy_version, '') || '|' || coalesce(engine_cost, '') || '|' || coalesce(plan_digest, '') FROM analytics_query_audits"
                )
            )
        ).scalar_one()

    for banned in ("SELECT", "postgres://", "env://", "password"):
        assert banned not in dumped
