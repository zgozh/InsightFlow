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

from langchain.tools import tool

from app.analytics.agent.evidence import canonical_json
from app.analytics.agent.runtime import get_bound_analytics_services, trusted_principal, trusted_thread_run
from app.analytics.domain import AnalysisReport
from deerflow.tools.types import Runtime

PUBLISH_REPORT_TOOL_NAME = "publish_analysis_report"

_UNAVAILABLE = "analytics_unavailable"
_INVALID_REQUEST = "invalid_request"


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


__all__ = ["PUBLISH_REPORT_TOOL_NAME", "publish_analysis_report"]
