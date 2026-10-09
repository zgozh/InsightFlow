"""Lead-only 的报告发布工具（Phase 4 §6）。

`publish_analysis_report` 只在 `analytics_analysis_reports` 里登记一行索引，**不读 artifact
内容**。它的模型可见参数只有三个：

- `title`：报告标题；
- `artifact_path`：`/mnt/user-data/outputs/` 下的相对目标；
- `evidence_ids`：本次分析引用的 evidence 摘要。

principal / thread / run 全部从受信 runtime 派生（见 `runtime.trusted_principal` 与
`runtime.trusted_thread_run`）。模型**没有** principal/thread/run/status/created_at/幂等键参数，
因此既不能把报告挂到别人名下，也不能伪造"某个不存在的 run 发布了报告"。

工具结果同样只回白名单字段：**不含** principal/thread/run，也不含任何 artifact 内容。这与
Phase 2C2 的 HTTP DTO 是两个不同的投影面——HTTP 面是"我自己的索引列表"，需要 thread_id 才能
打开对应分析；模型面不需要这些身份字段。

为什么顺序是"先 `present_files` 成功、再发布"：`present_files` 成功证明 artifact 真的进了
sandbox 的 outputs，此时登记索引才有意义。发布失败必须如实报告，绝不能把未登记的报告说成
已保存。
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.analytics.agent.evidence import ANALYSIS_EVIDENCE_UNAVAILABLE, canonical_json
from app.analytics.agent.evidence_bridge import DurableAnalysisRunEvidenceCollector
from app.analytics.agent.reviewer import AnalysisReportReviewerCapability, log_reviewer_failure_stage
from app.analytics.agent.roles import AnalysisRoleError, AnalysisRolesCapability, role_usage_fields
from app.analytics.agent.runtime import get_bound_analytics_services, trusted_principal, trusted_thread_run
from app.analytics.agent.stages import AnalysisStageError, emit_role_stage, stable_stage_code, stage_status_for_code
from app.analytics.application.metric_service import MetricService
from app.analytics.domain import AnalysisReport, ReportPublishCode, ReportStatus
from app.analytics.domain.verified_report import MAX_VERIFIED_REPORT_BYTES, render_verified_report
from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY, ANALYSIS_REPORT_WRITER_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
from deerflow.tools.types import Runtime

PUBLISH_REPORT_TOOL_NAME = "publish_analysis_report"

_UNAVAILABLE = "analytics_unavailable"
_INVALID_REQUEST = "invalid_request"
WRITE_ANALYSIS_REPORT_TOOL_NAME = "write_analysis_report"
_REPORT_SUCCESS_CODES = frozenset({ReportPublishCode.PUBLISHED, ReportPublishCode.EXISTING})
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FIXED_REPORT_TITLE = "经营分析报告"
_MAX_ANALYSIS_REQUEST_CHARACTERS = 8_192


def _payload(code: str, **extra: object) -> str:
    return canonical_json({"code": code, **extra})


def _report_view(report: AnalysisReport) -> dict:
    """模型可见的报告投影：身份字段与内部列一律不出现在这里。"""

    return {
        "id": report.id,
        "title": report.title,
        "artifact_path": report.artifact_path,
        "status": report.status.value,
        "evidence_ids": list(report.evidence_ids),
        "created_at": report.created_at.isoformat(),
    }


def _append_metric_snapshot(markdown: str, metrics: tuple) -> str:
    """把本次授权目录作为独立来源元数据追加到确定性报告。"""

    lines = [markdown.rstrip(), "", "## 可用指标目录快照", ""]
    if not metrics:
        lines.extend(
            [
                "未登记可用指标口径，本报告仅核对结果单元格与固定算式；这不证明 SQL 的业务语义或总体完整性。",
                "",
            ]
        )
    else:
        snapshot = [
            {
                "key": metric.key,
                "version": metric.version,
                "name": metric.name,
                "description": metric.description,
                "expression": metric.expression,
                "dimensions": list(metric.dimensions),
                "status": metric.status.value,
            }
            for metric in metrics
        ]
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        lines.extend("    " + line for line in encoded.splitlines())
        lines.extend(
            [
                "",
                "此快照记录本次可见的登记定义，不表示目录中的所有项目都参与了算式，也不证明 SQL 语义与业务定义一致。",
                "",
            ]
        )
    report = "\n".join(lines)
    if len(report.encode("utf-8", errors="strict")) > MAX_VERIFIED_REPORT_BYTES:
        raise ValueError("analysis_report_too_large")
    return report


async def _emit_stage(
    roles: AnalysisRolesCapability,
    principal_id: str,
    thread_id: str,
    run_id: str,
    stage: str,
    status: str,
    **fields: object,
) -> None:
    await emit_role_stage(
        roles,
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        stage=stage,
        status=status,
        **fields,
    )


@tool(PUBLISH_REPORT_TOOL_NAME, parse_docstring=True)
async def publish_analysis_report(title: str, artifact_path: str, evidence_ids: list[str], runtime: Runtime) -> str:
    """Register a finished analysis report in the report index.

    Call this only after the report file exists under
    `/mnt/user-data/outputs/` and `present_files` has delivered it. This tool
    records an index entry (title, path, evidence ids) for the signed-in user's
    current analysis session; it does not read, upload or copy the file, and it
    cannot publish on behalf of anyone else. Pass the evidence ids you copied
    from `query_business_data` results, one per number the report relies on.

    Args:
        title: Short report title shown in the report list.
        artifact_path: Path of the report file under `/mnt/user-data/outputs/`.
        evidence_ids: Evidence ids the report's numbers are based on.
        runtime: Injected tool runtime carrying the authenticated user context.

    Returns:
        A JSON object with a stable `code` (`published`, `existing` or
        `report_conflict`) and the registered index entry.
    """

    services = get_bound_analytics_services()
    if services is None:
        return _payload(_UNAVAILABLE)
    principal_id = trusted_principal(runtime)
    identity = trusted_thread_run(runtime)
    if principal_id is None or identity is None:
        return _payload(_UNAVAILABLE)
    thread_id, run_id = identity

    try:
        publication = await services.publish_report.execute(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            title=title,
            artifact_path=artifact_path,
            evidence_ids=evidence_ids,
        )
    except (ValueError, TypeError):
        # 客户端/模型输入不满足领域不变量：给稳定 code，不回显原值。
        return _payload(_INVALID_REQUEST)
    except Exception:  # noqa: BLE001 - 存储失败同样脱敏，绝不外泄驱动异常文本
        return _payload(_UNAVAILABLE)

    return _payload(publication.code.value, report=_report_view(publication.report))


@tool(WRITE_ANALYSIS_REPORT_TOOL_NAME, parse_docstring=True)
async def write_analysis_report(
    title: str,
    markdown: str,
    evidence_ids: list[str],
    runtime: Runtime,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command | str:
    """把不可信草稿转换为固定模板报告，再登记当前 analysis run。

    Gateway 能力固定所有者、线程、run、存储根目录和文件名。title 与 markdown 仅作为不可信请求描述。
    服务端读取耐久查询快照，调用固定数据分析和布局角色并确定性重建报告，再交由独立零工具 Reviewer。
    模型提供的正文、数字和标题不会直接进入发布文件或索引；安全回执不包含正文或内部身份。

    Args:
        title: 最多 200 字符的请求描述，不会作为发布标题。
        markdown: 最多 8192 字符的不可信分析目标或草稿。
        evidence_ids: 报告结论所依赖的 evidence 标识。
        runtime: 注入认证身份与 Gateway 能力的运行时。
        tool_call_id: 用于构造安全工具回执的注入调用标识。

    Returns:
        文件和报告索引均可用时返回安全回执；失败时只返回稳定错误码，且不生成 artifact 回执。
    """

    services = get_bound_analytics_services()
    if services is None:
        return _payload(_UNAVAILABLE)
    principal_id = trusted_principal(runtime)
    identity = trusted_thread_run(runtime)
    context = getattr(runtime, "context", None)
    if principal_id is None or identity is None or not isinstance(context, Mapping):
        return _payload(_UNAVAILABLE)
    thread_id, run_id = identity

    writer = context.get(ANALYSIS_REPORT_WRITER_CONTEXT_KEY)
    write_markdown = getattr(writer, "write_markdown", None)
    if not callable(getattr(writer, "matches", None)) or not callable(write_markdown) or not writer.matches(principal_id, thread_id, run_id):
        return _payload(_UNAVAILABLE)
    roles = context.get(ANALYSIS_ROLES_CONTEXT_KEY)
    if not isinstance(roles, AnalysisRolesCapability) or not roles.matches(principal_id, thread_id, run_id):
        return _payload("analysis_role_unavailable")
    evidence_collector = context.get(ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY)
    if not isinstance(evidence_collector, DurableAnalysisRunEvidenceCollector) or not evidence_collector.matches(principal_id, thread_id, run_id):
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    if not isinstance(tool_call_id, str) or not tool_call_id or tool_call_id != tool_call_id.strip():
        return _payload(_INVALID_REQUEST)
    if type(title) is not str or not title or title != title.strip() or len(title) > 200 or type(markdown) is not str or type(evidence_ids) is not list:
        return _payload(_INVALID_REQUEST)
    if len(markdown.strip()) > _MAX_ANALYSIS_REQUEST_CHARACTERS:
        return _payload("analysis_role_input_too_large")
    normalized_evidence_ids = tuple(evidence_ids)
    try:
        # 写文件前复用报告领域不变量；索引只使用固定标题与固定文件名。
        AnalysisReport(
            id="preflight",
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            artifact_path=f"/mnt/user-data/outputs/analysis-report-{run_id}.md",
            title=title,
            status=ReportStatus.PUBLISHED,
            evidence_ids=normalized_evidence_ids,
            created_at=datetime.now(UTC),
        )
    except (TypeError, ValueError):
        return _payload(_INVALID_REQUEST)

    try:
        snapshots = await evidence_collector.resolve_successful_queries_durable(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            evidence_ids=normalized_evidence_ids,
        )
    except Exception:  # noqa: BLE001 - durable evidence failure stays stable
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    if snapshots is None:
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    reviewer = context.get(ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY)
    if not isinstance(reviewer, AnalysisReportReviewerCapability) or not reviewer.matches(principal_id, thread_id, run_id):
        log_reviewer_failure_stage("capability_unavailable", run_id)
        return _payload("analysis_review_unavailable")

    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "data", "running")
        metrics = await MetricService(services.metrics).list_active_for_principal(principal_id=principal_id)
        data_result = await roles.analyze(
            principal_id,
            thread_id,
            run_id,
            snapshots,
            metrics,
            analysis_request=markdown.strip(),
        )
        await _emit_stage(roles, principal_id, thread_id, run_id, "data", "succeeded", code="ok", **role_usage_fields(data_result))
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "data", "cancelled", code="cancelled")
        except AnalysisStageError:
            pass
        raise
    except AnalysisRoleError as exc:
        code = stable_stage_code(exc.reason)
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "data", stage_status_for_code(code), code=code)
        except AnalysisStageError:
            return _payload("analysis_role_unavailable")
        return _payload(f"analysis_role_{exc.reason}")
    except AnalysisStageError:
        return _payload("analysis_role_unavailable")
    except Exception:  # noqa: BLE001 - snapshot/data failures never publish or expose input
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "data", "failed", code="unavailable")
        except AnalysisStageError:
            pass
        return _payload("analysis_role_unavailable")

    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "writer", "running")
        layout_invocation = await roles.layout_with_usage(
            principal_id,
            thread_id,
            run_id,
            data_result.verified_claims,
            data_result.labels,
        )
        layout = layout_invocation.value
        verified_markdown = render_verified_report(layout, data_result.labels, data_result.verified_claims)
        verified_markdown = _append_metric_snapshot(verified_markdown, metrics)
        await _emit_stage(roles, principal_id, thread_id, run_id, "writer", "succeeded", code="ok", **role_usage_fields(layout_invocation))
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "writer", "cancelled", code="cancelled")
        except AnalysisStageError:
            pass
        raise
    except AnalysisRoleError as exc:
        code = stable_stage_code(exc.reason)
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "writer", stage_status_for_code(code), code=code)
        except AnalysisStageError:
            return _payload("analysis_role_unavailable")
        return _payload(f"analysis_role_{exc.reason}")
    except AnalysisStageError:
        return _payload("analysis_role_unavailable")
    except Exception:  # noqa: BLE001 - snapshot/render failures never publish or expose input
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "writer", "failed", code="unavailable")
        except AnalysisStageError:
            pass
        return _payload("analysis_role_unavailable")

    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "reviewer", "running")
        review = await reviewer.review(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            title=_FIXED_REPORT_TITLE,
            markdown=verified_markdown,
            evidence_ids=normalized_evidence_ids,
            snapshots=snapshots,
            verified_claims=data_result.verified_claims,
        )
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "reviewer", "cancelled", code="cancelled")
        except AnalysisStageError:
            pass
        raise
    except AnalysisStageError:
        return _payload("analysis_review_unavailable")
    except Exception:  # noqa: BLE001 - 复核能力异常不向模型回显且绝不继续发布
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "reviewer", "failed", code="unavailable")
        except AnalysisStageError:
            pass
        log_reviewer_failure_stage("reviewer_internal_error", run_id)
        return _payload("analysis_review_unavailable")
    if review.code != "approved":
        reason_code = {
            "analysis_review_rejected": "review_rejected",
            "analysis_review_input_too_large": "input_too_large",
            "analysis_review_attempt_limit": "attempt_limit",
        }.get(review.code, "unavailable")
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "reviewer", stage_status_for_code(reason_code), code=reason_code)
        except AnalysisStageError:
            return _payload("analysis_review_unavailable")
        if review.code == "analysis_review_rejected" and review.reason_code is not None:
            return _payload(review.code, reason_code=review.reason_code)
        if review.code in {"analysis_review_unavailable", "analysis_review_input_too_large", "analysis_review_attempt_limit"}:
            return _payload(review.code)
        return _payload("analysis_review_unavailable")
    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "reviewer", "succeeded", code="ok")
    except AnalysisStageError:
        return _payload("analysis_review_unavailable")

    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "running")
        write_result = await write_markdown(verified_markdown)
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "cancelled", code="cancelled")
        except AnalysisStageError:
            pass
        raise
    except AnalysisStageError:
        return _payload(_UNAVAILABLE)
    except Exception:  # noqa: BLE001 - capability errors are never returned to the model
        try:
            await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        except AnalysisStageError:
            pass
        return _payload(_UNAVAILABLE)
    artifact_path = f"/mnt/user-data/outputs/analysis-report-{run_id}.md"
    write_code = getattr(write_result, "code", None)
    if not isinstance(write_code, str) or write_code not in {"published", "existing"} or getattr(write_result, "path", None) != artifact_path:
        code = write_code
        if code in ("invalid_request", "report_conflict"):
            stable_code = stable_stage_code(code)
            await _emit_stage(roles, principal_id, thread_id, run_id, "publish", stage_status_for_code(stable_code), code=stable_code)
            return _payload(code)
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        return _payload(_UNAVAILABLE)

    try:
        publication = await services.publish_report.execute(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            title=_FIXED_REPORT_TITLE,
            artifact_path=artifact_path,
            evidence_ids=normalized_evidence_ids,
        )
    except (ValueError, TypeError):
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "blocked", code="invalid_request")
        return _payload(_INVALID_REQUEST)
    except Exception:  # noqa: BLE001 - index failure has one stable external result
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        return _payload(_UNAVAILABLE)

    code = getattr(publication, "code", None)
    report = getattr(publication, "report", None)
    if not isinstance(code, ReportPublishCode):
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        return _payload(_UNAVAILABLE)
    if code not in _REPORT_SUCCESS_CODES:
        stable_code = stable_stage_code(code.value)
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", stage_status_for_code(stable_code), code=stable_code)
        return _payload(code.value)
    report_id = getattr(report, "id", None)
    report_identity = getattr(report, "identity", None)
    try:
        report_evidence_ids = tuple(getattr(report, "evidence_ids"))
    except Exception:  # noqa: BLE001 - malformed repository projection stays stable
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        return _payload(_UNAVAILABLE)
    if (
        not isinstance(report_id, str)
        or not _SAFE_REPORT_ID.fullmatch(report_id)
        or report_identity != (principal_id, thread_id, run_id, artifact_path)
        or getattr(report, "title", None) != _FIXED_REPORT_TITLE
        or report_evidence_ids != normalized_evidence_ids
    ):
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "failed", code="unavailable")
        return _payload(_UNAVAILABLE)

    try:
        await _emit_stage(roles, principal_id, thread_id, run_id, "publish", "succeeded", code="ok")
    except AnalysisStageError:
        return _payload(_UNAVAILABLE)

    receipt = canonical_json(
        {
            "code": code.value,
            "report_id": report_id,
            "artifact_path": artifact_path,
            "evidence_ids": list(normalized_evidence_ids),
        }
    )
    return Command(
        update={
            "artifacts": [artifact_path],
            "messages": [ToolMessage(content=receipt, tool_call_id=tool_call_id, name=WRITE_ANALYSIS_REPORT_TOOL_NAME)],
        }
    )


__all__ = [
    "PUBLISH_REPORT_TOOL_NAME",
    "WRITE_ANALYSIS_REPORT_TOOL_NAME",
    "publish_analysis_report",
    "write_analysis_report",
]
