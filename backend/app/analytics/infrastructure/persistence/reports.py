"""分析报告索引的 SQL 适配器（Phase 4 §6）。

写入语义是"先查后插 + 唯一键兜底"：

1. 先按服务端派生的身份键查一次，命中就直接分类（逐字相同 = 幂等重试，内容不同 = 冲突）；
2. 未命中才插入；插入撞上唯一键（并发发布、或 check-then-insert 之间的竞态）时回滚并重查，
   因此**并发重试最多留下一行**，而且永远不会静默覆盖已经登记的报告。

读取语义与审计账本一致：principal 精确过滤、`(created_at DESC, id DESC)` keyset 分页、
损坏行整页失败。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import PersistenceConflictError, PersistenceDataError
from app.analytics.application.report_ports import ReportPublication
from app.analytics.domain import AnalysisReport, ReportPublishCode, ReportStatus
from app.analytics.infrastructure.persistence.models import AnalysisReportRow

#: 单页硬上限。与审计读取同量级，客户端只能向下请求。
MAX_REPORT_PAGE_SIZE = 100


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("report timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _render_evidence(evidence_ids: tuple[str, ...]) -> str:
    # 紧凑且不转义非 ASCII：这一列只装 64 位十六进制摘要，形状稳定便于人工核对。
    return json.dumps(list(evidence_ids), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def _row_to_report(row: AnalysisReportRow) -> AnalysisReport:
    """损坏行整体失败：读取接口绝不返回"部分正确"的报告索引。"""

    try:
        created_at = row.created_at if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=UTC)
        decoded = json.loads(row.evidence_ids_json)
        if not isinstance(decoded, list):
            raise ValueError("evidence_ids_json must decode to a list")
        return AnalysisReport(
            id=row.id,
            principal_id=row.principal_id,
            thread_id=row.thread_id,
            run_id=row.run_id,
            artifact_path=row.artifact_path,
            title=row.title,
            status=ReportStatus(row.status),
            evidence_ids=tuple(decoded),
            created_at=created_at,
        )
    except PersistenceDataError:
        raise
    except (ValueError, TypeError) as error:
        raise PersistenceDataError("row_invalid_analysis_report") from error


def _classify(stored: AnalysisReport, candidate: AnalysisReport) -> ReportPublication:
    """把"读到的既有行"翻译成稳定结果：逐字相同 = 幂等重试，否则 = 内容冲突。

    冲突时返回的始终是**既有行**：调用方绝不能把本次候选值当成已保存的内容。
    """

    code = ReportPublishCode.EXISTING if stored.same_publication(candidate) else ReportPublishCode.REPORT_CONFLICT
    return ReportPublication(code=code, report=stored)


class SqlAnalysisReportRepository:
    """`AnalysisReportRepository` 端口的持久化实现。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _find(self, session: AsyncSession, report: AnalysisReport) -> AnalysisReport | None:
        statement = select(AnalysisReportRow).where(
            AnalysisReportRow.principal_id == report.principal_id,
            AnalysisReportRow.thread_id == report.thread_id,
            AnalysisReportRow.run_id == report.run_id,
            AnalysisReportRow.artifact_path == report.artifact_path,
        )
        row = (await session.execute(statement)).scalars().first()
        return None if row is None else _row_to_report(row)

    async def publish(self, report: AnalysisReport) -> ReportPublication:
        if not isinstance(report, AnalysisReport):
            raise TypeError("report must be an AnalysisReport")

        async with self._session_factory() as session:
            existing = await self._find(session, report)
            if existing is not None:
                return _classify(existing, report)

            session.add(
                AnalysisReportRow(
                    id=report.id,
                    principal_id=report.principal_id,
                    thread_id=report.thread_id,
                    run_id=report.run_id,
                    artifact_path=report.artifact_path,
                    title=report.title,
                    status=report.status.value,
                    evidence_ids_json=_render_evidence(report.evidence_ids),
                    created_at=_as_utc(report.created_at),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # 并发发布同一身份键：唯一约束保证只有一行存活，这里退回到"读既有行"。
                await session.rollback()
                raced = await self._find(session, report)
                if raced is None:
                    # 唯一键冲突却查不到行，说明失败原因不是我们假设的那一条，不能吞掉。
                    raise PersistenceConflictError("report_publish_race_unresolved") from None
                return _classify(raced, report)
            return ReportPublication(code=ReportPublishCode.PUBLISHED, report=report)

    async def list_for_principal(
        self,
        *,
        principal_id: str,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[AnalysisReport, ...]:
        """按 `(created_at DESC, id DESC)` 的 keyset 分页读取一个 principal 的报告索引。"""

        if not isinstance(principal_id, str) or not principal_id.strip() or principal_id != principal_id.strip():
            raise ValueError("principal_id must be a non-empty trimmed string")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_REPORT_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_REPORT_PAGE_SIZE}")
        if (before_created_at is None) != (before_id is None):
            raise ValueError("before_created_at and before_id must be provided together")

        statement = select(AnalysisReportRow).where(AnalysisReportRow.principal_id == principal_id)
        if before_created_at is not None and before_id is not None:
            cursor = _as_utc(before_created_at)
            if not isinstance(before_id, str) or not before_id.strip() or before_id != before_id.strip():
                raise ValueError("before_id must be a non-empty trimmed string")
            # 行值比较 (created_at, id) < (cursor) 的显式写法，避免依赖方言的 row value 支持。
            statement = statement.where(
                or_(
                    AnalysisReportRow.created_at < cursor,
                    and_(AnalysisReportRow.created_at == cursor, AnalysisReportRow.id < before_id),
                )
            )
        statement = statement.order_by(AnalysisReportRow.created_at.desc(), AnalysisReportRow.id.desc()).limit(limit)

        async with self._session_factory() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(_row_to_report(row) for row in rows)
