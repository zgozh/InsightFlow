"""通用 subagent `disallowed_tools` override 测试（Phase 3 任务 5）。

DeerFlow 会把父级 tool groups 原样继承给 subagent，因此"只给 Lead 的 tool group"必须靠
subagent 侧的 denylist 实现。这里固定新 seam 的语义：

- operator-owned：只来自 `config.yaml`，客户端/run context 无法覆盖；
- **加法式**：override 只能追加拒绝项，不能解除内置的硬编码拒绝（`task` 等）；
- 稳定去重、默认空值行为完全不变、按名字隔离（改 general-purpose 不影响 bash）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deerflow.config.subagents_config import SubagentOverrideConfig, SubagentsAppConfig
from deerflow.subagents.builtins.general_purpose import GENERAL_PURPOSE_CONFIG
from deerflow.subagents.registry import get_subagent_config


def _app_config(*, disallowed=None, name="general-purpose"):
    agents = {}
    if disallowed is not None:
        agents[name] = SubagentOverrideConfig(disallowed_tools=disallowed)
    return SimpleNamespace(subagents=SubagentsAppConfig(agents=agents), tools=[], tool_groups=[], models=[])


def _tool(name: str):
    return SimpleNamespace(name=name)


def _real_filter_tools():
    """取**真实**的 `SubagentExecutor._filter_tools`。

    `tests/conftest.py` 为了打断收集期的循环 import，把 `deerflow.subagents.executor`
    换成了 MagicMock（对 MagicMock 做列表推导会得到空列表）。这里临时恢复真实模块，
    用完把 mock 放回去，避免影响其它测试。
    """

    import importlib
    import sys

    saved = sys.modules.pop("deerflow.subagents.executor", None)
    try:
        module = importlib.import_module("deerflow.subagents.executor")
    finally:
        if saved is not None:
            sys.modules["deerflow.subagents.executor"] = saved
    return module._filter_tools


# --- 配置模型 ---------------------------------------------------------------


def test_the_override_defaults_to_none_and_preserves_existing_behaviour():
    override = SubagentOverrideConfig()

    assert override.disallowed_tools is None


def test_the_override_accepts_an_operator_supplied_denylist():
    override = SubagentOverrideConfig(disallowed_tools=["query_business_data"])

    assert override.disallowed_tools == ["query_business_data"]


def test_the_override_dedupes_and_keeps_order():
    override = SubagentOverrideConfig(disallowed_tools=["b_tool", "a_tool", "b_tool"])

    assert override.disallowed_tools == ["b_tool", "a_tool"]


@pytest.mark.parametrize("value", [[""], ["  "], [" tool"], ["tool "], [7], [None]])
def test_the_override_rejects_blank_or_non_string_entries(value):
    with pytest.raises(ValueError):
        SubagentOverrideConfig(disallowed_tools=value)


# --- 与内置 denylist 的合并 -------------------------------------------------


def test_the_default_general_purpose_denylist_is_unchanged():
    config = get_subagent_config("general-purpose", app_config=_app_config())

    assert config is not None
    assert config.disallowed_tools == GENERAL_PURPOSE_CONFIG.disallowed_tools


def test_an_override_is_merged_additively_after_the_builtin_entries():
    config = get_subagent_config("general-purpose", app_config=_app_config(disallowed=["query_business_data", "inspect_business_catalog"]))

    assert config is not None
    assert config.disallowed_tools == [*GENERAL_PURPOSE_CONFIG.disallowed_tools, "query_business_data", "inspect_business_catalog"]


def test_an_override_can_never_remove_a_builtin_denial():
    config = get_subagent_config("general-purpose", app_config=_app_config(disallowed=["bash"]))

    assert config is not None
    for required in GENERAL_PURPOSE_CONFIG.disallowed_tools:
        assert required in config.disallowed_tools


def test_an_override_repeating_a_builtin_entry_does_not_duplicate_it():
    config = get_subagent_config("general-purpose", app_config=_app_config(disallowed=["task", "task", "query_business_data"]))

    assert config is not None
    assert config.disallowed_tools.count("task") == 1
    assert config.disallowed_tools[-1] == "query_business_data"


def test_an_override_for_one_subagent_does_not_affect_another():
    app_config = _app_config(disallowed=["query_business_data"], name="general-purpose")

    general = get_subagent_config("general-purpose", app_config=app_config)
    bash = get_subagent_config("bash", app_config=app_config)

    assert "query_business_data" in general.disallowed_tools
    assert "query_business_data" not in (bash.disallowed_tools or [])


def test_an_unknown_agent_override_is_ignored():
    app_config = _app_config(disallowed=["query_business_data"], name="not-a-real-agent")

    assert get_subagent_config("general-purpose", app_config=app_config).disallowed_tools == GENERAL_PURPOSE_CONFIG.disallowed_tools


# --- 实际生效：真实 tool 列表被过滤 -----------------------------------------


def test_the_denied_analytics_tools_are_removed_from_a_real_subagent_tool_list():
    """`SubagentExecutor._filter_tools` 正是工具装配后的最后一道名字级过滤。"""

    names = ["bash", "read_file", "inspect_business_catalog", "query_business_data", "task"]
    tools = [_tool(name) for name in names]
    config = get_subagent_config("general-purpose", app_config=_app_config(disallowed=["inspect_business_catalog", "query_business_data"]))

    kept = [tool.name for tool in _real_filter_tools()(tools, config.tools, config.disallowed_tools)]

    assert kept == ["bash", "read_file"]
    assert "inspect_business_catalog" not in kept and "query_business_data" not in kept


def test_the_same_tool_list_is_untouched_without_an_override():
    names = ["bash", "inspect_business_catalog", "query_business_data"]
    tools = [_tool(name) for name in names]
    config = get_subagent_config("general-purpose", app_config=_app_config())

    kept = [tool.name for tool in _real_filter_tools()(tools, config.tools, config.disallowed_tools)]

    assert kept == names


def test_the_override_is_operator_owned_and_never_read_from_run_context():
    """seam 只接受 config.yaml 模型；没有任何从 run/request context 读取 denylist 的入口。"""

    import inspect

    from deerflow.subagents import registry

    source = inspect.getsource(registry.get_subagent_config)

    assert "disallowed_tools" in source
    for forbidden in ("runtime", "context.get", "config.configurable"):
        assert forbidden not in source, f"the denylist must not be resolved from {forbidden}"


# --- 样例配置的端到端契约 ---------------------------------------------------


def _example_app_config():
    """加载仓库真实的 `config.example.yaml`（严格解析）。"""

    from pathlib import Path

    from deerflow.config.app_config import AppConfig

    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    return AppConfig.from_file(str(example))


def test_the_example_config_parses_and_declares_the_analytics_group():
    config = _example_app_config()

    groups = {group.name for group in config.tool_groups}
    tools = {tool.name: tool for tool in config.tools}

    assert "analytics" in groups
    assert tools["inspect_business_catalog"].group == "analytics"
    assert tools["query_business_data"].group == "analytics"
    assert tools["query_business_data"].use == "app.analytics.agent.tools:query_business_data"


def test_the_lead_sees_the_analytics_tools_and_the_subagent_schema_does_not():
    """用真实 loader + 真实配置证明：Lead 有，Analyst/Reviewer 的实际工具列表没有。"""

    from deerflow.tools import get_available_tools

    config = _example_app_config()
    # 默认 Lead：agent_config 为 None => groups=None => 全部已配置工具。
    lead_tools = get_available_tools(groups=None, app_config=config, include_mcp=False)
    lead_names = {tool.name for tool in lead_tools}

    assert {"inspect_business_catalog", "query_business_data"} <= lead_names

    # general-purpose 继承 Lead 的 groups，因此同一份小组也会到它手里……
    subagent_groups = None
    inherited = get_available_tools(groups=subagent_groups, app_config=config, include_mcp=False)
    general_purpose = get_subagent_config("general-purpose", app_config=config)
    filtered = _real_filter_tools()(inherited, general_purpose.tools, general_purpose.disallowed_tools)
    subagent_names = {tool.name for tool in filtered}

    # ……但 denylist 把它们从实际工具 schema 里摘掉了。
    assert "inspect_business_catalog" not in subagent_names
    assert "query_business_data" not in subagent_names
    assert "bash" not in subagent_names  # builtin denial is untouched
    assert subagent_names, "the subagent must still get its ordinary tools"
