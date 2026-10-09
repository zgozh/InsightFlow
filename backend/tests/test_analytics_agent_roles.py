"""内部分析角色的合成安全边界与确定性验证链。"""

from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any, ClassVar

import httpx
import pytest
import pytest_asyncio
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables.config import var_child_runnable_config
from langchain_openai import ChatOpenAI
from pydantic import Field, PrivateAttr

from app.analytics.agent import roles as roles_module
from app.analytics.agent.evidence import canonical_json
from app.analytics.agent.roles import AnalysisRoleError, create_analysis_roles_capability
from app.analytics.domain import DatasourceEngine, QueryCostEstimate, QueryExecutionResult, QueryRisk
from app.analytics.domain.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult
from app.analytics.domain.metric import MetricDefinition, MetricStatus
from app.analytics.domain.verified_report import render_verified_report


class _CallbackProbe(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_end(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


_SDK_MODELS: list[ChatOpenAI] = []


def _default_http_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={}, request=request)


@pytest_asyncio.fixture(autouse=True)
async def _close_sdk_clients():
    _SDK_MODELS.clear()
    yield
    for model in _SDK_MODELS:
        if model.root_async_client is not None:
            await model.root_async_client.close()
        if model.root_client is not None:
            model.root_client.close()


class _RoleModel(ChatOpenAI):
    all_calls: ClassVar[list[dict[str, Any]]] = []
    max_tokens: int | None = None
    max_retries: int = 3
    tools: list[dict[str, Any]] | None = Field(default_factory=lambda: [{"name": "lead-tool"}])
    functions: list[dict[str, Any]] | None = Field(default_factory=lambda: [{"name": "lead-function"}])
    tool_choice: Any = "auto"
    default_tool_choice: Any = "auto"
    model_kwargs: dict[str, Any] = Field(
        default_factory=lambda: {
            "tools": [{"name": "model-kwargs-tool"}],
            "tool_choice": "auto",
            "max_tokens": 77,
            "temperature": 0,
        }
    )
    responses: list[Any] = Field(default_factory=list)
    delay_seconds: float = 0
    calls: list[dict[str, Any]] = Field(default_factory=list)
    _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def _llm_type(self) -> str:
        return "synthetic-analysis-role-openai"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("analysis roles must use the async model entry point")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self._started.set()
        type(self).all_calls.append(
            {
                "messages": messages,
                "kwargs": kwargs,
                "model": self,
                "handlers": tuple(getattr(run_manager, "handlers", ())),
                "tags": tuple(getattr(run_manager, "tags", ())),
                "metadata": dict(getattr(run_manager, "metadata", {}) or {}),
            }
        )
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        response = self.responses.pop(0) if self.responses else '{"sql":"SELECT 1"}'
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, BaseMessage):
            message = response
        else:
            message = AIMessage(content=response)
        return ChatResult(generations=[ChatGeneration(message=message)])


class _UnboundedModel(BaseChatModel):
    max_retries: int = 3

    @property
    def _llm_type(self) -> str:
        return "synthetic-unbounded-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("a model without an output-token field must not be bound")


def _snapshot(cell: object = 42, column: str = "amount") -> AnalyticsQueryToolResult:
    columns = (column,)
    rows = ((cell,),)
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
    return AnalyticsQueryToolResult(
        code="executed",
        columns=columns,
        rows=rows,
        truncated=False,
        evidence=evidence,
    )


def _metric() -> MetricDefinition:
    return MetricDefinition(
        key="sales_total",
        owner_id="OWNER_SECRET_SENTINEL",
        name="销售额",
        description="已登记销售金额",
        expression="sum(order_amount)",
        dimensions=("region",),
        version=3,
        status=MetricStatus.ACTIVE,
    )


def _role_model(*responses: Any) -> _RoleModel:
    async_http_client = httpx.AsyncClient(transport=httpx.MockTransport(_default_http_response))
    sync_http_client = httpx.Client(transport=httpx.MockTransport(_default_http_response))
    model = _RoleModel(
        model="gpt-synthetic",
        api_key="sk-local-test-only",
        base_url="https://offline.example/v1",
        max_retries=3,
        http_async_client=async_http_client,
        http_client=sync_http_client,
        responses=list(responses),
    )
    _SDK_MODELS.append(model)
    return model


