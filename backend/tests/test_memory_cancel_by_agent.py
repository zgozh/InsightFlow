"""Regression for #5037: scoped cancellation of buffered memory extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from deerflow.agents.memory.backends.deermem.deer_mem import DeerMem
from deerflow.agents.memory.backends.deermem.deermem.core.queue import ConversationContext
from deerflow.agents.memory.manager import MemoryManager


def test_deermem_cancel_by_agent_uses_canonical_bucket(tmp_path) -> None:
    mem = DeerMem(backend_config={"storage_path": str(tmp_path)})
    with patch.object(mem._queue, "_schedule_timer"):
        mem._queue.add(thread_id="t1", messages=["m"], agent_name="research-agent", user_id="u1")
        mem._queue.add(thread_id="t2", messages=["m"], agent_name="other", user_id="u1")

    removed = mem.cancel_by_agent("Research-Agent", user_id="u1")

    assert removed == 1
    assert mem._queue.pending_count == 1
    assert mem._queue._items[0].agent_name == "other"


def test_deermem_clear_memory_cancels_before_and_after_clear(tmp_path) -> None:
    mem = DeerMem(backend_config={"storage_path": str(tmp_path)})
    mem._queue._items = [
        ConversationContext(thread_id="t1", messages=["m"], agent_name="research-agent", user_id="u1"),
        ConversationContext(thread_id="t2", messages=["m"], agent_name="other", user_id="u1"),
    ]
    mem._updater = MagicMock()

    def _clear(**kwargs):
        mem._queue._items.append(ConversationContext(thread_id="t-mid", messages=["m"], agent_name="research-agent", user_id="u1"))
        return {"facts": []}

    mem._updater.clear_memory_data.side_effect = _clear

    mem.clear_memory(agent_name="research-agent", user_id="u1")

    assert [c.agent_name for c in mem._queue._items] == ["other"]
    mem._updater.clear_memory_data.assert_called_once_with(agent_name="research-agent", user_id="u1")


def test_deermem_clear_all_cancels_all_pending_for_user(tmp_path) -> None:
    mem = DeerMem(backend_config={"storage_path": str(tmp_path)})
    mem._queue._items = [
        ConversationContext(thread_id="t1", messages=["m"], agent_name="a", user_id="u1"),
        ConversationContext(thread_id="t2", messages=["m"], agent_name="b", user_id="u1"),
        ConversationContext(thread_id="t3", messages=["m"], agent_name="a", user_id="u2"),
    ]
    mem._updater = MagicMock()
    mem._updater.clear_all_memory_data.return_value = {"facts": []}

    mem.clear_memory(user_id="u1")

    assert mem._queue.pending_count == 1
    assert mem._queue._items[0].user_id == "u2"
    mem._updater.clear_all_memory_data.assert_called_once_with(user_id="u1")


def test_base_memory_manager_cancel_by_agent_defaults_to_zero() -> None:
    class _Bare(MemoryManager):
        def add(self, thread_id, messages, *, agent_name=None, user_id=None, trace_id=None) -> None:
            return None

        def get_context(self, user_id, *, agent_name=None, thread_id=None) -> str:
            return ""

        @classmethod
        def from_config(cls, backend_config, *, mode="middleware", **host_hooks):
            return cls(backend_config=backend_config or {}, mode=mode)

    assert _Bare().cancel_by_agent("x", user_id="u") == 0


def test_deermem_cancel_by_agent_forwards_scoped_queue_kwargs(tmp_path) -> None:
    """Manager mapping: None agent → all_agents; named agent → canonical bucket."""
    mem = DeerMem(backend_config={"storage_path": str(tmp_path)})
    queue = MagicMock()
    queue.cancel_by_agent.return_value = 0
    mem._queue = queue

    mem.cancel_by_agent(None, user_id=None)
    queue.cancel_by_agent.assert_called_with(user_id=None, all_agents=True)

    mem.cancel_by_agent("Research-Agent", user_id="u1")
    queue.cancel_by_agent.assert_called_with("research-agent", user_id="u1", all_agents=False)
