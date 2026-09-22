"""分析报告索引的 SQL 适配器与并发幂等发布（Phase 4 任务 2）。

报告索引的安全诉求与审计账本一致：

- 只保存"谁在哪个 thread/run 发布了哪个 artifact"这一层索引元数据；
- `principal_id` 精确过滤，没有"全部租户"的读法；
- 发布是**先查后插 + 唯一键兜底**的幂等写入：重试不产生第二行，内容不同不得静默覆盖；
- 损坏行整页失败，绝不返回"部分正确"的证据。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import PersistenceDataError
from app.analytics.domain import AnalysisReport, ReportPublishCode, ReportStatus
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.models import AnalysisReportRow
from app.analytics.infrastructure.persistence.reports import MAX_REPORT_PAGE_SIZE, SqlAnalysisReportRepository

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _engine(path):
    # aiosqlite 会把 timeout 透传给 sqlite3.connect：并发写入测试必须等锁而不是直接报错。
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False, connect_args={"timeout": 30})


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = _engine(tmp_path / "reports.db")
    try:
        await bootstrap_analytics_schema(engine, backend="sqlite")
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _report(**overrides) -> AnalysisReport:
    values = {
        "id": "report-1",
        "principal_id": "user-1",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "artifact_path": "/mnt/user-data/outputs/business-analysis.md",
        "title": "2026 Q3 经营分析",
        "status": ReportStatus.PUBLISHED,
        "evidence_ids": (_HASH_A,),
        "created_at": _NOW,
    }
    values.update(overrides)
    return AnalysisReport(**values)


async def _count(sessions) -> int:
    async with sessions() as session:
        return int((await session.execute(text("SELECT count(*) FROM analytics_analysis_reports"))).scalar_one())


# --- 表结构 -----------------------------------------------------------------


def test_the_report_table_declares_no_sensitive_columns():
    """结构层兜底：SQL、结果行、prompt、token/credential 都没有落脚点。"""

    banned = ("sql", "token", "secret", "dsn", "password", "credential", "result", "prompt", "rows", "content", "reasoning")

    for column in AnalysisReportRow.__table__.columns:
        assert not any(fragment in column.name.lower() for fragment in banned), column.name


def test_the_publish_key_is_the_server_derived_identity_tuple():
    constraints = {constraint.name: constraint for constraint in AnalysisReportRow.__table__.constraints}

    unique = constraints["uq_analytics_analysis_reports_identity"]
    assert {column.name for column in unique.columns} == {"principal_id", "thread_id", "run_id", "artifact_path"}


# --- 幂等发布 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_inserts_one_row_and_reports_creation(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    publication = await repository.publish(_report())

    assert publication.code is ReportPublishCode.PUBLISHED
    assert publication.report is not None
    assert publication.report.id == "report-1"
    assert await _count(sessions) == 1


@pytest.mark.asyncio
async def test_publishing_the_same_identity_twice_is_idempotent(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    first = await repository.publish(_report())
    second = await repository.publish(_report(id="report-2"))

    assert first.code is ReportPublishCode.PUBLISHED
    assert second.code is ReportPublishCode.EXISTING
    # 幂等重试返回的是**既有行**，不是本次候选值。
    assert second.report is not None
    assert second.report.id == "report-1"
    assert await _count(sessions) == 1


@pytest.mark.asyncio
async def test_a_different_payload_for_the_same_identity_is_a_conflict_and_never_overwrites(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())

    publication = await repository.publish(_report(id="report-2", title="改过的标题", evidence_ids=(_HASH_B,)))

    assert publication.code is ReportPublishCode.REPORT_CONFLICT
    assert publication.report is not None
    assert publication.report.title == "2026 Q3 经营分析"
    stored = await repository.list_for_principal(principal_id="user-1", limit=10)
    assert len(stored) == 1
    assert stored[0].title == "2026 Q3 经营分析"
    assert stored[0].evidence_ids == (_HASH_A,)


@pytest.mark.asyncio
async def test_concurrent_publishes_of_one_identity_leave_exactly_one_row(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    publications = await asyncio.gather(*(repository.publish(_report(id=f"report-{index}")) for index in range(5)))
    codes = [publication.code for publication in publications]

    assert await _count(sessions) == 1
    assert codes.count(ReportPublishCode.PUBLISHED) == 1
    assert set(codes) <= {ReportPublishCode.PUBLISHED, ReportPublishCode.EXISTING}
    # 无论谁赢，所有调用方看到的都是同一行。
    assert len({publication.report.id for publication in publications}) == 1


@pytest.mark.asyncio
async def test_the_same_run_and_artifact_under_another_principal_is_a_separate_row(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    await repository.publish(_report())
    await repository.publish(_report(id="report-2", principal_id="user-2"))

    assert await _count(sessions) == 2


# --- principal 隔离与 keyset ------------------------------------------------


@pytest.mark.asyncio
async def test_listing_is_exactly_principal_scoped(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())
    await repository.publish(_report(id="report-2", principal_id="user-2", thread_id="thread-2", run_id="run-2"))

    mine = await repository.list_for_principal(principal_id="user-1", limit=10)

    assert [report.principal_id for report in mine] == ["user-1"]


@pytest.mark.asyncio
async def test_listing_has_no_cross_tenant_read(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())

    assert await repository.list_for_principal(principal_id="user-9", limit=10) == ()


@pytest.mark.asyncio
async def test_listing_is_ordered_by_created_at_then_id_descending(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    for index in range(4):
        await repository.publish(
            _report(
                id=f"report-{index}",
                artifact_path=f"/mnt/user-data/outputs/report-{index}.md",
                created_at=_NOW + timedelta(minutes=index),
            )
        )

    page = await repository.list_for_principal(principal_id="user-1", limit=10)

    assert [report.id for report in page] == ["report-3", "report-2", "report-1", "report-0"]


@pytest.mark.asyncio
async def test_the_keyset_cursor_walks_strictly_backwards_without_gaps_or_repeats(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    # 同一时刻多行：游标必须靠 (created_at, id) 才能稳定推进。
    for index in range(5):
        await repository.publish(
            _report(
                id=f"report-{index}",
                artifact_path=f"/mnt/user-data/outputs/report-{index}.md",
                created_at=_NOW,
            )
        )

    first = await repository.list_for_principal(principal_id="user-1", limit=2)
    second = await repository.list_for_principal(principal_id="user-1", limit=2, before_created_at=first[-1].created_at, before_id=first[-1].id)
    third = await repository.list_for_principal(principal_id="user-1", limit=2, before_created_at=second[-1].created_at, before_id=second[-1].id)

    seen = [report.id for report in (*first, *second, *third)]
    assert seen == ["report-4", "report-3", "report-2", "report-1", "report-0"]
    assert len(set(seen)) == len(seen)


@pytest.mark.asyncio
async def test_the_cursor_must_be_fully_specified(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    with pytest.raises(ValueError):
        await repository.list_for_principal(principal_id="user-1", limit=10, before_created_at=_NOW)
    with pytest.raises(ValueError):
        await repository.list_for_principal(principal_id="user-1", limit=10, before_id="report-1")


@pytest.mark.asyncio
async def test_listing_rejects_an_unbounded_or_blank_request(sessions):
    repository = SqlAnalysisReportRepository(sessions)

    with pytest.raises(ValueError):
        await repository.list_for_principal(principal_id="user-1", limit=0)
    with pytest.raises(ValueError):
        await repository.list_for_principal(principal_id="user-1", limit=MAX_REPORT_PAGE_SIZE + 1)
    with pytest.raises(ValueError):
        await repository.list_for_principal(principal_id="  ", limit=10)


# --- 损坏行整页失败 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_row_with_a_blank_title_fails_the_whole_page(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())
    async with sessions() as session:
        await session.execute(update(AnalysisReportRow).values(title="   "))
        await session.commit()

    with pytest.raises(PersistenceDataError):
        await repository.list_for_principal(principal_id="user-1", limit=10)


@pytest.mark.asyncio
async def test_a_row_with_unparsable_evidence_json_fails_the_whole_page(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())
    async with sessions() as session:
        await session.execute(update(AnalysisReportRow).values(evidence_ids_json="{not json"))
        await session.commit()

    with pytest.raises(PersistenceDataError):
        await repository.list_for_principal(principal_id="user-1", limit=10)


@pytest.mark.asyncio
async def test_a_row_with_a_tampered_artifact_path_fails_the_whole_page(sessions):
    """绕过领域层直接写入越界路径的行，必须被读取侧再次拒绝，而不是原样返回给 UI。"""

    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())
    async with sessions() as session:
        await session.execute(update(AnalysisReportRow).values(artifact_path="/mnt/user-data/uploads/leak.md"))
        await session.commit()

    with pytest.raises(PersistenceDataError):
        await repository.list_for_principal(principal_id="user-1", limit=10)


@pytest.mark.asyncio
async def test_an_oversized_evidence_list_fails_the_whole_page(sessions):
    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())
    async with sessions() as session:
        await session.execute(update(AnalysisReportRow).values(evidence_ids_json=json.dumps([f"{index:064x}" for index in range(64)])))
        await session.commit()

    with pytest.raises(PersistenceDataError):
        await repository.list_for_principal(principal_id="user-1", limit=10)


# --- 约束 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_database_rejects_an_unknown_status(sessions):
    """状态只有一种合法值，因此"未知 status 的损坏行"在数据库层就不可能存在。"""

    repository = SqlAnalysisReportRepository(sessions)
    await repository.publish(_report())

    async with sessions() as session:
        with pytest.raises(Exception):
            await session.execute(update(AnalysisReportRow).values(status="tampered"))
            await session.commit()
        await session.rollback()


def test_the_report_table_has_no_cross_chain_foreign_key():
    """报告索引不引用 Harness 的任何表：跨链外键本来就是禁止的，这里把它固定下来。"""

    assert AnalysisReportRow.__table__.name == "analytics_analysis_reports"
    assert list(AnalysisReportRow.__table__.foreign_key_constraints) == []