def _standard_chat_openai(*, async_http_client: httpx.AsyncClient, max_retries: int = 2) -> ChatOpenAI:
    model = ChatOpenAI(
        model="gpt-synthetic",
        api_key="sk-local-test-only",
        base_url="https://offline.example/v1",
        max_retries=max_retries,
        http_async_client=async_http_client,
        http_client=httpx.Client(transport=httpx.MockTransport(_default_http_response)),
    )
    _SDK_MODELS.append(model)
    return model


def _capability(*responses: Any):
    _RoleModel.all_calls.clear()
    capability = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")
    model = _role_model(*responses)
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=model)
    return capability, model


def _claim_payload(snapshot: AnalyticsQueryToolResult, *, evidence_id: str | None = None) -> str:
    claim = {
        "id": "sales",
        "operation": "cell",
        "operands": [
            {
                "evidence_id": evidence_id or snapshot.evidence.evidence_id,
                "row_index": 0,
                "column_name": "amount",
            }
        ],
        "decimal_places": 0,
        "unit_reference": None,
        "period_reference": None,
    }
    return json.dumps(
        {
            "claims": [claim],
            "labels": [{"claim_id": "sales", "label": "销售额"}],
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    "branch",
    ["reference_domain", "claim_domain", "claim_label_ids", "numeric_verification"],
)
def test_data_parser_rejection_logs_only_fixed_reason_and_preserves_public_code(branch: str, caplog):
    snapshot = _snapshot()
    payload = json.loads(_claim_payload(snapshot))
    if branch == "reference_domain":
        payload["claims"][0]["operands"][0]["evidence_id"] = "SECRET_SENTINEL"
    elif branch == "claim_domain":
        payload["claims"][0]["id"] = "SECRET_SENTINEL"
    elif branch == "claim_label_ids":
        payload["labels"][0]["claim_id"] = "other-sentinel"
    else:
        payload["claims"][0]["operands"][0]["evidence_id"] = "f" * 64

    response = AIMessage(content=json.dumps(payload, ensure_ascii=False))
    with caplog.at_level(logging.WARNING, logger=roles_module.__name__):
        with pytest.raises(AnalysisRoleError) as failure:
            roles_module._parse_data_result(response, (snapshot,))

    assert failure.value.reason == "numeric_validation_failed"
    parser_records = [record for record in caplog.records if record.name == roles_module.__name__]
    assert len(parser_records) == 1
    assert parser_records[0].getMessage() == f"analysis_data_parser_rejected.{branch}"
    assert parser_records[0].args == ()
    assert parser_records[0].exc_info is None
    if branch == "numeric_verification":
        assert parser_records[0].numeric_claim_reason == "numeric_claim_reference_unavailable"
    else:
        assert not hasattr(parser_records[0], "numeric_claim_reason")
    assert str(failure.value) == "numeric_validation_failed"
    assert all(marker not in parser_records[0].getMessage() for marker in ("SECRET_SENTINEL", "other-sentinel", "f" * 64))


def test_data_parser_rejects_model_asserted_value_as_unknown_closed_schema_field():
    snapshot = _snapshot()
    payload = json.loads(_claim_payload(snapshot))
    payload["claims"][0]["value"] = "999999"

    with pytest.raises(AnalysisRoleError) as failure:
        roles_module._parse_data_result(AIMessage(content=json.dumps(payload, ensure_ascii=False)), (snapshot,))

    assert failure.value.reason == "invalid_response"


@pytest.mark.asyncio
async def test_data_reference_validation_feedback_retries_same_payload_once_and_caches_success():
    snapshot = _snapshot()
    invalid = _claim_payload(snapshot, evidence_id="f" * 64)
    valid = _claim_payload(snapshot)
    capability, _model = _capability(invalid, valid, valid)
    args = ("owner-1", "thread-1", "run-1", (snapshot,), ())

    with pytest.raises(AnalysisRoleError) as failure:
        await capability.analyze(*args)
    assert failure.value.reason == "numeric_validation_failed"
    assert "f" * 64 not in str(failure.value)

    result = await capability.analyze(*args)
    assert result.verified_claims[0].calculated_value == "42"
    assert len(_RoleModel.all_calls) == 2
    first_call, retry_call = _RoleModel.all_calls
    retry_system = retry_call["messages"][0].content
    assert "numeric_claim_reference_unavailable" in retry_system
    assert "请根据本次输入的证据修正引用或运算计划" in retry_system
    assert "f" * 64 not in retry_system
    assert first_call["messages"][1].content == retry_call["messages"][1].content

    cached = await capability.analyze(*args)
    assert cached.cached is True
    assert len(_RoleModel.all_calls) == 2


@pytest.mark.asyncio
async def test_repeated_invalid_data_plan_stops_at_two_attempt_limit():
    snapshot = _snapshot()
    invalid = _claim_payload(snapshot, evidence_id="f" * 64)
    capability, _model = _capability(invalid, invalid)
    args = ("owner-1", "thread-1", "run-1", (snapshot,), ())

    for _ in range(2):
        with pytest.raises(AnalysisRoleError) as failure:
            await capability.analyze(*args)
        assert failure.value.reason == "numeric_validation_failed"

    assert len(_RoleModel.all_calls) == 2
    assert "numeric_claim_reference_unavailable" in _RoleModel.all_calls[1]["messages"][0].content
    with pytest.raises(AnalysisRoleError) as exhausted:
        await capability.analyze(*args)
    assert exhausted.value.reason == "attempt_limit"
    assert len(_RoleModel.all_calls) == 2


@pytest.mark.asyncio
async def test_data_plan_validation_feedback_does_not_cross_payload_fingerprint():
    snapshot = _snapshot()
    invalid = _claim_payload(snapshot, evidence_id="f" * 64)
    valid = _claim_payload(snapshot)
    capability, _model = _capability(invalid, valid)

    with pytest.raises(AnalysisRoleError):
        await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), (), analysis_request="汇总")
    result = await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), (), analysis_request="比较")

    assert result.verified_claims[0].calculated_value == "42"
    assert len(_RoleModel.all_calls) == 2
    retry_system = _RoleModel.all_calls[1]["messages"][0].content
    assert "numeric_claim_reference_unavailable" not in retry_system
    assert "修正引用或运算计划" not in retry_system


