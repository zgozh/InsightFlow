"""Gateway analysis run 内的成功查询证据缓存。"""

from __future__ import annotations

from threading import Lock

from app.analytics.domain import ExecutionDecisionCode
from app.analytics.domain.evidence import (
    _SAFE_RUN_ID,
    MAX_ANALYSIS_EVIDENCE_PER_RUN,
    MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES,
    AnalyticsQueryEvidence,
    AnalyticsQueryToolResult,
    _sha256,
    canonical_json,
    compute_result_digest,
)
from app.analytics.domain.evidence import (
    ANALYSIS_EVIDENCE_UNAVAILABLE as ANALYSIS_EVIDENCE_UNAVAILABLE,
)
from app.analytics.domain.evidence import (
    EvidenceError as EvidenceError,
)


class AnalysisRunEvidenceCollector:
    """只在当前 Gateway analysis run 内保存成功查询的不可变快照。

    对象只由 Gateway 创建并通过 worker runtime context 注入；不属于图状态、事件或回执。
    结果数量与总字节数均有上限，且快照只含规范 evidence 与有界 JSON 结果。
    """

    __slots__ = ("__principal_id", "__thread_id", "__run_id", "__entries", "__snapshot_bytes", "__lock")

    def __init__(self, *, principal_id: str, thread_id: str, run_id: str) -> None:
        if (
            not isinstance(principal_id, str)
            or not principal_id
            or principal_id != principal_id.strip()
            or principal_id == "default"
            or not isinstance(thread_id, str)
            or not _SAFE_RUN_ID.fullmatch(thread_id)
            or not isinstance(run_id, str)
            or not _SAFE_RUN_ID.fullmatch(run_id)
        ):
            raise ValueError("analysis_evidence_unavailable")
        self.__principal_id = principal_id
        self.__thread_id = thread_id
        self.__run_id = run_id
        self.__entries: dict[str, tuple[AnalyticsQueryToolResult, int]] = {}
        self.__snapshot_bytes = 0
        self.__lock = Lock()

    def matches(self, principal_id: str, thread_id: str, run_id: str) -> bool:
        """确认调用仍处于签发此 collector 的唯一 owner/thread/run。"""

        return (principal_id, thread_id, run_id) == (self.__principal_id, self.__thread_id, self.__run_id)

    def record_success(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        result: AnalyticsQueryToolResult,
    ) -> bool:
        """仅登记与规范 evidence 精确对应的成功或有界截断结果。"""

        if not self.matches(principal_id, thread_id, run_id) or not isinstance(result, AnalyticsQueryToolResult):
            return False
        evidence = result.evidence
        evidence_payload = evidence.to_payload() if isinstance(evidence, AnalyticsQueryEvidence) else {}
        if (
            evidence is None
            or result.code not in {ExecutionDecisionCode.EXECUTED.value, ExecutionDecisionCode.RESULT_LIMIT_REACHED.value}
            or evidence.decision_code != result.code
            or evidence.row_count != len(result.rows)
            or evidence.truncated != result.truncated
            or evidence.result_digest != compute_result_digest(result.columns, result.rows)
            or evidence.evidence_id != _sha256(canonical_json({key: value for key, value in evidence_payload.items() if key != "evidence_id"}))
        ):
            return False

        snapshot_bytes = len(canonical_json({"columns": list(result.columns), "rows": [list(row) for row in result.rows]}).encode("utf-8"))
        if snapshot_bytes != evidence.byte_count or snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
            return False

        with self.__lock:
            existing = self.__entries.get(evidence.evidence_id)
            if existing is not None:
                return existing[0] == result
            if len(self.__entries) >= MAX_ANALYSIS_EVIDENCE_PER_RUN or self.__snapshot_bytes + snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
                return False
            self.__entries[evidence.evidence_id] = (result, snapshot_bytes)
            self.__snapshot_bytes += snapshot_bytes
        return True

    def resolve_successful_queries(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[AnalyticsQueryToolResult, ...] | None:
        """按报告请求顺序解析本 run 的全部成功快照；缺一项即整体拒绝。"""

        if (
            not self.matches(principal_id, thread_id, run_id)
            or not isinstance(evidence_ids, tuple)
            or not evidence_ids
            or len(evidence_ids) > MAX_ANALYSIS_EVIDENCE_PER_RUN
            or any(not isinstance(evidence_id, str) for evidence_id in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            return None
        with self.__lock:
            entries = tuple(self.__entries.get(evidence_id) for evidence_id in evidence_ids)
        if any(entry is None for entry in entries):
            return None
        return tuple(entry[0] for entry in entries if entry is not None)


def create_analysis_run_evidence_collector(*, principal_id: str, thread_id: str, run_id: str) -> AnalysisRunEvidenceCollector:
    """创建绑定单个 Gateway analysis run 的私有 evidence collector。"""

    return AnalysisRunEvidenceCollector(principal_id=principal_id, thread_id=thread_id, run_id=run_id)
