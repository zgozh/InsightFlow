"""基于已验证数字声明的确定性 Markdown 报告 consumer。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.claims import EvidenceCellReference, NumericClaimOperation, VerifiedNumericClaim
from app.analytics.domain.query import MAX_QUERY_ROWS

MAX_REPORT_CLAIM_LABEL_CHARACTERS = 80
MAX_REPORT_SECTION_CLAIMS = 50
MAX_VERIFIED_REPORT_BYTES = 32 * 1024

_CLAIM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_EVIDENCE_ID = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_INVALID = "verified_report_invalid"
_TOO_LARGE = "verified_report_too_large"

_SECTION_TITLES = {
    "summary": "摘要",
    "details": "明细",
    "comparison": "对比",
}
_OPERATION_LABELS = {
    NumericClaimOperation.CELL: "引用单元格",
    NumericClaimOperation.SUM: "求和",
    NumericClaimOperation.DIFFERENCE: "差值",
    NumericClaimOperation.RATIO: "比率",
    NumericClaimOperation.PERCENTAGE: "百分比",
    NumericClaimOperation.MEAN: "平均值",
    NumericClaimOperation.CHANGE_PERCENTAGE: "变化百分比",
}
_TEXT_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\\": "&#92;",
    "|": "&#124;",
    "*": "&#42;",
    "_": "&#95;",
    "[": "&#91;",
    "]": "&#93;",
    "(": "&#40;",
    ")": "&#41;",
    "!": "&#33;",
    "#": "&#35;",
    "+": "&#43;",
    "-": "&#45;",
    ".": "&#46;",
    ":": "&#58;",
    "/": "&#47;",
    "?": "&#63;",
    "=": "&#61;",
    "~": "&#126;",
    '"': "&quot;",
    "'": "&#39;",
    chr(96): "&#96;",
}


class VerifiedReportError(RuntimeError):
    """报告输入或输出不符合稳定领域边界。"""

    def __init__(self, reason: str) -> None:
        stable_reason = reason if type(reason) is str and reason in {_INVALID, _TOO_LARGE} else _INVALID
        self.reason = stable_reason
        super().__init__(stable_reason)


class ReportSectionKind(StrEnum):
    SUMMARY = "summary"
    DETAILS = "details"
    COMPARISON = "comparison"


def _require_claim_id(value: object) -> None:
    if type(value) is not str or len(value) > 64 or not _CLAIM_ID.fullmatch(value):
        raise VerifiedReportError(_INVALID)


def _require_display_text(value: object, maximum: int) -> None:
    if type(value) is not str or not value or len(value) > maximum or value != value.strip() or not all(character.isprintable() for character in value):
        raise VerifiedReportError(_INVALID)


@dataclass(frozen=True, slots=True)
class ReportClaimLabel:
    """与数字声明关联的安全展示说明，不承担指标语义证明。"""

    claim_id: str
    label: str

    def __post_init__(self) -> None:
        _require_claim_id(self.claim_id)
        _require_display_text(self.label, MAX_REPORT_CLAIM_LABEL_CHARACTERS)
        if any(character.isnumeric() for character in self.label):
            raise VerifiedReportError(_INVALID)


@dataclass(frozen=True, slots=True)
class VerifiedReportSection:
    """只选择预定义章节和声明 ID，不接受自由格式正文。"""

    kind: ReportSectionKind
    claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.kind) is not ReportSectionKind or type(self.claim_ids) is not tuple:
            raise VerifiedReportError(_INVALID)
        if len(self.claim_ids) > MAX_REPORT_SECTION_CLAIMS:
            raise VerifiedReportError(_INVALID)
        for claim_id in self.claim_ids:
            _require_claim_id(claim_id)


@dataclass(frozen=True, slots=True)
class VerifiedReportLayout:
    """由一至三个不重复的固定章节组成的完整报告布局。"""

    sections: tuple[VerifiedReportSection, ...]

    def __post_init__(self) -> None:
        if type(self.sections) is not tuple or not 1 <= len(self.sections) <= 3:
            raise VerifiedReportError(_INVALID)
        seen_kinds: set[ReportSectionKind] = set()
        seen_claim_ids: set[str] = set()
        for section in self.sections:
            if type(section) is not VerifiedReportSection or type(section.kind) is not ReportSectionKind:
                raise VerifiedReportError(_INVALID)
            if section.kind in seen_kinds:
                raise VerifiedReportError(_INVALID)
            seen_kinds.add(section.kind)
            for claim_id in section.claim_ids:
                _require_claim_id(claim_id)
                if claim_id in seen_claim_ids:
                    raise VerifiedReportError(_INVALID)
                seen_claim_ids.add(claim_id)
        if not seen_claim_ids or len(seen_claim_ids) > MAX_REPORT_SECTION_CLAIMS:
            raise VerifiedReportError(_INVALID)


def _require_reference(reference: object) -> None:
    if type(reference) is not EvidenceCellReference:
        raise VerifiedReportError(_INVALID)
    if type(reference.evidence_id) is not str or not _EVIDENCE_ID.fullmatch(reference.evidence_id) or type(reference.row_index) is not int or not 0 <= reference.row_index < MAX_QUERY_ROWS:
        raise VerifiedReportError(_INVALID)
    _require_display_text(reference.column_name, 256)


def _require_verified_claim(claim: object) -> None:
    if type(claim) is not VerifiedNumericClaim:
        raise VerifiedReportError(_INVALID)
    _require_claim_id(claim.id)
    if type(claim.operation) is not NumericClaimOperation:
        raise VerifiedReportError(_INVALID)
    if type(claim.source_references) is not tuple or not 1 <= len(claim.source_references) <= MAX_REPORT_SECTION_CLAIMS:
        raise VerifiedReportError(_INVALID)
    for reference in claim.source_references:
        _require_reference(reference)
    if claim.operation is NumericClaimOperation.CELL and len(claim.source_references) != 1:
        raise VerifiedReportError(_INVALID)
    if (
        claim.operation
        in {
            NumericClaimOperation.DIFFERENCE,
            NumericClaimOperation.RATIO,
            NumericClaimOperation.PERCENTAGE,
            NumericClaimOperation.CHANGE_PERCENTAGE,
        }
        and len(claim.source_references) != 2
    ):
        raise VerifiedReportError(_INVALID)
    if type(claim.calculated_value) is not str or len(claim.calculated_value) > 256 or not _DECIMAL_TEXT.fullmatch(claim.calculated_value) or type(claim.rounded) is not bool or type(claim.references_truncated_snapshot) is not bool:
        raise VerifiedReportError(_INVALID)
    for value, reference in ((claim.unit, claim.unit_reference), (claim.period, claim.period_reference)):
        if (value is None) != (reference is None):
            raise VerifiedReportError(_INVALID)
        if value is not None:
            _require_display_text(value, 128)
            _require_reference(reference)


def _escape_display_text(value: str) -> str:
    return "".join(_TEXT_ESCAPES.get(character, character) for character in value)


def _claim_references(claim: VerifiedNumericClaim) -> tuple[EvidenceCellReference, ...]:
    references = claim.source_references + (claim.unit_reference, claim.period_reference)
    distinct: list[EvidenceCellReference] = []
    seen: set[EvidenceCellReference] = set()
    for reference in references:
        if reference is not None and reference not in seen:
            seen.add(reference)
            distinct.append(reference)
    return tuple(distinct)


def render_verified_report(
    layout: VerifiedReportLayout,
    labels: tuple[ReportClaimLabel, ...],
    verified_claims: tuple[VerifiedNumericClaim, ...],
) -> str:
    """只把精确对应的标签与已验证声明渲染为有界 Markdown。"""

    if type(layout) is not VerifiedReportLayout or type(labels) is not tuple or type(verified_claims) is not tuple:
        raise VerifiedReportError(_INVALID)
    if not 1 <= len(labels) <= MAX_REPORT_SECTION_CLAIMS or len(verified_claims) != len(labels):
        raise VerifiedReportError(_INVALID)

    label_by_id: dict[str, ReportClaimLabel] = {}
    for label in labels:
        if type(label) is not ReportClaimLabel:
            raise VerifiedReportError(_INVALID)
        _require_claim_id(label.claim_id)
        _require_display_text(label.label, MAX_REPORT_CLAIM_LABEL_CHARACTERS)
        if any(character.isnumeric() for character in label.label) or label.claim_id in label_by_id:
            raise VerifiedReportError(_INVALID)
        label_by_id[label.claim_id] = label

    claim_by_id: dict[str, VerifiedNumericClaim] = {}
    for claim in verified_claims:
        _require_verified_claim(claim)
        if claim.id in claim_by_id:
            raise VerifiedReportError(_INVALID)
        claim_by_id[claim.id] = claim

    layout_ids = tuple(claim_id for section in layout.sections for claim_id in section.claim_ids)
    expected_ids = set(claim_by_id)
    if len(layout_ids) != len(expected_ids) or set(layout_ids) != expected_ids or set(label_by_id) != expected_ids:
        raise VerifiedReportError(_INVALID)

    lines = [
        "# 经营分析报告",
        "",
        "指标说明来自展示标签；标签不定义或证明指标语义。",
        "",
    ]
    for section in layout.sections:
        lines.extend(
            [
                f"## {_SECTION_TITLES[section.kind.value]}",
                "",
                "| 声明 ID | 指标说明 | 数值 | 单位 | 期间 | 计算方式与提示 |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for claim_id in section.claim_ids:
            claim = claim_by_id[claim_id]
            notes = [f"运算：{_OPERATION_LABELS[claim.operation]}"]
            if claim.rounded:
                notes.append("计算结果曾发生舍入")
            if claim.references_truncated_snapshot:
                notes.append("来源快照被截断，引用范围可能不完整")
            unit = "未提供" if claim.unit is None else _escape_display_text(claim.unit)
            period = "未提供" if claim.period is None else _escape_display_text(claim.period)
            lines.append(f"| {claim.id} | {_escape_display_text(label_by_id[claim_id].label)} | {claim.calculated_value} | {unit} | {period} | {'；'.join(notes)} |")
        lines.extend(["", "### 精确来源引用", ""])
        for claim_id in section.claim_ids:
            claim = claim_by_id[claim_id]
            for reference in _claim_references(claim):
                lines.append(f"- claim_id: {claim.id}; evidence_id: {reference.evidence_id}; row_index: {reference.row_index}; column_name: {_escape_display_text(reference.column_name)}")
        lines.append("")

    lines.extend(
        [
            "边界提示：证据引用与固定算式验证不等于业务口径正确或总体完整性证明。",
            "",
        ]
    )
    rendered = "\n".join(lines)
    if len(rendered.encode("utf-8")) > MAX_VERIFIED_REPORT_BYTES:
        raise VerifiedReportError(_TOO_LARGE)
    return rendered