@pytest.mark.asyncio
async def test_unknown_numeric_calculator_exception_fails_closed_without_retry_feedback(monkeypatch):
    snapshot = _snapshot()
    valid = _claim_payload(snapshot)
    capability, _model = _capability(valid, valid)

    def fail_with_unknown_error(*_args, **_kwargs):
        raise RuntimeError("UNKNOWN_ERROR_SENTINEL")

    monkeypatch.setattr(roles_module, "calculate_numeric_claim_plans", fail_with_unknown_error)
    with pytest.raises(AnalysisRoleError) as failure:
        await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), ())
    assert failure.value.reason == "numeric_validation_failed"
    assert "UNKNOWN_ERROR_SENTINEL" not in str(failure.value)

    monkeypatch.undo()
    result = await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), ())
    assert result.verified_claims[0].calculated_value == "42"
    assert len(_RoleModel.all_calls) == 2
    assert "numeric_claim_" not in _RoleModel.all_calls[1]["messages"][0].content


def test_valid_data_parser_response_has_no_rejection_log(caplog):
    snapshot = _snapshot()
    data_output = _claim_payload(snapshot)
    response = AIMessage(content=data_output)
    with caplog.at_level(logging.WARNING, logger=roles_module.__name__):
        result = roles_module._parse_data_result(response, (snapshot,))

    assert result.verified_claims[0].calculated_value == "42"
    assert result.labels[0].label == "销售额"
    assert "value" not in json.loads(data_output)["claims"][0]
    assert not any(record.name == roles_module.__name__ and record.getMessage().startswith("analysis_data_parser_rejected.") for record in caplog.records)


@pytest.mark.parametrize("invalid_label", ["Revenue 2026", "", " ", "x" * 81, "收入\n备注"])
def test_invalid_display_label_uses_fixed_operation_name(invalid_label: str, caplog):
    snapshot = _snapshot()
    payload = json.loads(_claim_payload(snapshot))
    payload["labels"][0]["label"] = invalid_label

    with caplog.at_level(logging.WARNING, logger=roles_module.__name__):
        result = roles_module._parse_data_result(AIMessage(content=json.dumps(payload, ensure_ascii=False)), (snapshot,))

    assert result.verified_claims[0].calculated_value == "42"
    assert result.labels[0].claim_id == "sales"
    assert result.labels[0].label == "引用单元格"
    assert not any(record.name == roles_module.__name__ for record in caplog.records)


