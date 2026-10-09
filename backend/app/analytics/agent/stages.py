"""受控分析阶段的 run-scoped live 与持久事件能力。"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from typing import Any

from langgraph.config import get_stream_writer

from deerflow.utils.custom_events import aemit_custom_event

ANALYSIS_STAGE_EVENT_TYPE = "analysis_stage"
ANALYSIS_STAGE_EVENT_VERSION = 1
ANALYSIS_STAGE_STORE_EVENT_TYPE = "analysis.stage"
ANALYSIS_STAGE_CATEGORY = "analysis"
MAX_ANALYSIS_STAGE_EVENTS = 128
STAGES = frozenset({"workflow", "catalog", "sql", "authorization", "execution", "data", "writer", "reviewer", "publish"})
STATUSES = frozenset({"running", "succeeded", "failed", "blocked", "cancelled"})
RISK_VALUES = frozenset({"LOW", "MEDIUM", "HIGH", "BLOCKED"})
FAILURE_CODES = frozenset(
    {
        "ok",
        "unavailable",
        "invalid_request",
        "invalid_response",
        "numeric_validation_failed",
        "attempt_limit",
        "input_too_large",
        "policy_denied",
        "cost_limit",
        "query_failed",
        "query_timeout",
        "result_limit_reached",
        "evidence_unavailable",
        "review_rejected",
        "report_conflict",
        "cancelled",
    }
)
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_EVIDENCE_ID = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "type",
        "version",
        "run_id",
        "seq",
        "stage",
        "status",
        "duration_ms",
        "row_count",
        "byte_count",
        "input_tokens",
        "output_tokens",
        "risk",
        "cached",
        "code",
        "evidence_ids",
    }
)
_INTEGER_LIMITS = {
    "seq": (1, 2_147_483_647),
    "duration_ms": (0, 86_400_000),
    "row_count": (0, 1_000_000),
    "byte_count": (0, 16_777_216),
    "input_tokens": (0, 10_000_000),
    "output_tokens": (0, 10_000_000),
}
_BLOCKED_CODES = frozenset(
    {
        "invalid_request",
        "attempt_limit",
        "input_too_large",
        "policy_denied",
        "cost_limit",
        "review_rejected",
        "report_conflict",
    }
)
_CODE_ALIASES = {
    "plan_created": "ok",
    "approved": "ok",
    "executed": "ok",
    "published": "ok",
    "existing": "ok",
    "cost_limit_exceeded": "cost_limit",
    "execution_timeout": "query_timeout",
    "explain_rejected": "policy_denied",
    "approval_required": "policy_denied",
    "datasource_not_accessible": "policy_denied",
    "relation_not_allowed": "policy_denied",
    "column_not_allowed": "policy_denied",
    "function_not_allowed": "policy_denied",
    "sensitive_column": "policy_denied",
    "cross_schema": "policy_denied",
    "cartesian_join": "policy_denied",
    "policy_unavailable": "unavailable",
    "schema_unavailable": "unavailable",
    "datasource_unavailable": "unavailable",
    "secret_unavailable": "unavailable",
    "plan_unavailable": "unavailable",
    "plan_store_unavailable": "unavailable",
    "authorization_stale": "unavailable",
    "audit_unavailable": "unavailable",
    "database_unavailable": "query_failed",
    "unsupported_result_type": "invalid_response",
}


class AnalysisStageError(RuntimeError):
    """持久或 live 阶段事件不能安全完成时使用的稳定错误。"""

    def __init__(self) -> None:
        super().__init__("analysis_stage_unavailable")


def stable_stage_code(value: object, *, fallback: str = "unavailable") -> str:
    """把内部决定码压到合同白名单，未知值统一降为 unavailable。"""

    candidate = getattr(value, "value", value)
    if type(candidate) is not str:
        return fallback
    candidate = _CODE_ALIASES.get(candidate, candidate)
    return candidate if candidate in FAILURE_CODES else fallback


def stage_status_for_code(code: object) -> str:
    stable = stable_stage_code(code)
    if stable == "cancelled":
        return "cancelled"
    if stable in _BLOCKED_CODES:
        return "blocked"
    if stable == "ok" or stable == "result_limit_reached":
        return "succeeded"
    return "failed"


def validate_analysis_stage_payload(value: object, *, expected_run_id: str | None = None) -> dict[str, Any]:
    """校验并投影闭合合同字段，拒绝附带 SQL、行数据或自由文本。"""

    if type(value) is not dict or not set(value).issubset(_FIELDS):
        raise ValueError("analysis_stage_invalid")
    required = {"type", "version", "run_id", "seq", "stage", "status"}
    if not required.issubset(value):
        raise ValueError("analysis_stage_invalid")
    if value["type"] != ANALYSIS_STAGE_EVENT_TYPE or type(value["version"]) is not int or value["version"] != ANALYSIS_STAGE_EVENT_VERSION:
        raise ValueError("analysis_stage_invalid")
    run_id = value["run_id"]
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id) or (expected_run_id is not None and run_id != expected_run_id):
        raise ValueError("analysis_stage_invalid")
    if type(value["stage"]) is not str or value["stage"] not in STAGES or type(value["status"]) is not str or value["status"] not in STATUSES:
        raise ValueError("analysis_stage_invalid")
    for name, (minimum, maximum) in _INTEGER_LIMITS.items():
        if name in value and (type(value[name]) is not int or not minimum <= value[name] <= maximum):
            raise ValueError("analysis_stage_invalid")
    if "risk" in value and (type(value["risk"]) is not str or value["risk"] not in RISK_VALUES):
        raise ValueError("analysis_stage_invalid")
    if "cached" in value and type(value["cached"]) is not bool:
        raise ValueError("analysis_stage_invalid")
    if "code" in value and (type(value["code"]) is not str or value["code"] not in FAILURE_CODES):
        raise ValueError("analysis_stage_invalid")
    if "evidence_ids" in value:
        evidence_ids = value["evidence_ids"]
        if type(evidence_ids) is not list or len(evidence_ids) > 20 or any(type(item) is not str or not _EVIDENCE_ID.fullmatch(item) for item in evidence_ids):
            raise ValueError("analysis_stage_invalid")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("analysis_stage_invalid")
    return {key: value[key] for key in value}


class AnalysisStageEmitter:
    """只绑定一个认证 run，先持久化再发送相同的 custom payload。"""

    __slots__ = (
        "_principal_id",
        "_thread_id",
        "_run_id",
        "_event_store",
        "_lock",
        "_writer",
        "_seq",
        "_count",
        "_active",
        "_started_at",
        "_workflow_started",
        "_closed",
        "_failed",
        "_storage_failed",
    )

    def __init__(self, *, principal_id: str, thread_id: str, run_id: str, event_store: Any) -> None:
        if type(principal_id) is not str or not principal_id or principal_id != principal_id.strip() or principal_id == "default":
            raise ValueError("analysis_stage_unavailable")
        if type(thread_id) is not str or not _RUN_ID.fullmatch(thread_id) or type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise ValueError("analysis_stage_unavailable")
        if event_store is None or not callable(getattr(event_store, "put", None)):
            raise ValueError("analysis_stage_unavailable")
        self._principal_id = principal_id
        self._thread_id = thread_id
        self._run_id = run_id
        self._event_store = event_store
        self._lock = asyncio.Lock()
        self._writer: Callable[[Any], None] | None = None
        self._seq = 0
        self._count = 0
        self._active: dict[str, int] = {}
        self._started_at: dict[str, list[float]] = {}
        self._workflow_started = False
        self._closed = False
        self._failed = False
        self._storage_failed = False

    def matches(self, principal_id: str, thread_id: str, run_id: str) -> bool:
        return (principal_id, thread_id, run_id) == (self._principal_id, self._thread_id, self._run_id)

    async def emit(
        self,
        *,
        principal_id: str,
        thread_id: str,
        run_id: str,
        writer: Callable[[Any], None],
        stage: str,
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        if not self.matches(principal_id, thread_id, run_id) or not callable(writer):
            raise AnalysisStageError
        if type(stage) is not str or stage not in STAGES or type(status) is not str or status not in STATUSES or set(fields) - (_FIELDS - {"type", "version", "run_id", "seq", "stage", "status"}):
            raise AnalysisStageError
        async with self._lock:
            if self._closed or self._failed:
                raise AnalysisStageError
            self._writer = writer
            if stage != "workflow" and not self._workflow_started:
                await self._emit_locked(writer=writer, stage="workflow", status="running", fields={})
                self._workflow_started = True
            payload = await self._emit_locked(writer=writer, stage=stage, status=status, fields=fields)
            if stage == "workflow" and status == "running":
                self._workflow_started = True
            return payload

    async def finish(self, *, status: str) -> tuple[dict[str, Any], ...]:
        """先持久收束活动阶段，再把终态 payload 交给仍有效的 worker bridge。"""

        if self._closed:
            return ()
        if self._storage_failed:
            raise AnalysisStageError
        if not self._active.get("workflow", 0):
            if self._failed:
                raise AnalysisStageError
            return ()
        final_status = {
            "success": "succeeded",
            "succeeded": "succeeded",
            "interrupted": "cancelled",
            "cancelled": "cancelled",
            "blocked": "blocked",
        }.get(status, "failed")
        if self._failed and final_status == "succeeded":
            final_status = "failed"
        async with self._lock:
            if self._closed:
                return ()
            if self._storage_failed:
                raise AnalysisStageError
            unresolved = tuple((stage, count) for stage, count in self._active.items() if stage != "workflow" and count > 0)
            terminal_for_open = "failed" if final_status == "succeeded" else final_status
            finalization_failed = False
            terminal_payloads = []
            for stage, count in unresolved:
                for _ in range(count):
                    code = "cancelled" if terminal_for_open == "cancelled" else "unavailable"
                    try:
                        terminal_payloads.append(await self._emit_locked(writer=None, stage=stage, status=terminal_for_open, fields={"code": code}, emit_live=False))
                    except AnalysisStageError:
                        finalization_failed = True
                        if self._storage_failed:
                            raise
            workflow_status = "failed" if unresolved and final_status == "succeeded" else final_status
            if self._failed and workflow_status == "succeeded":
                workflow_status = "failed"
            workflow_code = None if workflow_status == "succeeded" else ("cancelled" if workflow_status == "cancelled" else "unavailable")
            fields = {"code": workflow_code} if workflow_code is not None else {}
            if self._active.get("workflow", 0):
                try:
                    terminal_payloads.append(await self._emit_locked(writer=None, stage="workflow", status=workflow_status, fields=fields, emit_live=False))
                except AnalysisStageError:
                    finalization_failed = True
                    if self._storage_failed:
                        raise
            if finalization_failed or self._failed:
                raise AnalysisStageError
            return tuple(terminal_payloads)

    async def _emit_locked(
        self,
        *,
        writer: Callable[[Any], None] | None,
        stage: str,
        status: str,
        fields: dict[str, Any],
        emit_live: bool = True,
    ) -> dict[str, Any]:
        if self._count >= MAX_ANALYSIS_STAGE_EVENTS or self._seq >= 2_147_483_647:
            self._failed = True
            raise AnalysisStageError
        if status == "running" and stage != "workflow" and self._active.get(stage, 0) >= MAX_ANALYSIS_STAGE_EVENTS:
            self._failed = True
            raise AnalysisStageError
        if status != "running" and self._active.get(stage, 0) <= 0:
            self._failed = True
            raise AnalysisStageError
        duration = None
        starts = self._started_at.get(stage)
        if status != "running" and starts:
            duration = max(0, min(86_400_000, int((time.monotonic() - starts[-1]) * 1000)))
        self._seq += 1
        payload = {
            "type": ANALYSIS_STAGE_EVENT_TYPE,
            "version": ANALYSIS_STAGE_EVENT_VERSION,
            "run_id": self._run_id,
            "seq": self._seq,
            "stage": stage,
            "status": status,
        }
        if duration is not None and "duration_ms" not in fields:
            payload["duration_ms"] = duration
        payload.update(fields)
        try:
            payload = validate_analysis_stage_payload(payload, expected_run_id=self._run_id)
        except Exception as exc:
            self._failed = True
            raise AnalysisStageError from exc
        try:
            async with asyncio.timeout(5):
                await self._event_store.put(
                    thread_id=self._thread_id,
                    run_id=self._run_id,
                    event_type=ANALYSIS_STAGE_STORE_EVENT_TYPE,
                    category=ANALYSIS_STAGE_CATEGORY,
                    content="",
                    metadata=payload,
                )
        except asyncio.CancelledError:
            self._failed = True
            self._storage_failed = True
            raise
        except Exception as exc:
            self._failed = True
            self._storage_failed = True
            raise AnalysisStageError from exc
        self._count += 1
        if status == "running":
            self._active[stage] = self._active.get(stage, 0) + 1
            self._started_at.setdefault(stage, []).append(time.monotonic())
        else:
            self._active[stage] -= 1
            if not self._active[stage]:
                self._active.pop(stage)
            if starts:
                starts.pop()
                if not starts:
                    self._started_at.pop(stage, None)
        self._seq = payload["seq"]
        if emit_live:
            if not callable(writer):
                self._failed = True
                raise AnalysisStageError
            try:
                async with asyncio.timeout(5):
                    await aemit_custom_event(payload, writer=writer)
            except asyncio.CancelledError:
                self._failed = True
                raise
            except Exception as exc:
                self._failed = True
                raise AnalysisStageError from exc
        return payload

    def close(self) -> None:
        self._closed = True
        self._writer = None
        self._active.clear()
        self._started_at.clear()


async def emit_role_stage(
    roles: Any,
    *,
    principal_id: str,
    thread_id: str,
    run_id: str,
    stage: str,
    status: str,
    **fields: Any,
) -> dict[str, Any] | None:
    """只从当前 LangGraph tool 调用上下文取得 live writer。"""

    if not bool(getattr(roles, "has_stage_emitter", False)):
        return None
    try:
        writer = get_stream_writer()
    except Exception as exc:
        raise AnalysisStageError from exc
    return await roles.emit_stage(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        writer=writer,
        stage=stage,
        status=status,
        **fields,
    )


__all__ = [
    "ANALYSIS_STAGE_CATEGORY",
    "ANALYSIS_STAGE_EVENT_TYPE",
    "ANALYSIS_STAGE_STORE_EVENT_TYPE",
    "AnalysisStageEmitter",
    "AnalysisStageError",
    "MAX_ANALYSIS_STAGE_EVENTS",
    "emit_role_stage",
    "stage_status_for_code",
    "stable_stage_code",
    "validate_analysis_stage_payload",
]
