from __future__ import annotations

from typing import Any

from .scanner import is_sensitive_workspace_path
from .types import WORKSPACE_CHANGES_EVENT_TYPE, WORKSPACE_CHANGES_METADATA_KEY

EMPTY_SUMMARY = {
    "created": 0,
    "modified": 0,
    "deleted": 0,
    "symlink_created": 0,
    "additions": 0,
    "deletions": 0,
    "truncated": False,
}


async def get_workspace_changes_response(
    event_store: Any,
    thread_id: str,
    run_id: str,
    *,
    include_files: bool = True,
    include_diff: bool = True,
) -> dict[str, Any]:
    events = await event_store.list_events(
        thread_id,
        run_id,
        event_types=[WORKSPACE_CHANGES_EVENT_TYPE],
        limit=10,
    )
    if not events:
        return _empty_response()

    payload = project_workspace_changes_payload(_extract_workspace_changes_payload(events[-1]))
    if not isinstance(payload, dict):
        return _empty_response()

    response = dict(payload)
    response["available"] = True
    response.setdefault("summary", dict(EMPTY_SUMMARY))
    if include_files:
        response.setdefault("files", [])
        if not include_diff:
            response["files"] = [_without_diff(file) for file in response["files"]]
    else:
        response["files"] = []
    return response


def project_workspace_changes_payload(payload: Any) -> Any:
    """屏蔽历史敏感文件 diff，避免旧事件继续外发查询结果正文。"""
    if not isinstance(payload, dict):
        return payload

    projected = dict(payload)
    files = payload.get("files")
    if not isinstance(files, list):
        return projected

    projected_files = []
    removed_additions = 0
    removed_deletions = 0
    for file in files:
        path = file.get("path") if isinstance(file, dict) else None
        if not isinstance(path, str) or not is_sensitive_workspace_path(path):
            projected_files.append(file)
            continue

        safe_file = dict(file)
        safe_file.update(sensitive=True, diff="", diff_unavailable_reason="sensitive")
        for key in ("additions", "deletions"):
            value = safe_file.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                if key == "additions":
                    removed_additions += max(0, value)
                else:
                    removed_deletions += max(0, value)
                safe_file[key] = 0
        projected_files.append(safe_file)

    projected["files"] = projected_files
    summary = payload.get("summary")
    if isinstance(summary, dict) and (removed_additions or removed_deletions):
        safe_summary = dict(summary)
        for key, removed in (("additions", removed_additions), ("deletions", removed_deletions)):
            total = safe_summary.get(key)
            if isinstance(total, int) and not isinstance(total, bool):
                safe_summary[key] = max(0, total - removed)
        projected["summary"] = safe_summary
    return projected


def _empty_response() -> dict[str, Any]:
    return {
        "available": False,
        "version": 1,
        "summary": dict(EMPTY_SUMMARY),
        "files": [],
        "limits": {},
    }


def _extract_workspace_changes_payload(event: dict[str, Any]) -> Any:
    metadata = event.get("metadata") or {}
    if isinstance(metadata, dict) and WORKSPACE_CHANGES_METADATA_KEY in metadata:
        return metadata[WORKSPACE_CHANGES_METADATA_KEY]
    content = event.get("content")
    if isinstance(content, dict):
        return content
    return None


def _without_diff(file: Any) -> Any:
    if not isinstance(file, dict):
        return file
    sanitized = dict(file)
    sanitized["diff"] = ""
    return sanitized
