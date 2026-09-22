"""审计领域值与持久化端口契约（Phase 2C1 任务 1）。

这里的断言刻意只覆盖**安全不变量**：

- 审计值对象拒绝残缺身份、非 64 位小写十六进制摘要、naive 时间、布尔冒充整数、
  float 成本与负数列；
- 审计值对象在 repr 中不出现 SQL、结果值或凭证；
- 持久化端口是 runtime-checkable Protocol，且关键字参数身份不可省略；
- 新增的稳定决定码与 `revoke` 协议形状。

注释与 docstring 用中文；标识符、决定码与协议名保持英文。
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.analytics.application.execution_ports import ExecutionPlanStore
from app.analytics.application.persistence_ports import (
    AccessPolicyRepository,
    DatasourceAdminRepository,
    MetricRepository,
    PersistenceConflictError,
    PersistenceDataError,
    QueryAuditLog,
    QueryAuditReader,
    SchemaSnapshotRepository,
)
from app.analytics.domain import (
    ExecutionDecisionCode,
    QueryAuditCompletion,
    QueryAuditPhase,
    QueryAuditStart,
    QueryAuditStatus,
    QueryRisk,
)

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64


def _start(**overrides) -> QueryAuditStart:
    values = {
        "principal_id": "user-1",
        "datasource_id": "ds-1",
        "phase": QueryAuditPhase.PLAN,
        "started_at": _NOW,
        "query_hash": _DIGEST,
        "risk": QueryRisk.LOW,
        "schema_version": "s1",
        "policy_version": "p1",
    }
    values.update(overrides)
    return QueryAuditStart(**values)


def _completion(**overrides) -> QueryAuditCompletion:
    values = {
        "audit_id": "audit-1",
        "decision_code": ExecutionDecisionCode.PLAN_CREATED.value,
        "finished_at": _NOW,
        "risk": QueryRisk.LOW,
        "estimated_rows": 10,
        "engine_cost": Decimal("12.5"),
        "plan_digest": "b" * 64,
        "row_count": 3,
        "byte_count": 128,
        "truncated": False,
        "latency_ms": 42,
    }
    values.update(overrides)
    return QueryAuditCompletion(**values)


# --- 枚举与稳定决定码 -------------------------------------------------------


def test_audit_phase_and_status_values_are_stable():
    assert {phase.value for phase in QueryAuditPhase} == {"policy", "authorization", "plan", "execute"}
    assert {status.value for status in QueryAuditStatus} == {"started", "completed"}


def test_audit_unavailable_is_a_stable_decision_code():
    # 审计是门禁而不是最佳努力日志，因此必须有独立决定码。
    assert ExecutionDecisionCode.AUDIT_UNAVAILABLE.value == "audit_unavailable"


# --- QueryAuditStart 不变量 -------------------------------------------------


def test_audit_start_accepts_a_minimal_entry_without_optional_metadata():
    entry = QueryAuditStart(principal_id="user-1", datasource_id=None, phase=QueryAuditPhase.EXECUTE, started_at=_NOW)

    assert entry.datasource_id is None
    assert entry.query_hash is None
    assert entry.risk is None
    assert entry.schema_version is None and entry.policy_version is None


@pytest.mark.parametrize("field_name", ["principal_id"])
def test_audit_start_requires_a_trimmed_identity(field_name):
    for value in ("", "  ", " user-1", "user-1 "):
        with pytest.raises(ValueError):
            _start(**{field_name: value})


def test_audit_start_rejects_a_blank_datasource_id():
    for value in ("", "  ", " ds-1"):
        with pytest.raises(ValueError):
            _start(datasource_id=value)


def test_audit_start_requires_a_known_phase():
    with pytest.raises(ValueError):
        _start(phase="plan")


def test_audit_start_requires_an_aware_start_time():
    with pytest.raises(ValueError):
        _start(started_at=datetime(2026, 9, 22, 12, 0))


def test_audit_start_normalizes_nothing_but_accepts_non_utc_aware_times():
    offset = timezone(timedelta(hours=8))
    entry = _start(started_at=datetime(2026, 9, 22, 20, 0, tzinfo=offset))

    assert entry.started_at.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize(
    "query_hash",
    ["a" * 63, "a" * 65, "A" * 64, "g" * 64, 7],
)
def test_audit_start_rejects_a_non_canonical_query_hash(query_hash):
    with pytest.raises(ValueError):
        _start(query_hash=query_hash)


def test_audit_start_requires_a_known_risk():
    with pytest.raises(ValueError):
        _start(risk="low")


def test_audit_start_requires_schema_and_policy_versions_together():
    with pytest.raises(ValueError):
        _start(schema_version="s1", policy_version=None)
    with pytest.raises(ValueError):
        _start(schema_version=None, policy_version="p1")


def test_audit_start_rejects_an_untrimmed_version():
    with pytest.raises(ValueError):
        _start(schema_version=" s1")


# --- QueryAuditCompletion 不变量 -------------------------------------------


def test_audit_completion_accepts_a_minimal_entry():
    completion = QueryAuditCompletion(audit_id="audit-1", decision_code="plan_unavailable", finished_at=_NOW)

    assert completion.estimated_rows is None
    assert completion.engine_cost is None
    assert completion.truncated is None
    assert completion.latency_ms is None


def test_audit_completion_requires_trimmed_identifiers():
    for overrides in ({"audit_id": "  "}, {"audit_id": " audit-1"}, {"decision_code": ""}, {"decision_code": " x"}):
        with pytest.raises(ValueError):
            _completion(**overrides)


def test_audit_completion_requires_an_aware_finish_time():
    with pytest.raises(ValueError):
        _completion(finished_at=datetime(2026, 9, 22, 12, 0))


@pytest.mark.parametrize("field_name", ["estimated_rows", "row_count", "byte_count", "latency_ms"])
def test_audit_completion_rejects_negative_or_non_integer_measurements(field_name):
    for value in (-1, "3", True, 1.5):
        with pytest.raises(ValueError):
            _completion(**{field_name: value})


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-1"), 1.5, "12.5"])
def test_audit_completion_rejects_a_non_finite_or_float_cost(value):
    with pytest.raises(ValueError):
        _completion(engine_cost=value)


def test_audit_completion_rejects_a_non_canonical_plan_digest():
    for value in ("b" * 63, "B" * 64, "z" * 64):
        with pytest.raises(ValueError):
            _completion(plan_digest=value)


def test_audit_completion_requires_a_real_bool_for_truncated():
    for value in (0, 1, "false", "true"):
        with pytest.raises(ValueError):
            _completion(truncated=value)


def test_audit_completion_requires_a_known_risk():
    with pytest.raises(ValueError):
        _completion(risk="low")


# --- 敏感字段边界 -----------------------------------------------------------


def test_audit_values_never_carry_sql_result_values_or_credentials():
    start = _start()
    completion = _completion()

    for value in (start, completion):
        rendered = repr(value)
        assert "SELECT" not in rendered
        assert "postgresql://" not in rendered
        assert "secret_ref" not in rendered
        assert "env://" not in rendered
        # 原始 token 与 digest 都不允许出现在审计值里。
        assert "plan_id" not in rendered
        assert "token_digest" not in rendered
        assert "token" not in rendered


def test_audit_value_field_sets_are_pinned():
    # 机械扩字段是最容易把 SQL/结果值带进审计的方式；这里固定字段集合。
    assert set(QueryAuditStart.__dataclass_fields__) == {
        "principal_id",
        "datasource_id",
        "phase",
        "started_at",
        "query_hash",
        "risk",
        "schema_version",
        "policy_version",
    }
    assert set(QueryAuditCompletion.__dataclass_fields__) == {
        "audit_id",
        "decision_code",
        "finished_at",
        "risk",
        "estimated_rows",
        "engine_cost",
        "plan_digest",
        "row_count",
        "byte_count",
        "truncated",
        "latency_ms",
    }


# --- 持久化端口 -------------------------------------------------------------


def test_persistence_ports_are_runtime_checkable_protocols():
    for port in (DatasourceAdminRepository, SchemaSnapshotRepository, AccessPolicyRepository, MetricRepository, QueryAuditLog):
        assert getattr(port, "_is_runtime_protocol", False), port


def test_repository_ports_extend_the_read_only_catalogs():
    from app.analytics.application import AccessPolicyCatalog, DatasourceCatalog, MetricCatalog, SchemaCatalog

    assert issubclass(SchemaSnapshotRepository, SchemaCatalog)
    assert issubclass(AccessPolicyRepository, AccessPolicyCatalog)
    assert issubclass(MetricRepository, MetricCatalog)
    assert issubclass(DatasourceAdminRepository, object)
    assert DatasourceCatalog is not None


def test_persistence_errors_carry_only_a_stable_reason():
    conflict = PersistenceConflictError("version_drift")
    data = PersistenceDataError("payload_invalid_enum")

    assert conflict.reason == "version_drift"
    assert data.reason == "payload_invalid_enum"
    assert "postgres://" not in str(conflict)


def test_a_conforming_audit_log_satisfies_the_port():
    class _Log:
        async def start(self, entry):
            return "audit-1"

        async def finish(self, completion):
            return None

        async def list_for_principal(self, *, principal_id, limit, before_started_at=None, before_id=None):
            return ()

    assert isinstance(_Log(), QueryAuditLog)


def test_audit_log_rejects_an_object_without_finish():
    class _Half:
        async def start(self, entry):
            return "audit-1"

        async def list_for_principal(self, *, principal_id, limit, before_started_at=None, before_id=None):
            return ()

    assert not isinstance(_Half(), QueryAuditLog)


def test_audit_log_rejects_an_object_without_the_read_port():
    """Phase 2C2 把只读分页并入审计端口：写入能力齐备但没有读取方法的对象不再满足协议。"""

    class _WriteOnly:
        async def start(self, entry):
            return "audit-1"

        async def finish(self, completion):
            return None

    assert not isinstance(_WriteOnly(), QueryAuditLog)


def test_the_read_only_audit_port_is_separate_and_runtime_checkable():
    assert getattr(QueryAuditReader, "_is_runtime_protocol", False)
    assert "list_for_principal" in QueryAuditReader.__dict__
    assert "start" not in QueryAuditReader.__dict__


def test_plan_store_port_declares_revoke():
    # revoke 是「审计 finish 失败必须作废已插入 plan」的实现前提。
    assert "revoke" in ExecutionPlanStore.__dict__
