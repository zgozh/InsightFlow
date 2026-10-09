from dataclasses import replace
from decimal import Decimal

import pytest

from app.analytics.domain import (
    EvidenceCellReference,
    NumericClaim,
    NumericClaimOperation,
    ReportClaimLabel,
    ReportSectionKind,
    VerifiedNumericClaim,
    VerifiedReportError,
    VerifiedReportLayout,
    VerifiedReportSection,
    render_verified_report,
    verify_numeric_claims,
)
from app.analytics.domain.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json
from app.analytics.domain.execution import ExecutionDecisionCode, QueryExecutionResult
from app.analytics.domain.query import QueryRisk
from app.analytics.domain.verified_report import MAX_VERIFIED_REPORT_BYTES


def _snapshot(
    columns: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
    *,
    truncated: bool = False,
) -> AnalyticsQueryToolResult:
    code = ExecutionDecisionCode.RESULT_LIMIT_REACHED.value if truncated else ExecutionDecisionCode.EXECUTED.value
    byte_count = len(canonical_json({"columns": list(columns), "rows": [list(row) for row in rows]}).encode("utf-8"))
    result = QueryExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        byte_count=byte_count,
        truncated=truncated,
    )
    evidence = AnalyticsQueryEvidence.build(
        datasource_id="datasource",
        query_hash="a" * 64,
        risk=QueryRisk.LOW,
        schema_version="schema-1",
        policy_version="policy-1",
        plan_digest="b" * 64,
        estimated_rows=len(rows),
        engine_cost=Decimal(0),
        result=result,
        decision_code=code,
    )
    return AnalyticsQueryToolResult(code=code, columns=columns, rows=rows, truncated=truncated, evidence=evidence)


def _ref(snapshot: AnalyticsQueryToolResult, column: str, row: int = 0) -> EvidenceCellReference:
    assert snapshot.evidence is not None
    return EvidenceCellReference(snapshot.evidence.evidence_id, row, column)


def _report(
    verified_claims: tuple[VerifiedNumericClaim, ...],
    labels: tuple[ReportClaimLabel, ...],
    *,
    kind: ReportSectionKind = ReportSectionKind.SUMMARY,
) -> str:
    return render_verified_report(
        VerifiedReportLayout((VerifiedReportSection(kind, tuple(claim.id for claim in verified_claims)),)),
        labels,
        verified_claims,
    )


def _expect_report_error(action) -> None:
    with pytest.raises(VerifiedReportError) as error:
        action()
    assert error.value.reason == "verified_report_invalid"
    assert str(error.value) == error.value.reason


def test_report_renders_calculated_values_from_claims_verified_against_two_snapshots():
    first = _snapshot(("gross", "currency", "period"), ((10, "CNY", "2026-Q1"),))
    second = _snapshot(("adjustment",), ((2,),))
    combined = NumericClaim(
        "net",
        NumericClaimOperation.DIFFERENCE,
        (_ref(first, "gross"), _ref(second, "adjustment")),
        "8.00",
        2,
        unit_reference=_ref(first, "currency"),
        period_reference=_ref(first, "period"),
    )
    other = NumericClaim("adjustment", NumericClaimOperation.CELL, (_ref(second, "adjustment"),), "2.00", 2)
    verified = verify_numeric_claims((combined, other), (first, second))
    layout = VerifiedReportLayout(
        (
            VerifiedReportSection(ReportSectionKind.SUMMARY, ("net",)),
            VerifiedReportSection(ReportSectionKind.DETAILS, ("adjustment",)),
        )
    )

    rendered = render_verified_report(
        layout,
        (ReportClaimLabel("net", "净额"), ReportClaimLabel("adjustment", "调整额")),
        verified,
    )

    assert "# 经营分析报告" in rendered
    assert "## 摘要" in rendered and "## 明细" in rendered
    assert "| net | 净额 | 8.00 | CNY | 2026&#45;Q1 |" in rendered
    assert "| adjustment | 调整额 | 2.00 | 未提供 | 未提供 |" in rendered
    assert f"evidence_id: {first.evidence.evidence_id}" in rendered
    assert f"evidence_id: {second.evidence.evidence_id}" in rendered
    assert "column_name: gross" in rendered
    assert "column_name: currency" in rendered
    assert "column_name: period" in rendered
    assert "column_name: adjustment" in rendered
    assert "边界提示：证据引用与固定算式验证不等于业务口径正确或总体完整性证明。" in rendered


@pytest.mark.parametrize("label", ("revenue 2026", "growth ²", "change ٣"))
def test_report_labels_reject_ascii_and_unicode_numeric_characters(label: str):
    with pytest.raises(VerifiedReportError) as error:
        ReportClaimLabel("amount", label)
    assert error.value.reason == "verified_report_invalid"
    assert str(error.value) == "verified_report_invalid"


