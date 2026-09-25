"""The /events route forwards task_id + after_seq to the store (#3779).

The subtask card pages through one subagent task's persisted steps via these
query params; this locks the wiring so a rename/typo can't silently drop them
(which would make reload backfill fetch the whole run again, or nothing).
"""

import hashlib
from types import SimpleNamespace
from unittest import mock

import pytest
from langchain_core.messages import HumanMessage

from deerflow.agents.middlewares.dynamic_context_middleware import DynamicContextMiddleware
from deerflow.runtime.events.store.memory import MemoryRunEventStore
from deerflow.runtime.journal import RunJournal


class _ModelRequestFake:
    """Minimal ModelRequest stand-in for the wrap_model_call hooks."""

    def __init__(self, messages, runtime):
        self.messages = list(messages)
        self.runtime = runtime

    def override(self, **kwargs):
        return _ModelRequestFake(kwargs.get("messages", self.messages), self.runtime)


@pytest.mark.anyio
async def test_list_run_events_forwards_task_id_and_after_seq():
    from app.gateway.routers.thread_runs import list_run_events

    calls: dict = {}

    class FakeStore:
        async def list_events(self, thread_id, run_id, *, event_types=None, task_id=None, limit=500, after_seq=None):
            calls.update(thread_id=thread_id, run_id=run_id, event_types=event_types, task_id=task_id, limit=limit, after_seq=after_seq)
            return [{"seq": 1, "event_type": "subagent.step"}]

    class FakeState:
        run_event_store = FakeStore()

    class FakeApp:
        state = FakeState()

    class FakeRequest:
        app = FakeApp()
        _deerflow_test_bypass_auth = True

    result = await list_run_events(
        thread_id="t1",
        run_id="r1",
        request=FakeRequest(),
        event_types="subagent.start,subagent.step,subagent.end",
        task_id="task-A",
        limit=500,
        after_seq=7,
    )

    assert result == [{"seq": 1, "event_type": "subagent.step"}]
    assert calls["task_id"] == "task-A"
    assert calls["after_seq"] == 7
    assert calls["event_types"] == ["subagent.start", "subagent.step", "subagent.end"]


@pytest.mark.anyio
async def test_list_run_events_redacts_historical_run_start_metadata():
    from app.gateway.routers.thread_runs import list_run_events

    stored_row = {
        "seq": 1,
        "event_type": "run.start",
        "metadata": {
            "caller": "lead_agent",
            "auth_token": "legacy-secret",
            "token_usage": 7,
        },
    }

    class FakeStore:
        async def list_events(self, thread_id, run_id, *, event_types=None, task_id=None, limit=500, after_seq=None):
            return [stored_row]

    class FakeState:
        run_event_store = FakeStore()

    class FakeApp:
        state = FakeState()

    class FakeRequest:
        app = FakeApp()
        _deerflow_test_bypass_auth = True

    events = await list_run_events(
        thread_id="legacy-thread",
        run_id="legacy-run",
        request=FakeRequest(),
        event_types=None,
        task_id=None,
        limit=500,
        after_seq=None,
    )

    assert events[0]["metadata"] == {
        "caller": "lead_agent",
        "token_usage": 7,
    }
    assert stored_row["metadata"]["auth_token"] == "legacy-secret"
    assert events[0] is not stored_row


