"""应用数据库中的只追加、按 run 隔离的成功查询证据仓储。"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application.evidence_ports import AnalysisEvidenceStoreError, StoredAnalysisEvidence
from app.analytics.domain.evidence import MAX_ANALYSIS_EVIDENCE_PER_RUN, MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES, _require_digest
from app.analytics.infrastructure.persistence.evidence_codec import (
    ANALYSIS_EVIDENCE_PAYLOAD_VERSION,
    AnalysisEvidenceCodecError,
    decode_analysis_evidence_result,
    encode_analysis_evidence_result,
)
from app.analytics.infrastructure.persistence.models import AnalysisEvidenceRow

_CAPACITY_ADVISORY_LOCK_KEY = 0x1F10_2C10_5A11_7E03
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("analysis_evidence_unavailable")
    return value.astimezone(UTC)


class SqlAnalysisEvidenceRepository:
    """SQLite 与 PostgreSQL 共用的 owner/thread/run-scoped 持久仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _begin_capacity_transaction(self, session: AsyncSession) -> None:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CAPACITY_ADVISORY_LOCK_KEY})
        elif dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        else:
            raise AnalysisEvidenceStoreError("store_unavailable")

    async def put(self, record: StoredAnalysisEvidence) -> None:
        if not isinstance(record, StoredAnalysisEvidence):
            raise AnalysisEvidenceStoreError("invalid_evidence")
        try:
            payload_json = encode_analysis_evidence_result(record.result)
            created_at = _as_utc(record.created_at)
            snapshot_bytes = record.snapshot_bytes
        except (AnalysisEvidenceCodecError, ValueError, TypeError):
            raise AnalysisEvidenceStoreError("invalid_evidence") from None

        try:
            async with self._session_factory() as session:
                try:
                    await self._begin_capacity_transaction(session)
                    identity = (
                        AnalysisEvidenceRow.principal_id == record.principal_id,
                        AnalysisEvidenceRow.thread_id == record.thread_id,
                        AnalysisEvidenceRow.run_id == record.run_id,
                        AnalysisEvidenceRow.evidence_id == record.evidence_id,
                    )
                    existing = (await session.execute(select(AnalysisEvidenceRow).where(*identity))).scalar_one_or_none()
                    if existing is not None:
                        if existing.payload_version != ANALYSIS_EVIDENCE_PAYLOAD_VERSION or existing.payload_json != payload_json or existing.snapshot_bytes != snapshot_bytes or existing.artifact_path != record.artifact_path:
                            raise AnalysisEvidenceStoreError("evidence_conflict")
                        await session.commit()
                        return

                    scope = (
                        AnalysisEvidenceRow.principal_id == record.principal_id,
                        AnalysisEvidenceRow.thread_id == record.thread_id,
                        AnalysisEvidenceRow.run_id == record.run_id,
                    )
                    count, total_bytes = (await session.execute(select(func.count(), func.coalesce(func.sum(AnalysisEvidenceRow.snapshot_bytes), 0)).where(*scope))).one()
                    if count >= MAX_ANALYSIS_EVIDENCE_PER_RUN or total_bytes + snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
                        raise AnalysisEvidenceStoreError("capacity_exceeded")

                    await session.execute(
                        insert(AnalysisEvidenceRow).values(
                            principal_id=record.principal_id,
                            thread_id=record.thread_id,
                            run_id=record.run_id,
                            evidence_id=record.evidence_id,
                            payload_version=ANALYSIS_EVIDENCE_PAYLOAD_VERSION,
                            payload_json=payload_json,
                            snapshot_bytes=snapshot_bytes,
                            artifact_path=record.artifact_path,
                            created_at=created_at,
                        )
                    )
                    await session.commit()
                except AnalysisEvidenceStoreError:
                    await session.rollback()
                    raise
                except Exception:
                    await session.rollback()
                    raise AnalysisEvidenceStoreError("store_unavailable") from None
        except AnalysisEvidenceStoreError:
            raise
        except Exception:
            raise AnalysisEvidenceStoreError("store_unavailable") from None

    async def get_many(self, principal_id: str, thread_id: str, run_id: str, evidence_ids: tuple[str, ...]) -> tuple[StoredAnalysisEvidence, ...]:
        records = await self.get_existing_many(principal_id, thread_id, run_id, evidence_ids)
        if len(records) != len(evidence_ids):
            raise AnalysisEvidenceStoreError("evidence_unavailable")
        return records

    async def get_existing_many(self, principal_id: str, thread_id: str, run_id: str, evidence_ids: tuple[str, ...]) -> tuple[StoredAnalysisEvidence, ...]:
        """按 exact scope 返回存在的记录；损坏行和存储故障仍整体失败。"""
        if (
            not isinstance(principal_id, str)
            or not principal_id
            or principal_id != principal_id.strip()
            or principal_id == "default"
            or len(principal_id) > 64
            or not isinstance(thread_id, str)
            or not _SAFE_ID.fullmatch(thread_id)
            or not isinstance(run_id, str)
            or not _SAFE_ID.fullmatch(run_id)
            or not isinstance(evidence_ids, tuple)
            or not 1 <= len(evidence_ids) <= MAX_ANALYSIS_EVIDENCE_PER_RUN
            or any(not isinstance(evidence_id, str) for evidence_id in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            raise AnalysisEvidenceStoreError("evidence_unavailable")
        try:
            for evidence_id in evidence_ids:
                _require_digest(evidence_id, "evidence_id")
        except ValueError:
            raise AnalysisEvidenceStoreError("evidence_unavailable") from None

        try:
            async with self._session_factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(AnalysisEvidenceRow).where(
                                AnalysisEvidenceRow.principal_id == principal_id,
                                AnalysisEvidenceRow.thread_id == thread_id,
                                AnalysisEvidenceRow.run_id == run_id,
                                AnalysisEvidenceRow.evidence_id.in_(evidence_ids),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
        except Exception:
            raise AnalysisEvidenceStoreError("store_unavailable") from None

        by_id = {row.evidence_id: row for row in rows}
        if len(by_id) != len(rows):
            raise AnalysisEvidenceStoreError("evidence_unavailable")

        restored: list[StoredAnalysisEvidence] = []
        for evidence_id in evidence_ids:
            row = by_id.get(evidence_id)
            if row is None:
                continue
            try:
                result = decode_analysis_evidence_result(row.payload_json, payload_version=row.payload_version)
                created_at = row.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                record = StoredAnalysisEvidence(
                    principal_id=row.principal_id,
                    thread_id=row.thread_id,
                    run_id=row.run_id,
                    result=result,
                    artifact_path=row.artifact_path,
                    created_at=created_at,
                )
                if row.snapshot_bytes != record.snapshot_bytes or record.evidence_id != row.evidence_id:
                    raise AnalysisEvidenceCodecError("analysis_evidence_payload_invalid")
                restored.append(record)
            except Exception:
                raise AnalysisEvidenceStoreError("evidence_unavailable") from None
        return tuple(restored)
