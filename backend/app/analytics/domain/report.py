"""分析报告索引的领域值对象（Phase 4 §6）。

Phase 3 已经能把分析结论写成 artifact，但系统里没有"这份报告属于谁、属于哪个分析会话"的
索引。Phase 4 补上 `analytics_analysis_reports`，这个模块就是它的领域契约。

设计边界（与审计账本同源）：

- 只登记索引元数据：`principal_id` / `thread_id` / `run_id` / `artifact_path` / `title` /
  `status` / `evidence_ids` / `created_at`。**不保存 artifact 内容**，也不保存原始 SQL、
  结果行、prompt、chain-of-thought、token、credential 或 DSN——字段白名单本身就是安全边界，
  由 `tests/test_analytics_report_domain.py` 的字段集合断言钉住。
- `artifact_path` 必须是 `/mnt/user-data/outputs/` 下的规范化相对目标。这不是显示偏好：
  报告索引只是"指向 artifact 的指针"，打开它仍然要经过 Gateway 的 thread ownership 检查，
  所以这里必须先拒绝一切越界写法，避免索引本身成为越权读取的跳板。
- `evidence_ids` 只接受有限数量的 64 位小写 SHA-256，且至少一条。没有 evidence 的"分析报告"
  正是 Phase 3 要禁止的无依据数字。

`ReportPublishCode` 是发布用例对外唯一的稳定结果词汇表；模型可见的 `code` 直接取这里的值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed

#: 报告 artifact 的虚拟根。必须与 Gateway artifact 路由认得的 `/mnt/user-data/outputs` 逐字一致。
ANALYSIS_REPORT_ARTIFACT_ROOT = "/mnt/user-data/outputs/"

#: 单份报告允许引用的 evidence 上限：它约束的是索引体积，不是分析规模。
MAX_REPORT_EVIDENCE_IDS = 20

#: 标题长度上限（按字符计）。标题会进入列表页，必须是有界单行文本。
MAX_REPORT_TITLE_CHARACTERS = 200

#: artifact 路径长度上限。它与数据库列宽一致，保证领域层与表结构不会各自为政。
MAX_REPORT_ARTIFACT_PATH_CHARACTERS = 512

#: 身份字段（id/principal/thread/run）的长度上限：与其它 Analytics 表保持同一量级。
MAX_REPORT_ID_CHARACTERS = 64

_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


class ReportStatus(StrEnum):
    """报告索引状态。

    V1 只有"已登记"一种：发布要么落一行，要么根本不落行——不存在"草稿"或"审核中"的中间态，
    因为中间态会让 UI 有理由显示一份尚未通过 Reviewer 的报告。
    """

    PUBLISHED = "published"


class ReportPublishCode(StrEnum):
    """发布操作的稳定结果码。

    - `PUBLISHED`：本次调用真的插入了新行；
    - `EXISTING`：同一身份键上的**逐字重试**，返回既有行，不产生第二行；
    - `REPORT_CONFLICT`：同一身份键上出现了不同内容。这不是重试，绝不静默覆盖已登记的报告。
    """

    PUBLISHED = "published"
    EXISTING = "existing"
    REPORT_CONFLICT = "report_conflict"


def _require_optional_text(value: object, field_name: str) -> None:
    """标题等展示文本：必须是有界单行文本，拒绝控制字符。"""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    if any(character < " " or character == "\x7f" for character in value):
        raise ValueError(f"{field_name} must not contain control characters")


def _require_bounded_identity(value: object, field_name: str) -> None:
    _require_trimmed(value, field_name)  # type: ignore[arg-type]
    if len(value) > MAX_REPORT_ID_CHARACTERS:  # type: ignore[arg-type]
        raise ValueError(f"{field_name} must be at most {MAX_REPORT_ID_CHARACTERS} characters")


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def normalize_report_artifact_path(value: object) -> str:
    """把 artifact 路径规范化成 `/mnt/user-data/outputs/` 下的相对目标。

    拒绝的东西都是同一类问题——"索引指向 outputs 之外"：绝对路径、反斜杠、空段、`.`、`..`、
    目录本身、NUL 与控制字符、前后空白。这里刻意**不**做任何"尽力修正"（不做 `normpath`、
    不替换反斜杠）：一个需要修正才能合理解释的路径，本身就是不该被登记的输入。
    """

    if not isinstance(value, str):
        raise ValueError("artifact_path must be a string")
    if not value or value != value.strip():
        raise ValueError("artifact_path must be a non-empty trimmed string")
    if any(character < " " or character == "\x7f" for character in value):
        raise ValueError("artifact_path must not contain control characters")
    if not value.startswith(ANALYSIS_REPORT_ARTIFACT_ROOT):
        raise ValueError(f"artifact_path must be under {ANALYSIS_REPORT_ARTIFACT_ROOT}")

    relative = value[len(ANALYSIS_REPORT_ARTIFACT_ROOT) :]
    # 目录本身。
    if not relative:
        raise ValueError("artifact_path must name a file, not the outputs directory")
    if "\\" in relative:
        raise ValueError("artifact_path must use forward slashes only")

    segments = relative.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError("artifact_path must not contain empty, '.' or '..' segments")
    if len(value) > MAX_REPORT_ARTIFACT_PATH_CHARACTERS:
        raise ValueError(f"artifact_path must be at most {MAX_REPORT_ARTIFACT_PATH_CHARACTERS} characters")

    return value


def _normalize_evidence_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError("evidence_ids must be a tuple of lowercase SHA-256 digests")
    if not value:
        # 报告必须至少引用一条 evidence：无依据的结论不允许成为"已登记报告"。
        raise ValueError("evidence_ids must not be empty")
    if len(value) > MAX_REPORT_EVIDENCE_IDS:
        raise ValueError(f"evidence_ids must contain at most {MAX_REPORT_EVIDENCE_IDS} digests")

    seen: set[str] = set()
    for digest in value:
        if not isinstance(digest, str) or len(digest) != _HASH_LENGTH or any(character not in _HEX_DIGITS for character in digest):
            raise ValueError("evidence_ids must contain only 64 lowercase hexadecimal characters")
        if digest in seen:
            raise ValueError("evidence_ids must not contain duplicates")
        seen.add(digest)
    return value


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """一条报告索引。不可变，且字段白名单固定。

    `principal_id` / `thread_id` / `run_id` 只能由服务端从受信 runtime 派生（见
    `app/analytics/agent/reports.py`）：模型可见参数里没有它们，因此客户端无法把一份报告
    挂到别人名下，也无法伪造"某个不存在的 run 发布了报告"。
    """

    id: str
    principal_id: str
    thread_id: str
    run_id: str
    artifact_path: str
    title: str
    status: ReportStatus
    evidence_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("id", "principal_id", "thread_id", "run_id"):
            _require_bounded_identity(getattr(self, field_name), field_name)
        normalize_report_artifact_path(self.artifact_path)
        _require_optional_text(self.title, "title")
        if len(self.title) > MAX_REPORT_TITLE_CHARACTERS:
            raise ValueError(f"title must be at most {MAX_REPORT_TITLE_CHARACTERS} characters")
        if not isinstance(self.status, ReportStatus):
            raise ValueError("status must be a ReportStatus")
        _normalize_evidence_ids(self.evidence_ids)
        _require_aware_datetime(self.created_at, "created_at")

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """服务端派生的幂等键：模型无法提供、也无法计算它。"""

        return (self.principal_id, self.thread_id, self.run_id, self.artifact_path)

    def same_publication(self, other: AnalysisReport) -> bool:
        """判断两条索引是否描述同一次发布（幂等重试 vs. 内容冲突）。"""

        return self.identity == other.identity and self.title == other.title and self.evidence_ids == other.evidence_ids