@pytest.mark.anyio
async def test_list_run_events_projects_legacy_analytics_structures_without_mutating_store():
    import json

    from app.gateway.routers.thread_runs import list_run_events

    ai_content = {
        "type": "ai",
        "id": "legacy-ai",
        "content": "",
        "tool_calls": [
            {
                "id": "legacy-analytics-call",
                "name": "query_business_data",
                "args": {"datasource_id": "ds-1", "sql": "LEGACY_SQL_SENTINEL", "token": "LEGACY_TOKEN_SENTINEL"},
            }
        ],
    }
    tool_content = {
        "type": "tool",
        "id": "legacy-tool",
        "tool_call_id": "legacy-analytics-call",
        "content": json.dumps(
            {
                "code": "executed",
                "columns": ["LEGACY_COLUMN_SENTINEL"],
                "rows": [["LEGACY_ROW_SENTINEL"]],
                "row_count": 1,
                "evidence": {"evidence_id": "a" * 64},
                "secret": "LEGACY_SECRET_SENTINEL",
            }
        ),
    }
    stored_rows = [
        {"seq": 1, "run_id": "analytics-run", "event_type": "llm.ai.response", "content": ai_content, "metadata": {}},
        {"seq": 2, "run_id": "analytics-run", "event_type": "llm.tool.result", "content": tool_content, "metadata": {}},
        {
            "seq": 3,
            "run_id": "analytics-run",
            "event_type": "run.end",
            "content": {"messages": [ai_content, tool_content], "note": "arbitrary model text is preserved"},
            "metadata": {},
        },
        {
            "seq": 6,
            "run_id": "other-run",
            "event_type": "llm.ai.response",
            "content": {
                "type": "ai",
                "tool_calls": [{"id": "legacy-analytics-call", "name": "web_search", "args": {"query": "ordinary"}}],
            },
            "metadata": {},
        },
        {
            "seq": 4,
            "event_type": "subagent.step",
            "content": {
                "kind": "ai",
                "tool_calls": [
                    {
                        "name": "query_business_data",
                        "args": {"datasource_id": "ds-1", "sql": "SUBAGENT_LEGACY_SQL_SENTINEL"},
                    }
                ],
            },
            "metadata": {},
        },
        {
            "seq": 5,
            "event_type": "subagent.step",
            "content": {
                "kind": "tool",
                "tool_name": "query_business_data",
                "text": json.dumps({"code": "executed", "rows": [["SUBAGENT_LEGACY_ROW_SENTINEL"]]}),
            },
            "metadata": {},
        },
    ]

    class FakeStore:
        async def list_events(self, thread_id, run_id, *, event_types=None, task_id=None, limit=500, after_seq=None):
            return stored_rows

    class FakeState:
        run_event_store = FakeStore()

    class FakeApp:
        state = FakeState()

    class FakeRequest:
        app = FakeApp()
        _deerflow_test_bypass_auth = True

    events = await list_run_events(
        thread_id="legacy-thread",
        run_id="legacy-run",
        request=FakeRequest(),
        event_types=None,
        task_id=None,
        limit=500,
        after_seq=None,
    )

    encoded = json.dumps(events, ensure_ascii=False)
    assert not any(
        sentinel in encoded
        for sentinel in (
            "LEGACY_SQL_SENTINEL",
            "LEGACY_TOKEN_SENTINEL",
            "LEGACY_COLUMN_SENTINEL",
            "LEGACY_ROW_SENTINEL",
            "LEGACY_SECRET_SENTINEL",
            "SUBAGENT_LEGACY_SQL_SENTINEL",
            "SUBAGENT_LEGACY_ROW_SENTINEL",
        )
    )
    assert events[0]["content"]["tool_calls"][0]["args"] == {"datasource_id": "ds-1"}
    projected_result = json.loads(events[1]["content"]["content"])
    assert projected_result["evidence"]["evidence_id"] == "a" * 64
    assert events[2]["content"]["note"] == "arbitrary model text is preserved"
    assert stored_rows[0]["content"]["tool_calls"][0]["args"]["sql"] == "LEGACY_SQL_SENTINEL"
    assert "LEGACY_ROW_SENTINEL" in stored_rows[1]["content"]["content"]


@pytest.mark.anyio
async def test_effective_memory_flows_from_injection_to_the_existing_debug_api():
    """The production run-events route is the field-level consumer for M1.

    The event fires at the first model-request assembly (wrap_model_call),
    once injection results are known.
    """
    from app.gateway.routers.thread_runs import list_run_events

    store = MemoryRunEventStore()
    journal = RunJournal("r1", "t1", store, flush_threshold=100)
    runtime = SimpleNamespace(context={"__run_journal": journal})
    memory = "<memory>\nUser prefers Python.\n</memory>\n"
    mw = DynamicContextMiddleware()

    with (
        mock.patch("deerflow.agents.lead_agent.prompt._get_memory_context", return_value=memory),
        mock.patch("deerflow.agents.middlewares.dynamic_context_middleware.datetime") as mock_dt,
    ):
        mock_dt.now.return_value.strftime.return_value = "2026-05-08, Friday"
        update = mw.before_agent(
            {"messages": [HumanMessage(content="Hi", id="msg-1")]},
            runtime,
        )

    from langgraph.graph.message import add_messages

    assembled = add_messages([HumanMessage(content="Hi", id="msg-1")], update["messages"])

    mw.wrap_model_call(_ModelRequestFake(assembled, runtime), lambda _request: "response")
    await journal.flush()

    class FakeState:
        run_event_store = store

    class FakeApp:
        state = FakeState()

    class FakeRequest_:
        app = FakeApp()
        _deerflow_test_bypass_auth = True

    events = await list_run_events(
        thread_id="t1",
        run_id="r1",
        request=FakeRequest_(),
        event_types="context:memory",
        task_id=None,
        limit=500,
        after_seq=None,
    )

    effective_content = update["messages"][1].content
    assert events[0]["content"] == {
        "content_sha256": hashlib.sha256(effective_content.encode("utf-8")).hexdigest(),
        "project_context_revision": None,
        "project_shelf_revision": None,
    }
