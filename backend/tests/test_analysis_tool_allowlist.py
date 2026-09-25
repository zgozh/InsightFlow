"""受控分析工具边界：合成运行只绑定固定 Analytics 来源。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, StructuredTool, tool
from pydantic import Field

from deerflow.agents.lead_agent import agent as lead_agent_module
from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.config.tool_config import ToolConfig
from deerflow.config.tool_search_config import ToolSearchConfig
from deerflow.tools import tools as tools_module

_ALLOWED_SOURCES = {
    "inspect_business_catalog": "app.analytics.agent.tools:inspect_business_catalog",
    "query_business_data": "app.analytics.agent.tools:query_business_data",
    "write_analysis_report": "app.analytics.agent.reports:write_analysis_report",
}


class _SyntheticModel(BaseChatModel):
    """记录模型绑定的 schema，并在首轮发起一个合成工具调用。"""

    bound_tool_names: list[list[str]] = Field(default_factory=list)
    tool_call_name: str = "inspect_business_catalog"
    tool_call_names: list[str] = Field(default_factory=list)
    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "analysis-tool-allowlist-test"

    def bind_tools(self, tools: Any, **kwargs: Any):
        self.bound_tool_names.append([item.name for item in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            names = self.tool_call_names or [self.tool_call_name]
            message = AIMessage(
                content="",
                tool_calls=[{"id": f"synthetic-call-{index}", "name": name, "args": {}} for index, name in enumerate(names)],
            )
        else:
            message = AIMessage(content="synthetic complete")
        return ChatResult(generations=[ChatGeneration(message=message)])


def _app_config(tools: list[ToolConfig]) -> AppConfig:
    return AppConfig(
        models=[
            ModelConfig(
                name="synthetic-model",
                display_name="synthetic-model",
                use="langchain_openai:ChatOpenAI",
                model="synthetic-model",
                supports_thinking=False,
                supports_vision=False,
            )
        ],
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
        tools=tools,
        tool_search=ToolSearchConfig(enabled=True),
    )


def _analysis_tool_configs() -> list[ToolConfig]:
    return [ToolConfig(name=name, group="analytics", use=source) for name, source in _ALLOWED_SOURCES.items() if name in {"inspect_business_catalog", "query_business_data"}]


@tool("write_analysis_report")
def _synthetic_report_writer(title: str, markdown: str, evidence_ids: list[str]) -> str:
    """返回合成报告 writer 结果。"""
    return "synthetic report result"


def _poison_tool(name: str, calls: list[str]) -> BaseTool:
    def poison() -> str:
        calls.append(name)
        return "must never execute"

    return StructuredTool.from_function(poison, name=name, description="Record an unexpected tool dispatch.")


def _wire_lead_assembly(monkeypatch, *, model: _SyntheticModel) -> None:
    monkeypatch.setattr(lead_agent_module, "load_agent_config", lambda name, *, user_id=None: None)
    monkeypatch.setattr(lead_agent_module, "_load_enabled_available_skills", lambda *args, **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "build_middlewares", lambda *args, **kwargs: pytest.fail("analysis must not add middleware tools"))
    monkeypatch.setattr(lead_agent_module, "apply_tool_authorization", lambda candidates, **kwargs: (candidates, None))
    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", lambda **kwargs: "synthetic analysis prompt")
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: model)
    monkeypatch.setattr(lead_agent_module, "build_tracing_callbacks", lambda: [])


@pytest.mark.asyncio
async def test_analysis_assembly_uses_server_context_and_one_set_for_model_and_dispatch(monkeypatch):
    calls: list[str] = []

    @tool("inspect_business_catalog")
    def inspect_catalog() -> str:
        """Return a synthetic catalog for this test."""
        calls.append("inspect_business_catalog")
        return "synthetic catalog"

    @tool("query_business_data")
    def query_data(datasource_id: str, sql: str) -> str:
        """Return a synthetic query result for this test."""
        calls.append("query_business_data")
        return "synthetic query result"

    resolve_calls: list[str] = []
    denied_names = [
        "tool_search",
        "bash",
        "task",
        "list_background_tasks",
        "cancel_background_task",
        "publish_analysis_report",
        "dynamic_plugin_tool",
    ]
    poison_tools = {name: _poison_tool(name, calls) for name in denied_names}
    poison_sources = {name: f"tests.synthetic:{name}" for name in denied_names}
    resolved_tools = {
        _ALLOWED_SOURCES["inspect_business_catalog"]: inspect_catalog,
        _ALLOWED_SOURCES["query_business_data"]: query_data,
        _ALLOWED_SOURCES["write_analysis_report"]: _synthetic_report_writer,
        **{poison_sources[name]: poison_tools[name] for name in denied_names},
    }

    def resolve_source(source: str, target: type[BaseTool]):
        assert target is BaseTool
        resolve_calls.append(source)
        return resolved_tools[source]

    monkeypatch.setattr(tools_module, "resolve_variable", resolve_source)
    model = _SyntheticModel()
    _wire_lead_assembly(monkeypatch, model=model)
    app_config = _app_config(
        [
            *_analysis_tool_configs(),
            *[ToolConfig(name=name, group="dynamic", use=poison_sources[name]) for name in denied_names],
            ToolConfig(name="inspect_business_catalog", group="analytics", use=poison_sources["tool_search"]),
        ]
    )

    assembly = lead_agent_module._assemble_lead_agent(
        {
            "context": {"analysis_mode": True},
            "configurable": {"analysis_mode": False, "agent_name": "synthetic-custom", "subagent_enabled": True},
        },
        app_config=app_config,
    )
    result = await assembly.graph.ainvoke({"messages": [HumanMessage(content="inspect synthetic data")]})

    expected = {"inspect_business_catalog", "query_business_data", "write_analysis_report"}
    assert resolve_calls == list(_ALLOWED_SOURCES.values())
    assert model.bound_tool_names and all(set(names) == expected for names in model.bound_tool_names)
    assert calls == ["inspect_business_catalog"]
    assert any(isinstance(message, ToolMessage) and message.name == "inspect_business_catalog" for message in result["messages"])

    forged_model = _SyntheticModel(tool_call_names=denied_names)
    _wire_lead_assembly(monkeypatch, model=forged_model)
    forged_assembly = lead_agent_module._assemble_lead_agent(
        {
            "context": {"analysis_mode": True},
            "configurable": {"analysis_mode": False, "subagent_enabled": True},
        },
        app_config=app_config,
    )
    try:
        await forged_assembly.graph.ainvoke({"messages": [HumanMessage(content="resume synthetic history")]})
    except Exception:
        pass
    assert forged_model.bound_tool_names and all(set(names) == expected for names in forged_model.bound_tool_names)
    assert calls == ["inspect_business_catalog"]


def test_analysis_tool_loader_ignores_later_catalog_and_mcp_updates(monkeypatch):
    from deerflow.config.extensions_config import ExtensionsConfig
    from deerflow.mcp import cache as mcp_cache

    @tool("inspect_business_catalog")
    def inspect_catalog() -> str:
        """Return a synthetic catalog for this test."""
        return "synthetic catalog"

    @tool("query_business_data")
    def query_data(datasource_id: str, sql: str) -> str:
        """Return a synthetic query result for this test."""
        return "synthetic query result"

    resolve_calls: list[str] = []

    def resolve_source(source: str, target: type[BaseTool]):
        resolve_calls.append(source)
        return {
            _ALLOWED_SOURCES["inspect_business_catalog"]: inspect_catalog,
            _ALLOWED_SOURCES["query_business_data"]: query_data,
            _ALLOWED_SOURCES["write_analysis_report"]: _synthetic_report_writer,
        }[source]

    monkeypatch.setattr(tools_module, "resolve_variable", resolve_source)
    monkeypatch.setattr(ExtensionsConfig, "from_file", classmethod(lambda cls: pytest.fail("analysis must not read MCP config")))
    monkeypatch.setattr(mcp_cache, "get_cached_mcp_tools", lambda: pytest.fail("analysis must not discover cached MCP tools"))
    app_config = _app_config(_analysis_tool_configs())

    first = tools_module.get_available_tools(analysis_mode=True, include_mcp=True, app_config=app_config)
    app_config.tools.append(ToolConfig(name="new_dynamic_tool", group="analytics", use="untrusted.plugin:tool"))
    second = tools_module.get_available_tools(analysis_mode=True, include_mcp=True, app_config=app_config)

    expected = ["inspect_business_catalog", "query_business_data", "write_analysis_report"]
    assert [item.name for item in first] == expected
    assert [item.name for item in second] == expected
    assert resolve_calls == [*_ALLOWED_SOURCES.values(), *_ALLOWED_SOURCES.values()]


def test_analysis_assembly_adds_dedicated_chinese_work_instructions(monkeypatch):
    from langchain_core.tools import tool

    @tool("inspect_business_catalog")
    def inspect_catalog() -> str:
        """Synthetic catalog."""
        return "{}"

    @tool("query_business_data")
    def query_data(datasource_id: str, sql: str) -> str:
        """Synthetic query."""
        return "{}"

    resolved = {
        _ALLOWED_SOURCES["inspect_business_catalog"]: inspect_catalog,
        _ALLOWED_SOURCES["query_business_data"]: query_data,
        _ALLOWED_SOURCES["write_analysis_report"]: _synthetic_report_writer,
    }
    monkeypatch.setattr(tools_module, "resolve_variable", lambda source, _target: resolved[source])
    model = _SyntheticModel()
    _wire_lead_assembly(monkeypatch, model=model)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        lead_agent_module,
        "create_agent",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    lead_agent_module._assemble_lead_agent(
        {"context": {"analysis_mode": True}},
        app_config=_app_config(_analysis_tool_configs()),
    )

    prompt = captured["system_prompt"]
    for required in (
        "受控经营分析工作方式",
        "inspect_business_catalog",
        "query_business_data",
        "evidence ID",
        "write_analysis_report",
        "只有工具确认成功后才称报告已保存",
    ):
        assert required in prompt


def test_analysis_tool_loader_fails_closed_when_approved_source_is_missing(monkeypatch):
    monkeypatch.setattr(
        tools_module,
        "resolve_variable",
        lambda source, target: pytest.fail("incomplete allowlist must fail before loading tools"),
    )
    app_config = _app_config(_analysis_tool_configs()[:1])

    with pytest.raises(RuntimeError, match="analysis_tool_allowlist_incomplete"):
        tools_module.get_available_tools(analysis_mode=True, app_config=app_config)


def test_analysis_tool_loader_fails_closed_when_source_returns_a_different_tool(monkeypatch):
    @tool("unexpected_analytics_tool")
    def unexpected_tool() -> str:
        """Return a synthetic unexpected tool result."""
        return "not allowed"

    monkeypatch.setattr(tools_module, "resolve_variable", lambda source, target: unexpected_tool)

    with pytest.raises(RuntimeError, match="analysis_tool_allowlist_source_mismatch"):
        tools_module.get_available_tools(analysis_mode=True, app_config=_app_config(_analysis_tool_configs()))


def test_ordinary_tool_loader_keeps_synthetic_mcp_tools(monkeypatch):
    from deerflow.config.extensions_config import ExtensionsConfig
    from deerflow.mcp import cache as mcp_cache

    @tool("synthetic_operator_mcp")
    def operator_mcp() -> str:
        """Return a synthetic ordinary-chat MCP result."""
        return "synthetic MCP result"

    monkeypatch.setattr(
        ExtensionsConfig,
        "from_file",
        classmethod(lambda cls: SimpleNamespace(get_enabled_mcp_servers=lambda: {"synthetic": object()})),
    )
    monkeypatch.setattr(mcp_cache, "get_cached_mcp_tools", lambda: [operator_mcp])

    loaded = tools_module.get_available_tools(
        include_mcp=True,
        model_name="synthetic-model",
        app_config=_app_config(
            [
                ToolConfig(
                    name="write_analysis_report",
                    group="analytics",
                    use=_ALLOWED_SOURCES["write_analysis_report"],
                )
            ]
        ),
    )

    assert "synthetic_operator_mcp" in {item.name for item in loaded}
    assert "write_analysis_report" not in {item.name for item in loaded}


def test_ordinary_tool_loader_skips_report_writer_source_even_if_aliased(monkeypatch):
    report_source = _ALLOWED_SOURCES["write_analysis_report"]

    def resolve_source(source: str, target: type[BaseTool]):
        assert target is BaseTool
        if source == report_source:
            return _synthetic_report_writer
        pytest.fail("unexpected source resolution")

    monkeypatch.setattr(tools_module, "resolve_variable", resolve_source)
    loaded = tools_module.get_available_tools(
        include_mcp=False,
        app_config=_app_config([ToolConfig(name="report_alias", group="analytics", use=report_source)]),
    )

    assert "write_analysis_report" not in {item.name for item in loaded}
