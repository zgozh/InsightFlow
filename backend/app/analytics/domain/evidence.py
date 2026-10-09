"""查询证据的纯领域契约：规范安全元数据、有界结果与确定性摘要。

模块只依赖标准库与 Analytics domain，供 Agent、应用仓储和 codec 共同使用。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal

from app.analytics.domain.datasource import _require_trimmed
from app.analytics.domain.execution import ExecutionDecisionCode, JsonScalar, QueryCostEstimate, QueryExecutionResult
from app.analytics.domain.query import MAX_QUERY_ROWS, QueryRisk, _require_plain_int

_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ANALYSIS_EVIDENCE_PER_RUN = 20
MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES = 16 * 1024 * 1024
ANALYSIS_EVIDENCE_UNAVAILABLE = "analysis_evidence_unavailable"


class EvidenceError(RuntimeError):
    """evidence 无法安全构造。只携带稳定 reason，绝不回显 payload。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def canonical_json(payload: object) -> str:
    """固定字段序、紧凑分隔符、保留非 ASCII 的 canonical JSON。"""

    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        # 异常文本可能带上原始片段（Pydantic/JSON 都会回显输入），一律只给稳定 reason。
        raise EvidenceError("evidence_payload_not_serializable") from error


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_result_digest(columns: tuple[str, ...], rows: tuple[tuple[JsonScalar, ...], ...]) -> str:
    return _sha256(canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}))


def _require_digest(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class AnalyticsQueryEvidence:
    """成功执行的安全 evidence envelope。"""

    evidence_id: str
    datasource_id: str
    query_hash: str
    risk: QueryRisk
    schema_version: str
    policy_version: str
    plan_digest: str
    estimated_rows: int
    engine_cost: Decimal
    row_count: int
    byte_count: int
    truncated: bool
    result_digest: str
    decision_code: str

    def __post_init__(self) -> None:
        _require_digest(self.evidence_id, "evidence_id")
        _require_trimmed(self.datasource_id, "datasource_id")
        _require_digest(self.query_hash, "query_hash")
        if not isinstance(self.risk, QueryRisk):
            raise ValueError("risk must be a QueryRisk")
        _require_trimmed(self.schema_version, "schema_version")
        _require_trimmed(self.policy_version, "policy_version")
        _require_digest(self.plan_digest, "plan_digest")
        _require_plain_int(self.estimated_rows, "estimated_rows")
        if self.estimated_rows < 0:
            raise ValueError("estimated_rows must not be negative")
        if not isinstance(self.engine_cost, Decimal) or not self.engine_cost.is_finite() or self.engine_cost < 0:
            raise ValueError("engine_cost must be a finite non-negative Decimal")
        for field_name in ("row_count", "byte_count"):
            _require_plain_int(getattr(self, field_name), field_name)
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must not be negative")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a boolean")
        _require_digest(self.result_digest, "result_digest")
        _require_trimmed(self.decision_code, "decision_code")

    @staticmethod
    def _metadata_payload(
        *,
        datasource_id: str,
        query_hash: str,
        risk: QueryRisk,
        schema_version: str,
        policy_version: str,
        plan_digest: str,
        estimated_rows: int,
        engine_cost: Decimal,
        row_count: int,
        byte_count: int,
        truncated: bool,
        result_digest: str,
        decision_code: str,
    ) -> dict:
        return {
            "datasource_id": datasource_id,
            "query_hash": query_hash,
            "risk": risk.value if isinstance(risk, QueryRisk) else risk,
            "schema_version": schema_version,
            "policy_version": policy_version,
            "plan_digest": plan_digest,
            "estimated_rows": estimated_rows,
            # canonical decimal 字符串：float 会破坏"同结果同 digest"。
            "engine_cost": format(engine_cost, "f") if isinstance(engine_cost, Decimal) else engine_cost,
            "row_count": row_count,
            "byte_count": byte_count,
            "truncated": truncated,
            "result_digest": result_digest,
            "decision_code": decision_code,
        }

    @classmethod
    def build(
        cls,
        *,
        datasource_id: str,
        query_hash: str,
        risk: QueryRisk,
        schema_version: str,
        policy_version: str,
        estimate: QueryCostEstimate | None = None,
        plan_digest: str | None = None,
        estimated_rows: int | None = None,
        engine_cost: Decimal | None = None,
        result: QueryExecutionResult,
        decision_code: str = ExecutionDecisionCode.EXECUTED.value,
    ) -> AnalyticsQueryEvidence:
        """由服务端派生值构造 evidence；两个 digest 都在这里计算。"""

        if estimate is not None:
            plan_digest = estimate.plan_digest
            estimated_rows = estimate.estimated_rows
            engine_cost = estimate.engine_cost

        result_digest = compute_result_digest(result.columns, result.rows)
        payload = cls._metadata_payload(
            datasource_id=datasource_id,
            query_hash=query_hash,
            risk=risk,
            schema_version=schema_version,
            policy_version=policy_version,
            plan_digest=plan_digest,  # type: ignore[arg-type]
            estimated_rows=estimated_rows,  # type: ignore[arg-type]
            engine_cost=engine_cost,  # type: ignore[arg-type]
            row_count=result.row_count,
            byte_count=result.byte_count,
            truncated=result.truncated,
            result_digest=result_digest,
            decision_code=decision_code,
        )
        return cls(
            evidence_id=_sha256(canonical_json(payload)),
            datasource_id=datasource_id,
            query_hash=query_hash,
            risk=risk,
            schema_version=schema_version,
            policy_version=policy_version,
            plan_digest=plan_digest,  # type: ignore[arg-type]
            estimated_rows=estimated_rows,  # type: ignore[arg-type]
            engine_cost=engine_cost,  # type: ignore[arg-type]
            row_count=result.row_count,
            byte_count=result.byte_count,
            truncated=result.truncated,
            result_digest=result_digest,
            decision_code=decision_code,
        )

    def to_payload(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            **self._metadata_payload(
                datasource_id=self.datasource_id,
                query_hash=self.query_hash,
                risk=self.risk,
                schema_version=self.schema_version,
                policy_version=self.policy_version,
                plan_digest=self.plan_digest,
                estimated_rows=self.estimated_rows,
                engine_cost=self.engine_cost,
                row_count=self.row_count,
                byte_count=self.byte_count,
                truncated=self.truncated,
                result_digest=self.result_digest,
                decision_code=self.decision_code,
            ),
        }


