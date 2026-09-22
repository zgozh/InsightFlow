"""报告索引持久化侧的应用端口（Phase 4 §6）。

与审计端口同源的三条约束：

- 只暴露不可变领域值与 keyword-only 身份参数，绝不暴露 SQLAlchemy session；
- 没有"返回任意 dict"的万能 repository，也没有"列出全部 principal"的读法；
- 异常只携带稳定 reason，不携带行内容或驱动异常文本。

`publish` 返回 `ReportPublication` 而不是 bool：调用方必须能区分"本次真的新建了"与"这是一次
幂等重试"，并且**总是拿到权威的既有行**——否则 UI 会向用户谎报"报告已保存"。幂等键
`(principal_id, thread_id, run_id, artifact_path)` 由服务端从受信 runtime 派生，端口上没有任何
"由调用方指定幂等键"的入口。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.analytics.domain import AnalysisReport, ReportPublishCode


@dataclass(frozen=True, slots=True)
class ReportPublication:
    """一次发布的结果。

    - `PUBLISHED`：`report` 就是本次插入的行；
    - `EXISTING`：同一身份键上的逐字重试，`report` 是既有行；
    - `REPORT_CONFLICT`：同一身份键上内容不同，`report` 是既有行（**不是**本次候选值）。
    """

    code: ReportPublishCode
    report: AnalysisReport


@runtime_checkable
class AnalysisReportRepository(Protocol):
    """发布与读取报告索引的端口。"""

    async def publish(self, report: AnalysisReport) -> ReportPublication: ...

    async def list_for_principal(
        self,
        *,
        principal_id: str,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: str | None = None,
    ) -> tuple[AnalysisReport, ...]: ...
