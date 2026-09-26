"""受控报告 Reviewer 的合成安全边界。"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables.config import var_child_runnable_config
from langchain_openai import ChatOpenAI
from pydantic import Field, PrivateAttr

from app.analytics.agent.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json
from app.analytics.agent.reviewer import (
    MAX_ANALYSIS_REVIEWER_OUTPUT_TOKENS,
    create_analysis_report_reviewer_capability,
)
from app.analytics.domain import DatasourceEngine, QueryCostEstimate, QueryExecutionResult, QueryRisk


class _NoToolModel(BaseChatModel):
    """带可检查调用参数、响应和等待行为的离线模型。"""

    max_tokens: int | None = None
    responses: list[Any] = Field(default_factory=list)
    delay_seconds: float = 0
    messages_seen: list[list[BaseMessage]] = Field(default_factory=list)
    invocation_kwargs: list[dict[str, Any]] = Field(default_factory=list)
    _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def _llm_type(self) -> str:
        return "synthetic-no-tool-reviewer"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("Reviewer must use its async model entry point")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.messages_seen.append(messages)
        self.invocation_kwargs.append(kwargs)
        self._started.set()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        response = self.responses.pop(0) if self.responses else '{"approved":true,"reason_code":"approved"}'
        if isinstance(response, BaseMessage):
            message = response
        elif isinstance(response, BaseException):
            raise response
        else:
            message = AIMessage(content=response)
        return ChatResult(generations=[ChatGeneration(message=message)])


class _UnboundedModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "synthetic-unbounded-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("An unbounded model must never be invoked for review")


class _CallbackProbe(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_end(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


def _successful_snapshot() -> tuple[AnalyticsQueryToolResult, str]:
    columns = ("amount",)
    rows = ((42,),)
    byte_count = len(canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8"))
    result = QueryExecutionResult(columns=columns, rows=rows, row_count=1, byte_count=byte_count, truncated=False)
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="synthetic-source",
        query_hash="b" * 64,
        risk=QueryRisk.LOW,
        schema_version="synthetic-schema-v1",
        policy_version="synthetic-policy-v1",
        estimate=QueryCostEstimate(
            engine=DatasourceEngine.POSTGRESQL,
            estimated_rows=1,
            engine_cost=Decimal("1"),
            plan_digest="c" * 64,
        ),
        result=result,
    )
    return (
        AnalyticsQueryToolResult(
            code="executed",
            columns=columns,
            rows=rows,
            truncated=False,
            evidence=evidence,
        ),
        evidence.evidence_id,
    )


def _capability(*, responses: list[Any] | None = None, delay_seconds: float = 0):
    snapshot, evidence_id = _successful_snapshot()
    capability = create_analysis_report_reviewer_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")
    model = _NoToolModel(responses=list(responses or []), delay_seconds=delay_seconds)
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=model)
    return capability, model, snapshot, evidence_id


async def _review(capability, snapshot, evidence_id, markdown="# Synthetic result is 42.\n", *, owner="owner-1"):
    return await capability.review(
        principal_id=owner,
        thread_id="thread-1",
        run_id="run-1",
        title="Synthetic report",
        markdown=markdown,
        evidence_ids=(evidence_id,),
        snapshots=(snapshot,),
    )


@pytest.mark.asyncio
async def test_reviewer_uses_the_bound_lead_model_without_tools_or_inherited_run_callbacks():
    capability, model, snapshot, evidence_id = _capability()
    probe = _CallbackProbe()
    token = var_child_runnable_config.set({"callbacks": [probe], "tags": ["lead-run"], "metadata": {"run_id": "run-1"}})
    try:
        result = await _review(capability, snapshot, evidence_id)
    finally:
        var_child_runnable_config.reset(token)

    assert result.code == "approved"
    assert probe.calls == 0
    assert len(model.messages_seen) == 1
    assert model.invocation_kwargs == [{"max_tokens": MAX_ANALYSIS_REVIEWER_OUTPUT_TOKENS}]
    review_payload = json.loads(model.messages_seen[0][1].content)
    assert review_payload["evidence_ids"] == [evidence_id]
    assert review_payload["successful_queries"][0]["rows"] == [[42]]
    assert "sql" not in review_payload["successful_queries"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_response", "expected_stage", "private_sentinel"),
    [
        (RuntimeError("REVIEWER_EXCEPTION_SECRET_SENTINEL"), "provider_error", "REVIEWER_EXCEPTION_SECRET_SENTINEL"),
        ("REVIEWER_RESPONSE_SECRET_SENTINEL", "invalid_response", "REVIEWER_RESPONSE_SECRET_SENTINEL"),
    ],
)
async def test_reviewer_failure_logs_only_safe_stage_and_run_id(caplog, model_response, expected_stage, private_sentinel):
    import logging

    from app.analytics.agent import reviewer as reviewer_module

    caplog.set_level(logging.WARNING, logger=reviewer_module.__name__)
    capability, _model, snapshot, evidence_id = _capability(responses=[model_response])

    result = await _review(capability, snapshot, evidence_id, markdown="# REVIEWER_INPUT_SECRET_SENTINEL\n")

    assert result.code == "analysis_review_unavailable"
    assert f"stage={expected_stage}" in caplog.text
    assert "run_id=run-1" in caplog.text
    assert private_sentinel not in caplog.text
    assert "REVIEWER_INPUT_SECRET_SENTINEL" not in caplog.text


@pytest.mark.asyncio
async def test_deepseek_reviewer_uses_the_legacy_token_field_on_the_real_sdk_wire_body():
    """Pin DeepSeek's wire contract through ChatOpenAI and an offline HTTP transport."""

    wire_bodies: list[dict[str, Any]] = []
    wire_metadata: list[tuple[str | None, str]] = []
    response_body = {
        "id": "offline-review",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": '{"approved":true,"reason_code":"approved"}'},
                "finish_reason": "stop",
            }
        ],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        wire_bodies.append(json.loads(request.content))
        wire_metadata.append((request.headers.get("authorization"), str(request.url)))
        return httpx.Response(200, json=response_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = ChatOpenAI(
        model="deepseek-flash",
        api_key="offline-test-key",
        base_url="https://offline.example/v1",
        http_async_client=client,
        max_retries=0,
        max_tokens=99,
        extra_body={"synthetic_option": "preserved"},
    )
    snapshot, evidence_id = _successful_snapshot()
    capability = create_analysis_report_reviewer_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=model)

    try:
        result = await _review(capability, snapshot, evidence_id)
    finally:
        await client.aclose()

    assert result.code == "approved"
    assert len(wire_bodies) == 1
    assert wire_metadata == [("Bearer offline-test-key", "https://offline.example/v1/chat/completions")]
    assert model.model_name == "deepseek-flash"
    assert model.max_tokens == 99
    body = wire_bodies[0]
    assert body["model"] == "deepseek-flash"
    assert body["max_tokens"] == MAX_ANALYSIS_REVIEWER_OUTPUT_TOKENS
    assert "max_completion_tokens" not in body
    assert "max_output_tokens" not in body
    assert "tools" not in body
    assert body["synthetic_option"] == "preserved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "not json",
        '{"approved":"true","reason_code":"approved"}',
        '{"approved":true,"reason_code":"approved","extra":"reject"}',
        '{"approved":true,"approved":false,"reason_code":"approved"}',
        AIMessage(content="", tool_calls=[{"id": "call-forbidden", "name": "task", "args": {}}]),
        "x" * 2049,
    ],
)
async def test_reviewer_rejects_non_closed_or_oversized_responses(response):
    capability, _model, snapshot, evidence_id = _capability(responses=[response])

    result = await _review(capability, snapshot, evidence_id)

    assert result.code == "analysis_review_unavailable"
    assert result.reason_code is None


