"""耐久 evidence collector 的 repository + 固定 artifact 接线。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.agent.evidence_bridge import create_durable_analysis_run_evidence_collector
from app.analytics.domain import DatasourceEngine, ExecutionDecisionCode, QueryCostEstimate, QueryExecutionResult, QueryRisk
from app.analytics.domain.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.evidence import SqlAnalysisEvidenceRepository
from app.gateway import path_utils
from app.gateway.analysis_query_artifacts import create_analysis_query_artifact_capability
from deerflow.config import paths as paths_module
from deerflow.config.paths import Paths


@pytest_asyncio.fixture
async def evidence_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analytics.db'}", poolclass=NullPool, echo=False)
    await bootstrap_analytics_schema(engine, backend="sqlite")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlAnalysisEvidenceRepository(sessions)
    finally:
        await engine.dispose()


def _result(*, code=ExecutionDecisionCode.EXECUTED, rows=((7,),)) -> AnalyticsQueryToolResult:
    truncated = code is ExecutionDecisionCode.RESULT_LIMIT_REACHED
    columns = ("value",)
    snapshot = canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8")
    execution = QueryExecutionResult(columns=columns, rows=rows, row_count=len(rows), byte_count=len(snapshot), truncated=truncated)
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="ds-1",
        query_hash="a" * 64,
        risk=QueryRisk.LOW,
        schema_version="schema-1",
        policy_version="policy-1",
        estimate=QueryCostEstimate(
            engine=DatasourceEngine.POSTGRESQL,
            estimated_rows=len(rows),
            engine_cost=Decimal("1"),
            plan_digest="b" * 64,
        ),
        result=execution,
        decision_code=code.value,
    )
    return AnalyticsQueryToolResult(
        code=code.value,
        columns=columns,
        rows=rows,
        truncated=truncated,
        evidence=evidence,
    )


def _capability(monkeypatch, root, *, principal_id="user-1", thread_id="thread-1", run_id="run-1"):
    paths = Paths(root)
    monkeypatch.setattr(paths_module, "get_paths", lambda: paths)
    monkeypatch.setattr(path_utils, "get_paths", lambda: paths)
    return create_analysis_query_artifact_capability(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        paths=paths,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "rows"),
    [
        (ExecutionDecisionCode.EXECUTED, ()),
        (ExecutionDecisionCode.RESULT_LIMIT_REACHED, ((7,),)),
    ],
)
async def test_durable_collector_persists_fixed_json_and_rebuilds_from_repository_and_file(monkeypatch, tmp_path, evidence_repository, code, rows):
    result = _result(code=code, rows=rows)
    artifact = _capability(monkeypatch, tmp_path / "sandbox")
    collector = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        repository=evidence_repository,
        artifact_capability=artifact,
    )

    assert await collector.record_success_durable(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        result=result,
    )
    evidence_id = result.evidence.evidence_id
    output_path = artifact._output_root / f"query-result-run-1-{evidence_id}.json"
    assert output_path.read_bytes() == canonical_json(result.to_payload()).encode("utf-8")

    rebuilt = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        repository=evidence_repository,
        artifact_capability=_capability(monkeypatch, tmp_path / "sandbox"),
    )
    assert await rebuilt.resolve_successful_queries_durable(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        evidence_ids=(evidence_id,),
    ) == (result,)
    assert (
        await rebuilt.resolve_successful_queries_durable(
            principal_id="other-user",
            thread_id="thread-1",
            run_id="run-1",
            evidence_ids=(evidence_id,),
        )
        is None
    )
    assert (
        await rebuilt.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-2",
            run_id="run-1",
            evidence_ids=(evidence_id,),
        )
        is None
    )
    assert (
        await rebuilt.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-2",
            evidence_ids=(evidence_id,),
        )
        is None
    )


@pytest.mark.asyncio
async def test_durable_collector_propagates_cancellation_before_file_write(monkeypatch, tmp_path):
    import asyncio

    class BlockingRepository:
        def __init__(self):
            self.started = asyncio.Event()

        async def put(self, _record):
            self.started.set()
            await asyncio.Event().wait()

        async def get_many(self, *_args):
            return ()

    repository = BlockingRepository()
    artifact = _capability(monkeypatch, tmp_path / "sandbox")
    collector = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        repository=repository,
        artifact_capability=artifact,
    )
    task = asyncio.create_task(
        collector.record_success_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-1",
            result=_result(),
        )
    )
    await repository.started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert not artifact._output_root.exists()


@pytest.mark.asyncio
async def test_durable_collector_restores_current_and_checkpoint_producer_evidence_in_request_order(monkeypatch, tmp_path, evidence_repository):
    producer_result = _result(rows=((1,),))
    current_result = _result(rows=((2,),))
    producer_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="producer-1")
    current_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="run-2")
    producer_writer = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="producer-1",
        repository=evidence_repository,
        artifact_capability=producer_artifact,
    )
    current_writer = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=evidence_repository,
        artifact_capability=current_artifact,
    )
    assert await producer_writer.record_success_durable(principal_id="user-1", thread_id="thread-1", run_id="producer-1", result=producer_result)
    assert await current_writer.record_success_durable(principal_id="user-1", thread_id="thread-1", run_id="run-2", result=current_result)

    reader = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=evidence_repository,
        artifact_capability=_capability(monkeypatch, tmp_path / "sandbox", run_id="run-2"),
        producer_run_id="producer-1",
        producer_artifact_capability=_capability(monkeypatch, tmp_path / "sandbox", run_id="producer-1"),
    )

    assert await reader.resolve_successful_queries_durable(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        evidence_ids=(current_result.evidence.evidence_id, producer_result.evidence.evidence_id),
    ) == (current_result, producer_result)
    assert await reader.resolve_successful_queries_durable(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        evidence_ids=(producer_result.evidence.evidence_id,),
    ) == (producer_result,)
    current_only_reader = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=evidence_repository,
        artifact_capability=_capability(monkeypatch, tmp_path / "sandbox", run_id="run-2"),
    )
    assert (
        await current_only_reader.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-2",
            evidence_ids=(producer_result.evidence.evidence_id,),
        )
        is None
    )


@pytest.mark.asyncio
async def test_durable_collector_rejects_cross_run_duplicate_evidence_and_tampered_source_artifact(monkeypatch, tmp_path, evidence_repository):
    result = _result()
    source_only_result = _result(rows=((99,),))
    producer_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="producer-1")
    current_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="run-2")
    for run_id, artifact in (("producer-1", producer_artifact), ("run-2", current_artifact)):
        writer = create_durable_analysis_run_evidence_collector(
            principal_id="user-1",
            thread_id="thread-1",
            run_id=run_id,
            repository=evidence_repository,
            artifact_capability=artifact,
        )
        assert await writer.record_success_durable(principal_id="user-1", thread_id="thread-1", run_id=run_id, result=result)
        if run_id == "producer-1":
            assert await writer.record_success_durable(principal_id="user-1", thread_id="thread-1", run_id=run_id, result=source_only_result)

    reader = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=evidence_repository,
        artifact_capability=_capability(monkeypatch, tmp_path / "sandbox", run_id="run-2"),
        producer_run_id="producer-1",
        producer_artifact_capability=producer_artifact,
    )
    assert await reader.resolve_successful_queries_durable(principal_id="user-1", thread_id="thread-1", run_id="run-2", evidence_ids=(result.evidence.evidence_id,)) is None

    destination = producer_artifact._output_root / f"query-result-producer-1-{source_only_result.evidence.evidence_id}.json"
    destination.write_bytes(b"tampered")
    assert await reader.resolve_successful_queries_durable(principal_id="user-1", thread_id="thread-1", run_id="run-2", evidence_ids=(source_only_result.evidence.evidence_id,)) is None


@pytest.mark.asyncio
async def test_durable_collector_keeps_combined_snapshot_budget_across_sources(monkeypatch, tmp_path, evidence_repository):
    from app.analytics.agent import evidence_bridge
    from app.analytics.domain.evidence import validate_successful_query_result

    producer_result = _result(rows=tuple((index,) for index in range(10)))
    current_result = _result(rows=tuple((index + 10,) for index in range(10)))
    combined_bytes = validate_successful_query_result(producer_result) + validate_successful_query_result(current_result)
    monkeypatch.setattr(evidence_bridge, "MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES", combined_bytes - 1)

    producer_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="producer-1")
    current_artifact = _capability(monkeypatch, tmp_path / "sandbox", run_id="run-2")
    for run_id, artifact, result in (
        ("producer-1", producer_artifact, producer_result),
        ("run-2", current_artifact, current_result),
    ):
        writer = create_durable_analysis_run_evidence_collector(
            principal_id="user-1",
            thread_id="thread-1",
            run_id=run_id,
            repository=evidence_repository,
            artifact_capability=artifact,
        )
        assert await writer.record_success_durable(principal_id="user-1", thread_id="thread-1", run_id=run_id, result=result)

    reader = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=evidence_repository,
        artifact_capability=_capability(monkeypatch, tmp_path / "sandbox", run_id="run-2"),
        producer_run_id="producer-1",
        producer_artifact_capability=producer_artifact,
    )

    assert (
        await reader.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-2",
            evidence_ids=(producer_result.evidence.evidence_id, current_result.evidence.evidence_id),
        )
        is None
    )


@pytest.mark.asyncio
async def test_durable_collector_rejects_repository_record_with_wrong_owner():
    from app.analytics.application.evidence_ports import StoredAnalysisEvidence

    result = _result()

    class ArtifactCapability:
        def matches(self, principal_id, thread_id, run_id):
            return (principal_id, thread_id, run_id) == ("user-1", "thread-1", "run-2")

        def virtual_path_for(self, evidence_id):
            return f"/mnt/user-data/outputs/query-result-run-2-{evidence_id}.json"

        async def write(self, _record):
            return True

        async def verify(self, _record):
            return True

    artifact = ArtifactCapability()
    wrong_owner_record = StoredAnalysisEvidence(
        principal_id="other-user",
        thread_id="thread-1",
        run_id="run-2",
        result=result,
        artifact_path=artifact.virtual_path_for(result.evidence.evidence_id),
        created_at=datetime.now(UTC),
    )

    class MisScopedRepository:
        async def put(self, _record):
            return None

        async def get_many(self, *_args):
            return (wrong_owner_record,)

    collector = create_durable_analysis_run_evidence_collector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-2",
        repository=MisScopedRepository(),
        artifact_capability=artifact,
    )

    assert (
        await collector.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-2",
            evidence_ids=(result.evidence.evidence_id,),
        )
        is None
    )


@pytest.mark.asyncio
async def test_query_artifact_capability_is_create_only_scope_bound_and_rejects_special_files(monkeypatch, tmp_path):
    artifact = _capability(monkeypatch, tmp_path / "sandbox")
    record_result = _result()
    from app.analytics.application.evidence_ports import StoredAnalysisEvidence

    record = StoredAnalysisEvidence(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        result=record_result,
        artifact_path=artifact.virtual_path_for(record_result.evidence.evidence_id),
        created_at=datetime.now(UTC),
    )

    assert await artifact.write(record)
    assert await artifact.write(record)
    assert await artifact.verify(record)
    destination = artifact._output_root / f"query-result-run-1-{record.evidence_id}.json"
    original = destination.read_bytes()
    destination.write_bytes(b"different")
    assert not await artifact.verify(record)
    assert not await artifact.write(record)
    assert destination.read_bytes() == b"different"
    destination.unlink()
    destination.mkdir()
    assert not await artifact.verify(record)
    assert not await artifact.write(record)
    destination.rmdir()
    assert original == canonical_json(record_result.to_payload()).encode("utf-8")

    assert not await _capability(monkeypatch, tmp_path / "sandbox", thread_id="other-thread").verify(record)
    with pytest.raises(ValueError):
        artifact.virtual_path_for("../uploads/escape")


@pytest.mark.asyncio
async def test_query_artifact_capability_rejects_symlink_at_fixed_destination(monkeypatch, tmp_path):
    from support.symlinks import symlink_or_skip

    from app.analytics.application.evidence_ports import StoredAnalysisEvidence

    artifact = _capability(monkeypatch, tmp_path / "sandbox")
    result = _result()
    record = StoredAnalysisEvidence(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        result=result,
        artifact_path=artifact.virtual_path_for(result.evidence.evidence_id),
        created_at=datetime.now(UTC),
    )
    artifact._output_root.mkdir(parents=True)
    destination = artifact._output_root / f"query-result-run-1-{record.evidence_id}.json"
    target = tmp_path / "outside.json"
    target.write_bytes(b"outside")
    symlink_or_skip(destination, target)

    assert not await artifact.verify(record)
    assert not await artifact.write(record)
    assert target.read_bytes() == b"outside"
