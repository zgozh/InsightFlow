"""成功查询证据的严格、显式版本 JSON codec。"""

from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation

from app.analytics.domain.evidence import (
    MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES,
    AnalyticsQueryEvidence,
    AnalyticsQueryToolResult,
    canonical_json,
    validate_successful_query_result,
)
from app.analytics.domain.query import QueryRisk

ANALYSIS_EVIDENCE_PAYLOAD_VERSION = 1
MAX_ANALYSIS_EVIDENCE_PAYLOAD_BYTES = MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES + 64 * 1024

_RESULT_KEYS = frozenset({"code", "columns", "rows", "row_count", "truncated", "evidence"})
_EVIDENCE_KEYS = frozenset(
    {
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
)


class AnalysisEvidenceCodecError(ValueError):
    """版本未知、payload 损坏或违反固定字段契约。"""


def _fail() -> None:
    raise AnalysisEvidenceCodecError("analysis_evidence_payload_invalid")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    _fail()


def _require_object(value: object, expected: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != expected:
        _fail()
    return value


def _require_plain_int(value: object) -> int:
    if type(value) is not int:
        _fail()
    return value


def _require_scalar(value: object) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float and math.isfinite(value):
        return
    _fail()


def encode_analysis_evidence_result(result: AnalyticsQueryToolResult) -> str:
    if not isinstance(result, AnalyticsQueryToolResult):
        _fail()
    try:
        validate_successful_query_result(result)
        payload = canonical_json(result.to_payload())
        encoded = payload.encode("utf-8")
    except Exception:
        _fail()
    if len(encoded) > MAX_ANALYSIS_EVIDENCE_PAYLOAD_BYTES:
        _fail()
    return payload


def decode_analysis_evidence_result(payload_json: str, *, payload_version: int) -> AnalyticsQueryToolResult:
    if type(payload_version) is not int or payload_version != ANALYSIS_EVIDENCE_PAYLOAD_VERSION or not isinstance(payload_json, str):
        _fail()
    try:
        encoded = payload_json.encode("utf-8")
    except UnicodeEncodeError:
        _fail()
    if len(encoded) > MAX_ANALYSIS_EVIDENCE_PAYLOAD_BYTES:
        _fail()
    try:
        payload = json.loads(payload_json, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except AnalysisEvidenceCodecError:
        raise
    except Exception:
        _fail()

    value = _require_object(payload, _RESULT_KEYS)
    code = value["code"]
    columns = value["columns"]
    rows = value["rows"]
    row_count = _require_plain_int(value["row_count"])
    truncated = value["truncated"]
    if not isinstance(code, str) or type(columns) is not list or type(rows) is not list or row_count != len(rows) or type(truncated) is not bool:
        _fail()
    for row in rows:
        if type(row) is not list:
            _fail()
        for cell in row:
            _require_scalar(cell)

    evidence_value = _require_object(value["evidence"], _EVIDENCE_KEYS)
    engine_cost_text = evidence_value["engine_cost"]
    if not isinstance(engine_cost_text, str):
        _fail()
    try:
        engine_cost = Decimal(engine_cost_text)
    except InvalidOperation:
        _fail()
    if not engine_cost.is_finite() or engine_cost.is_signed() or format(engine_cost, "f") != engine_cost_text:
        _fail()

    try:
        evidence = AnalyticsQueryEvidence(
            evidence_id=evidence_value["evidence_id"],
            datasource_id=evidence_value["datasource_id"],
            query_hash=evidence_value["query_hash"],
            risk=QueryRisk(evidence_value["risk"]),
            schema_version=evidence_value["schema_version"],
            policy_version=evidence_value["policy_version"],
            plan_digest=evidence_value["plan_digest"],
            estimated_rows=_require_plain_int(evidence_value["estimated_rows"]),
            engine_cost=engine_cost,
            row_count=_require_plain_int(evidence_value["row_count"]),
            byte_count=_require_plain_int(evidence_value["byte_count"]),
            truncated=evidence_value["truncated"],
            result_digest=evidence_value["result_digest"],
            decision_code=evidence_value["decision_code"],
        )
        result = AnalyticsQueryToolResult(
            code=code,
            columns=tuple(columns),
            rows=tuple(tuple(row) for row in rows),
            truncated=truncated,
            evidence=evidence,
        )
        validate_successful_query_result(result)
        return result
    except Exception:
        _fail()
