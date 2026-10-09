"""Analytics Agent 与耐久查询证据 repository / 固定文件能力之间的桥接。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.analytics.agent.evidence import (
    ANALYSIS_EVIDENCE_UNAVAILABLE,
    AnalysisRunEvidenceCollector,
    AnalyticsQueryToolResult,
)
from app.analytics.application.evidence_ports import AnalysisEvidenceRepository, StoredAnalysisEvidence
from app.analytics.domain.evidence import (
    MAX_ANALYSIS_EVIDENCE_PER_RUN,
    MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES,
    validate_successful_query_result,
)

_SAFE_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_OUTPUTS_VIRTUAL_ROOT = "/mnt/user-data/outputs"


class DurableAnalysisRunEvidenceCollector(AnalysisRunEvidenceCollector):
    """兼容原 run-local API，同时以 repository+固定 JSON 文件作为发布依据。"""

    __slots__ = ("__repository", "__artifact_capability", "__producer_run_id", "__producer_artifact_capability")

    def __init__(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        repository: AnalysisEvidenceRepository,
        artifact_capability: Any,
        producer_run_id: str | None = None,
        producer_artifact_capability: Any | None = None,
    ) -> None:
        super().__init__(principal_id=principal_id, thread_id=thread_id, run_id=run_id)
        if not callable(getattr(repository, "put", None)) or not callable(getattr(repository, "get_many", None)):
            raise ValueError(ANALYSIS_EVIDENCE_UNAVAILABLE)
        if (
            not callable(getattr(artifact_capability, "write", None))
            or not callable(getattr(artifact_capability, "verify", None))
            or not callable(getattr(artifact_capability, "virtual_path_for", None))
            or not callable(getattr(artifact_capability, "matches", None))
            or not artifact_capability.matches(principal_id, thread_id, run_id)
        ):
            raise ValueError(ANALYSIS_EVIDENCE_UNAVAILABLE)
        if (producer_run_id is None) != (producer_artifact_capability is None):
            raise ValueError(ANALYSIS_EVIDENCE_UNAVAILABLE)
        if producer_run_id is not None and (
            not isinstance(producer_run_id, str)
            or not _SAFE_RUN_ID.fullmatch(producer_run_id)
            or producer_run_id == run_id
            or not callable(getattr(repository, "get_existing_many", None))
            or not callable(getattr(producer_artifact_capability, "verify", None))
            or not callable(getattr(producer_artifact_capability, "virtual_path_for", None))
            or not callable(getattr(producer_artifact_capability, "matches", None))
            or not producer_artifact_capability.matches(principal_id, thread_id, producer_run_id)
        ):
            raise ValueError(ANALYSIS_EVIDENCE_UNAVAILABLE)
        self.__repository = repository
        self.__artifact_capability = artifact_capability
        self.__producer_run_id = producer_run_id
        self.__producer_artifact_capability = producer_artifact_capability

    def artifact_path(self, evidence_id: str) -> str:
        """导出该 scope 下按 digest 固定派生的虚拟路径。"""

        if not isinstance(evidence_id, str) or not _SAFE_DIGEST.fullmatch(evidence_id):
            raise ValueError(ANALYSIS_EVIDENCE_UNAVAILABLE)
        return self.__artifact_capability.virtual_path_for(evidence_id)

    async def record_success_durable(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        result: AnalyticsQueryToolResult,
    ) -> bool:
        """先完整校验，再按 repo → 固定文件 → run-local cache 顺序登记。"""

        if not self.matches(principal_id, thread_id, run_id) or not isinstance(result, AnalyticsQueryToolResult):
            return False
        try:
            validate_successful_query_result(result)
            evidence = result.evidence
            if evidence is None:
                return False
            record = StoredAnalysisEvidence(
                principal_id=principal_id,
                thread_id=thread_id,
                run_id=run_id,
                result=result,
                artifact_path=self.artifact_path(evidence.evidence_id),
                created_at=datetime.now(UTC),
            )
            await self.__repository.put(record)
            if await self.__artifact_capability.write(record) is not True:
                return False
            return super().record_success(
                principal_id=principal_id,
                thread_id=thread_id,
                run_id=run_id,
                result=result,
            )
        except Exception:
            # 存储异常和 capability 异常都只形成稳定的 False；取消仍按原样传播。
            return False

    async def resolve_successful_queries_durable(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[AnalyticsQueryToolResult, ...] | None:
        """按 repo 请求顺序恢复，并逐条验证当前 scope 的固定 JSON 文件。"""

        if (
            not self.matches(principal_id, thread_id, run_id)
            or not isinstance(evidence_ids, tuple)
            or not 1 <= len(evidence_ids) <= MAX_ANALYSIS_EVIDENCE_PER_RUN
            or any(not isinstance(evidence_id, str) or not _SAFE_DIGEST.fullmatch(evidence_id) for evidence_id in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            return None
        try:
            if self.__producer_run_id is None:
                records = await self.__repository.get_many(principal_id, thread_id, run_id, evidence_ids)
                if not isinstance(records, tuple) or len(records) != len(evidence_ids):
                    return None
            else:
                records_by_id: dict[str, StoredAnalysisEvidence] = {}
                sources = (
                    (run_id, self.__artifact_capability),
                    (self.__producer_run_id, self.__producer_artifact_capability),
                )
                for source_run_id, _capability in sources:
                    source_records = await self.__repository.get_existing_many(principal_id, thread_id, source_run_id, evidence_ids)
                    if not isinstance(source_records, tuple):
                        return None
                    for source_record in source_records:
                        if (
                            not isinstance(source_record, StoredAnalysisEvidence)
                            or (source_record.principal_id, source_record.thread_id, source_record.run_id) != (principal_id, thread_id, source_run_id)
                            or source_record.evidence_id not in evidence_ids
                            or source_record.evidence_id in records_by_id
                        ):
                            return None
                        records_by_id[source_record.evidence_id] = source_record
                if set(records_by_id) != set(evidence_ids):
                    return None
                records = tuple(records_by_id[evidence_id] for evidence_id in evidence_ids)
            results: list[AnalyticsQueryToolResult] = []
            total_snapshot_bytes = 0
            for expected_id, record in zip(evidence_ids, records, strict=True):
                if not isinstance(record, StoredAnalysisEvidence):
                    return None
                if (record.principal_id, record.thread_id) != (principal_id, thread_id):
                    return None
                if record.run_id == run_id:
                    artifact_capability = self.__artifact_capability
                elif self.__producer_run_id is not None and record.run_id == self.__producer_run_id:
                    artifact_capability = self.__producer_artifact_capability
                else:
                    return None
                if record.evidence_id != expected_id or record.artifact_path != artifact_capability.virtual_path_for(expected_id) or await artifact_capability.verify(record) is not True:
                    return None
                total_snapshot_bytes += validate_successful_query_result(record.result)
                if total_snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
                    return None
                results.append(record.result)
            return tuple(results)
        except Exception:
            # 取消不会被吞掉；其他 repository / file 错误不允许部分复核。
            return None


def create_durable_analysis_run_evidence_collector(
    *,
    principal_id: str,
    thread_id: str,
    run_id: str,
    repository: AnalysisEvidenceRepository,
    artifact_capability: Any,
    producer_run_id: str | None = None,
    producer_artifact_capability: Any | None = None,
) -> DurableAnalysisRunEvidenceCollector:
    """Gateway admission 专用 factory；普通聊天继续不发行 collector。"""

    return DurableAnalysisRunEvidenceCollector(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        repository=repository,
        artifact_capability=artifact_capability,
        producer_run_id=producer_run_id,
        producer_artifact_capability=producer_artifact_capability,
    )


__all__ = ["DurableAnalysisRunEvidenceCollector", "create_durable_analysis_run_evidence_collector"]
