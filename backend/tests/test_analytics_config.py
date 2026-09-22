"""Analytics App 配置解析测试（Phase 2C2 任务 1）。

`analytics:` 是 `AppConfig(extra="allow")` 上的 App 扩展块，由 `app.analytics` 严格校验：
未知字段、bool 冒充整数、float 成本、跨字段行数关系都必须拒绝；边界值本身继续交给既有
`ExecutionLimits` 校验，不复制第二套阈值。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.analytics.config import MAX_AUDIT_PAGE_SIZE, AnalyticsConfig, AnalyticsConfigError
from app.analytics.domain import MAX_QUERY_ROWS, ExecutionLimits


def _config(block=None):
    return SimpleNamespace(analytics=block)


# --- 默认值 -----------------------------------------------------------------


def test_defaults_match_the_approved_contract():
    config = AnalyticsConfig.from_app_config(_config())

    assert config.enabled is True
    assert config.query_max_rows == 1_000
    assert config.connect_timeout_ms == 3_000
    assert config.statement_timeout_ms == 5_000
    assert config.cancellation_grace_ms == 500
    assert config.max_estimated_rows == 100_000
    assert config.max_engine_cost == Decimal("100000")
    assert config.max_explain_bytes == 1_048_576
    assert config.max_result_columns == 128
    assert config.max_result_rows == 1_000
    assert config.max_result_bytes == 1_048_576
    assert config.plan_ttl_seconds == 60
    assert config.audit_page_size == 50
    assert MAX_AUDIT_PAGE_SIZE == 100


def test_a_config_object_without_the_block_still_produces_defaults():
    assert AnalyticsConfig.from_app_config(object()) == AnalyticsConfig()


def test_the_parsed_config_is_immutable():
    config = AnalyticsConfig()

    with pytest.raises(FrozenInstanceError):
        config.enabled = False  # type: ignore[misc]


# --- 严格性 -----------------------------------------------------------------


def test_an_unknown_field_is_rejected():
    with pytest.raises(AnalyticsConfigError) as error:
        AnalyticsConfig.from_app_config(_config({"query_max_rows": 10, "max_rows": 10}))

    assert "unknown" in error.value.reason


def test_a_non_mapping_block_is_rejected():
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config(["enabled"]))


@pytest.mark.parametrize("value", [True, False, "1000", 1000.0, None])
def test_a_non_integer_int_field_is_rejected(value):
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"query_max_rows": value}))


def test_a_boolean_cannot_masquerade_as_an_integer():
    # bool 是 int 的子类：`enabled: true` 出现在整数键上必须被拒绝。
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"max_result_rows": True}))


def test_a_non_boolean_enabled_is_rejected():
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"enabled": "yes"}))


@pytest.mark.parametrize("value", [100000.5, True, "abc", "", "  ", "NaN", "Infinity", "-1", "0"])
def test_a_non_positive_or_non_decimal_cost_is_rejected(value):
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"max_engine_cost": value}))


def test_cost_accepts_an_exact_decimal_string_or_integer_but_never_a_float():
    assert AnalyticsConfig.from_app_config(_config({"max_engine_cost": "12.50"})).max_engine_cost == Decimal("12.50")
    assert AnalyticsConfig.from_app_config(_config({"max_engine_cost": 100000})).max_engine_cost == Decimal("100000")
    assert isinstance(AnalyticsConfig.from_app_config(_config({"max_engine_cost": "12.50"})).max_engine_cost, Decimal)


# --- 跨字段与领域边界复用 ---------------------------------------------------


def test_query_max_rows_cannot_exceed_the_sql_row_ceiling():
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"query_max_rows": MAX_QUERY_ROWS + 1}))


def test_max_result_rows_cannot_exceed_query_max_rows():
    with pytest.raises(AnalyticsConfigError) as error:
        AnalyticsConfig.from_app_config(_config({"query_max_rows": 500, "max_result_rows": 501}))

    assert "max_result_rows" in error.value.reason


def test_max_result_rows_cannot_exceed_the_sql_row_ceiling():
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"query_max_rows": MAX_QUERY_ROWS, "max_result_rows": MAX_QUERY_ROWS + 1}))


def test_the_audit_page_size_is_bounded():
    assert AnalyticsConfig.from_app_config(_config({"audit_page_size": 1})).audit_page_size == 1
    assert AnalyticsConfig.from_app_config(_config({"audit_page_size": 100})).audit_page_size == 100
    for value in (0, 101):
        with pytest.raises(AnalyticsConfigError):
            AnalyticsConfig.from_app_config(_config({"audit_page_size": value}))


def test_domain_limits_still_own_the_transport_bounds():
    # 这里只提供「不复制领域阈值」的证据：越界的传输值仍由 ExecutionLimits 拒绝。
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"max_result_columns": 257}))
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"plan_ttl_seconds": 301}))


def test_execution_limits_are_constructed_from_the_configured_values():
    config = AnalyticsConfig.from_app_config(
        _config(
            {
                "query_max_rows": 400,
                "connect_timeout_ms": 4_000,
                "statement_timeout_ms": 6_000,
                "cancellation_grace_ms": 250,
                "max_estimated_rows": 5_000,
                "max_engine_cost": "42.5",
                "max_explain_bytes": 100_000,
                "max_result_columns": 8,
                "max_result_rows": 200,
                "max_result_bytes": 200_000,
                "plan_ttl_seconds": 30,
            }
        )
    )

    limits = config.execution_limits()

    assert isinstance(limits, ExecutionLimits)
    assert (limits.connect_timeout_ms, limits.statement_timeout_ms, limits.cancellation_grace_ms) == (4_000, 6_000, 250)
    assert (limits.max_estimated_rows, limits.max_engine_cost) == (5_000, Decimal("42.5"))
    assert (limits.max_explain_bytes, limits.max_result_columns) == (100_000, 8)
    assert (limits.max_result_rows, limits.max_result_bytes, limits.plan_ttl_seconds) == (200, 200_000, 30)


def test_disabled_configuration_still_parses_strictly():
    config = AnalyticsConfig.from_app_config(_config({"enabled": False}))

    assert config.enabled is False
    with pytest.raises(AnalyticsConfigError):
        AnalyticsConfig.from_app_config(_config({"enabled": False, "bogus": 1}))