@pytest.mark.parametrize(
    ("operation", "expected_value", "expected_label"),
    [
        ("cell", "42", "引用单元格"),
        ("sum", "84", "合计"),
        ("difference", "0", "差值"),
        ("ratio", "1", "比率"),
        ("percentage", "100", "占比"),
        ("mean", "42", "均值"),
        ("change_percentage", "0", "变动比例"),
    ],
)
def test_invalid_display_label_fallback_is_defined_for_each_operation(operation: str, expected_value: str, expected_label: str):
    snapshot = _snapshot()
    payload = json.loads(_claim_payload(snapshot))
    claim = payload["claims"][0]
    reference = claim["operands"][0]
    claim["operation"] = operation
    claim["operands"] = [reference] if operation == "cell" else [reference, reference]
    payload["labels"][0]["label"] = "Metric 2026"

    result = roles_module._parse_data_result(AIMessage(content=json.dumps(payload, ensure_ascii=False)), (snapshot,))

    assert result.verified_claims[0].calculated_value == expected_value
    assert result.labels[0].label == expected_label


@pytest.mark.parametrize("duplicate", ["claim", "label"])
def test_duplicate_claim_or_label_ids_are_rejected_after_label_fallback(duplicate: str, caplog):
    snapshot = _snapshot()
    payload = json.loads(_claim_payload(snapshot))
    payload["labels"][0]["label"] = "Metric 2026"
    if duplicate == "claim":
        payload["claims"].append(payload["claims"][0])
    else:
        payload["labels"].append(payload["labels"][0])

    with caplog.at_level(logging.WARNING, logger=roles_module.__name__):
        with pytest.raises(AnalysisRoleError) as failure:
            roles_module._parse_data_result(AIMessage(content=json.dumps(payload, ensure_ascii=False)), (snapshot,))

    assert failure.value.reason == "numeric_validation_failed"
    assert [record.getMessage() for record in caplog.records if record.name == roles_module.__name__] == ["analysis_data_parser_rejected.claim_label_ids"]


