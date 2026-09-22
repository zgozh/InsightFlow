"""报告索引的应用用例（Phase 4 §6）。

两个用例，边界都很窄：

- `PublishAnalysisReport`：**只**接受 `title` / `artifact_path` / `evidence_ids` 与三个从受信
  runtime 派生的身份参数。它不读 artifact 内容，不计算 evidence，也不接受
  principal/thread/run/status/created_at/幂等键。`id` 与 `created_at` 由服务端时钟与 ID 发行器
  产生，因此"谁在什么时候发布了什么"不可能被模型改写。
- `ListAnalysisReports`：principal 精确过滤的 keyset 分页。没有"列出全部 principal"的入口；
  管理员要查别人必须走显式 admin 端点并给出精确 principal。

发布结果由端口返回 `ReportPublication`（稳定 code + 权威既有行），因此冲突时用例绝不把本次
候选值回报成"已保存"。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.analytics.application.execution_ports import Clock
from app.analytics.application.report_ports import AnalysisReportRepository, ReportPublication
from app.analytics.domain import AnalysisReport, ReportStatus, normalize_report_artifact_path


def _as_evidence_tuple(evidence_ids: object) -> tuple[str, ...]:
    """把模型传来的 list 规范化成不可变 tuple。

    只做形状规范化，不做内容修正：元素本身仍然由 `AnalysisReport` 的领域校验决定去留。
    """

    if isinstance(evidence_ids, tuple):
        return evidence_ids
    if isinstance(evidence_ids, Sequence) and not isinstance(evidence_ids, (str, bytes, bytearray)):
        return tuple(evidence_ids)
    raise ValueError("evidence_ids must be a sequence of SHA-256 digests")


class PublishAnalysisReport:
    """登记一份已发布的 artifact。只登记索引，不读 artifact 内容。"""

    def __init__(self, *, repository: AnalysisReportRepository, clock: Clock, id_issuer) -> None:
        self._repository = repository
        self._clock = clock
        self._id_issuer = id_issuer

    async def execute(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        title: str,
        artifact_path: str,
        evidence_ids: object,
    ) -> ReportPublication:
        report = AnalysisReport(
            id=str(self._id_issuer()),
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            artifact_path=normalize_report_artifact_path(artifact_path),
            title=title,
            status=ReportStatus.PUBLISHED,
            evidence_ids=_as_evidence_tuple(evidence_ids),
            created_at=self._clock.now(),
        )
        return await self._repository.publish(report)


class ListAnalysisReports:
    """按 principal 精确过滤的 keyset 分页读取。"""

    def __init__(self, *, repository: AnalysisReportRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        principal_id: str,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[AnalysisReport, ...]:
        return await self._repository.list_for_principal(
            principal_id=principal_id,
            limit=limit,
            before_created_at=before_created_at,
            before_id=before_id,
        )