def test_report_escapes_html_table_links_markdown_and_backticks_in_labels_and_source_names():
    backtick = chr(96)
    column = f"amount | <script> [x](https://example.test) {backtick}raw{backtick}"
    snapshot = _snapshot((column,), ((1.235,),))
    source = _ref(snapshot, column)
    claim = NumericClaim("amount", NumericClaimOperation.CELL, (source,), "1.24", 2)
    verified = verify_numeric_claims((claim,), (snapshot,))
    label = f"<script>|[x](https://example.test){backtick} 说明"

    rendered = _report(verified, (ReportClaimLabel("amount", label),))

    assert "<script>" not in rendered
    assert "](https://example.test)" not in rendered
    assert backtick not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&#124;" in rendered
    assert "&#91;x&#93;" in rendered
    assert "&#96;raw&#96;" in rendered
    assert "&#58;&#47;&#47;example&#46;test" in rendered


def test_missing_labels_and_periods_are_explicit_and_rounding_and_truncation_are_warned():
    snapshot = _snapshot(("amount",), ((1.235,),), truncated=True)
    claim = NumericClaim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "1.24", 2)
    verified = verify_numeric_claims((claim,), (snapshot,))

    rendered = _report(verified, (ReportClaimLabel("amount", "金额"),))

    assert "| amount | 金额 | 1.24 | 未提供 | 未提供 |" in rendered
    assert "计算结果曾发生舍入" in rendered
    assert "来源快照被截断，引用范围可能不完整" in rendered


def test_layout_label_and_claim_id_mismatches_are_rejected_as_a_whole():
    snapshot = _snapshot(("amount",), ((3,),))
    claim = NumericClaim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "3", 0)
    verified = verify_numeric_claims((claim,), (snapshot,))
    label = ReportClaimLabel("amount", "金额")

    _expect_report_error(lambda: _report(verified, ()))
    _expect_report_error(lambda: _report(verified, (ReportClaimLabel("other", "其他"),)))
    _expect_report_error(lambda: _report(verified, (label, label)))
    _expect_report_error(
        lambda: render_verified_report(
            VerifiedReportLayout((VerifiedReportSection(ReportSectionKind.SUMMARY, ("unknown",)),)),
            (label,),
            verified,
        )
    )
    _expect_report_error(
        lambda: render_verified_report(
            VerifiedReportLayout((VerifiedReportSection(ReportSectionKind.SUMMARY, ("amount",)),)),
            (label,),
            (verified[0], verified[0]),
        )
    )


def test_duplicate_section_kinds_and_claim_ids_are_rejected():
    with pytest.raises(VerifiedReportError) as duplicate_kinds:
        VerifiedReportLayout(
            (
                VerifiedReportSection(ReportSectionKind.SUMMARY, ("a",)),
                VerifiedReportSection(ReportSectionKind.SUMMARY, ("b",)),
            )
        )
    assert duplicate_kinds.value.reason == "verified_report_invalid"

    with pytest.raises(VerifiedReportError) as duplicate_ids:
        VerifiedReportLayout(
            (
                VerifiedReportSection(ReportSectionKind.SUMMARY, ("a",)),
                VerifiedReportSection(ReportSectionKind.DETAILS, ("a",)),
            )
        )
    assert duplicate_ids.value.reason == "verified_report_invalid"


def test_only_exact_verified_claim_type_with_safe_rendering_structure_is_accepted():
    snapshot = _snapshot(("amount",), ((3,),))
    claim = NumericClaim("amount", NumericClaimOperation.CELL, (_ref(snapshot, "amount"),), "3", 0)
    verified = verify_numeric_claims((claim,), (snapshot,))
    malformed = replace(verified[0], calculated_value="3 <script>")
    layout = VerifiedReportLayout((VerifiedReportSection(ReportSectionKind.SUMMARY, ("amount",)),))
    label = (ReportClaimLabel("amount", "金额"),)

    _expect_report_error(lambda: render_verified_report(layout, label, (object(),)))
    _expect_report_error(lambda: render_verified_report(layout, label, (malformed,)))
    _expect_report_error(lambda: render_verified_report(object(), label, verified))


def test_report_utf8_size_limit_rejects_instead_of_truncating():
    assert MAX_VERIFIED_REPORT_BYTES == 32 * 1024
    references = tuple(EvidenceCellReference("a" * 64, row, "x" * 256) for row in range(50))
    claim_ids = ("first", "second")
    claims = tuple(
        VerifiedNumericClaim(
            claim_id,
            NumericClaimOperation.SUM,
            references,
            "1.00",
            False,
            False,
            None,
            None,
            None,
            None,
        )
        for claim_id in claim_ids
    )
    layout = VerifiedReportLayout((VerifiedReportSection(ReportSectionKind.SUMMARY, claim_ids),))
    labels = (ReportClaimLabel("first", "收入项"), ReportClaimLabel("second", "费用项"))

    with pytest.raises(VerifiedReportError) as error:
        render_verified_report(layout, labels, claims)
    assert error.value.reason == "verified_report_too_large"
    assert str(error.value) == "verified_report_too_large"


def test_duplicate_source_references_are_rendered_once():
    snapshot = _snapshot(("amount",), ((2,),))
    source = _ref(snapshot, "amount")
    claim = NumericClaim("double", NumericClaimOperation.SUM, (source, source), "4", 0)
    verified = verify_numeric_claims((claim,), (snapshot,))

    rendered = _report(verified, (ReportClaimLabel("double", "重复求和"),))

    citation = f"claim_id: double; evidence_id: {snapshot.evidence.evidence_id}; row_index: 0; column_name: amount"
    assert rendered.count(citation) == 1
