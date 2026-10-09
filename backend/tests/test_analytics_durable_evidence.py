"""成功查询证据的应用数据库持久化、隔离、容量与恢复契约。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import AnalysisEvidenceStoreError, StoredAnalysisEvidence
from app.analytics.domain import ExecutionDecisionCode, QueryExecutionResult, QueryRisk
from app.analytics.domain.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.evidence import SqlAnalysisEvidenceRepository
from app.analytics.infrastructure.persistence.evidence_codec import (
    MAX_ANALYSIS_EVIDENCE_PAYLOAD_BYTES,
    AnalysisEvidenceCodecError,
    decode_analysis_evidence_result,
    encode_analysis_evidence_result,
)
from app.analytics.infrastructure.persistence.models import AnalysisEvidenceRow

_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False, connect_args={"timeout": 30})


@pytest_asyncio.fixture
async def evidence_store(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    await bootstrap_analytics_schema(engine, backend="sqlite")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, sessions, SqlAnalysisEvidenceRepository(sessions)
    finally:
        await engine.dispose()


def _record(
    index: int = 1,
    *,
    principal_id: str = "user-1",
    thread_id: str = "thread-1",
    run_id: str = "run-1",
    value: object | None = None,
    rows: tuple[tuple[object, ...], ...] | None = None,
    code: str = "executed",
    risk: QueryRisk = QueryRisk.LOW,
    created_at: datetime = _NOW,
) -> StoredAnalysisEvidence:
    columns = ("value",)
    rows = rows if rows is not None else ((index if value is None else value,),)
    truncated = code == ExecutionDecisionCode.RESULT_LIMIT_REACHED.value
    snapshot = canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8")
    execution = QueryExecutionResult(columns=columns, rows=rows, row_count=len(rows), byte_count=len(snapshot), truncated=truncated)
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="ds-1",
        query_hash=f"{index:064x}",
        risk=risk,
        schema_version="schema-1",
        policy_version="policy-1",
        plan_digest="b" * 64,
        estimated_rows=1,
        engine_cost=Decimal("12.5"),
        result=execution,
        decision_code=code,
    )
    result = AnalyticsQueryToolResult(code=code, columns=columns, rows=rows, truncated=truncated, evidence=evidence)
    artifact_path = f"/mnt/user-data/outputs/query-result-{run_id}-{evidence.evidence_id}.json"
    return StoredAnalysisEvidence(principal_id, thread_id, run_id, result, artifact_path, created_at)


async def _count(sessions, *, principal_id="user-1", thread_id="thread-1", run_id="run-1") -> int:
    async with sessions() as session:
        statement = (
            select(func.count())
            .select_from(AnalysisEvidenceRow)
            .where(
                AnalysisEvidenceRow.principal_id == principal_id,
                AnalysisEvidenceRow.thread_id == thread_id,
                AnalysisEvidenceRow.run_id == run_id,
            )
        )
        return int((await session.execute(statement)).scalar_one())


@pytest.mark.asyncio
async def test_put_is_idempotent_and_keeps_the_first_created_at(evidence_store):
    _engine, _sessions, repository = evidence_store
    record = _record()

    await repository.put(record)
    await repository.put(_record(created_at=_NOW + timedelta(minutes=1)))

    restored = await repository.get_many("user-1", "thread-1", "run-1", (record.evidence_id,))
    assert restored == (record,)
    assert await _count(_sessions) == 1


@pytest.mark.asyncio
async def test_same_identity_conflict_never_overwrites_an_existing_row(evidence_store):
    _engine, sessions, repository = evidence_store
    record = _record()
    await repository.put(record)
    async with sessions() as session:
        await session.execute(update(AnalysisEvidenceRow).values(artifact_path="/mnt/user-data/outputs/tampered.json"))
        await session.commit()

    with pytest.raises(AnalysisEvidenceStoreError) as error:
        await repository.put(record)

    assert error.value.reason == "evidence_conflict"
    async with sessions() as session:
        path = (await session.execute(select(AnalysisEvidenceRow.artifact_path))).scalar_one()
    assert path == "/mnt/user-data/outputs/tampered.json"


@pytest.mark.asyncio
async def test_get_many_requires_exact_scope_and_is_all_or_nothing(evidence_store):
    _engine, _sessions, repository = evidence_store
    record = _record()
    await repository.put(record)

    for scope in (("user-2", "thread-1", "run-1"), ("user-1", "thread-2", "run-1"), ("user-1", "thread-1", "run-2")):
        with pytest.raises(AnalysisEvidenceStoreError) as error:
            await repository.get_many(*scope, (record.evidence_id,))
        assert error.value.reason == "evidence_unavailable"

    with pytest.raises(AnalysisEvidenceStoreError) as error:
        await repository.get_many("user-1", "thread-1", "run-1", (record.evidence_id, "f" * 64))
    assert error.value.reason == "evidence_unavailable"
    with pytest.raises(AnalysisEvidenceStoreError) as error:
        await repository.get_many("user-1", "thread-1", "run-1", ([],))  # type: ignore[arg-type]
    assert error.value.reason == "evidence_unavailable"


@pytest.mark.asyncio
async def test_get_many_preserves_request_order(evidence_store):
    _engine, _sessions, repository = evidence_store
    first, second = _record(1), _record(2)
    await repository.put(first)
    await repository.put(second)

    restored = await repository.get_many("user-1", "thread-1", "run-1", (second.evidence_id, first.evidence_id))

    assert restored == (second, first)


@pytest.mark.asyncio
async def test_sqlite_capacity_check_serializes_competing_writers(evidence_store):
    _engine, sessions, repository = evidence_store
    for index in range(19):
        await repository.put(_record(index + 1))

    outcomes = await asyncio.gather(repository.put(_record(20)), repository.put(_record(21)), return_exceptions=True)

    errors = [outcome for outcome in outcomes if isinstance(outcome, AnalysisEvidenceStoreError)]
    assert len(errors) == 1
    assert errors[0].reason == "capacity_exceeded"
    assert await _count(sessions) == 20


@pytest.mark.asyncio
async def test_snapshot_byte_budget_is_enforced_per_run(evidence_store):
    _engine, _sessions, repository = evidence_store
    await repository.put(_record(1, value="a" * (8 * 1024 * 1024)))

    with pytest.raises(AnalysisEvidenceStoreError) as error:
        await repository.put(_record(2, value="b" * (8 * 1024 * 1024)))

    assert error.value.reason == "capacity_exceeded"


@pytest.mark.asyncio
async def test_evidence_survives_reopening_the_same_sqlite_file_with_a_new_engine(tmp_path):
    path = tmp_path / "analytics.db"
    first_engine = _engine(path)
    await bootstrap_analytics_schema(first_engine, backend="sqlite")
    first_sessions = async_sessionmaker(first_engine, expire_on_commit=False)
    record = _record()
    await SqlAnalysisEvidenceRepository(first_sessions).put(record)
    await first_engine.dispose()

    reopened_engine = _engine(path)
    try:
        await bootstrap_analytics_schema(reopened_engine, backend="sqlite")
        reopened_sessions = async_sessionmaker(reopened_engine, expire_on_commit=False)
        restored = await SqlAnalysisEvidenceRepository(reopened_sessions).get_many("user-1", "thread-1", "run-1", (record.evidence_id,))
        assert restored == (record,)
    finally:
        await reopened_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("payload_version", 999), ("payload_json", "{broken")])
async def test_corrupt_or_unknown_payload_fails_closed(evidence_store, field, value):
    _engine, sessions, repository = evidence_store
    record = _record()
    await repository.put(record)
    async with sessions() as session:
        await session.execute(update(AnalysisEvidenceRow).values({field: value}))
        await session.commit()

    with pytest.raises(AnalysisEvidenceStoreError) as error:
        await repository.get_many("user-1", "thread-1", "run-1", (record.evidence_id,))
    assert error.value.reason == "evidence_unavailable"


def test_codec_rejects_unknown_fields_boolean_integers_and_oversized_payloads():
    payload = json.loads(encode_analysis_evidence_result(_record().result))
    payload["unexpected"] = 1
    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(json.dumps(payload), payload_version=1)

    payload = json.loads(encode_analysis_evidence_result(_record().result))
    payload["evidence"]["row_count"] = True
    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(json.dumps(payload), payload_version=1)

    payload = json.loads(encode_analysis_evidence_result(_record().result))
    payload["evidence"]["engine_cost"] = "NaN"
    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(json.dumps(payload), payload_version=1)

    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(" " * (MAX_ANALYSIS_EVIDENCE_PAYLOAD_BYTES + 1), payload_version=1)
    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(encode_analysis_evidence_result(_record().result), payload_version=True)


def test_stored_record_rejects_untrusted_identity_and_artifact_path():
    record = _record()
    with pytest.raises(ValueError):
        StoredAnalysisEvidence("default", record.thread_id, record.run_id, record.result, record.artifact_path, _NOW)
    with pytest.raises(ValueError):
        StoredAnalysisEvidence(record.principal_id, record.thread_id, record.run_id, record.result, "/tmp/model-chosen.json", _NOW)
    with pytest.raises(ValueError):
        StoredAnalysisEvidence(record.principal_id, record.thread_id, record.run_id, record.result, record.artifact_path, datetime(2026, 10, 7))


@pytest.mark.asyncio
async def test_successful_zero_row_evidence_persists_and_restores(evidence_store):
    _engine, _sessions, repository = evidence_store
    record = _record(17, rows=())

    await repository.put(record)
    restored = await repository.get_many("user-1", "thread-1", "run-1", (record.evidence_id,))

    assert restored == (record,)
    assert restored[0].result.rows == ()


def test_codec_rejects_rows_that_no_longer_match_the_stored_digest():
    record = _record()
    payload = json.loads(encode_analysis_evidence_result(record.result))
    payload["rows"][0][0] = 2

    with pytest.raises(AnalysisEvidenceCodecError):
        decode_analysis_evidence_result(json.dumps(payload), payload_version=1)

    changed_result = AnalyticsQueryToolResult(
        code=record.result.code,
        columns=record.result.columns,
        rows=((2,),),
        truncated=record.result.truncated,
        evidence=record.result.evidence,
    )
    with pytest.raises(AnalysisEvidenceCodecError):
        encode_analysis_evidence_result(changed_result)


@pytest.mark.parametrize("risk", [QueryRisk.HIGH, QueryRisk.BLOCKED])
def test_high_or_blocked_success_evidence_is_rejected(risk):
    with pytest.raises(ValueError):
        _record(risk=risk)
