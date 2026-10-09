import json
from pathlib import Path

import pytest

from app.analytics.agent.stages import (
    _FIELDS,
    ANALYSIS_STAGE_STORE_EVENT_TYPE,
    AnalysisStageEmitter,
    AnalysisStageError,
    stage_status_for_code,
    validate_analysis_stage_payload,
)


def test_runtime_projection_matches_the_frozen_contract_and_rejects_untrusted_fields():
    contract_path = Path(__file__).resolve().parents[2] / "contracts" / "analysis-stage.v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["additionalProperties"] is False
    assert set(contract["properties"]) == _FIELDS
    assert set(contract["required"]) == {"type", "version", "run_id", "seq", "stage", "status"}

    base = {"type": "analysis_stage", "version": 1, "run_id": "run-1", "seq": 1, "stage": "sql", "status": "running"}
    assert validate_analysis_stage_payload(base) == base
    for extra in ({"sql": "SELECT 1"}, {"rows": [[1]]}):
        with pytest.raises(ValueError):
            validate_analysis_stage_payload({**base, **extra})
    with pytest.raises(ValueError):
        validate_analysis_stage_payload({**base, "seq": True})
    with pytest.raises(ValueError):
        validate_analysis_stage_payload({**base, "input_tokens": False})


def test_role_usage_projection_omits_unknown_or_invalid_counters_and_marks_cache_hits():
    from types import SimpleNamespace

    from app.analytics.agent.roles import role_usage_fields

    assert role_usage_fields(SimpleNamespace(input_tokens=12, output_tokens=34, cached=False)) == {
        "input_tokens": 12,
        "output_tokens": 34,
    }
    assert role_usage_fields(SimpleNamespace(input_tokens=True, output_tokens=10_000_001, cached=True)) == {"cached": True}
    assert role_usage_fields(object()) == {}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("cost_limit_exceeded", "blocked"),
        ("policy_denied", "blocked"),
        ("execution_timeout", "failed"),
        ("database_unavailable", "failed"),
        ("result_limit_reached", "succeeded"),
        ("cancelled", "cancelled"),
        ("provider exception text", "failed"),
    ],
)
def test_stage_failure_codes_map_to_fixed_terminal_statuses(code, expected):
    assert stage_status_for_code(code) == expected


@pytest.mark.asyncio
async def test_stage_emitter_persists_the_same_payload_before_live_emit_and_keeps_cursors_distinct():
    order = []

    class Store:
        async def put(self, **event):
            record = {**event, "seq": 701 + len(order)}
            order.append(("put", record))
            return record

    def writer(payload):
        order.append(("writer", payload.copy()))

    emitter = AnalysisStageEmitter(principal_id="owner-1", thread_id="thread-1", run_id="run-1", event_store=Store())
    await emitter.emit(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-1",
        writer=writer,
        stage="catalog",
        status="running",
    )
    await emitter.emit(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-1",
        writer=writer,
        stage="catalog",
        status="succeeded",
        code="ok",
    )

    assert [kind for kind, _value in order] == ["put", "writer", "put", "writer", "put", "writer"]
    persisted = [value for kind, value in order if kind == "put"]
    live = [value for kind, value in order if kind == "writer"]
    assert all(event["event_type"] == ANALYSIS_STAGE_STORE_EVENT_TYPE for event in persisted)
    assert all(event["category"] == "analysis" and event["content"] == "" for event in persisted)
    assert [event["metadata"] for event in persisted] == live
    assert [event["metadata"]["seq"] for event in persisted] == [1, 2, 3]
    assert [event["seq"] for event in persisted] == [701, 703, 705]


@pytest.mark.asyncio
async def test_stage_store_failure_never_emits_and_finish_closes_open_stages_with_real_outcome():
    emitted = []

    class BrokenStore:
        async def put(self, **_event):
            raise OSError("private database detail")

    failed = AnalysisStageEmitter(principal_id="owner-1", thread_id="thread-1", run_id="run-1", event_store=BrokenStore())
    with pytest.raises(AnalysisStageError):
        await failed.emit(
            principal_id="owner-1",
            thread_id="thread-1",
            run_id="run-1",
            writer=emitted.append,
            stage="execution",
            status="running",
        )
    assert emitted == []

    class Store:
        async def put(self, **event):
            return {**event, "seq": 500 + len(emitted)}

    emitter = AnalysisStageEmitter(principal_id="owner-1", thread_id="thread-1", run_id="run-2", event_store=Store())
    await emitter.emit(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-2",
        writer=emitted.append,
        stage="data",
        status="running",
    )
    terminal = await emitter.finish(status="interrupted")
    assert [(item["stage"], item["status"]) for item in emitted] == [
        ("workflow", "running"),
        ("data", "running"),
    ]
    assert [(item["stage"], item["status"]) for item in terminal] == [
        ("data", "cancelled"),
        ("workflow", "cancelled"),
    ]
    emitter.close()
    with pytest.raises(AnalysisStageError):
        await emitter.emit(
            principal_id="owner-1",
            thread_id="thread-1",
            run_id="run-2",
            writer=emitted.append,
            stage="publish",
            status="running",
        )


@pytest.mark.asyncio
async def test_live_failure_keeps_durable_stage_and_workflow_terminalized_as_failed():
    persisted = []

    class Store:
        async def put(self, **event):
            persisted.append(event["metadata"].copy())

    def writer(payload):
        if payload["stage"] == "data" and payload["status"] == "running":
            raise OSError("stream is closed")

    emitter = AnalysisStageEmitter(principal_id="owner-1", thread_id="thread-1", run_id="run-3", event_store=Store())
    with pytest.raises(AnalysisStageError):
        await emitter.emit(
            principal_id="owner-1",
            thread_id="thread-1",
            run_id="run-3",
            writer=writer,
            stage="data",
            status="running",
        )

    with pytest.raises(AnalysisStageError):
        await emitter.finish(status="success")

    assert [(event["stage"], event["status"]) for event in persisted] == [
        ("workflow", "running"),
        ("data", "running"),
        ("data", "failed"),
        ("workflow", "failed"),
    ]
    assert persisted[-1]["code"] == "unavailable"