@pytest.mark.asyncio
async def test_three_roles_run_independently_verify_values_and_render_only_fixed_data():
    snapshot = _snapshot()
    sql_output = '{"sql":"SELECT amount FROM sales"}'
    layout_output = '{"sections":[{"kind":"summary","claim_ids":["sales"]}]}'
    capability, source = _capability(
        AIMessage(content=[{"type": "text", "text": sql_output}]),
        _claim_payload(snapshot),
        layout_output,
    )
    source.callbacks = [_CallbackProbe()]
    source.tools = [{"name": "lead-tool"}]
    source.functions = [{"name": "lead-function"}]
    source.tool_choice = "auto"
    source.default_tool_choice = "auto"
    original_callbacks = tuple(source.callbacks)
    source_callback = source.callbacks[0]
    ambient = _CallbackProbe()
    token = var_child_runnable_config.set({"callbacks": [ambient], "tags": ["lead-run"], "metadata": {"run_id": "run-1"}})
    try:
        sql_result = await capability.refine_sql(
            "owner-1",
            "thread-1",
            "run-1",
            "source-1",
            "SELECT amount FROM sales",
            (_metric(),),
        )
        cached_sql = await capability.refine_sql(
            "owner-1",
            "thread-1",
            "run-1",
            "source-1",
            "SELECT amount FROM sales",
            (_metric(),),
        )
        data_result = await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), (_metric(),))
        layout = await capability.layout(
            "owner-1",
            "thread-1",
            "run-1",
            data_result.verified_claims,
            data_result.labels,
        )
    finally:
        var_child_runnable_config.reset(token)

    rendered = render_verified_report(layout, data_result.labels, data_result.verified_claims)
    assert sql_result.sql == cached_sql.sql == "SELECT amount FROM sales"
    assert sql_result.input_tokens == cached_sql.input_tokens
    assert sql_result.output_tokens == cached_sql.output_tokens
    assert sql_result.cached is False
    assert cached_sql.cached is True
    assert data_result.verified_claims[0].calculated_value == "42"
    assert "42" in rendered and "sales" in rendered
    role_calls = _RoleModel.all_calls
    assert all(call["model"] is not source for call in role_calls)
    assert len(role_calls) == 3
    assert len({id(call["model"]) for call in role_calls}) == 3
    assert [call["kwargs"]["max_tokens"] for call in role_calls] == [2_048, 4_096, 1_024]
    assert len({call["messages"][0].content for call in role_calls}) == 3
    assert all(ambient not in call["handlers"] and source_callback not in call["handlers"] and "lead-run" not in call["tags"] and "run_id" not in call["metadata"] for call in role_calls)
    assert ambient.calls == 0
    assert source.callbacks == list(original_callbacks)
    assert source.tools == [{"name": "lead-tool"}]
    assert source.functions == [{"name": "lead-function"}]
    assert source.tool_choice == "auto" and source.default_tool_choice == "auto"
    assert source.max_retries == 3
    assert source.root_async_client.max_retries == 3
    assert source.root_client.max_retries == 3
    for call in role_calls:
        model = call["model"]
        assert model.max_retries == 0
        assert model.root_async_client.max_retries == 0
        assert model.root_async_client._client is source.root_async_client._client
        assert model.root_client.max_retries == 0
        assert model.root_client._client is source.root_client._client
        assert model.callbacks == []
        assert model.tags == []
        assert model.metadata == {}
        assert model.tools is None and model.functions is None
        assert model.tool_choice is None and model.default_tool_choice is None
        assert "tools" not in model.model_kwargs and "tool_choice" not in model.model_kwargs
        assert "max_tokens" not in model.model_kwargs

    sql_input = json.loads(role_calls[0]["messages"][1].content)
    writer_input = json.loads(role_calls[2]["messages"][1].content)
    assert sql_input["metrics"][0]["version"] == 3
    assert "owner_id" not in sql_input["metrics"][0]
    assert "OWNER_SECRET_SENTINEL" not in role_calls[0]["messages"][1].content
    assert "rows" not in writer_input and "sql" not in writer_input
    data_contract = role_calls[1]["messages"][0].content
    writer_contract = role_calls[2]["messages"][0].content
    assert all(
        part in data_contract
        for part in (
            "unit_reference",
            "period_reference",
            "change_percentage",
            "ROUND_HALF_UP",
            "不得提供 value",
            "服务器使用 Decimal",
            "str.isnumeric()",
        )
    )
    assert all(part in writer_contract for part in ("sections", "summary|details|comparison", "claim_ids"))
    capability.close()


@pytest.mark.asyncio
async def test_binding_rejects_unbounded_runnablebinding_and_different_rebind():
    capability = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")
    source = _role_model()
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=source)
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=source)
    assert not capability.bind_lead_model(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-1",
        model=_role_model(),
    )

    unbounded = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-2")
    assert not unbounded.bind_lead_model(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-2",
        model=_UnboundedModel(),
    )
    wrapped = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-3")
    assert not wrapped.bind_lead_model(
        principal_id="owner-1",
        thread_id="thread-1",
        run_id="run-3",
        model=_role_model().bind(stop=["never"]),
    )


