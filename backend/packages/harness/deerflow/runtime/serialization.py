"""Canonical serialization for LangChain / LangGraph objects.

Provides a single source of truth for converting LangChain message
objects, Pydantic models, and LangGraph state dicts into plain
JSON-serialisable Python structures.

Consumers: ``deerflow.runtime.runs.worker`` (SSE publishing) and
``app.gateway.routers.threads`` (REST responses).
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

_ANALYTICS_QUERY_TOOL = "query_business_data"
_ANALYTICS_RESULT_FALLBACK_CODE = "analytics_result_unavailable"
_SAFE_ANALYTICS_CODES = frozenset(
    {
        "analytics_unavailable",
        "invalid_request",
        "approved",
        "datasource_not_accessible",
        "schema_unavailable",
        "policy_unavailable",
        "prepared_query_mismatch",
        "analysis_error",
        "correlated_subquery_not_allowed",
        "unknown_relation",
        "relation_not_allowed",
        "unknown_column",
        "column_not_allowed",
        "function_not_allowed",
        "sensitive_column",
        "cross_schema",
        "cartesian_join",
        "approval_required",
        "empty_sql",
        "parse_error",
        "multiple_statements",
        "unsupported_statement",
        "forbidden_operation",
        "comment_not_allowed",
        "wildcard_projection",
        "dangerous_function",
        "offset_not_allowed",
        "non_literal_limit",
        "invalid_limit",
        "unbound_parameter",
        "limit_applied",
        "limit_reduced",
        "complex_query",
        "plan_created",
        "plan_unavailable",
        "plan_store_unavailable",
        "audit_unavailable",
        "authorization_stale",
        "datasource_unavailable",
        "secret_unavailable",
        "explain_rejected",
        "cost_limit_exceeded",
        "unsupported_identifier_mode",
        "execution_timeout",
        "result_limit_reached",
        "unsupported_result_type",
        "database_unavailable",
        "executed",
    }
)
_ANALYTICS_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _analytics_tool_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str):
        return name
    function = value.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    return None


def _collect_analytics_tool_call_names(value: Any, tool_names: dict[str, str]) -> None:
    if isinstance(value, dict):
        message_type = value.get("type")
        if isinstance(message_type, str) and message_type in {"ai", "AIMessage", "AIMessageChunk"}:
            additional_kwargs = value.get("additional_kwargs")
            for key in ("tool_calls", "invalid_tool_calls", "tool_call_chunks"):
                calls = value.get(key)
                if isinstance(calls, list):
                    for call in calls:
                        tool_id = call.get("id") if isinstance(call, dict) else None
                        tool_name = _analytics_tool_name(call)
                        if isinstance(tool_id, str) and tool_id and isinstance(tool_name, str):
                            tool_names[tool_id] = tool_name
            if isinstance(additional_kwargs, dict):
                raw_calls = additional_kwargs.get("tool_calls")
                if isinstance(raw_calls, list):
                    for call in raw_calls:
                        tool_id = call.get("id") if isinstance(call, dict) else None
                        tool_name = _analytics_tool_name(call)
                        if isinstance(tool_id, str) and tool_id and isinstance(tool_name, str):
                            tool_names[tool_id] = tool_name
                raw_call = additional_kwargs.get("function_call")
                if isinstance(raw_call, dict):
                    tool_id = raw_call.get("id")
                    tool_name = _analytics_tool_name(raw_call)
                    if isinstance(tool_id, str) and tool_id and isinstance(tool_name, str):
                        tool_names[tool_id] = tool_name
        for child in value.values():
            _collect_analytics_tool_call_names(child, tool_names)
    elif isinstance(value, list):
        for child in value:
            _collect_analytics_tool_call_names(child, tool_names)


def _is_analytics_call(call: Any, tool_names: dict[str, str]) -> bool:
    if not isinstance(call, dict):
        return False
    tool_name = _analytics_tool_name(call)
    if tool_name == _ANALYTICS_QUERY_TOOL:
        return True
    tool_id = call.get("id")
    return isinstance(tool_id, str) and tool_names.get(tool_id) == _ANALYTICS_QUERY_TOOL


def _safe_analytics_tool_args(args: Any) -> dict[str, Any] | str:
    was_json_text = isinstance(args, str)
    if was_json_text:
        try:
            args = json.loads(args)
        except (TypeError, ValueError):
            args = None
    safe: dict[str, Any] = {}
    if isinstance(args, dict):
        datasource_id = args.get("datasource_id")
        if isinstance(datasource_id, str) and len(datasource_id) <= 64:
            safe["datasource_id"] = datasource_id
    if was_json_text:
        return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    return safe


def _safe_analytics_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    safe: dict[str, Any] = {}
    for key in ("evidence_id", "query_hash", "plan_digest", "result_digest"):
        candidate = value.get(key)
        if isinstance(candidate, str) and _ANALYTICS_DIGEST.fullmatch(candidate):
            safe[key] = candidate
    for key in ("datasource_id", "schema_version", "policy_version"):
        candidate = value.get(key)
        if isinstance(candidate, str) and 0 < len(candidate) <= 64:
            safe[key] = candidate
    risk = value.get("risk")
    if isinstance(risk, str) and risk in {"low", "medium", "high", "blocked"}:
        safe["risk"] = risk
    for key in ("estimated_rows", "row_count", "byte_count"):
        candidate = value.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
            safe[key] = candidate
    engine_cost = value.get("engine_cost")
    if isinstance(engine_cost, str) and len(engine_cost) <= 128 and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", engine_cost):
        safe["engine_cost"] = engine_cost
    truncated = value.get("truncated")
    if isinstance(truncated, bool):
        safe["truncated"] = truncated
    decision_code = value.get("decision_code")
    if isinstance(decision_code, str) and decision_code in _SAFE_ANALYTICS_CODES:
        safe["decision_code"] = decision_code
    return safe or None


def _project_analytics_result_content(content: Any) -> str:
    if not isinstance(content, str):
        return json.dumps({"code": _ANALYTICS_RESULT_FALLBACK_CODE}, separators=(",", ":"))
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        payload = {"code": _ANALYTICS_RESULT_FALLBACK_CODE}

    code = payload.get("code")
    safe: dict[str, Any] = {"code": code if isinstance(code, str) and code in _SAFE_ANALYTICS_CODES else _ANALYTICS_RESULT_FALLBACK_CODE}
    row_count = payload.get("row_count")
    if isinstance(row_count, int) and not isinstance(row_count, bool) and row_count >= 0:
        safe["row_count"] = row_count
    truncated = payload.get("truncated")
    if isinstance(truncated, bool):
        safe["truncated"] = truncated
    evidence = _safe_analytics_evidence(payload.get("evidence"))
    if evidence is not None:
        safe["evidence"] = evidence
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))


def _project_analytics_message(value: dict[str, Any], tool_names: dict[str, str]) -> dict[str, Any]:
    message_type = value.get("type")
    if isinstance(message_type, str) and message_type in {"ai", "AIMessage", "AIMessageChunk"}:
        for key in ("tool_calls", "invalid_tool_calls", "tool_call_chunks"):
            calls = value.get(key)
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not _is_analytics_call(call, tool_names):
                    continue
                if key == "tool_call_chunks":
                    call["args"] = ""
                elif key == "invalid_tool_calls":
                    call["args"] = ""
                    call["error"] = "invalid_arguments"
                else:
                    call["args"] = _safe_analytics_tool_args(call.get("args"))

        additional_kwargs = value.get("additional_kwargs")
        if isinstance(additional_kwargs, dict):
            raw_calls = additional_kwargs.get("tool_calls")
            if isinstance(raw_calls, list):
                for call in raw_calls:
                    if not _is_analytics_call(call, tool_names):
                        continue
                    function = call.get("function") if isinstance(call, dict) else None
                    if isinstance(function, dict):
                        function["arguments"] = _safe_analytics_tool_args(function.get("arguments"))
                    elif isinstance(call, dict):
                        call["args"] = _safe_analytics_tool_args(call.get("args"))
            raw_call = additional_kwargs.get("function_call")
            if isinstance(raw_call, dict) and _analytics_tool_name(raw_call) == _ANALYTICS_QUERY_TOOL:
                raw_call["arguments"] = _safe_analytics_tool_args(raw_call.get("arguments"))
    elif isinstance(message_type, str) and message_type in {"tool", "ToolMessage"}:
        tool_id = value.get("tool_call_id")
        tool_name = value.get("name")
        if tool_name != _ANALYTICS_QUERY_TOOL and not (isinstance(tool_id, str) and tool_names.get(tool_id) == _ANALYTICS_QUERY_TOOL):
            return value
        value["content"] = _project_analytics_result_content(value.get("content"))
        value["artifact"] = None
        additional_kwargs = value.get("additional_kwargs")
        safe_additional_kwargs: dict[str, Any] = {}
        if isinstance(additional_kwargs, dict):
            hidden = additional_kwargs.get("hide_from_ui")
            if isinstance(hidden, bool):
                safe_additional_kwargs["hide_from_ui"] = hidden
            sequence = additional_kwargs.get("deerflow_seq")
            if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0:
                safe_additional_kwargs["deerflow_seq"] = sequence
        value["additional_kwargs"] = safe_additional_kwargs
        value["response_metadata"] = {}
    return value


def _project_analytics_value(value: Any, tool_names: dict[str, str]) -> Any:
    if isinstance(value, dict):
        message_type = value.get("type")
        if isinstance(message_type, str) and message_type in {"ai", "AIMessage", "AIMessageChunk", "tool", "ToolMessage"}:
            return _project_analytics_message(value, tool_names)
        return {key: _project_analytics_value(child, tool_names) for key, child in value.items()}
    if isinstance(value, list):
        return [_project_analytics_value(child, tool_names) for child in value]
    return value


def project_analytics_structured_value(value: Any, *, tool_names: dict[str, str] | None = None) -> Any:
    """在独立序列化副本上投影 Analytics 工具调用与结果字段。"""
    result = deepcopy(serialize_lc_object(value))
    names = dict(tool_names or {})
    _collect_analytics_tool_call_names(result, names)
    return _project_analytics_value(result, names)


def project_analytics_messages(messages: list[Any]) -> list[Any]:
    """在独立消息列表中投影 Analytics 字段，并关联结果调用 ID。"""
    result = deepcopy(serialize_lc_object(messages))
    if not isinstance(result, list):
        return []
    tool_names: dict[str, str] = {}
    projected = []
    for message in result:
        _collect_analytics_tool_call_names(message, tool_names)
        projected.append(_project_analytics_value(message, tool_names))
    return projected


def project_analytics_event_rows(events: list[Any]) -> list[Any]:
    """投影事件行中的 Analytics 消息结构，也兼容已有历史行。"""
    result = deepcopy(serialize_lc_object(events))
    if not isinstance(result, list):
        return []
    names_by_run: dict[str | None, dict[str, str]] = {}
    projected = []
    for event in result:
        run_id = event.get("run_id") if isinstance(event, dict) else None
        scope = run_id if isinstance(run_id, str) else None
        names = names_by_run.setdefault(scope, {})
        _collect_analytics_tool_call_names(event, names)
        projected.append(_project_analytics_value(event, names))
    for event in projected:
        if not isinstance(event, dict) or event.get("event_type") != "subagent.step":
            continue
        run_id = event.get("run_id")
        scope = run_id if isinstance(run_id, str) else None
        tool_names = names_by_run.get(scope, {})
        content = event.get("content")
        if not isinstance(content, dict):
            continue
        if content.get("kind") == "ai":
            calls = content.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if _is_analytics_call(call, tool_names):
                        call["args"] = _safe_analytics_tool_args(call.get("args"))
        elif content.get("kind") == "tool" and content.get("tool_name") == _ANALYTICS_QUERY_TOOL:
            content["text"] = _project_analytics_result_content(content.get("text"))
    return projected


class AnalyticsToolCallChunkProjector:
    """跨消息块在外发副本中只移除 Analytics 参数。

    LangChain 可能只在首个增量携带工具名。后续增量通过稳定消息 ID 与工具
    索引关联。身份未明时只遮盖当前模糊参数，不因无法关联而中止整次 run；
    名称分叉为其他工具后，后续参数仍按普通工具参数保留。
    """

    def __init__(self) -> None:
        self._names_by_index: dict[tuple[tuple[str, ...], str, int], str] = {}
        self._ids_by_index: dict[tuple[tuple[str, ...], str, int], str] = {}

    @staticmethod
    def _message_from_payload(payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict):
            return payload[0]
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _name_state(previous: str | None, delta: Any) -> str | None:
        if previous == "__other_tool__":
            return previous
        if delta is None:
            return previous
        if not isinstance(delta, str) or not delta:
            return previous
        combined = f"{previous}{delta}" if previous and _ANALYTICS_QUERY_TOOL.startswith(previous) else delta
        if combined == _ANALYTICS_QUERY_TOOL:
            return _ANALYTICS_QUERY_TOOL
        if _ANALYTICS_QUERY_TOOL.startswith(combined):
            return combined
        return "__other_tool__"

    def project(self, payload: Any, *, namespace: tuple[str, ...] = ()) -> Any:
        """Return a detached SSE payload with Analytics argument deltas removed."""
        result = deepcopy(payload)
        message = self._message_from_payload(result)
        if message is None or message.get("type") != "AIMessageChunk":
            return result

        message_id = message.get("id")
        chunks = message.get("tool_call_chunks")
        if not isinstance(chunks, list):
            return result

        analytics_ids: set[str] = set()
        has_ambiguous_chunk = False
        tool_names: dict[str, str] = {}
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            index = chunk.get("index")
            stable_index = isinstance(index, int) and not isinstance(index, bool)
            stable_message_id = isinstance(message_id, str) and bool(message_id)
            key = (namespace, message_id, index) if stable_index and stable_message_id else None
            previous = self._names_by_index.get(key) if key is not None else None
            state = self._name_state(previous, chunk.get("name"))
            has_args = bool(chunk.get("args"))
            tool_id = chunk.get("id")

            if state == "__other_tool__":
                if key is not None:
                    self._names_by_index[key] = state
                    self._ids_by_index.pop(key, None)
                continue
            if state is None:
                if has_args:
                    chunk["args"] = ""
                    has_ambiguous_chunk = True
                continue

            # 工具名仍是 Analytics 名称前缀时身份尚未确定；完成判定前不外发参数增量。
            if key is not None:
                self._names_by_index[key] = state
            if state != _ANALYTICS_QUERY_TOOL:
                has_ambiguous_chunk = True
                if has_args:
                    chunk["args"] = ""
                continue

            has_ambiguous_chunk = True
            previous_id = self._ids_by_index.get(key) if key is not None else None
            tool_id = tool_id or previous_id
            if isinstance(tool_id, str) and tool_id:
                analytics_ids.add(tool_id)
                tool_names[tool_id] = _ANALYTICS_QUERY_TOOL
                if key is not None:
                    self._ids_by_index[key] = tool_id
            chunk["args"] = ""

        _project_analytics_message(message, tool_names)

        for field in ("tool_calls", "invalid_tool_calls"):
            calls = message.get(field)
            if not isinstance(calls, list):
                continue
            for call in calls:
                direct_analytics = _is_analytics_call(call, tool_names)
                call_id = call.get("id") if isinstance(call, dict) else None
                if isinstance(call_id, str) and call_id in analytics_ids:
                    direct_analytics = True
                call_name = _analytics_tool_name(call)
                # LangChain 组装中的解析壳可能没有名称或 ID；只遮盖模糊壳，
                # 不把同帧中有明确名称的普通工具参数一起清空。
                if not direct_analytics and not call_name and not call_id and len(calls) == 1 and len(chunks) == 1 and has_ambiguous_chunk:
                    direct_analytics = True
                possible_analytics = isinstance(call_name, str) and call_name != _ANALYTICS_QUERY_TOOL and _ANALYTICS_QUERY_TOOL.startswith(call_name)
                direct_analytics = direct_analytics or possible_analytics
                if not direct_analytics:
                    explicit_other = isinstance(call_name, str) and bool(call_name)
                    if explicit_other or not has_ambiguous_chunk:
                        continue
                    direct_analytics = True
                if field == "invalid_tool_calls":
                    call["args"] = ""
                    call["error"] = "invalid_arguments"
                else:
                    call["args"] = _safe_analytics_tool_args(call.get("args"))

        return result


def serialize_lc_object(obj: Any) -> Any:
    """Recursively serialize a LangChain object to a JSON-serialisable dict."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: serialize_lc_object(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_lc_object(item) for item in obj]
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    # Pydantic v1 / older objects
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    # Interrupt is a __slots__ class — no model_dump/dict/__dict__, so it
    # would reach str() and produce a malformed payload.
    try:
        from langgraph.types import Interrupt
    except ImportError:
        pass
    else:
        if isinstance(obj, Interrupt):
            return serialize_lc_object(
                {
                    "value": obj.value,
                    "id": getattr(obj, "id", None),
                }
            )
    # Last resort
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def serialize_channel_values(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values, stripping internal LangGraph keys.

    Only ``__pregel_*`` keys are removed — ``__interrupt__`` is deliberately
    preserved so the LangGraph SDK can detect interrupt events from values
    chunks (see issue #3595).
    """
    result: dict[str, Any] = {}
    for key, value in channel_values.items():
        if key.startswith("__pregel_"):
            continue
        result[key] = serialize_lc_object(value)
    return result


def strip_data_url_image_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove ``data:``-scheme ``image_url`` blocks from *hide_from_ui* messages.

    The history and run-wait endpoints return checkpoint-persisted messages to
    the frontend.  ``ViewImageMiddleware`` now keeps its base64 image payloads
    inside the model request, but threads checkpointed by earlier versions still
    hold them in ``hide_from_ui`` human messages — these are internal model
    context and must not be sent over the wire (huge response bodies, no UI
    value).

    Only content blocks of type ``image_url`` whose URL starts with ``data:``
    are stripped.  Text blocks, ``https://`` image URLs, and non-hidden
    messages are left untouched so that message ordering and count are
    preserved.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            result.append(msg)
            continue

        # Only touch messages explicitly flagged as hidden from the UI.
        additional_kwargs = msg.get("additional_kwargs")
        if not (isinstance(additional_kwargs, dict) and additional_kwargs.get("hide_from_ui") is True):
            result.append(msg)
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue

        # Filter out image_url blocks with data: scheme.
        filtered = [block for block in content if not (isinstance(block, dict) and block.get("type") == "image_url" and isinstance(block.get("image_url"), dict) and str(block["image_url"].get("url", "")).startswith("data:"))]
        result.append({**msg, "content": filtered})
    return result


def serialize_channel_values_for_api(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values and strip base64 image data from messages.

    Convenience wrapper combining :func:`serialize_channel_values` with
    :func:`strip_data_url_image_blocks`.  Use this in all REST endpoints
    that return channel values to the frontend so that ``data:``-scheme
    base64 image payloads are never sent over the wire.
    """
    result = serialize_channel_values(channel_values)
    if isinstance(result.get("messages"), list):
        result["messages"] = project_analytics_messages(result["messages"])
        result["messages"] = strip_data_url_image_blocks(result["messages"])
    return result


def serialize_messages_tuple(obj: Any) -> Any:
    """Serialize a messages-mode tuple ``(chunk, metadata)``."""
    if isinstance(obj, tuple) and len(obj) == 2:
        chunk, metadata = obj
        return [project_analytics_structured_value(chunk), metadata if isinstance(metadata, dict) else {}]
    return project_analytics_structured_value(obj)


def serialize(obj: Any, *, mode: str = "") -> Any:
    """Serialize LangChain objects with mode-specific handling.

    * ``messages`` — obj is ``(message_chunk, metadata_dict)``
    * ``values`` — obj is the full state dict; ``__pregel_*`` keys stripped and
      base64 ``data:`` image blocks dropped from hide_from_ui messages
    * everything else — recursive ``model_dump()`` / ``dict()`` fallback
    """
    if mode == "messages":
        return serialize_messages_tuple(obj)
    if mode == "values":
        # ``values`` snapshots stream the full state to the frontend, so they
        # must drop base64 image payloads the same way the REST endpoints do.
        return serialize_channel_values_for_api(obj) if isinstance(obj, dict) else serialize_lc_object(obj)
    return serialize_lc_object(obj)
