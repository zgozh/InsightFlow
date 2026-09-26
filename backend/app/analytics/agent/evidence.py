"""Analytics Agent 的 evidence 契约（Phase 3 §4）。

evidence 是交给 Reviewer 的**确定性引用**：Reviewer 用它判断转述的数字是否对应当前结果，
Lead 用它在最终回复里引用。因此它必须：

- 可 JSON 序列化，字段白名单固定，同输入同摘要；
- 只含安全元数据——没有 raw/canonical SQL、plan token 或 digest、secret、DSN、异常文本或 PII；
- `result_digest` 对 canonical columns+rows 计算，任何单元格变化都会改变它。

`canonical_json` 的 `allow_nan=False` 是硬边界：NaN/Infinity 无法稳定序列化，一旦进入 evidence
就会让"同一结果同一 digest"的承诺失效。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from app.analytics.domain import ExecutionDecisionCode, JsonScalar, QueryCostEstimate, QueryExecutionResult, QueryRisk
from app.analytics.domain.datasource import _require_trimmed
from app.analytics.domain.query import _require_plain_int

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
        # 有行必有 evidence，有 evidence 必有行：拒绝"半截"结果，Reviewer 才能稳定引用。
        if bool(self.rows) != (self.evidence is not None):
            raise ValueError("rows and evidence must be provided together")

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


class AnalysisRunEvidenceCollector:
    """只在当前 Gateway analysis run 内保存成功查询的不可变快照。

    对象只由 Gateway 创建并通过 worker runtime context 注入；不属于图状态、事件或回执。
    结果数量与总字节数均有上限，且快照只含规范 evidence 与有界 JSON 结果。
    """

    __slots__ = ("__principal_id", "__thread_id", "__run_id", "__entries", "__snapshot_bytes", "__lock")

    def __init__(self, *, principal_id: str, thread_id: str, run_id: str) -> None:
        if (
            not isinstance(principal_id, str)
            or not principal_id
            or principal_id != principal_id.strip()
            or principal_id == "default"
            or not isinstance(thread_id, str)
            or not _SAFE_RUN_ID.fullmatch(thread_id)
            or not isinstance(run_id, str)
            or not _SAFE_RUN_ID.fullmatch(run_id)
        ):
            raise ValueError("analysis_evidence_unavailable")
        self.__principal_id = principal_id
        self.__thread_id = thread_id
        self.__run_id = run_id
        self.__entries: dict[str, tuple[AnalyticsQueryToolResult, int]] = {}
        self.__snapshot_bytes = 0
        self.__lock = Lock()

    def matches(self, principal_id: str, thread_id: str, run_id: str) -> bool:
        """确认调用仍处于签发此 collector 的唯一 owner/thread/run。"""

        return (principal_id, thread_id, run_id) == (self.__principal_id, self.__thread_id, self.__run_id)

    def record_success(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        result: AnalyticsQueryToolResult,
    ) -> bool:
        """仅登记与规范 evidence 精确对应的成功或有界截断结果。"""

        if not self.matches(principal_id, thread_id, run_id) or not isinstance(result, AnalyticsQueryToolResult):
            return False
        evidence = result.evidence
        evidence_payload = evidence.to_payload() if isinstance(evidence, AnalyticsQueryEvidence) else {}
        if (
            evidence is None
            or result.code not in {ExecutionDecisionCode.EXECUTED.value, ExecutionDecisionCode.RESULT_LIMIT_REACHED.value}
            or evidence.decision_code != result.code
            or evidence.row_count != len(result.rows)
            or evidence.truncated != result.truncated
            or evidence.result_digest != compute_result_digest(result.columns, result.rows)
            or evidence.evidence_id != _sha256(canonical_json({key: value for key, value in evidence_payload.items() if key != "evidence_id"}))
        ):
            return False

        snapshot_bytes = len(canonical_json({"columns": list(result.columns), "rows": [list(row) for row in result.rows]}).encode("utf-8"))
        if snapshot_bytes != evidence.byte_count or snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
            return False

        with self.__lock:
            existing = self.__entries.get(evidence.evidence_id)
            if existing is not None:
                return existing[0] == result
            if len(self.__entries) >= MAX_ANALYSIS_EVIDENCE_PER_RUN or self.__snapshot_bytes + snapshot_bytes > MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES:
                return False
            self.__entries[evidence.evidence_id] = (result, snapshot_bytes)
            self.__snapshot_bytes += snapshot_bytes
        return True

    def resolve_successful_queries(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[AnalyticsQueryToolResult, ...] | None:
        """按报告请求顺序解析本 run 的全部成功快照；缺一项即整体拒绝。"""

        if (
            not self.matches(principal_id, thread_id, run_id)
            or not isinstance(evidence_ids, tuple)
            or not evidence_ids
            or len(evidence_ids) > MAX_ANALYSIS_EVIDENCE_PER_RUN
            or any(not isinstance(evidence_id, str) for evidence_id in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids)
        ):
            return None
        with self.__lock:
            entries = tuple(self.__entries.get(evidence_id) for evidence_id in evidence_ids)
        if any(entry is None for entry in entries):
            return None
        return tuple(entry[0] for entry in entries if entry is not None)


def create_analysis_run_evidence_collector(*, principal_id: str, thread_id: str, run_id: str) -> AnalysisRunEvidenceCollector:
    """创建绑定单个 Gateway analysis run 的私有 evidence collector。"""

    return AnalysisRunEvidenceCollector(principal_id=principal_id, thread_id=thread_id, run_id=run_id)
