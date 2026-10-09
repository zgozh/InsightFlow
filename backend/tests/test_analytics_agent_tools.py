"""Analytics Agent 工具测试（Phase 3 任务 3、4）。

两个工具的契约：

- `inspect_business_catalog`：**无身份参数**，只返回白名单目录字段；
- `query_business_data`：参数恰为 `datasource_id` + `sql`，一次调用内完成 plan→execute，
  plan token 只活在局部变量里，绝不进入返回值、日志、异常或异常文本。

principal、limits、schema/policy version 与 credential 全部服务端派生。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from analytics_test_support import AnalysisChatOpenAI, clear_analysis_model_calls, close_analysis_chat_models, create_analysis_chat_model

from app.analytics.agent import tools as agent_tools
from app.analytics.agent.evidence import AnalyticsQueryEvidence, canonical_json, create_analysis_run_evidence_collector
from app.analytics.agent.evidence_bridge import DurableAnalysisRunEvidenceCollector
from app.analytics.agent.runtime import bind_analytics_services, clear_analytics_services
from app.analytics.application.delivery import QueryPlanDelivery, QueryPlanDeliveryMetadata
from app.analytics.domain import (
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionDecisionCode,
    MetricDefinition,
    MetricStatus,
    QueryCostEstimate,
    QueryExecutionResult,
    QueryPlanReceipt,
    QueryRisk,
)

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_SQL = "SELECT id FROM orders LIMIT 10"
_TOKEN = "raw-plan-token-value"
_HASH = "b" * 64


def _runtime(user_id="user-1", *, context=None, tool_call_id=None):
    """真实的 LangGraph `ToolRuntime`：`runtime` 参数由框架注入，测试里显式构造。"""

    from langgraph.prebuilt.tool_node import ToolRuntime

    resolved = {"user_id": user_id} if user_id is not None else {}
    if context:
        resolved.update(context)
    from deerflow.constants import ANALYSIS_ROLES_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    if resolved.get(THREAD_ANALYSIS_MODE_METADATA_KEY) is True and ANALYSIS_ROLES_CONTEXT_KEY not in resolved:
        from app.analytics.agent.roles import create_analysis_roles_capability

        roles = create_analysis_roles_capability(principal_id=user_id, thread_id="thread-1", run_id="run-1")
        model = create_analysis_chat_model()
        assert roles.bind_lead_model(principal_id=user_id, thread_id="thread-1", run_id="run-1", model=model)
        resolved[ANALYSIS_ROLES_CONTEXT_KEY] = roles
    return ToolRuntime(state={}, context=resolved, config={}, stream_writer=lambda _: None, tool_call_id=tool_call_id, store=None, tools=[])


def _datasource(datasource_id="ds-1", name="Warehouse"):
    return DatasourceDefinition(id=datasource_id, owner_id="owner-1", name=name, engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public", status=DatasourceStatus.ACTIVE)


def _metric(key="revenue"):
    return MetricDefinition(key=key, owner_id="user-1", name="Revenue", description="Total revenue", expression="sum(amount)", dimensions=("region",), version=2, status=MetricStatus.ACTIVE)


def _metadata():
    return QueryPlanDeliveryMetadata(datasource_id="ds-1", query_hash=_HASH, risk=QueryRisk.LOW, schema_version="s1", policy_version="p1")


def _estimate():
    return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)


def _result(rows=((1,),), *, truncated=False):
    byte_count = len(canonical_json({"columns": ["id"], "rows": [list(row) for row in rows]}).encode("utf-8"))
    return QueryExecutionResult(columns=("id",), rows=rows, row_count=len(rows), byte_count=byte_count, truncated=truncated)


class _Catalog:
    def __init__(self, items, *, error=None):
        self._items = items
        self._error = error

    async def list_accessible(self, *, principal_id):
        if self._error is not None:
            raise self._error
        return tuple(self._items)

    async def get_accessible(self, *, principal_id, datasource_id):
        if self._error is not None:
            raise self._error
        return next((item for item in self._items if getattr(item, "id", None) == datasource_id), None)


class _PlanQuery:
    def __init__(self, delivery, *, error=None):
        self._delivery = delivery
        self._error = error
        self.calls: list[dict] = []

    async def execute(self, *, principal_id, datasource_id, raw_sql):
        self.calls.append({"principal_id": principal_id, "datasource_id": datasource_id, "raw_sql": raw_sql})
        if self._error is not None:
            raise self._error
        return self._delivery


class _ExecuteQuery:
    def __init__(self, delivery, *, error=None):
        self._delivery = delivery
        self._error = error
        self.calls: list[dict] = []

    async def execute(self, *, principal_id, plan_id):
        self.calls.append({"principal_id": principal_id, "plan_id": plan_id})
        if self._error is not None:
            raise self._error
        return self._delivery


def _services(*, datasources=None, metrics=None, plan=None, execute=None):
    return SimpleNamespace(
        datasources=_Catalog(list(datasources if datasources is not None else [_datasource()])),
        metrics=_Catalog(list(metrics if metrics is not None else [_metric()])),
        plan_query=plan,
        execute_query=execute,
    )


def _plan_created():
    return QueryPlanDelivery(
        code=ExecutionDecisionCode.PLAN_CREATED.value,
        receipt=QueryPlanReceipt(plan_id=_TOKEN, expires_at=_NOW + timedelta(seconds=60), estimate=_estimate()),
        metadata=_metadata(),
    )


def _executed(result=None, *, code=ExecutionDecisionCode.EXECUTED):
    from app.analytics.domain import QueryExecutionDecision

    return QueryExecutionDecision(code=code, result=result or _result())


def _failure(code):
    from app.analytics.domain import QueryExecutionDecision

    return QueryExecutionDecision(code=code)


class _EvidenceRepository:
    def __init__(self):
        self.records = {}
        self.error = None

    async def put(self, record):
        if self.error is not None:
            raise self.error
        key = (record.principal_id, record.thread_id, record.run_id, record.evidence_id)
        existing = self.records.get(key)
        if existing is not None and existing != record:
            raise ValueError("evidence_conflict")
        self.records[key] = record

    async def get_many(self, principal_id, thread_id, run_id, evidence_ids):
        if self.error is not None:
            raise self.error
        return tuple(self.records[(principal_id, thread_id, run_id, evidence_id)] for evidence_id in evidence_ids)


class _ArtifactCapability:
    def __init__(self, principal_id="user-1", thread_id="thread-1", run_id="run-1"):
        self.scope = (principal_id, thread_id, run_id)
        self.records = {}
        self.fail_write = False
        self.fail_verify = False

    def matches(self, principal_id, thread_id, run_id):
        return self.scope == (principal_id, thread_id, run_id)

    def virtual_path_for(self, evidence_id):
        return f"/mnt/user-data/outputs/query-result-{self.scope[2]}-{evidence_id}.json"

    async def write(self, record):
        if self.fail_write:
            return False
        self.records[record.evidence_id] = record
        return True

    async def verify(self, record):
        return not self.fail_verify and self.records.get(record.evidence_id) == record


def _durable_collector(repository=None, artifact_capability=None, *, run_id="run-1"):
    return DurableAnalysisRunEvidenceCollector(
        principal_id="user-1",
        thread_id="thread-1",
        run_id=run_id,
        repository=repository or _EvidenceRepository(),
        artifact_capability=artifact_capability or _ArtifactCapability(run_id=run_id),
    )


@pytest.fixture(autouse=True)
def _clean_binding():
    clear_analytics_services()
    clear_analysis_model_calls()
    yield
    clear_analytics_services()


@pytest_asyncio.fixture(autouse=True)
async def _close_analysis_models():
    yield
    await close_analysis_chat_models()


# --- schema -----------------------------------------------------------------


def test_the_query_tool_takes_exactly_a_datasource_id_and_sql():
    """模型可见的入参就是这两个：没有 principal/owner/limits/token/credential 的位置。"""

    schema = agent_tools.query_business_data.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"datasource_id", "sql"}
    assert set(schema.get("required", [])) == {"datasource_id", "sql"}


def test_the_catalog_tool_takes_no_identity_arguments():
    schema = agent_tools.inspect_business_catalog.tool_call_schema.model_json_schema()

    assert schema.get("properties", {}) == {}


@pytest.mark.asyncio
async def test_a_forged_principal_argument_cannot_change_the_principal_used():
    """客户端字段没有对应的入参位；即使塞进来也被丢弃，principal 仍来自可信 runtime context。"""

    plan = _PlanQuery(_plan_created())
    bind_analytics_services(_services(plan=plan, execute=_ExecuteQuery(_executed())))

    await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime("user-1"), "principal_id": "attacker"})

    assert plan.calls[0]["principal_id"] == "user-1"
    assert "principal_id" not in agent_tools.query_business_data.tool_call_schema.model_json_schema()["properties"]


# --- 可用性 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_tools_report_analytics_unavailable_when_unbound():
    assert json.loads(await agent_tools.inspect_business_catalog.ainvoke({"runtime": _runtime()})) == {"code": "analytics_unavailable"}
    assert json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()})) == {"code": "analytics_unavailable"}


@pytest.mark.asyncio
async def test_both_tools_report_analytics_unavailable_without_a_trusted_principal():
    bind_analytics_services(_services(datasources=[_datasource()], plan=_PlanQuery(_plan_created())))

    assert json.loads(await agent_tools.inspect_business_catalog.ainvoke({"runtime": _runtime(user_id=None)})) == {"code": "analytics_unavailable"}
    assert json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime(user_id="default")})) == {"code": "analytics_unavailable"}


# --- catalog ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_catalog_tool_returns_only_whitelisted_fields_in_a_stable_order():
    bind_analytics_services(_services(datasources=[_datasource("ds-b", "beta"), _datasource("ds-a", "alpha")], metrics=[_metric()]))

    payload = json.loads(await agent_tools.inspect_business_catalog.ainvoke({"runtime": _runtime()}))

    assert payload["code"] == "ok"
    assert set(payload["datasources"][0]) == {"id", "name", "engine", "default_schema", "status"}
    assert set(payload["metrics"][0]) == {"key", "name", "description", "expression", "dimensions", "version", "status"}
    rendered = json.dumps(payload)
    for banned in ("secret_ref", "owner_id", "env://", "policy_version", "annalytics"):
        assert banned not in rendered
    assert [item["id"] for item in payload["datasources"]] == ["ds-b", "ds-a"], "catalog order follows the repository"


@pytest.mark.asyncio
async def test_a_catalog_failure_is_a_stable_code_without_exception_text(caplog):
    bind_analytics_services(_services(datasources=[_datasource()]))
    services = agent_tools.get_bound_analytics_services()
    services.datasources = _Catalog([], error=RuntimeError("dsn=postgres://user:pw@host/db"))

    with caplog.at_level(logging.DEBUG):
        payload = await agent_tools.inspect_business_catalog.ainvoke({"runtime": _runtime()})

    assert json.loads(payload) == {"code": "analytics_unavailable"}
    assert "postgres://" not in caplog.text


# --- query ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_query_plans_once_executes_once_and_returns_evidence():
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))

    payload = json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()}))

    assert plan.calls == [{"principal_id": "user-1", "datasource_id": "ds-1", "raw_sql": _SQL}]
    assert execute.calls == [{"principal_id": "user-1", "plan_id": _TOKEN}]
    assert payload["code"] == "executed"
    assert payload["rows"] == [[1]] and payload["row_count"] == 1
    assert payload["evidence"]["datasource_id"] == "ds-1"
    assert payload["evidence"]["query_hash"] == _HASH
    assert payload["evidence"]["result_digest"] == agent_tools.compute_result_digest(("id",), ((1,),))


@pytest.mark.asyncio
async def test_a_successful_query_registers_the_same_bounded_snapshot_in_its_run_collector():
    from langgraph.types import Command

    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))
    collector = _durable_collector()
    runtime = _runtime(
        context={
            "thread_id": "thread-1",
            "run_id": "run-1",
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
        },
        tool_call_id="call-query-success",
    )

    command = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)
    assert isinstance(command, Command)
    payload = json.loads(command.update["messages"][0].content)
    evidence_id = payload["evidence"]["evidence_id"]
    snapshots = await collector.resolve_successful_queries_durable(
        principal_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        evidence_ids=(evidence_id,),
    )

    assert payload["code"] == "executed"
    assert command.update["artifacts"] == [f"/mnt/user-data/outputs/query-result-run-1-{evidence_id}.json"]
    assert command.update["messages"][0].tool_call_id == "call-query-success"
    assert snapshots is not None and snapshots[0].rows == ((1,),)


@pytest.mark.asyncio
async def test_analysis_query_calls_the_independent_sql_role_before_one_plan_and_execution():
    from langgraph.types import Command

    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    services = _services(plan=plan, execute=execute)
    bind_analytics_services(services)
    collector = _durable_collector()
    runtime = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-analysis-role-query",
    )

    result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)

    assert isinstance(result, Command)
    assert json.loads(result.update["messages"][0].content)["code"] == "executed"
    assert len(plan.calls) == len(execute.calls) == 1
    assert plan.calls[0]["raw_sql"] == "SELECT 1"
    assert execute.calls[0]["plan_id"] == _TOKEN
    role_calls = [call for call in AnalysisChatOpenAI.calls if call["role"] == "sql_analyst"]
    assert len(role_calls) == 1
    call = role_calls[0]
    request = json.loads(call["messages"][1].content)
    assert request["candidate_sql"] == _SQL
    assert request["metrics"][0]["expression"] == "sum(amount)"
    assert call["model"].max_retries == 0
    assert not (set(call["kwargs"]) & {"tools", "functions", "tool_choice", "function_call"})


@pytest.mark.asyncio
async def test_analysis_query_emits_persisted_stages_in_phase_order_and_finishes_workflow(monkeypatch):
    from langgraph.types import Command

    from app.analytics.agent.roles import create_analysis_roles_capability
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    class Store:
        def __init__(self):
            self.events = []

        async def put(self, **event):
            self.events.append(event.copy())
            return {**event, "seq": 100 + len(self.events)}

    store = Store()
    live = []
    monkeypatch.setattr("app.analytics.agent.stages.get_stream_writer", lambda: live.append)
    roles = create_analysis_roles_capability(principal_id="user-1", thread_id="thread-1", run_id="run-1", event_store=store)
    model = create_analysis_chat_model()
    assert roles.bind_lead_model(principal_id="user-1", thread_id="thread-1", run_id="run-1", model=model)
    runtime = _runtime(
        context={"thread_id": "thread-1", "run_id": "run-1"},
        tool_call_id="call-analysis-stage-query",
    )
    runtime.context[THREAD_ANALYSIS_MODE_METADATA_KEY] = True
    runtime.context[ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY] = _durable_collector()
    runtime.context[ANALYSIS_ROLES_CONTEXT_KEY] = roles
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))

    try:
        result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)
        await roles.finish(status="success")
    finally:
        roles.close()

    assert isinstance(result, Command)
    assert [(event["metadata"]["stage"], event["metadata"]["status"]) for event in store.events] == [
        ("workflow", "running"),
        ("catalog", "running"),
        ("catalog", "succeeded"),
        ("sql", "running"),
        ("sql", "succeeded"),
        ("authorization", "running"),
        ("authorization", "succeeded"),
        ("execution", "running"),
        ("execution", "succeeded"),
        ("workflow", "succeeded"),
    ]
    assert [event["metadata"] for event in store.events] == live
    assert all(event["event_type"] == "analysis.stage" and event["category"] == "analysis" and event["content"] == "" for event in store.events)


@pytest.mark.asyncio
async def test_analysis_role_scope_and_catalog_visibility_fail_before_model_or_plan():
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(datasources=[], plan=plan, execute=execute))
    collector = _durable_collector()
    runtime = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-unavailable-source",
    )

    denied = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)
    assert json.loads(denied) == {"code": "analysis_role_unavailable"}
    assert plan.calls == [] and execute.calls == []
    assert AnalysisChatOpenAI.calls == []

    wrong_scope = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
            ANALYSIS_ROLES_CONTEXT_KEY: object(),
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-forged-role",
    )
    denied = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=wrong_scope)
    assert json.loads(denied) == {"code": "analysis_role_unavailable"}
    assert plan.calls == [] and AnalysisChatOpenAI.calls == []


@pytest.mark.asyncio
async def test_analysis_query_budget_rejects_before_role_or_plan():
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    plan = _PlanQuery(_plan_created())
    bind_analytics_services(_services(plan=plan, execute=_ExecuteQuery(_executed())))
    runtime = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: _durable_collector(),
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-over-budget",
    )
    roles = runtime.context[ANALYSIS_ROLES_CONTEXT_KEY]
    for _ in range(4):
        async with roles.serialize_query("user-1", "thread-1", "run-1"):
            pass

    result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)

    assert json.loads(result) == {"code": "analysis_role_attempt_limit"}
    assert plan.calls == []
    assert AnalysisChatOpenAI.calls == []


@pytest.mark.asyncio
async def test_parallel_analysis_queries_hold_the_run_lock_through_planning():
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    class BlockingDeniedPlan:
        def __init__(self):
            self.calls = 0
            self.active = 0
            self.maximum_active = 0
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def execute(self, *, principal_id, datasource_id, raw_sql):
            self.calls += 1
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            if self.calls == 1:
                self.entered.set()
                await self.release.wait()
            self.active -= 1
            return QueryPlanDelivery(code=ExecutionDecisionCode.COST_LIMIT_EXCEEDED.value)

    plan = BlockingDeniedPlan()
    bind_analytics_services(_services(plan=plan, execute=_ExecuteQuery(_executed())))
    shared = {
        THREAD_ANALYSIS_MODE_METADATA_KEY: True,
        ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: _durable_collector(),
        "thread_id": "thread-1",
        "run_id": "run-1",
    }
    first_runtime = _runtime(context=shared, tool_call_id="call-parallel-a")
    roles = first_runtime.context[ANALYSIS_ROLES_CONTEXT_KEY]
    second_runtime = _runtime(context={**shared, ANALYSIS_ROLES_CONTEXT_KEY: roles}, tool_call_id="call-parallel-b")
    first = asyncio.create_task(agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql="SELECT id FROM orders LIMIT 10", runtime=first_runtime))
    await plan.entered.wait()
    second = asyncio.create_task(agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql="SELECT id FROM orders LIMIT 20", runtime=second_runtime))
    await asyncio.sleep(0)
    assert plan.calls == 1
    assert len([call for call in AnalysisChatOpenAI.calls if call["role"] == "sql_analyst"]) == 1

    plan.release.set()
    await asyncio.gather(first, second)
    assert plan.calls == 2
    assert plan.maximum_active == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision_code", "result", "expected_rows"),
    [
        (ExecutionDecisionCode.EXECUTED, _result(rows=()), []),
        (ExecutionDecisionCode.RESULT_LIMIT_REACHED, _result(rows=((1,),), truncated=True), [[1]]),
    ],
)
async def test_analysis_query_persists_zero_row_and_truncated_results_before_artifact_command(decision_code, result, expected_rows):
    from langgraph.types import Command

    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    repository = _EvidenceRepository()
    artifacts = _ArtifactCapability()
    collector = _durable_collector(repository, artifacts)
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed(result, code=decision_code))
    bind_analytics_services(_services(plan=plan, execute=execute))
    runtime = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-query-persisted",
    )

    command = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)

    assert isinstance(command, Command)
    payload = json.loads(command.update["messages"][0].content)
    evidence_id = payload["evidence"]["evidence_id"]
    assert payload["rows"] == expected_rows
    assert len(repository.records) == 1
    assert evidence_id in artifacts.records
    assert command.update["artifacts"] == [artifacts.virtual_path_for(evidence_id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["repository", "file", "conflict"])
async def test_analysis_query_storage_failure_never_returns_a_success_command(failure):
    from langgraph.types import Command

    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    repository = _EvidenceRepository()
    artifacts = _ArtifactCapability()
    if failure in {"repository", "conflict"}:
        if failure == "conflict":
            from app.analytics.application.evidence_ports import AnalysisEvidenceStoreError

            repository.error = AnalysisEvidenceStoreError("evidence_conflict")
        else:
            repository.error = RuntimeError("dsn=synthetic-secret")
    else:
        artifacts.fail_write = True
    collector = _durable_collector(repository, artifacts)
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))
    runtime = _runtime(
        context={
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
            "thread_id": "thread-1",
            "run_id": "run-1",
        },
        tool_call_id="call-query-storage-failure",
    )

    result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)

    assert isinstance(result, str) and json.loads(result) == {"code": "analysis_evidence_unavailable"}
    assert not isinstance(result, Command)
    assert len(plan.calls) == 1 and len(execute.calls) == 1
    assert "synthetic-secret" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("collector_kind", ["missing", "forged", "memory", "wrong_scope", "missing_call_id"])
async def test_analysis_query_requires_durable_gateway_collector_and_tool_call_id_before_planning(collector_kind):
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))
    collector = None
    context = {THREAD_ANALYSIS_MODE_METADATA_KEY: True, "thread_id": "thread-1", "run_id": "run-1"}
    call_id = "call-query-admission"
    if collector_kind == "forged":
        collector = {"principal_id": "user-1", "thread_id": "thread-1", "run_id": "run-1"}
    elif collector_kind == "memory":
        collector = create_analysis_run_evidence_collector(principal_id="user-1", thread_id="thread-1", run_id="run-1")
    elif collector_kind == "wrong_scope":
        collector = _durable_collector(run_id="other-run")
    elif collector_kind == "missing_call_id":
        collector = _durable_collector()
        call_id = None
    elif collector_kind != "missing":
        raise AssertionError(collector_kind)
    if collector is not None:
        context[ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY] = collector
    runtime = _runtime(context=context, tool_call_id=call_id)

    result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)

    assert isinstance(result, str) and json.loads(result) == {"code": "analysis_evidence_unavailable"}
    assert plan.calls == [] and execute.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["plan", "execute"])
async def test_a_failed_plan_or_execution_never_registers_evidence(failed_stage):
    from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY
    from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY

    if failed_stage == "plan":
        plan = _PlanQuery(QueryPlanDelivery(code=ExecutionDecisionCode.COST_LIMIT_EXCEEDED.value))
        execute = _ExecuteQuery(_executed())
    else:
        plan = _PlanQuery(_plan_created())
        execute = _ExecuteQuery(_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE))
    bind_analytics_services(_services(plan=plan, execute=execute))
    collector = _durable_collector()
    runtime = _runtime(
        context={
            "thread_id": "thread-1",
            "run_id": "run-1",
            THREAD_ANALYSIS_MODE_METADATA_KEY: True,
            ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY: collector,
        },
        tool_call_id="call-query-failed",
    )

    result = await agent_tools.query_business_data.coroutine(datasource_id="ds-1", sql=_SQL, runtime=runtime)
    evidence_id = AnalyticsQueryEvidence.build(
        datasource_id="ds-1",
        query_hash=_HASH,
        risk=QueryRisk.LOW,
        schema_version="s1",
        policy_version="p1",
        estimate=_estimate(),
        result=_result(),
    ).evidence_id

    assert isinstance(result, str)
    assert json.loads(result)["code"] != "executed"
    assert (
        await collector.resolve_successful_queries_durable(
            principal_id="user-1",
            thread_id="thread-1",
            run_id="run-1",
            evidence_ids=(evidence_id,),
        )
        is None
    )


@pytest.mark.asyncio
async def test_a_denied_plan_never_executes_and_returns_only_the_stable_code():
    plan = _PlanQuery(QueryPlanDelivery(code=ExecutionDecisionCode.COST_LIMIT_EXCEEDED.value))
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))

    payload = json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()}))

    assert payload == {"code": "cost_limit_exceeded", "columns": [], "rows": [], "row_count": 0, "truncated": False}
    assert execute.calls == []


@pytest.mark.asyncio
async def test_a_failed_execution_is_not_replanned_and_returns_only_the_stable_code():
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_failure(ExecutionDecisionCode.DATABASE_UNAVAILABLE))
    bind_analytics_services(_services(plan=plan, execute=execute))

    payload = json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()}))

    assert payload["code"] == "database_unavailable"
    assert len(plan.calls) == 1, "execute failure must never trigger a second plan"
    assert len(execute.calls) == 1


@pytest.mark.asyncio
async def test_the_plan_token_never_reaches_the_result_logs_or_errors(caplog):
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(_executed())
    bind_analytics_services(_services(plan=plan, execute=execute))

    with caplog.at_level(logging.DEBUG):
        payload = await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()})

    assert _TOKEN not in payload
    assert _TOKEN not in caplog.text
    assert _TOKEN not in repr(payload)


@pytest.mark.asyncio
async def test_an_execute_exception_is_mapped_without_leaking_text_or_the_token(caplog):
    plan = _PlanQuery(_plan_created())
    execute = _ExecuteQuery(None, error=RuntimeError(f"driver said {_TOKEN} dsn=postgres://user:pw@host/db"))
    bind_analytics_services(_services(plan=plan, execute=execute))

    with caplog.at_level(logging.DEBUG):
        payload = await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()})

    assert json.loads(payload) == {"code": "analytics_unavailable"}
    assert _TOKEN not in payload and _TOKEN not in caplog.text
    assert "postgres://" not in payload and "postgres://" not in caplog.text


@pytest.mark.asyncio
async def test_blank_or_oversized_sql_is_rejected_before_planning():
    plan = _PlanQuery(_plan_created())
    bind_analytics_services(_services(plan=plan, execute=_ExecuteQuery(_executed())))

    blank = json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": "   ", "runtime": _runtime()}))
    oversized = json.loads(await agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": "SELECT 1 " + "x" * agent_tools.MAX_SQL_CHARACTERS, "runtime": _runtime()}))

    assert blank == {"code": "analytics_unavailable"} or blank["code"] != "executed"
    assert oversized["code"] != "executed"
    assert plan.calls == []


@pytest.mark.asyncio
async def test_cancellation_propagates_and_never_starts_a_second_query():
    class _Blocking:
        def __init__(self):
            self.calls = 0
            self.entered = asyncio.Event()

        async def execute(self, *, principal_id, datasource_id, raw_sql):
            self.calls += 1
            self.entered.set()
            await asyncio.sleep(30)

    plan = _Blocking()
    bind_analytics_services(_services(plan=plan, execute=_ExecuteQuery(_executed())))

    task = asyncio.create_task(agent_tools.query_business_data.ainvoke({"datasource_id": "ds-1", "sql": _SQL, "runtime": _runtime()}))
    # 用事件同步而不是 sleep：必须确定性地等到工具真正进入查询，再取消。
    await asyncio.wait_for(plan.entered.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert plan.calls == 1
