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

from app.analytics.agent import tools as agent_tools
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


def _runtime(user_id="user-1", *, context=None):
    """真实的 LangGraph `ToolRuntime`：`runtime` 参数由框架注入，测试里显式构造。"""

    from langgraph.prebuilt.tool_node import ToolRuntime

    resolved = {"user_id": user_id} if user_id is not None else {}
    if context:
        resolved.update(context)
    return ToolRuntime(state={}, context=resolved, config={}, stream_writer=lambda _: None, tool_call_id=None, store=None, tools=[])


def _datasource(datasource_id="ds-1", name="Warehouse"):
    return DatasourceDefinition(id=datasource_id, owner_id="owner-1", name=name, engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public", status=DatasourceStatus.ACTIVE)


def _metric(key="revenue"):
    return MetricDefinition(key=key, owner_id="user-1", name="Revenue", description="Total revenue", expression="sum(amount)", dimensions=("region",), version=2, status=MetricStatus.ACTIVE)


def _metadata():
    return QueryPlanDeliveryMetadata(datasource_id="ds-1", query_hash=_HASH, risk=QueryRisk.LOW, schema_version="s1", policy_version="p1")


def _estimate():
    return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)


def _result(rows=((1,),)):
    return QueryExecutionResult(columns=("id",), rows=rows, row_count=len(rows), byte_count=21 * len(rows), truncated=False)


class _Catalog:
    def __init__(self, items, *, error=None):
        self._items = items
        self._error = error

    async def list_accessible(self, *, principal_id):
        if self._error is not None:
            raise self._error
        return tuple(self._items)


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


def _services(*, datasources=(), metrics=(), plan=None, execute=None):
    return SimpleNamespace(
        datasources=_Catalog(list(datasources)),
        metrics=_Catalog(list(metrics)),
        plan_query=plan,
        execute_query=execute,
    )


def _plan_created():
    return QueryPlanDelivery(
        code=ExecutionDecisionCode.PLAN_CREATED.value,
        receipt=QueryPlanReceipt(plan_id=_TOKEN, expires_at=_NOW + timedelta(seconds=60), estimate=_estimate()),
        metadata=_metadata(),
    )


def _executed(result=None):
    from app.analytics.domain import QueryExecutionDecision

    return QueryExecutionDecision(code=ExecutionDecisionCode.EXECUTED, result=result or _result())


def _failure(code):
    from app.analytics.domain import QueryExecutionDecision

    return QueryExecutionDecision(code=code)


@pytest.fixture(autouse=True)
def _clean_binding():
    clear_analytics_services()
    yield
    clear_analytics_services()


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
    assert set(payload["metrics"][0]) == {"key", "name", "description", "dimensions", "version", "status"}
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
