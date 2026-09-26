"""`publish_analysis_report` 工具契约（Phase 4 任务 3）。

这个工具是 Phase 3 artifact 与报告索引之间的唯一关口，因此断言集中在四条边界：

1. **参数最小化**：模型可见参数恰为 `title` / `artifact_path` / `evidence_ids`；没有
   principal / thread / run / status / created_at / 幂等键；
2. **身份服务端派生**：principal 与 thread/run 只来自受信 runtime，工具结果里也不再回显它们；
3. **fail closed**：未绑定控制面、取不到身份、非法输入、存储异常都有稳定 code，且异常文本、
   DSN 与候选标题都不外泄；
4. **不读 artifact 内容**：工具只调用 `publish_report` 一个应用入口，不接触 sandbox 或文件系统。

这里的假件只替换**仓储**（最后一道 I/O 边界），其余全部走真实用例，因此领域不变量是真的被
执行过的，而不是被 mock 掉的。
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr

from app.analytics.agent import reports as agent_reports
from app.analytics.agent.runtime import bind_analytics_services, clear_analytics_services
from app.analytics.application.report_ports import ReportPublication
from app.analytics.application.reports import PublishAnalysisReport
from app.analytics.domain import AnalysisReport, ReportPublishCode, ReportStatus

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_PATH = "/mnt/user-data/outputs/business-analysis.md"
_TITLE = "2026 Q3 经营分析"


class _ReviewerModel(BaseChatModel):
    """通过可检查输入与调用参数的无网络模型替身。"""

    max_tokens: int | None = None
    responses: list[object] = Field(default_factory=list)
    delay_seconds: float = 0
    prompts: list[list[object]] = Field(default_factory=list)
    invocation_kwargs: list[dict] = Field(default_factory=list)
    _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def _llm_type(self) -> str:
        return "synthetic-analysis-reviewer"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise AssertionError("Reviewer must use its async model entry point")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        self.invocation_kwargs.append(kwargs)
        self._started.set()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        response = self.responses.pop(0) if self.responses else '{"approved":true,"reason_code":"approved"}'
        if isinstance(response, BaseException):
            raise response
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(response)))])


def _runtime(user_id="user-1", *, thread_id="thread-1", run_id="run-1"):
    from langgraph.prebuilt.tool_node import ToolRuntime

    resolved: dict = {}
    if user_id is not None:
        resolved["user_id"] = user_id
    if thread_id is not None:
        resolved["thread_id"] = thread_id
    if run_id is not None:
        resolved["run_id"] = run_id
    return ToolRuntime(state={}, context=resolved, config={}, stream_writer=lambda _: None, tool_call_id=None, store=None, tools=[])


def _report(**overrides) -> AnalysisReport:
    values = {
        "id": "report-1",
        "principal_id": "user-1",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "artifact_path": _PATH,
        "title": _TITLE,
        "status": ReportStatus.PUBLISHED,
        "evidence_ids": (_HASH_A,),
        "created_at": _NOW,
    }
    values.update(overrides)
    return AnalysisReport(**values)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Repo:
    """只替换仓储：记录真实用例交给它的不可变报告值。"""

    def __init__(self, *, code=ReportPublishCode.PUBLISHED, stored=None, error=None):
        self._code = code
        self._stored = stored
        self._error = error
        self.reports: list[AnalysisReport] = []

    async def publish(self, report):
        self.reports.append(report)
        if self._error is not None:
            raise self._error
        return ReportPublication(code=self._code, report=self._stored if self._stored is not None else report)

    async def list_for_principal(self, **_kwargs):  # pragma: no cover - 用例不调用读取侧
        raise AssertionError("publish must not read the index")


def _bind(repo) -> None:
    bind_analytics_services(SimpleNamespace(publish_report=PublishAnalysisReport(repository=repo, clock=_Clock(), id_issuer=lambda: "report-1")))


@pytest.fixture(autouse=True)
def _unbound():
    clear_analytics_services()
    yield
    clear_analytics_services()


def _body(raw: str) -> dict:
    return json.loads(raw)


async def _invoke(runtime, **arguments) -> tuple[str, dict]:
    """调用工具并同时返回原始字符串与解析后的 payload。

    保留原始字符串是刻意的：有几条断言检查的是"结果文本里不出现某个值"，
    只看解析后的 dict 会漏掉被塞进键名或嵌套字符串的情况。
    """

    raw = await agent_reports.publish_analysis_report.ainvoke({**arguments, "runtime": runtime})
    return raw, json.loads(raw)


# --- 参数面 -----------------------------------------------------------------


def test_the_model_visible_schema_is_exactly_three_fields():
    schema = agent_reports.publish_analysis_report.tool_call_schema

    assert set(schema.model_fields) == {"title", "artifact_path", "evidence_ids"}
    properties = schema.model_json_schema()["properties"]
    assert set(properties) == {"title", "artifact_path", "evidence_ids"}


@pytest.mark.parametrize(
    "forbidden",
    ["principal_id", "principal", "user_id", "thread_id", "run_id", "status", "created_at", "owner_id", "id", "publish_key", "sql", "content"],
)
def test_no_identity_or_authority_field_is_model_visible(forbidden):
    assert forbidden not in agent_reports.publish_analysis_report.tool_call_schema.model_fields


def test_the_injected_runtime_is_not_part_of_the_model_visible_schema():
    """`runtime` 由框架注入；它绝不能出现在模型可见的参数里。"""

    assert "runtime" not in agent_reports.publish_analysis_report.tool_call_schema.model_fields


def test_evidence_ids_is_declared_as_an_array_of_strings():
    declared = agent_reports.publish_analysis_report.tool_call_schema.model_json_schema()["properties"]["evidence_ids"]

    assert declared.get("type") == "array"
    assert declared.get("items", {}).get("type") == "string"


def test_the_tool_is_registered_under_a_stable_name():
    assert agent_reports.PUBLISH_REPORT_TOOL_NAME == "publish_analysis_report"
    assert agent_reports.publish_analysis_report.name == "publish_analysis_report"


def test_report_writer_schema_has_only_content_and_evidence_fields():
    schema = agent_reports.write_analysis_report.tool_call_schema

    assert set(schema.model_fields) == {"title", "markdown", "evidence_ids"}
    assert set(schema.model_json_schema()["properties"]) == {"title", "markdown", "evidence_ids"}


def _writer_runtime(capability=None, *, evidence_collector=None, reviewer=None, user_id="user-1", thread_id="thread-1", run_id="run-1"):
    runtime = _runtime(user_id=user_id, thread_id=thread_id, run_id=run_id)
    if evidence_collector is not None:
        from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY

        runtime.context[ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY] = evidence_collector
    if reviewer is not None:
        from deerflow.constants import ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY

        runtime.context[ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY] = reviewer
    if capability is not None:
        from deerflow.constants import ANALYSIS_REPORT_WRITER_CONTEXT_KEY

        runtime.context[ANALYSIS_REPORT_WRITER_CONTEXT_KEY] = capability
    return runtime


def _reviewer_capability(*, principal_id="user-1", thread_id="thread-1", run_id="run-1", responses=None, delay_seconds=0):
    from app.analytics.agent.reviewer import create_analysis_report_reviewer_capability

    reviewer = create_analysis_report_reviewer_capability(principal_id=principal_id, thread_id=thread_id, run_id=run_id)
    model = _ReviewerModel(responses=list(responses or []), delay_seconds=delay_seconds)
    assert reviewer.bind_lead_model(principal_id=principal_id, thread_id=thread_id, run_id=run_id, model=model)
    return reviewer, model


def _successful_run_evidence(*, principal_id="user-1", thread_id="thread-1", run_id="run-1"):
    from app.analytics.agent.evidence import (
        AnalyticsQueryEvidence,
        AnalyticsQueryToolResult,
        canonical_json,
        create_analysis_run_evidence_collector,
    )
    from app.analytics.domain import DatasourceEngine, QueryCostEstimate, QueryExecutionResult, QueryRisk

    columns = ("amount",)
    rows = ((42,),)
    byte_count = len(canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8"))
    query_result = QueryExecutionResult(columns=columns, rows=rows, row_count=1, byte_count=byte_count, truncated=False)
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="synthetic-datasource",
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
        result=query_result,
    )
    result = AnalyticsQueryToolResult(
        code="executed",
        columns=query_result.columns,
        rows=query_result.rows,
        truncated=query_result.truncated,
        evidence=evidence,
    )
    collector = create_analysis_run_evidence_collector(principal_id=principal_id, thread_id=thread_id, run_id=run_id)
    assert collector.record_success(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        result=result,
    )
    return collector, evidence.evidence_id


def _writer_capability(monkeypatch, tmp_path, *, principal_id="user-1", thread_id="thread-1", run_id="run-1"):
    from app.gateway import path_utils
    from app.gateway.analysis_report_writer import create_analysis_report_writer_capability
    from deerflow.config import paths as paths_module
    from deerflow.config.paths import Paths

    paths = Paths(tmp_path)
    monkeypatch.setattr(paths_module, "get_paths", lambda: paths)
    monkeypatch.setattr(path_utils, "get_paths", lambda: paths)
    return create_analysis_report_writer_capability(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        paths=paths,
    )


@pytest.mark.asyncio
async def test_report_writer_writes_then_indexes_and_returns_only_a_safe_receipt(monkeypatch, tmp_path):
    from langgraph.types import Command

    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, _model = _reviewer_capability()
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    markdown = "# Synthetic\n\nREPORT_BODY_SENTINEL SELECT SQL_SENTINEL\n"
    repo = _Repo()
    _bind(repo)

    command = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown=markdown,
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-report-writer",
    )

    assert isinstance(command, Command)
    expected_path = "/mnt/user-data/outputs/analysis-report-run-1.md"
    assert capability.output_path.read_text(encoding="utf-8") == markdown
    assert command.update["artifacts"] == [expected_path]
    assert len(repo.reports) == 1
    assert repo.reports[0].artifact_path == expected_path
    receipt = json.loads(command.update["messages"][0].content)
    assert receipt == {
        "code": "published",
        "report_id": "report-1",
        "artifact_path": expected_path,
        "evidence_ids": [evidence_id],
    }
    assert "REPORT_BODY_SENTINEL" not in json.dumps([message.model_dump() for message in command.update["messages"]])
    assert "principal_id" not in receipt and "thread_id" not in receipt and "run_id" not in receipt


@pytest.mark.asyncio
async def test_report_writer_requires_current_run_reviewer_before_any_write(monkeypatch, tmp_path, caplog):
    """Reviewer 缺失时，合法 evidence 也不能越过复核直接发布。"""

    import logging

    from app.analytics.agent import reviewer as reviewer_module

    caplog.set_level(logging.WARNING, logger=reviewer_module.__name__)
    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    runtime = _writer_runtime(capability, evidence_collector=collector)
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Needs reviewer\n",
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-missing-reviewer",
    )

    assert isinstance(result, str)
    assert _body(result) == {"code": "analysis_review_unavailable"}
    assert "stage=capability_unavailable" in caplog.text
    assert "run_id=run-1" in caplog.text
    assert repo.reports == []
    assert not capability.output_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ('{"approved":false,"reason_code":"unsupported_claim"}', {"code": "analysis_review_rejected", "reason_code": "unsupported_claim"}),
        ('{"approved":true,"reason_code":"approved","extra":"invalid"}', {"code": "analysis_review_unavailable"}),
        (RuntimeError("synthetic reviewer failure"), {"code": "analysis_review_unavailable"}),
    ],
)
async def test_report_writer_reviewer_rejection_or_invalid_response_has_zero_writes(monkeypatch, tmp_path, response, expected):
    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, model = _reviewer_capability(responses=[response])
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Must be reviewed\n",
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-review-denied",
    )

    assert isinstance(result, str)
    assert _body(result) == expected
    assert len(model.prompts) == 1
    assert repo.reports == []
    assert not capability.output_path.exists()


@pytest.mark.asyncio
async def test_report_writer_rejects_oversized_review_input_without_model_or_writes(monkeypatch, tmp_path):
    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, model = _reviewer_capability()
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# " + ("x" * (64 * 1024)),
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-review-input-large",
    )

    assert isinstance(result, str)
    assert _body(result) == {"code": "analysis_review_input_too_large"}
    assert model.prompts == []
    assert repo.reports == []
    assert not capability.output_path.exists()


@pytest.mark.asyncio
async def test_report_writer_timeout_and_cancellation_never_reach_file_or_index(monkeypatch, tmp_path):
    from app.analytics.agent import reviewer as reviewer_module

    monkeypatch.setattr(reviewer_module, "ANALYSIS_REVIEWER_TIMEOUT_SECONDS", 0.01)
    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, _model = _reviewer_capability(delay_seconds=0.1)
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    repo = _Repo()
    _bind(repo)

    timed_out = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Timeout\n",
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-review-timeout",
    )

    assert isinstance(timed_out, str)
    assert _body(timed_out) == {"code": "analysis_review_unavailable"}
    assert repo.reports == []
    assert not capability.output_path.exists()

    monkeypatch.setattr(reviewer_module, "ANALYSIS_REVIEWER_TIMEOUT_SECONDS", 30)
    cancel_capability = _writer_capability(monkeypatch, tmp_path, run_id="run-cancel")
    cancel_collector, cancel_evidence_id = _successful_run_evidence(run_id="run-cancel")
    cancel_reviewer, cancel_model = _reviewer_capability(run_id="run-cancel", delay_seconds=30)
    cancel_runtime = _writer_runtime(
        cancel_capability,
        evidence_collector=cancel_collector,
        reviewer=cancel_reviewer,
        run_id="run-cancel",
    )
    cancel_task = asyncio.create_task(
        agent_reports.write_analysis_report.coroutine(
            title=_TITLE,
            markdown="# Cancelled\n",
            evidence_ids=[cancel_evidence_id],
            runtime=cancel_runtime,
            tool_call_id="call-review-cancel",
        )
    )
    await cancel_model._started.wait()
    cancel_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancel_task

    assert repo.reports == []
    assert not cancel_capability.output_path.exists()


@pytest.mark.asyncio
async def test_report_writer_index_failure_leaves_reusable_file_but_no_success_receipt(monkeypatch, tmp_path):
    from langgraph.types import Command

    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, model = _reviewer_capability()
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    markdown = "# Retry after index failure\n"
    failing_repo = _Repo(error=RuntimeError("dsn=synthetic-secret"))
    _bind(failing_repo)

    failed = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown=markdown,
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-failed",
    )
    assert isinstance(failed, str)
    assert _body(failed) == {"code": "analytics_unavailable"}
    assert capability.output_path.read_text(encoding="utf-8") == markdown

    clear_analytics_services()
    successful_repo = _Repo()
    _bind(successful_repo)
    retried = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown=markdown,
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-retry",
    )
    assert isinstance(retried, Command)
    assert json.loads(retried.update["messages"][0].content)["code"] == "published"
    assert len(successful_repo.reports) == 1


@pytest.mark.asyncio
async def test_report_writer_same_run_same_evidence_and_content_retry_remains_existing(monkeypatch, tmp_path):
    from langgraph.types import Command

    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, model = _reviewer_capability()
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    markdown = "# Idempotent synthetic report\n"
    first_repo = _Repo()
    _bind(first_repo)

    first = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown=markdown,
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-first-report",
    )
    assert isinstance(first, Command)
    assert json.loads(first.update["messages"][0].content)["code"] == "published"

    stored = _report(
        id="report-original",
        run_id="run-1",
        artifact_path="/mnt/user-data/outputs/analysis-report-run-1.md",
        evidence_ids=(evidence_id,),
    )
    retry_repo = _Repo(code=ReportPublishCode.EXISTING, stored=stored)
    clear_analytics_services()
    _bind(retry_repo)
    retry = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown=markdown,
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-report-retry",
    )

    assert isinstance(retry, Command)
    assert json.loads(retry.update["messages"][0].content)["code"] == "existing"
    assert retry_repo.reports[0].identity == stored.identity
    assert len(model.prompts) == 1


@pytest.mark.asyncio
async def test_concurrent_report_variants_share_two_review_slots_and_create_only_artifact(monkeypatch, tmp_path):
    from langgraph.types import Command

    capability = _writer_capability(monkeypatch, tmp_path)
    collector, evidence_id = _successful_run_evidence()
    reviewer, model = _reviewer_capability(
        responses=[
            '{"approved":true,"reason_code":"approved"}',
            '{"approved":true,"reason_code":"approved"}',
        ]
    )
    runtime = _writer_runtime(capability, evidence_collector=collector, reviewer=reviewer)
    repo = _Repo()
    _bind(repo)

    async def publish(markdown: str, call_id: str):
        return await agent_reports.write_analysis_report.coroutine(
            title=_TITLE,
            markdown=markdown,
            evidence_ids=[evidence_id],
            runtime=runtime,
            tool_call_id=call_id,
        )

    results = await asyncio.gather(
        publish("# Variant A\n", "call-variant-a"),
        publish("# Variant B\n", "call-variant-b"),
        publish("# Variant C\n", "call-variant-c"),
    )

    codes = [json.loads(result.update["messages"][0].content)["code"] if isinstance(result, Command) else _body(result)["code"] for result in results]
    assert sorted(codes) == ["analysis_review_attempt_limit", "published", "report_conflict"]
    assert capability.output_path.read_text(encoding="utf-8") in {"# Variant A\n", "# Variant B\n"}
    assert len(repo.reports) == 1
    assert len(model.prompts) == 2


@pytest.mark.asyncio
async def test_report_writer_fails_closed_without_matching_gateway_capability(monkeypatch, tmp_path):
    capability = _writer_capability(monkeypatch, tmp_path, thread_id="other-thread")
    runtime = _writer_runtime(capability)
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Must not be written\n",
        evidence_ids=[_HASH_A],
        runtime=runtime,
        tool_call_id="call-mismatch",
    )

    assert isinstance(result, str)
    assert _body(result) == {"code": "analytics_unavailable"}
    assert repo.reports == []
    assert not capability.output_path.exists()


@pytest.mark.asyncio
async def test_report_writer_rejects_unregistered_evidence_before_any_write(monkeypatch, tmp_path):
    """模型自报的 SHA-256 不是当前 run 的查询证据。"""

    capability = _writer_capability(monkeypatch, tmp_path)
    runtime = _writer_runtime(capability)
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Must not be written\n",
        evidence_ids=[_HASH_A],
        runtime=runtime,
        tool_call_id="call-unregistered-evidence",
    )

    assert isinstance(result, str)
    assert _body(result) == {"code": "analysis_evidence_unavailable"}
    assert repo.reports == []
    assert not capability.output_path.exists()


@pytest.mark.asyncio
async def test_report_writer_rejects_evidence_owned_by_another_run_before_any_write(monkeypatch, tmp_path):
    collector, evidence_id = _successful_run_evidence(run_id="run-1")
    capability = _writer_capability(monkeypatch, tmp_path, run_id="run-2")
    runtime = _writer_runtime(capability, evidence_collector=collector, run_id="run-2")
    repo = _Repo()
    _bind(repo)

    result = await agent_reports.write_analysis_report.coroutine(
        title=_TITLE,
        markdown="# Must not be written\n",
        evidence_ids=[evidence_id],
        runtime=runtime,
        tool_call_id="call-cross-run-evidence",
    )

    assert isinstance(result, str)
    assert _body(result) == {"code": "analysis_evidence_unavailable"}
    assert repo.reports == []
    assert not capability.output_path.exists()


# --- fail closed ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_tool_is_unavailable_when_no_control_plane_is_bound():
    result, payload = await _invoke(_runtime(), title=_TITLE, artifact_path=_PATH, evidence_ids=[_HASH_A])

    assert payload == {"code": "analytics_unavailable"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_kwargs",
    [
        {"user_id": None},
        {"user_id": "default"},
        {"user_id": "  "},
        {"thread_id": None},
        {"run_id": None},
        {"thread_id": "  "},
        {"run_id": "x" * 65},
        {"thread_id": 42},
    ],
)
async def test_the_tool_fails_closed_without_a_trusted_identity(runtime_kwargs):
    repo = _Repo()
    _bind(repo)

    _result, payload = await _invoke(_runtime(**runtime_kwargs), title=_TITLE, artifact_path=_PATH, evidence_ids=[_HASH_A])

    assert payload == {"code": "analytics_unavailable"}
    assert repo.reports == []


@pytest.mark.asyncio
async def test_a_storage_failure_is_reported_as_a_stable_code_without_exception_text():
    repo = _Repo(error=RuntimeError(f"dsn=postgres://user:pw@host/db {_HASH_A}"))
    _bind(repo)

    result, payload = await _invoke(_runtime(), title=_TITLE, artifact_path=_PATH, evidence_ids=[_HASH_A])

    assert payload == {"code": "analytics_unavailable"}
    assert "postgres" not in result and "dsn" not in result.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("artifact_path", "/mnt/user-data/uploads/leak.md"),
        ("artifact_path", "/mnt/user-data/outputs/../uploads/leak.md"),
        ("artifact_path", "/mnt/user-data/outputs"),
        ("artifact_path", "/mnt/user-data/outputs/a\\b.md"),
        ("artifact_path", "business-analysis.md"),
        ("evidence_ids", []),
        ("evidence_ids", ["NOT-A-DIGEST"]),
        ("evidence_ids", ["A" * 64]),
        ("evidence_ids", [_HASH_A, _HASH_A]),
        ("evidence_ids", [f"{index:064x}" for index in range(64)]),
        ("title", ""),
        ("title", "  "),
        ("title", "两\n行"),
    ],
)
async def test_invalid_arguments_are_rejected_before_any_write(argument, value):
    repo = _Repo()
    _bind(repo)
    arguments = {"title": _TITLE, "artifact_path": _PATH, "evidence_ids": [_HASH_A]}
    arguments[argument] = value

    _result, payload = await _invoke(_runtime(), **arguments)

    assert payload == {"code": "invalid_request"}
    assert repo.reports == []


# --- 成功路径 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_publish_derives_identity_from_the_runtime():
    repo = _Repo()
    _bind(repo)

    _result, payload = await _invoke(
        _runtime(user_id="user-9", thread_id="thread-9", run_id="run-9"),
        title=_TITLE,
        artifact_path=_PATH,
        evidence_ids=[_HASH_A, _HASH_B],
    )

    assert payload["code"] == "published"
    assert len(repo.reports) == 1
    stored = repo.reports[0]
    assert (stored.principal_id, stored.thread_id, stored.run_id) == ("user-9", "thread-9", "run-9")
    assert stored.title == _TITLE
    assert stored.artifact_path == _PATH
    assert stored.evidence_ids == (_HASH_A, _HASH_B)
    assert stored.status is ReportStatus.PUBLISHED
    # id 与 created_at 由服务端派生，模型无法提供。
    assert stored.id == "report-1"
    assert stored.created_at == _NOW


@pytest.mark.asyncio
async def test_the_tool_result_does_not_echo_identity_or_internal_fields():
    _bind(_Repo())

    result, payload = await _invoke(
        _runtime(user_id="user-9", thread_id="thread-9", run_id="run-9"),
        title=_TITLE,
        artifact_path=_PATH,
        evidence_ids=[_HASH_A],
    )

    assert set(payload) == {"code", "report"}
    assert set(payload["report"]) == {"id", "title", "artifact_path", "status", "evidence_ids", "created_at"}
    for leaked in ("user-9", "thread-9", "run-9", "principal_id", "thread_id", "run_id"):
        assert leaked not in result


@pytest.mark.asyncio
async def test_an_idempotent_retry_reports_existing_without_claiming_a_new_row():
    _bind(_Repo(code=ReportPublishCode.EXISTING, stored=_report(id="report-original")))

    _result, payload = await _invoke(_runtime(), title=_TITLE, artifact_path=_PATH, evidence_ids=[_HASH_A])

    assert payload["code"] == "existing"
    assert payload["report"]["id"] == "report-original"


@pytest.mark.asyncio
async def test_a_conflict_returns_the_stored_entry_and_never_the_candidate():
    stored = _report(id="report-original", title="原始标题", evidence_ids=(_HASH_A,))
    _bind(_Repo(code=ReportPublishCode.REPORT_CONFLICT, stored=stored))

    result, payload = await _invoke(_runtime(), title="改过的标题", artifact_path=_PATH, evidence_ids=[_HASH_B])

    assert payload["code"] == "report_conflict"
    # 权威内容是既有行：模型必须看到"没有保存你的新内容"，而不是被回显的候选值。
    assert payload["report"]["title"] == "原始标题"
    assert payload["report"]["evidence_ids"] == [_HASH_A]
    assert "改过的标题" not in result


def test_the_agent_report_module_never_touches_the_filesystem_or_the_database():
    """只登记索引，不读 artifact：模块里不应出现文件系统、sandbox 或 SQL 依赖。"""

    source = inspect.getsource(agent_reports)

    for forbidden in ("pathlib", "open(", "sqlalchemy", "sqlglot", "asyncpg", "secret"):
        assert forbidden not in source, forbidden