@pytest.mark.asyncio
async def test_reviewer_limits_input_before_model_invocation(monkeypatch):
    from app.analytics.agent import reviewer as reviewer_module

    capability, model, snapshot, evidence_id = _capability()
    monkeypatch.setattr(reviewer_module, "MAX_ANALYSIS_REVIEWER_INPUT_BYTES", 1024)

    result = await _review(capability, snapshot, evidence_id, markdown="x" * 2048)

    assert result.code == "analysis_review_input_too_large"
    assert model.messages_seen == []


@pytest.mark.asyncio
async def test_reviewer_fails_closed_when_selected_model_has_no_enforceable_output_limit():
    snapshot, evidence_id = _successful_snapshot()
    capability = create_analysis_report_reviewer_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")

    assert not capability.bind_lead_model(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-1",
        model=_UnboundedModel(),
    )
    result = await _review(capability, snapshot, evidence_id)

    assert result.code == "analysis_review_unavailable"


@pytest.mark.asyncio
async def test_reviewer_budget_is_run_scoped_and_exact_approved_retries_are_cached():
    capability, model, snapshot, evidence_id = _capability(
        responses=[
            '{"approved":false,"reason_code":"unsupported_claim"}',
            '{"approved":true,"reason_code":"approved"}',
        ]
    )

    rejected = await _review(capability, snapshot, evidence_id, "# unsupported")
    rejected_retry = await _review(capability, snapshot, evidence_id, "# unsupported")
    approved = await _review(capability, snapshot, evidence_id, "# supported 42")
    approved_retry = await _review(capability, snapshot, evidence_id, "# supported 42")
    exhausted = await _review(capability, snapshot, evidence_id, "# another variant")

    assert rejected.code == rejected_retry.code == "analysis_review_rejected"
    assert rejected.reason_code == rejected_retry.reason_code == "unsupported_claim"
    assert approved.code == approved_retry.code == "approved"
    assert exhausted.code == "analysis_review_attempt_limit"
    assert len(model.messages_seen) == 2


