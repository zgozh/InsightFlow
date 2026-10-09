"""持久查询证据的应用端口与不可变记录。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.analytics.domain.evidence import (
    AnalyticsQueryToolResult,
    validate_successful_query_result,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ARTIFACT_ROOT = "/mnt/user-data/outputs"


class AnalysisEvidenceStoreError(RuntimeError):
    """持久证据不可用的稳定错误，不携带记录内容或数据库异常。"""

    def __init__(self, reason: str = "evidence_unavailable") -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class StoredAnalysisEvidence:
    """一个成功查询结果及其由服务端派生的身份和 artifact 路径。"""

    principal_id: str
    thread_id: str
    run_id: str
    result: AnalyticsQueryToolResult
    artifact_path: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, str) or not self.principal_id or self.principal_id != self.principal_id.strip() or self.principal_id == "default" or len(self.principal_id) > 64:
            raise ValueError("analysis_evidence_unavailable")
        for value in (self.thread_id, self.run_id):
            if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
                raise ValueError("analysis_evidence_unavailable")
        if not isinstance(self.result, AnalyticsQueryToolResult):
            raise ValueError("analysis_evidence_unavailable")
        validate_successful_query_result(self.result)
        evidence = self.result.evidence
        if evidence is None:
            raise ValueError("analysis_evidence_unavailable")
        expected_path = f"{_ARTIFACT_ROOT}/query-result-{self.run_id}-{evidence.evidence_id}.json"
        if self.artifact_path != expected_path:
            raise ValueError("analysis_evidence_unavailable")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("analysis_evidence_unavailable")
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))

    @property
    def evidence_id(self) -> str:
        evidence = self.result.evidence
        if evidence is None:
            raise ValueError("analysis_evidence_unavailable")
        return evidence.evidence_id

    @property
    def snapshot_bytes(self) -> int:
        return validate_successful_query_result(self.result)


class AnalysisEvidenceRepository(Protocol):
    """只按精确 principal/thread/run 隔离读取证据的持久化端口。"""

    async def put(self, record: StoredAnalysisEvidence) -> None: ...

    async def get_many(self, principal_id: str, thread_id: str, run_id: str, evidence_ids: tuple[str, ...]) -> tuple[StoredAnalysisEvidence, ...]: ...

    async def get_existing_many(self, principal_id: str, thread_id: str, run_id: str, evidence_ids: tuple[str, ...]) -> tuple[StoredAnalysisEvidence, ...]: ...