@dataclass(frozen=True, slots=True)
class AnalyticsQueryToolResult:
    """交给模型的安全工具结果：稳定 code + 有界结果 + evidence。

    token 永远不会出现在这里——它只活在工具函数的局部变量里。
    """

    code: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[JsonScalar, ...], ...] = ()
    truncated: bool = False
    evidence: AnalyticsQueryEvidence | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.code, "code")
        if not isinstance(self.columns, tuple):
            raise ValueError("columns must be a tuple")
        for column in self.columns:
            _require_trimmed(column, "columns")
        if not isinstance(self.rows, tuple):
            raise ValueError("rows must be a tuple")
        for row in self.rows:
            if not isinstance(row, tuple) or len(row) != len(self.columns):
                raise ValueError("each row must be a tuple with one cell per column")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a boolean")
        if self.evidence is not None and not isinstance(self.evidence, AnalyticsQueryEvidence):
            raise ValueError("evidence must be an AnalyticsQueryEvidence")
        successful_codes = {ExecutionDecisionCode.EXECUTED.value, ExecutionDecisionCode.RESULT_LIMIT_REACHED.value}
        if self.evidence is not None and self.code not in successful_codes:
            raise ValueError("failed results cannot carry evidence")
        if self.rows and self.evidence is None:
            raise ValueError("rows require evidence")
        if not self.rows and self.code in successful_codes:
            if self.evidence is None:
                raise ValueError("successful results require evidence")
            validate_successful_query_result(self)

    def to_payload(self) -> dict:
        payload: dict = {
            "code": self.code,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "row_count": len(self.rows),
            "truncated": self.truncated,
        }
        if self.evidence is not None:
            payload["evidence"] = self.evidence.to_payload()
        return payload

    def to_json(self) -> str:
        return canonical_json(self.to_payload())


def validate_successful_query_result(result: AnalyticsQueryToolResult) -> int:
    """校验可持久化成功结果及其 evidence，返回规范快照 UTF-8 字节数。"""

    if (
        not isinstance(result, AnalyticsQueryToolResult)
        or not isinstance(result.evidence, AnalyticsQueryEvidence)
        or not isinstance(result.code, str)
        or not isinstance(result.columns, tuple)
        or not isinstance(result.rows, tuple)
        or type(result.truncated) is not bool
    ):
        raise ValueError("analysis_evidence_unavailable")
    evidence = result.evidence
    if (
        result.code not in {ExecutionDecisionCode.EXECUTED.value, ExecutionDecisionCode.RESULT_LIMIT_REACHED.value}
        or evidence.decision_code != result.code
        or result.truncated != (result.code == ExecutionDecisionCode.RESULT_LIMIT_REACHED.value)
        or not isinstance(evidence.risk, QueryRisk)
        or evidence.risk not in {QueryRisk.LOW, QueryRisk.MEDIUM}
        or len(result.columns) > 256
        or len(result.rows) > MAX_QUERY_ROWS
    ):
        raise ValueError("analysis_evidence_unavailable")
    for column in result.columns:
        if type(column) is not str or not column or column != column.strip():
            raise ValueError("analysis_evidence_unavailable")
    for row in result.rows:
        if not isinstance(row, tuple) or len(row) != len(result.columns):
            raise ValueError("analysis_evidence_unavailable")
        for cell in row:
            if cell is None or type(cell) in (bool, int, str):
                continue
            if type(cell) is float and math.isfinite(cell):
                continue
            raise ValueError("analysis_evidence_unavailable")

    try:
        snapshot = canonical_json({"columns": list(result.columns), "rows": [list(row) for row in result.rows]}).encode("utf-8")
        evidence_payload = evidence.to_payload()
        evidence_digest = _sha256(canonical_json({key: value for key, value in evidence_payload.items() if key != "evidence_id"}))
        result_digest = compute_result_digest(result.columns, result.rows)
    except Exception:
        raise ValueError("analysis_evidence_unavailable") from None
    if (
        len(snapshot) > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES
        or evidence.row_count != len(result.rows)
        or evidence.truncated != result.truncated
        or evidence.byte_count != len(snapshot)
        or evidence.result_digest != result_digest
        or evidence.evidence_id != evidence_digest
    ):
        raise ValueError("analysis_evidence_unavailable")
    return len(snapshot)
