from types import SimpleNamespace

import pytest

from deerflow.config.subagent_runtime_config import SubagentRuntimeConfig
from deerflow.subagents import SubagentRuntime


def test_runtime_uses_one_caller_owned_app_config_snapshot() -> None:
    app_config = SimpleNamespace(
        subagent_runtime=SubagentRuntimeConfig(max_running=11),
        subagents=SimpleNamespace(max_total_per_run=14),
    )

    runtime = SubagentRuntime.from_app_config(app_config)

    assert runtime.config.max_running == 11
    assert runtime.max_total_per_run == 14
    assert runtime.app_config is app_config


def test_runtime_shares_one_execution_capacity_instance() -> None:
    runtime = SubagentRuntime(SubagentRuntimeConfig(max_running=5))

    assert runtime.execution_capacity.snapshot().max_running == 5


def test_runtime_rejects_max_total_outside_schema_range() -> None:
    with pytest.raises(ValueError, match="max_total_per_run must be between"):
        SubagentRuntime(SubagentRuntimeConfig(), max_total_per_run=0)
