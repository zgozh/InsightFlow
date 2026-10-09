"""Worker-level regression tests for the terminal run.delivery event (#4272 slice 1)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from deerflow.config.app_config import AppConfig
from deerflow.config.paths import Paths
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.config.tool_output_config import ToolOutputConfig
from deerflow.runtime.events.store.memory import MemoryRunEventStore
from deerflow.runtime.runs.manager import RunManager
from deerflow.runtime.runs.schemas import RunStatus
from deerflow.runtime.runs.store.memory import MemoryRunStore
from deerflow.runtime.runs.worker import RunContext, _build_runtime_context, _delivery_content_with_outputs, _install_runtime_context, _release_run_scoped_references, run_agent
from deerflow.runtime.user_context import get_effective_user_id


def _make_bridge():
    return SimpleNamespace(publish=AsyncMock(), publish_end=AsyncMock(), cleanup=AsyncMock())


def test_checkpoint_producer_metadata_overwrites_client_value():
    from deerflow.constants import DEERFLOW_ANALYSIS_RUN_ID_METADATA_KEY
    from deerflow.runtime.runs.worker import _stamp_checkpoint_producer_metadata

    original_metadata = {DEERFLOW_ANALYSIS_RUN_ID_METADATA_KEY: "client-forged", "retained": "value"}
    config = {"metadata": original_metadata}

    stamped = _stamp_checkpoint_producer_metadata(config, "server-run")

    assert stamped[DEERFLOW_ANALYSIS_RUN_ID_METADATA_KEY] == "server-run"
    assert stamped["retained"] == "value"
    assert original_metadata[DEERFLOW_ANALYSIS_RUN_ID_METADATA_KEY] == "client-forged"


async def _delivery_events(store: MemoryRunEventStore, thread_id: str, run_id: str) -> list[dict]:
    events = await store.list_events(thread_id, run_id)
    return [e for e in events if e["event_type"] == "run.delivery"]


def test_delivery_verification_treats_presented_directory_as_covering_produced_files():
    content = {
        "presented": 1,
        "paths": ["/mnt/user-data/outputs/site"],
        "by_tool": {"present_files": ["/mnt/user-data/outputs/site"]},
    }

    delivery = _delivery_content_with_outputs(
        content,
        [
            "/mnt/user-data/outputs/site/index.html",
            "/mnt/user-data/outputs/site/assets/style.css",
        ],
    )

    assert delivery["matched_paths"] == [
        "/mnt/user-data/outputs/site/index.html",
        "/mnt/user-data/outputs/site/assets/style.css",
    ]
    assert delivery["satisfied"] is True


def test_delivery_verification_accepts_only_the_run_bound_report_writer_receipt():
    run_id = "run_123"
    path = f"/mnt/user-data/outputs/analysis-report-{run_id}.md"
    content = {
        "presented": 1,
        "paths": [path],
        "by_tool": {"write_analysis_report": [path]},
    }

    delivery = _delivery_content_with_outputs(content, [path], run_id=run_id)

    assert delivery["matched_paths"] == [path]
    assert delivery["satisfied"] is True
    assert delivery["verification"]["requirement"] == "present_files_or_bound_analysis_report"

    forged = _delivery_content_with_outputs(content, ["/mnt/user-data/outputs/another.md"], run_id=run_id)
    assert forged["matched_paths"] == []
    assert forged["satisfied"] is False


def test_runtime_context_rejects_a_caller_forged_report_writer_capability():
    forged = object()
    runtime_context = _build_runtime_context(
        "thread_1",
        "run_1",
        {"__analysis_report_writer": forged},
    )
    config = {
        "context": {"__analysis_report_writer": forged},
        "configurable": {"__analysis_report_writer": forged},
    }

    _install_runtime_context(config, runtime_context)

    assert "__analysis_report_writer" not in runtime_context
    assert "__analysis_report_writer" not in config["context"]
    assert "__analysis_report_writer" not in config["configurable"]


def test_runtime_context_carries_the_gateway_collector_by_identity_without_checkpoint_config_or_cleanup_leak():
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY

    forged = object()
    collector = object()
    reviewer = SimpleNamespace(closed=False)
    reviewer.close = lambda: setattr(reviewer, "closed", True)
    roles = SimpleNamespace(closed=False)
    roles.close = lambda: setattr(roles, "closed", True)
    runtime_context = _build_runtime_context(
        "thread_1",
        "run_1",
        {
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: forged,
            ANALYSIS_ROLES_CONTEXT_KEY: forged,
            ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY: forged,
        },
        analysis_evidence_collector=collector,
        analysis_report_reviewer=reviewer,
        analysis_roles=roles,
    )
    config = {
        "context": {
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: forged,
            ANALYSIS_ROLES_CONTEXT_KEY: forged,
            ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY: forged,
        },
        "configurable": {
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: forged,
            ANALYSIS_ROLES_CONTEXT_KEY: forged,
            ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY: forged,
        },
    }

    _install_runtime_context(config, runtime_context)

    assert runtime_context[ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY] is collector
    assert config["context"][ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY] is collector
    assert runtime_context[ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY] is reviewer
    assert config["context"][ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY] is reviewer
    assert runtime_context[ANALYSIS_ROLES_CONTEXT_KEY] is roles
    assert config["context"][ANALYSIS_ROLES_CONTEXT_KEY] is roles
    assert ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY not in config["configurable"]
    assert ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY not in config["configurable"]
    assert ANALYSIS_ROLES_CONTEXT_KEY not in config["configurable"]
    assert forged not in runtime_context.values()

    _release_run_scoped_references([config], runtime_context, None)

    assert ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY not in runtime_context
    assert ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY not in config["context"]
    assert ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY not in runtime_context
    assert ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY not in config["context"]
    assert reviewer.closed is True
    assert ANALYSIS_ROLES_CONTEXT_KEY not in runtime_context
    assert ANALYSIS_ROLES_CONTEXT_KEY not in config["context"]
    assert roles.closed is True


@pytest.mark.anyio
async def test_preflight_failure_stays_error_without_constructing_agent():
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    assert await run_manager.fail_start_if_pending(record.run_id, error="analysis_mode_unavailable")
    factory_calls: list[object] = []
    bridge = _make_bridge()

    await run_agent(
        bridge,
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=MemoryRunEventStore()),
        agent_factory=lambda **kwargs: factory_calls.append(kwargs),
        graph_input={},
        config={},
    )

    current = await run_manager.get(record.run_id)
    assert current.status == RunStatus.error
    assert current.error == "analysis_mode_unavailable"
    assert factory_calls == []
    bridge.publish_end.assert_awaited_once()


@pytest.mark.anyio
async def test_delivery_event_records_present_files_paths_on_success():
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            journal = config["context"]["__run_journal"]
            ai = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "present_files", "args": {}}])
            journal._remember_current_run_tool_calls(ai, caller="lead_agent")
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": ["/mnt/user-data/outputs/report.md"],
                        "messages": [ToolMessage("Successfully presented files", tool_call_id="call_1")],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )
    await asyncio.sleep(0)

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"]["presented"] == 1
    assert delivery[0]["content"]["paths"] == ["/mnt/user-data/outputs/report.md"]
    assert delivery[0]["content"]["by_tool"] == {"present_files": ["/mnt/user-data/outputs/report.md"]}
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.success


@pytest.mark.anyio
async def test_delivery_event_presented_zero_without_artifact_production():
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )
    await asyncio.sleep(0)

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"] == {"presented": 0, "paths": [], "by_tool": {}}
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.success


@pytest.mark.anyio
async def test_changed_outputs_succeed_when_a_produced_output_is_presented(monkeypatch):
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    monkeypatch.setattr(
        "deerflow.runtime.runs.worker._produced_output_paths",
        AsyncMock(return_value=["/mnt/user-data/outputs/report.md"]),
    )

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            journal = config["context"]["__run_journal"]
            ai = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "present_files", "args": {}}])
            journal._remember_current_run_tool_calls(ai, caller="lead_agent")
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": ["/mnt/user-data/outputs/report.md"],
                        "messages": [ToolMessage("Successfully presented files", tool_call_id="call_1")],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert delivery[0]["content"] == {
        "presented": 1,
        "paths": ["/mnt/user-data/outputs/report.md"],
        "by_tool": {"present_files": ["/mnt/user-data/outputs/report.md"]},
        "verification": {
            "source": "outputs_changed",
            "requirement": "present_files_matches_produced_output",
        },
        "produced_paths": ["/mnt/user-data/outputs/report.md"],
        "presented_paths": ["/mnt/user-data/outputs/report.md"],
        "matched_paths": ["/mnt/user-data/outputs/report.md"],
        "stage": "presented",
        "satisfied": True,
    }
    assert record.status == RunStatus.success


@pytest.mark.anyio
async def test_changed_outputs_fail_closed_when_not_presented(monkeypatch):
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    monkeypatch.setattr(
        "deerflow.runtime.runs.worker._produced_output_paths",
        AsyncMock(return_value=["/mnt/user-data/outputs/report.md"]),
    )

    class ProseOnlyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": [AIMessage(content="SESSION SUMMARY")]}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: ProseOnlyAgent(),
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert delivery[0]["content"] == {
        "presented": 0,
        "paths": [],
        "by_tool": {},
        "verification": {
            "source": "outputs_changed",
            "requirement": "present_files_matches_produced_output",
        },
        "produced_paths": ["/mnt/user-data/outputs/report.md"],
        "presented_paths": [],
        "matched_paths": [],
        "stage": "not_started",
        "satisfied": False,
    }
    assert record.status == RunStatus.error
    assert record.error == "Artifact delivery incomplete: no produced output artifact was presented"
    assert record.stop_reason is None


@pytest.mark.anyio
async def test_externalized_tool_results_do_not_trigger_delivery_verification(tmp_path, monkeypatch):
    """Oversized tool outputs externalized under outputs/.tool-results/ are
    process feedback for the model, not deliverables: a run that only produced
    those files must succeed without any present_files call."""
    paths = Paths(base_dir=tmp_path)
    monkeypatch.setattr("deerflow.workspace_changes.recorder.get_paths", lambda: paths)
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()

    class ExternalizingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            # Simulates ToolOutputBudgetMiddleware persisting an oversized tool
            # output mid-run (default storage_subdir is ".tool-results").
            tool_results = paths.sandbox_outputs_dir("thread-1", user_id=get_effective_user_id()) / ".tool-results"
            tool_results.mkdir(parents=True, exist_ok=True)
            (tool_results / "bash-abcdef123456.log").write_text("x" * 20000, encoding="utf-8")
            yield {"messages": [AIMessage(content="Here is the answer.")]}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: ExternalizingAgent(),
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"] == {"presented": 0, "paths": [], "by_tool": {}}
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.success


@pytest.mark.anyio
async def test_custom_tool_output_storage_subdir_does_not_trigger_delivery_verification(tmp_path, monkeypatch):
    """A custom tool_output.storage_subdir is honoured by the exclusion, not
    only the default .tool-results name."""
    paths = Paths(base_dir=tmp_path)
    monkeypatch.setattr("deerflow.workspace_changes.recorder.get_paths", lambda: paths)
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    app_config = AppConfig(sandbox=SandboxConfig(use="test"), tool_output=ToolOutputConfig(storage_subdir="tool-output-cache"))

    class ExternalizingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            cache = paths.sandbox_outputs_dir("thread-1", user_id=get_effective_user_id()) / "tool-output-cache"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "web_fetch-abcdef123456.log").write_text("y" * 20000, encoding="utf-8")
            yield {"messages": [AIMessage(content="Here is the answer.")]}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store, app_config=app_config),
        agent_factory=lambda *, config: ExternalizingAgent(),
        graph_input={},
        config={},
    )

    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.success


@pytest.mark.anyio
async def test_changed_outputs_succeed_when_one_of_multiple_outputs_is_presented(monkeypatch):
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    monkeypatch.setattr(
        "deerflow.runtime.runs.worker._produced_output_paths",
        AsyncMock(
            return_value=[
                "/mnt/user-data/outputs/report.md",
                "/mnt/user-data/outputs/appendix.md",
            ]
        ),
    )

    class PartiallyPresentingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            journal = config["context"]["__run_journal"]
            journal._remember_current_run_tool_calls(
                AIMessage(content="", tool_calls=[{"id": "call_1", "name": "present_files", "args": {}}]),
                caller="lead_agent",
            )
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": ["/mnt/user-data/outputs/report.md"],
                        "messages": [ToolMessage("Successfully presented files", tool_call_id="call_1")],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: PartiallyPresentingAgent(),
        graph_input={},
        config={},
    )

    delivery = (await _delivery_events(store, "thread-1", record.run_id))[0]["content"]
    assert delivery["stage"] == "presented"
    assert delivery["presented_paths"] == ["/mnt/user-data/outputs/report.md"]
    assert delivery["matched_paths"] == ["/mnt/user-data/outputs/report.md"]
    assert delivery["satisfied"] is True
    assert record.status == RunStatus.success


@pytest.mark.anyio
async def test_changed_outputs_fail_when_present_files_only_presents_an_unrelated_file(monkeypatch):
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    monkeypatch.setattr(
        "deerflow.runtime.runs.worker._produced_output_paths",
        AsyncMock(return_value=["/mnt/user-data/outputs/report.md"]),
    )

    class UnrelatedPresentingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            journal = config["context"]["__run_journal"]
            journal._remember_current_run_tool_calls(
                AIMessage(content="", tool_calls=[{"id": "call_1", "name": "present_files", "args": {}}]),
                caller="lead_agent",
            )
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": ["/mnt/user-data/outputs/old-report.md"],
                        "messages": [ToolMessage("Successfully presented files", tool_call_id="call_1")],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: UnrelatedPresentingAgent(),
        graph_input={},
        config={},
    )

    delivery = (await _delivery_events(store, "thread-1", record.run_id))[0]["content"]
    assert delivery["stage"] == "mismatched"
    assert delivery["presented_paths"] == ["/mnt/user-data/outputs/old-report.md"]
    assert delivery["matched_paths"] == []
    assert delivery["satisfied"] is False
    assert record.status == RunStatus.error


@pytest.mark.anyio
async def test_fenced_worker_leaves_delivery_receipt_to_peer_recovery():
    """A stale worker must not finalize the singleton delivery receipt."""
    run_manager = RunManager()
    record = await run_manager.create("thread-lease-lost")
    record.ownership_lost = True
    record.abort_event.set()
    record.status = RunStatus.error
    event_store = MemoryRunEventStore()
    thread_store = SimpleNamespace(
        update_display_name=AsyncMock(),
        update_status=AsyncMock(),
    )
    on_run_completed = AsyncMock()
    agent_factory = MagicMock(side_effect=AssertionError("fenced worker started the agent"))

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(
            checkpointer=None,
            event_store=event_store,
            thread_store=thread_store,
            on_run_completed=on_run_completed,
        ),
        agent_factory=agent_factory,
        graph_input={},
        config={},
    )

    assert await _delivery_events(event_store, record.thread_id, record.run_id) == []
    agent_factory.assert_not_called()
    thread_store.update_display_name.assert_not_awaited()
    thread_store.update_status.assert_not_awaited()
    on_run_completed.assert_not_awaited()


@pytest.mark.anyio
async def test_delivery_event_is_singleton_across_goal_continuations(monkeypatch):
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    stream_calls = 0
    continuation_calls = 0

    class ContinuingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            nonlocal stream_calls
            stream_calls += 1
            journal = config["context"]["__run_journal"]
            tool_call_id = f"call_{stream_calls}"
            journal._remember_current_run_tool_calls(
                AIMessage(content="", tool_calls=[{"id": tool_call_id, "name": "present_files", "args": {}}]),
                caller="lead_agent",
            )
            artifacts = ["/mnt/user-data/outputs/report.md"]
            if stream_calls == 2:
                artifacts.append("/mnt/user-data/outputs/appendix.md")
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": artifacts,
                        "messages": [ToolMessage("Successfully presented files", tool_call_id=tool_call_id)],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    async def prepare_continuation(**kwargs):
        nonlocal continuation_calls
        continuation_calls += 1
        if continuation_calls == 1:
            return {"messages": []}
        return None

    monkeypatch.setattr("deerflow.runtime.runs.worker._prepare_goal_continuation_input", prepare_continuation)

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: ContinuingAgent(),
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert stream_calls == 2
    assert len(delivery) == 1
    assert delivery[0]["content"] == {
        "presented": 2,
        "paths": [
            "/mnt/user-data/outputs/report.md",
            "/mnt/user-data/outputs/appendix.md",
        ],
        "by_tool": {
            "present_files": [
                "/mnt/user-data/outputs/report.md",
                "/mnt/user-data/outputs/appendix.md",
            ]
        },
    }


@pytest.mark.anyio
async def test_delivery_event_emitted_exactly_once_on_error_path():
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()

    class FailingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            raise RuntimeError("boom")
            yield  # pragma: no cover - make this an async generator

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store),
        agent_factory=lambda *, config: FailingAgent(),
        graph_input={},
        config={},
    )
    await asyncio.sleep(0)

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"]["presented"] == 0
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.error


@pytest.mark.anyio
async def test_delivery_is_durable_before_terminal_run_status():
    events = MemoryRunEventStore()

    class OrderingRunStore(MemoryRunStore):
        async def update_status(self, run_id, status, *, error=None, stop_reason=None):
            if status not in {"pending", "running"}:
                receipt = await events.list_events("thread-1", run_id, event_types=["run.delivery"])
                assert len(receipt) == 1
            return await super().update_status(run_id, status, error=error, stop_reason=stop_reason)

    run_store = OrderingRunStore()
    run_manager = RunManager(store=run_store)
    record = await run_manager.create("thread-1")

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=events),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    assert (await run_store.get(record.run_id))["status"] == "success"


@pytest.mark.anyio
async def test_delivery_write_retries_before_persisting_success():
    class FlakyReceiptStore(MemoryRunEventStore):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def put_if_absent(self, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient event store outage")
            return await super().put_if_absent(**kwargs)

    event_store = FlakyReceiptStore()
    run_store = MemoryRunStore()
    run_manager = RunManager(store=run_store)
    record = await run_manager.create("thread-1")

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=event_store),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    assert event_store.attempts == 2
    assert len(await _delivery_events(event_store, "thread-1", record.run_id)) == 1
    assert (await run_store.get(record.run_id))["status"] == "success"


@pytest.mark.anyio
async def test_delivery_write_failure_preserves_real_durable_terminal_status():
    class FailingReceiptStore(MemoryRunEventStore):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def put_if_absent(self, **kwargs):
            self.attempts += 1
            raise RuntimeError("event store unavailable")

    run_store = MemoryRunStore()
    run_manager = RunManager(store=run_store)
    record = await run_manager.create("thread-1")
    event_store = FailingReceiptStore()

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=event_store),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    # A receipt outage must not let lease recovery rewrite a genuine success
    # as an error. After bounded retries, preserve the worker's real outcome.
    assert event_store.attempts > 1
    assert record.status == RunStatus.success
    assert (await run_store.get(record.run_id))["status"] == "success"


@pytest.mark.anyio
async def test_produced_artifact_delivery_fails_closed_when_receipt_cannot_be_persisted(monkeypatch):
    class FailingReceiptStore(MemoryRunEventStore):
        async def put_if_absent(self, **kwargs):
            raise RuntimeError("event store unavailable")

    run_store = MemoryRunStore()
    run_manager = RunManager(store=run_store)
    record = await run_manager.create("thread-1")
    monkeypatch.setattr(
        "deerflow.runtime.runs.worker._produced_output_paths",
        AsyncMock(return_value=["/mnt/user-data/outputs/report.md"]),
    )

    class PresentingAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            journal = config["context"]["__run_journal"]
            journal._remember_current_run_tool_calls(
                AIMessage(content="", tool_calls=[{"id": "call_1", "name": "present_files", "args": {}}]),
                caller="lead_agent",
            )
            journal.on_tool_end(
                Command(
                    update={
                        "artifacts": ["/mnt/user-data/outputs/report.md"],
                        "messages": [ToolMessage("Successfully presented files", tool_call_id="call_1")],
                    }
                ),
                run_id=uuid4(),
            )
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=FailingReceiptStore()),
        agent_factory=lambda *, config: PresentingAgent(),
        graph_input={},
        config={},
    )

    assert record.status == RunStatus.error
    assert record.error == "Artifact delivery verification failed: terminal delivery receipt could not be persisted"
    assert (await run_store.get(record.run_id))["status"] == "error"


@pytest.mark.anyio
async def test_delivery_event_emitted_when_checkpoint_preflight_fails(monkeypatch):
    run_manager = RunManager()
    run_manager.update_run_completion = AsyncMock(wraps=run_manager.update_run_completion)
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    compatibility_check = AsyncMock(side_effect=RuntimeError("incompatible checkpoint"))
    monkeypatch.setattr("deerflow.runtime.runs.worker.aensure_checkpoint_mode_compatible", compatibility_check)

    def unexpected_agent_factory(**kwargs):
        raise AssertionError("agent must not be built after preflight failure")

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=object(), event_store=store),
        agent_factory=unexpected_agent_factory,
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"] == {"presented": 0, "paths": [], "by_tool": {}}
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.error
    run_manager.update_run_completion.assert_not_awaited()


@pytest.mark.anyio
async def test_delivery_event_emitted_when_cancelled_waiting_for_prior_finalization(monkeypatch):
    run_manager = RunManager()
    run_manager.update_run_completion = AsyncMock(wraps=run_manager.update_run_completion)
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    finalized_statuses = []

    async def finish_analysis(*, status):
        finalized_statuses.append(status)
        return ()

    monkeypatch.setattr(
        run_manager,
        "wait_for_prior_finalizing",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )

    def unexpected_agent_factory(**kwargs):
        raise AssertionError("agent must not be built after preflight cancellation")

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store, analysis_roles=SimpleNamespace(finish=finish_analysis)),
        agent_factory=unexpected_agent_factory,
        graph_input={},
        config={},
    )

    delivery = await _delivery_events(store, "thread-1", record.run_id)
    assert len(delivery) == 1
    assert delivery[0]["content"] == {"presented": 0, "paths": [], "by_tool": {}}
    fetched = await run_manager.get(record.run_id)
    assert fetched.status == RunStatus.interrupted
    assert finalized_statuses == ["interrupted"]
    run_manager.update_run_completion.assert_not_awaited()


@pytest.mark.anyio
async def test_analysis_stage_finalization_failure_cannot_leave_run_successful():
    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    finish = AsyncMock(side_effect=RuntimeError("private persistence detail"))

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            yield {"messages": []}

    await run_agent(
        _make_bridge(),
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store, analysis_roles=SimpleNamespace(finish=finish)),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    current = await run_manager.get(record.run_id)
    assert finish.await_args.kwargs == {"status": "success"}
    assert current.status == RunStatus.error
    assert current.error == "analysis_stage_unavailable"


@pytest.mark.anyio
async def test_analysis_stage_terminal_payloads_publish_on_bridge_after_graph_stream_closes():
    from app.analytics.agent.roles import create_analysis_roles_capability

    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = MemoryRunEventStore()
    roles = create_analysis_roles_capability(principal_id="owner-a", thread_id="thread-1", run_id=record.run_id, event_store=store)
    writer_open = True
    old_writer_payloads = []
    bridge_events = []

    def old_stream_writer(payload):
        if not writer_open:
            raise AssertionError("closed graph writer was reused after stream completion")
        old_writer_payloads.append(payload)

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            nonlocal writer_open
            try:
                await roles.emit_stage(
                    principal_id="owner-a",
                    thread_id="thread-1",
                    run_id=record.run_id,
                    writer=old_stream_writer,
                    stage="execution",
                    status="running",
                )
                yield {"messages": []}
            finally:
                writer_open = False

    bridge = _make_bridge()
    bridge.publish.side_effect = lambda run_id, event_type, payload: bridge_events.append((run_id, event_type, payload))
    bridge.publish_end.side_effect = lambda run_id: bridge_events.append((run_id, "end", None))

    await run_agent(
        bridge,
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store, analysis_roles=roles),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    persisted = await store.list_events("thread-1", record.run_id, event_types=["analysis.stage"])
    terminal_payloads = [payload for _run_id, event_type, payload in bridge_events if event_type == "custom" and payload["status"] != "running"]
    terminal_custom_indexes = [index for index, (_run_id, event_type, payload) in enumerate(bridge_events) if event_type == "custom" and payload["status"] != "running"]
    end_index = next(index for index, (_run_id, event_type, _payload) in enumerate(bridge_events) if event_type == "end")

    assert writer_open is False
    assert all(payload["status"] == "running" for payload in old_writer_payloads)
    assert record.status == RunStatus.success
    assert [payload for payload in terminal_payloads] == [event["metadata"] for event in persisted if event["metadata"]["status"] != "running"]
    assert terminal_payloads
    assert all(run_id == record.run_id for run_id, event_type, payload in bridge_events if event_type == "custom")
    assert all(index < end_index for index in terminal_custom_indexes)


@pytest.mark.anyio
async def test_analysis_stage_terminal_put_failure_does_not_publish_terminal_custom_event():
    from app.analytics.agent.roles import create_analysis_roles_capability

    class FailTerminalStore:
        def __init__(self):
            self.memory = MemoryRunEventStore()

        async def put(self, **event):
            if event["metadata"]["status"] != "running":
                raise OSError("private database detail")
            return await self.memory.put(**event)

        async def list_events(self, *args, **kwargs):
            return await self.memory.list_events(*args, **kwargs)

    run_manager = RunManager()
    record = await run_manager.create("thread-1")
    store = FailTerminalStore()
    roles = create_analysis_roles_capability(principal_id="owner-a", thread_id="thread-1", run_id=record.run_id, event_store=store)
    writer_open = True
    bridge_events = []

    def old_stream_writer(_payload):
        if not writer_open:
            raise AssertionError("closed graph writer was reused after stream completion")

    class DummyAgent:
        async def astream(self, graph_input, config=None, stream_mode=None, subgraphs=False):
            nonlocal writer_open
            try:
                await roles.emit_stage(
                    principal_id="owner-a",
                    thread_id="thread-1",
                    run_id=record.run_id,
                    writer=old_stream_writer,
                    stage="execution",
                    status="running",
                )
                yield {"messages": []}
            finally:
                writer_open = False

    bridge = _make_bridge()
    bridge.publish.side_effect = lambda run_id, event_type, payload: bridge_events.append((run_id, event_type, payload))
    bridge.publish_end.side_effect = lambda run_id: bridge_events.append((run_id, "end", None))

    await run_agent(
        bridge,
        run_manager,
        record,
        ctx=RunContext(checkpointer=None, event_store=store, analysis_roles=roles),
        agent_factory=lambda *, config: DummyAgent(),
        graph_input={},
        config={},
    )

    terminal_customs = [payload for _run_id, event_type, payload in bridge_events if event_type == "custom" and payload["status"] != "running"]
    persisted = await store.list_events("thread-1", record.run_id, event_types=["analysis.stage"])
    current = await run_manager.get(record.run_id)

    assert writer_open is False
    assert terminal_customs == []
    assert all(event["metadata"]["status"] == "running" for event in persisted)
    assert current.status == RunStatus.error
    assert current.error == "analysis_stage_unavailable"