@pytest.mark.asyncio
async def test_chatopenai_role_copy_disables_sdk_retries_for_actual_async_request():
    requests: list[str] = []

    def fail_request(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(
            500,
            headers={"x-should-retry": "true"},
            json={"error": {"message": "synthetic provider failure", "type": "server_error"}},
            request=request,
        )

    async_http_client = httpx.AsyncClient(transport=httpx.MockTransport(fail_request))
    source = _standard_chat_openai(async_http_client=async_http_client, max_retries=2)
    capability = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-1")
    assert capability.bind_lead_model(principal_id="owner-1", thread_id="thread-1", run_id="run-1", model=source)
    role_model = capability._AnalysisRolesCapability__models["sql_analyst"].model
    assert source.root_async_client.max_retries == 2
    assert role_model.root_async_client is not source.root_async_client
    assert role_model.async_client is role_model.root_async_client.chat.completions
    assert role_model.root_async_client.max_retries == 0
    assert role_model.root_async_client._client is source.root_async_client._client
    assert source.root_client.max_retries == 2
    assert role_model.root_client is not source.root_client
    assert role_model.root_client.max_retries == 0
    assert role_model.root_client._client is source.root_client._client

    with pytest.raises(AnalysisRoleError) as provider_failure:
        await capability.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 1", ())
    assert provider_failure.value.reason == "unavailable"
    assert requests == ["/v1/chat/completions"]
    assert source.root_async_client.max_retries == 2


@pytest.mark.asyncio
async def test_identity_unbound_and_closed_calls_fail_before_model_use():
    capability, model = _capability('{"sql":"SELECT 1"}')
    with pytest.raises(AnalysisRoleError) as wrong_identity:
        await capability.refine_sql("other-user", "thread-1", "run-1", "source", "SELECT 1", ())
    assert wrong_identity.value.reason == "unavailable"
    assert model.calls == []

    capability.close()
    with pytest.raises(AnalysisRoleError) as closed_call:
        await capability.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 1", ())
    assert closed_call.value.reason == "unavailable"
    assert model.calls == []

    unbound = create_analysis_roles_capability(principal_id="owner-1", thread_id="thread-1", run_id="run-4")
    with pytest.raises(AnalysisRoleError) as unbound_call:
        await unbound.refine_sql("owner-1", "thread-1", "run-4", "source", "SELECT 1", ())
    assert unbound_call.value.reason == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        RuntimeError("PROVIDER_SECRET_SENTINEL"),
        '{"sql":"first","sql":"second"}',
        '{"sql":NaN}',
        chr(96) * 3 + "json" + chr(10) + '{"sql":"SELECT 1"}' + chr(10) + chr(96) * 3,
        AIMessage(content="{}", tool_calls=[{"id": "tool-1", "name": "secret-tool", "args": {}}]),
    ],
)
async def test_provider_and_invalid_response_consume_attempts_without_leaking_details(response):
    capability, model = _capability(response, '{"sql":"SELECT 2"}', '{"sql":"SELECT 3"}')
    with pytest.raises(AnalysisRoleError) as first:
        await capability.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 1", ())
    assert first.value.reason == ("unavailable" if isinstance(response, RuntimeError) else "invalid_response")
    assert "PROVIDER_SECRET_SENTINEL" not in str(first.value)

    second = await capability.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 2", ())
    assert second.sql == "SELECT 2"
    with pytest.raises(AnalysisRoleError) as third:
        await capability.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 3", ())
    assert third.value.reason == "attempt_limit"
    assert len(_RoleModel.all_calls) == 2


@pytest.mark.asyncio
async def test_missing_source_plan_never_reaches_writer():
    snapshot = _snapshot()
    capability, model = _capability(_claim_payload(snapshot, evidence_id="f" * 64), '{"sections":[]}')
    with pytest.raises(AnalysisRoleError) as failure:
        await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), ())
    assert failure.value.reason == "numeric_validation_failed"
    assert len(_RoleModel.all_calls) == 1
    with pytest.raises(AnalysisRoleError) as writer_unbound:
        await capability.layout("owner-1", "thread-1", "run-1", (), ())
    assert writer_unbound.value.reason == "numeric_validation_failed"
    assert len(_RoleModel.all_calls) == 1


@pytest.mark.asyncio
async def test_analysis_request_is_forwarded_and_separates_success_cache_entries():
    snapshot = _snapshot()
    capability, _model = _capability(_claim_payload(snapshot), _claim_payload(snapshot))
    first = await capability.analyze(
        "owner-1",
        "thread-1",
        "run-1",
        (snapshot,),
        (),
        analysis_request="按销售额汇总",
    )
    second = await capability.analyze(
        "owner-1",
        "thread-1",
        "run-1",
        (snapshot,),
        (),
        analysis_request="按销售额比较",
    )
    assert first == second
    assert len(_RoleModel.all_calls) == 2
    requests = [json.loads(call["messages"][1].content)["analysis_request"] for call in _RoleModel.all_calls]
    assert requests == ["按销售额汇总", "按销售额比较"]
    assert all("不可信的待处理目标" in call["messages"][0].content for call in _RoleModel.all_calls)

    with pytest.raises(AnalysisRoleError) as too_long:
        await capability.analyze("owner-1", "thread-1", "run-1", (snapshot,), (), analysis_request="a" * 8_193)
    assert too_long.value.reason == "input_too_large"
    assert len(_RoleModel.all_calls) == 2


