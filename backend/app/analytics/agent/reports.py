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

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.analytics.agent.evidence import ANALYSIS_EVIDENCE_UNAVAILABLE, AnalysisRunEvidenceCollector, canonical_json
from app.analytics.agent.reviewer import AnalysisReportReviewerCapability, log_reviewer_failure_stage
from app.analytics.agent.runtime import get_bound_analytics_services, trusted_principal, trusted_thread_run
from app.analytics.domain import AnalysisReport, ReportPublishCode, ReportStatus
from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY, ANALYSIS_REPORT_WRITER_CONTEXT_KEY
from deerflow.tools.types import Runtime

PUBLISH_REPORT_TOOL_NAME = "publish_analysis_report"

_UNAVAILABLE = "analytics_unavailable"
_INVALID_REQUEST = "invalid_request"
WRITE_ANALYSIS_REPORT_TOOL_NAME = "write_analysis_report"
_REPORT_SUCCESS_CODES = frozenset({ReportPublishCode.PUBLISHED, ReportPublishCode.EXISTING})
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
    """写入并登记当前 analysis run 的唯一 Markdown 报告。

    Gateway 能力固定所有者、线程、run、存储根目录和文件名。模型只提供报告正文与 evidence
    引用；引用必须属于该 run 的成功受控查询。发布前有服务端零工具 Reviewer；若返回
    `analysis_review_rejected` 和稳定 reason code，可据此修订并最多再提交一次。Reviewer 只提供流程复核，
    不证明数字正确；安全回执不包含正文或内部身份。

    Args:
        title: 报告列表显示的短标题。
        markdown: UTF-8 Markdown 正文，最多 2 MiB。
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
    capability = context.get(ANALYSIS_REPORT_WRITER_CONTEXT_KEY) if isinstance(context, Mapping) else None
    if principal_id is None or identity is None or capability is None:
        return _payload(_UNAVAILABLE)
    thread_id, run_id = identity
    matches = getattr(capability, "matches", None)
    write_markdown = getattr(capability, "write_markdown", None)
    if not callable(matches) or not callable(write_markdown):
        return _payload(_UNAVAILABLE)
    try:
        normalized_evidence_ids = tuple(evidence_ids)
    except (TypeError, ValueError):
        return _payload(_INVALID_REQUEST)
    try:
        if not matches(principal_id, thread_id, run_id):
            return _payload(_UNAVAILABLE)
        # 写文件前复用报告领域不变量；索引仍只由 PublishAnalysisReport 用例负责。
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

    evidence_collector = context.get(ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY) if isinstance(context, Mapping) else None
    if not isinstance(evidence_collector, AnalysisRunEvidenceCollector):
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    try:
        snapshots = evidence_collector.resolve_successful_queries(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            evidence_ids=normalized_evidence_ids,
        )
    except (TypeError, ValueError):
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    if snapshots is None:
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)

    reviewer = context.get(ANALYSIS_REPORT_REVIEWER_CONTEXT_KEY) if isinstance(context, Mapping) else None
    if not isinstance(reviewer, AnalysisReportReviewerCapability) or not reviewer.matches(principal_id, thread_id, run_id):
        log_reviewer_failure_stage("capability_unavailable", run_id)
        return _payload("analysis_review_unavailable")
    try:
        review = await reviewer.review(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            title=title,
            markdown=markdown,
            evidence_ids=normalized_evidence_ids,
            snapshots=snapshots,
        )
    except Exception:  # noqa: BLE001 - 复核能力异常不向模型回显且绝不继续发布
        log_reviewer_failure_stage("reviewer_internal_error", run_id)
        return _payload("analysis_review_unavailable")
    if review.code != "approved":
        if review.code == "analysis_review_rejected" and review.reason_code is not None:
            return _payload(review.code, reason_code=review.reason_code)
        if review.code in {"analysis_review_unavailable", "analysis_review_input_too_large", "analysis_review_attempt_limit"}:
            return _payload(review.code)
        return _payload("analysis_review_unavailable")

    try:
        write_result = await write_markdown(markdown)
    except Exception:  # noqa: BLE001 - capability errors are never returned to the model
        return _payload(_UNAVAILABLE)
    artifact_path = f"/mnt/user-data/outputs/analysis-report-{run_id}.md"
    write_code = getattr(write_result, "code", None)
    if not isinstance(write_code, str) or write_code not in {"published", "existing"} or getattr(write_result, "path", None) != artifact_path:
        code = write_code
        if code in ("invalid_request", "report_conflict"):
            return _payload(code)
        return _payload(_UNAVAILABLE)

    try:
        publication = await services.publish_report.execute(
            principal_id=principal_id,
            thread_id=thread_id,
            run_id=run_id,
            title=title,
            artifact_path=artifact_path,
            evidence_ids=normalized_evidence_ids,
        )
    except (ValueError, TypeError):
        return _payload(_INVALID_REQUEST)
    except Exception:  # noqa: BLE001 - index failure has one stable external result
        return _payload(_UNAVAILABLE)

    code = getattr(publication, "code", None)
    report = getattr(publication, "report", None)
    if not isinstance(code, ReportPublishCode):
        return _payload(_UNAVAILABLE)
    if code not in _REPORT_SUCCESS_CODES:
        return _payload(code.value)
    report_id = getattr(report, "id", None)
    report_identity = getattr(report, "identity", None)
    try:
        report_evidence_ids = tuple(getattr(report, "evidence_ids"))
    except (TypeError, ValueError):
        return _payload(_UNAVAILABLE)
    if (
        not isinstance(report_id, str)
        or not _SAFE_REPORT_ID.fullmatch(report_id)
        or report_identity != (principal_id, thread_id, run_id, artifact_path)
        or getattr(report, "title", None) != title
        or report_evidence_ids != normalized_evidence_ids
    ):
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