@pytest.mark.asyncio
async def test_reviewer_serializes_concurrent_content_and_never_grants_more_than_two_attempts():
    capability, model, snapshot, evidence_id = _capability(
        responses=[
            '{"approved":true,"reason_code":"approved"}',
            '{"approved":true,"reason_code":"approved"}',
        ]
    )

    results = await asyncio.gather(
        _review(capability, snapshot, evidence_id, "# variant A"),
        _review(capability, snapshot, evidence_id, "# variant B"),
        _review(capability, snapshot, evidence_id, "# variant C"),
    )

    assert [result.code for result in results] == ["approved", "approved", "analysis_review_attempt_limit"]
    assert len(model.messages_seen) == 2


@pytest.mark.asyncio
async def test_reviewer_timeout_fails_closed_and_cancellation_propagates(monkeypatch, caplog):
    import logging

    from app.analytics.agent import reviewer as reviewer_module

    caplog.set_level(logging.WARNING, logger=reviewer_module.__name__)
    monkeypatch.setattr(reviewer_module, "ANALYSIS_REVIEWER_TIMEOUT_SECONDS", 0.01)
    timeout_capability, timeout_model, snapshot, evidence_id = _capability(delay_seconds=0.1)
    timed_out = await _review(timeout_capability, snapshot, evidence_id)
    assert timed_out.code == "analysis_review_unavailable"
    assert "stage=timeout" in caplog.text
    assert "run_id=run-1" in caplog.text
    assert len(timeout_model.messages_seen) == 1

    monkeypatch.setattr(reviewer_module, "ANALYSIS_REVIEWER_TIMEOUT_SECONDS", 30)
    cancel_capability, cancel_model, snapshot, evidence_id = _capability(delay_seconds=30)
    task = asyncio.create_task(_review(cancel_capability, snapshot, evidence_id))
    await cancel_model._started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The cancelled attempt consumes one slot, but the single allowed revision remains usable.
    cancel_model.delay_seconds = 0
    retry = await _review(cancel_capability, snapshot, evidence_id, "# revised")
    exhausted = await _review(cancel_capability, snapshot, evidence_id, "# another revision")
    assert retry.code == "approved"
    assert exhausted.code == "analysis_review_attempt_limit"