@pytest.mark.asyncio
async def test_snapshot_lower_bound_and_bad_metric_reject_before_model_call():
    large_snapshot = _snapshot("x" * (70 * 1024), "large_column")
    capability, model = _capability('{"claims":[],"labels":[]}')
    with pytest.raises(AnalysisRoleError) as too_large:
        await capability.analyze("owner-1", "thread-1", "run-1", (large_snapshot,), ())
    assert too_large.value.reason == "input_too_large"

    duplicate_metric = _metric()
    with pytest.raises(AnalysisRoleError) as duplicate:
        await capability.refine_sql(
            "owner-1",
            "thread-1",
            "run-1",
            "source",
            "SELECT 1",
            (duplicate_metric, duplicate_metric),
        )
    assert duplicate.value.reason == "unavailable"
    assert len(_RoleModel.all_calls) == 0


@pytest.mark.asyncio
async def test_timeout_and_cancellation_are_bounded_and_cancellation_propagates(monkeypatch):
    token_budget, output_bytes, _timeout = roles_module._ROLE_LIMITS["sql_analyst"]
    monkeypatch.setitem(roles_module._ROLE_LIMITS, "sql_analyst", (token_budget, output_bytes, 0.01))
    timed, _timed_source = _capability('{"sql":"SELECT 1"}')
    timed_role = timed._AnalysisRolesCapability__models["sql_analyst"]
    timed_role.model.delay_seconds = 0.1
    with pytest.raises(AnalysisRoleError) as timeout_error:
        await timed.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 1", ())
    assert timeout_error.value.reason == "unavailable"
    assert len(_RoleModel.all_calls) == 1
    monkeypatch.setitem(roles_module._ROLE_LIMITS, "sql_analyst", (token_budget, output_bytes, 1))

    cancelled, _cancelled_source = _capability('{"sql":"SELECT 2"}')
    role_model = cancelled._AnalysisRolesCapability__models["sql_analyst"].model
    role_model.delay_seconds = 30
    call = asyncio.create_task(cancelled.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 2", ()))
    await role_model._started.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    role_model.delay_seconds = 0
    assert (await cancelled.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 2", ())).sql == "SELECT 2"
    with pytest.raises(AnalysisRoleError) as exhausted:
        await cancelled.refine_sql("owner-1", "thread-1", "run-1", "source", "SELECT 3", ())
    assert exhausted.value.reason == "attempt_limit"


@pytest.mark.asyncio
async def test_query_scope_serializes_work_and_caps_started_attempts_even_after_cancellation():
    capability, _model = _capability()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def hold_first():
        async with capability.serialize_query("owner-1", "thread-1", "run-1"):
            first_started.set()
            await release_first.wait()

    async def enter_second():
        async with capability.serialize_query("owner-1", "thread-1", "run-1"):
            second_started.set()

    first = asyncio.create_task(hold_first())
    await first_started.wait()
    second = asyncio.create_task(enter_second())
    await asyncio.sleep(0)
    assert not second_started.is_set()
    release_first.set()
    await asyncio.gather(first, second)
    assert second_started.is_set()

    async def cancelled_query():
        async with capability.serialize_query("owner-1", "thread-1", "run-1"):
            await asyncio.Event().wait()

    cancelled = asyncio.create_task(cancelled_query())
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    # The serialization and cancellation above consumed three started queries.
    async with capability.serialize_query("owner-1", "thread-1", "run-1"):
        pass
    with pytest.raises(AnalysisRoleError) as exhausted:
        async with capability.serialize_query("owner-1", "thread-1", "run-1"):
            raise AssertionError("attempt five must not enter its body")
    assert exhausted.value.reason == "attempt_limit"


@pytest.mark.asyncio
async def test_query_scope_rechecks_identity_and_close_after_waiting_for_lock():
    capability, _model = _capability()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold():
        async with capability.serialize_query("owner-1", "thread-1", "run-1"):
            entered.set()
            await release.wait()

    holder = asyncio.create_task(hold())
    await entered.wait()
    wrong_scope = asyncio.create_task(capability.serialize_query("other-owner", "thread-1", "run-1").__aenter__())
    await asyncio.sleep(0)
    capability.close()
    release.set()
    await holder
    with pytest.raises(AnalysisRoleError) as closed:
        await wrong_scope
    assert closed.value.reason == "unavailable"
