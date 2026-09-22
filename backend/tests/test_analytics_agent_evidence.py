"""Analytics Agent evidence 契约测试（Phase 3 任务 1）。

evidence 是给 Reviewer 用的确定性引用：它必须可 JSON 序列化、字段白名单固定、同输入同摘要，
且**绝不**携带 raw/canonical SQL、plan token/digest、secret、DSN、异常文本或 PII。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analytics.agent.evidence import (
    AnalyticsQueryEvidence,
    AnalyticsQueryToolResult,
    EvidenceError,
    canonical_json,
    compute_result_digest,
)
from app.analytics.application.delivery import QueryPlanDelivery, QueryPlanDeliveryMetadata
from app.analytics.domain import ExecutionDecisionCode, QueryCostEstimate, QueryExecutionResult, QueryPlanReceipt, QueryRisk

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_HASH = "a" * 64


def _metadata(**overrides) -> QueryPlanDeliveryMetadata:
    values = {
        "datasource_id": "ds-1",
        "query_hash": _HASH,
        "risk": QueryRisk.LOW,
        "schema_version": "s1",
        "policy_version": "p1",
    }
    values.update(overrides)
    return QueryPlanDeliveryMetadata(**values)


def _estimate(**overrides) -> QueryCostEstimate:
    values = {"engine": "postgresql", "estimated_rows": 10, "engine_cost": Decimal("12.5"), "plan_digest": "b" * 64}
    values.update(overrides)
    from app.analytics.domain import DatasourceEngine

    values["engine"] = DatasourceEngine(values["engine"]) if isinstance(values["engine"], str) else values["engine"]
    return QueryCostEstimate(**values)


def _result(**overrides) -> QueryExecutionResult:
    values = {"columns": ("id",), "rows": ((1,),), "row_count": 1, "byte_count": 21, "truncated": False}
    values.update(overrides)
    return QueryExecutionResult(**values)


def _evidence(**overrides) -> AnalyticsQueryEvidence:
    values = {
        "datasource_id": "ds-1",
        "query_hash": _HASH,
        "risk": QueryRisk.LOW,
        "schema_version": "s1",
        "policy_version": "p1",
        "plan_digest": "b" * 64,
        "estimated_rows": 10,
        "engine_cost": Decimal("12.5"),
        "result": _result(),
        "decision_code": ExecutionDecisionCode.EXECUTED.value,
    }
    values.update(overrides)
    return AnalyticsQueryEvidence.build(**values)


# --- canonical JSON ---------------------------------------------------------


def test_canonical_json_is_deterministic_compact_and_utf8_preserving():
    first = canonical_json({"b": 1, "a": "订单"})
    second = canonical_json({"a": "订单", "b": 1})

    assert first == second == '{"a":"订单","b":1}'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value):
    with pytest.raises(EvidenceError):
        canonical_json({"value": value})


def test_canonical_json_rejects_unserializable_objects():
    with pytest.raises(EvidenceError):
        canonical_json({"value": object()})


def test_canonical_json_error_never_echoes_the_payload():
    with pytest.raises(EvidenceError) as error:
        canonical_json({"sql": "SELECT secret FROM t", "bad": object()})

    assert "SELECT secret" not in str(error.value)
    assert " " not in error.value.reason


# --- result digest ----------------------------------------------------------


def test_result_digest_is_stable_for_the_same_columns_and_rows():
    assert compute_result_digest(("id",), ((1,), (2,))) == compute_result_digest(("id",), ((1,), (2,)))


def test_result_digest_changes_when_a_cell_changes():
    baseline = compute_result_digest(("id",), ((1,), (2,)))

    assert compute_result_digest(("id",), ((1,), (3,))) != baseline
    assert compute_result_digest(("id",), ((1,),)) != baseline
    assert compute_result_digest(("other",), ((1,), (2,))) != baseline


def test_result_digest_is_a_lowercase_sha256():
    digest = compute_result_digest(("id",), ())

    assert len(digest) == 64 and digest == digest.lower()


# --- evidence ---------------------------------------------------------------


def test_evidence_id_is_deterministic_for_the_same_inputs():
    assert _evidence().evidence_id == _evidence().evidence_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("datasource_id", "ds-2"),
        ("query_hash", "c" * 64),
        ("schema_version", "s2"),
        ("policy_version", "p2"),
        ("plan_digest", "d" * 64),
        ("estimated_rows", 11),
        ("engine_cost", Decimal("13")),
        ("decision_code", ExecutionDecisionCode.RESULT_LIMIT_REACHED.value),
    ],
)
def test_evidence_id_changes_when_a_safe_metadata_field_changes(field, value):
    baseline = _evidence().evidence_id
    changed = _evidence(**{field: value})

    assert changed.evidence_id != baseline


def test_evidence_id_changes_when_the_result_changes_but_the_metadata_does_not():
    baseline = _evidence()
    changed = _evidence(result=_result(rows=((2,),), row_count=1))

    assert changed.result_digest != baseline.result_digest
    assert changed.evidence_id != baseline.evidence_id


def test_a_changed_risk_changes_the_evidence_id():
    assert _evidence(risk=QueryRisk.MEDIUM).evidence_id != _evidence(risk=QueryRisk.LOW).evidence_id


def test_evidence_payload_is_an_exact_whitelist():
    payload = _evidence().to_payload()

    assert set(payload) == {
        "evidence_id",
        "datasource_id",
        "query_hash",
        "risk",
        "schema_version",
        "policy_version",
        "plan_digest",
        "estimated_rows",
        "engine_cost",
        "row_count",
        "byte_count",
        "truncated",
        "result_digest",
        "decision_code",
    }
    assert payload["risk"] == "low"
    assert payload["engine_cost"] == "12.5"
    assert isinstance(payload["engine_cost"], str)


def test_evidence_payload_carries_no_sql_token_secret_or_exception_text():
    rendered = json.dumps(_evidence().to_payload(), ensure_ascii=False)

    for banned in ("select", "sql", "token", "secret", "dsn", "password", "traceback", "postgres://", "env://"):
        assert banned not in rendered.lower()


def test_evidence_rejects_an_untrimmed_or_wrong_typed_field():
    with pytest.raises(ValueError):
        _evidence(datasource_id=" ds-1")
    with pytest.raises(ValueError):
        _evidence(query_hash="A" * 64)
    with pytest.raises(ValueError):
        _evidence(estimated_rows=-1)
    with pytest.raises(ValueError):
        _evidence(engine_cost=12.5)
    with pytest.raises(ValueError):
        _evidence(decision_code="  ")


# --- plan delivery metadata -------------------------------------------------


def test_plan_delivery_metadata_is_validated_and_safe():
    metadata = _metadata()

    assert metadata.query_hash == _HASH
    with pytest.raises(ValueError):
        _metadata(query_hash="zz")
    with pytest.raises(ValueError):
        _metadata(risk="low")


def test_plan_delivery_carries_metadata_only_together_with_a_receipt():
    receipt = QueryPlanReceipt(plan_id="raw-token", expires_at=_NOW, estimate=_estimate())

    delivery = QueryPlanDelivery(code=ExecutionDecisionCode.PLAN_CREATED.value, receipt=receipt, metadata=_metadata())
    assert delivery.metadata is not None

    with pytest.raises(ValueError):
        QueryPlanDelivery(code=ExecutionDecisionCode.PLAN_CREATED.value, receipt=receipt)
    with pytest.raises(ValueError):
        QueryPlanDelivery(code=ExecutionDecisionCode.DATABASE_UNAVAILABLE.value, metadata=_metadata())


# --- tool result ------------------------------------------------------------


def test_tool_result_payload_is_an_exact_whitelist_and_never_carries_a_token():
    result = AnalyticsQueryToolResult(code=ExecutionDecisionCode.EXECUTED.value, columns=("id",), rows=((1,),), truncated=False, evidence=_evidence())

    payload = result.to_payload()

    assert set(payload) == {"code", "columns", "rows", "row_count", "truncated", "evidence"}
    assert payload["row_count"] == 1
    rendered = result.to_json()
    assert "raw-token" not in rendered
    assert json.loads(rendered)["evidence"]["evidence_id"] == _evidence().evidence_id


def test_a_denied_tool_result_carries_only_a_stable_code():
    result = AnalyticsQueryToolResult(code=ExecutionDecisionCode.PLAN_UNAVAILABLE.value)

    assert result.to_payload() == {"code": "plan_unavailable", "columns": [], "rows": [], "row_count": 0, "truncated": False}
    assert result.evidence is None


def test_tool_result_requires_evidence_only_when_it_carries_rows():
    with pytest.raises(ValueError):
        AnalyticsQueryToolResult(code=ExecutionDecisionCode.EXECUTED.value, columns=("id",), rows=((1,),), truncated=False)
    with pytest.raises(ValueError):
        AnalyticsQueryToolResult(code=ExecutionDecisionCode.PLAN_UNAVAILABLE.value, evidence=_evidence())
