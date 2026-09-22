"""分析报告索引的领域不变量（Phase 4 任务 2）。

报告索引是 Phase 3 artifact 的**补口**：它只登记"哪个 principal 在哪个 thread/run 里发布了哪个
artifact"，绝不保存 artifact 内容。因此这里的断言集中在三件事：

1. 字段白名单固定：值对象里没有任何 SQL、结果行、prompt、token、credential 或 DSN 字段；
2. `artifact_path` 必须是 `/mnt/user-data/outputs/` 下的规范化相对目标，越界一律拒绝；
3. `evidence_ids` 只接受有限数量的 64 位小写 SHA-256，且不接受重复项。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from app.analytics.domain import (
    ANALYSIS_REPORT_ARTIFACT_ROOT,
    MAX_REPORT_ARTIFACT_PATH_CHARACTERS,
    MAX_REPORT_EVIDENCE_IDS,
    MAX_REPORT_TITLE_CHARACTERS,
    AnalysisReport,
    ReportPublishCode,
    ReportStatus,
    normalize_report_artifact_path,
)

_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _report(**overrides) -> AnalysisReport:
    values = {
        "id": "report-1",
        "principal_id": "user-1",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "artifact_path": "/mnt/user-data/outputs/business-analysis.md",
        "title": "2026 Q3 经营分析",
        "status": ReportStatus.PUBLISHED,
        "evidence_ids": (_HASH_A,),
        "created_at": _NOW,
    }
    values.update(overrides)
    return AnalysisReport(**values)


# --- 字段白名单 -------------------------------------------------------------


def test_the_report_value_object_has_exactly_the_indexed_fields():
    """报告值对象的字段集合是安全契约：多一个字段就可能带出 artifact 内容或敏感上下文。"""

    assert {field.name for field in fields(AnalysisReport)} == {
        "id",
        "principal_id",
        "thread_id",
        "run_id",
        "artifact_path",
        "title",
        "status",
        "evidence_ids",
        "created_at",
    }


def test_the_report_value_object_does_not_expose_sensitive_field_names():
    banned = ("sql", "rows", "prompt", "token", "secret", "dsn", "password", "credential", "content", "reasoning")

    for field in fields(AnalysisReport):
        assert not any(fragment in field.name.lower() for fragment in banned), field.name


def test_report_status_v1_only_knows_published():
    """V1 只有"已登记"一种状态：发布要么落一行，要么根本不落行。"""

    assert [member.value for member in ReportStatus] == ["published"]


def test_publish_code_vocabulary_is_stable():
    assert [member.value for member in ReportPublishCode] == ["published", "existing", "report_conflict"]


# --- artifact path ----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "/mnt/user-data/outputs/business-analysis.md",
        "/mnt/user-data/outputs/2026/q3/business-analysis.md",
        "/mnt/user-data/outputs/a b.md",
        "/mnt/user-data/outputs/.hidden.md",
    ],
)
def test_normalize_accepts_outputs_scoped_paths(value):
    assert normalize_report_artifact_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        # 目录本身
        "/mnt/user-data/outputs",
        "/mnt/user-data/outputs/",
        # 不在 outputs 下
        "",
        "business-analysis.md",
        "outputs/business-analysis.md",
        "/mnt/user-data/uploads/business-analysis.md",
        "/mnt/user-data/outputs-backup/business-analysis.md",
        "/tmp/business-analysis.md",
        # 越界与畸形段
        "/mnt/user-data/outputs/../uploads/business-analysis.md",
        "/mnt/user-data/outputs/a/../../business-analysis.md",
        "/mnt/user-data/outputs/./business-analysis.md",
        "/mnt/user-data/outputs//business-analysis.md",
        "/mnt/user-data/outputs/a//b.md",
        "/mnt/user-data/outputs/a/b.md/",
        "/mnt/user-data/outputs/a\\b.md",
        "\\mnt\\user-data\\outputs\\a.md",
        # 控制字符
        "/mnt/user-data/outputs/a\x00b.md",
        "/mnt/user-data/outputs/a\nb.md",
        # 前后空白
        " /mnt/user-data/outputs/a.md",
        "/mnt/user-data/outputs/a.md ",
        # 非字符串
        None,
        42,
        b"/mnt/user-data/outputs/a.md",
        ["/mnt/user-data/outputs/a.md"],
    ],
)
def test_normalize_rejects_anything_outside_the_outputs_root(value):
    with pytest.raises(ValueError):
        normalize_report_artifact_path(value)


def test_the_outputs_root_constant_matches_the_gateway_virtual_prefix():
    """索引里存的路径必须与 Gateway artifact 路由认得的虚拟前缀逐字一致。"""

    assert ANALYSIS_REPORT_ARTIFACT_ROOT == "/mnt/user-data/outputs/"


def test_the_first_path_segment_may_not_look_like_the_root():
    """`outputs` 前缀比较必须按完整段做，不能是字符串前缀包含。"""

    with pytest.raises(ValueError):
        normalize_report_artifact_path("/mnt/user-data/outputs/../outputs/a.md")


def test_the_artifact_path_is_bounded():
    prefix = ANALYSIS_REPORT_ARTIFACT_ROOT
    assert normalize_report_artifact_path(prefix + "a" * (MAX_REPORT_ARTIFACT_PATH_CHARACTERS - len(prefix)))

    with pytest.raises(ValueError):
        normalize_report_artifact_path(prefix + "a" * (MAX_REPORT_ARTIFACT_PATH_CHARACTERS - len(prefix) + 1))


# --- evidence ids -----------------------------------------------------------


def test_evidence_ids_are_stored_as_an_immutable_tuple():
    report = _report(evidence_ids=(_HASH_A, _HASH_B))

    assert isinstance(report.evidence_ids, tuple)
    assert report.evidence_ids == (_HASH_A, _HASH_B)


def test_a_report_requires_at_least_one_evidence_id():
    """没有 evidence 的"分析报告"正是 Phase 3 要禁止的无依据数字。"""

    with pytest.raises(ValueError):
        _report(evidence_ids=())


def test_evidence_ids_accept_the_documented_upper_bound():
    report = _report(evidence_ids=tuple(f"{index:064x}" for index in range(MAX_REPORT_EVIDENCE_IDS)))

    assert len(report.evidence_ids) == MAX_REPORT_EVIDENCE_IDS


def test_evidence_ids_reject_more_than_the_upper_bound():
    with pytest.raises(ValueError):
        _report(evidence_ids=tuple(f"{index:064x}" for index in range(MAX_REPORT_EVIDENCE_IDS + 1)))


def test_evidence_ids_reject_duplicates():
    with pytest.raises(ValueError):
        _report(evidence_ids=(_HASH_A, _HASH_A))


@pytest.mark.parametrize(
    "value",
    [
        "A" * 64,  # 大写
        "a" * 63,
        "a" * 65,
        "g" * 64,
        "sha256:" + "a" * 64,
        "",
        " " + "a" * 63,
    ],
)
def test_evidence_ids_reject_anything_that_is_not_a_lowercase_sha256(value):
    with pytest.raises(ValueError):
        _report(evidence_ids=(value,))


def test_evidence_ids_reject_a_mutable_sequence():
    """领域值必须是不可变的；调用方负责把模型传来的 list 规范化成 tuple。"""

    with pytest.raises(ValueError):
        _report(evidence_ids=[_HASH_A])


# --- 其它字段 ---------------------------------------------------------------


@pytest.mark.parametrize("field_name", ["id", "principal_id", "thread_id", "run_id"])
def test_identity_fields_must_be_non_empty_trimmed_strings(field_name):
    for bad in ("", "  ", " padded ", None, 42):
        with pytest.raises(ValueError):
            _report(**{field_name: bad})


@pytest.mark.parametrize("field_name", ["id", "principal_id", "thread_id", "run_id"])
def test_identity_fields_are_bounded(field_name):
    assert _report(**{field_name: "x" * 64})
    with pytest.raises(ValueError):
        _report(**{field_name: "x" * 65})


def test_title_must_be_a_bounded_trimmed_single_line():
    assert _report(title="分" * MAX_REPORT_TITLE_CHARACTERS)

    with pytest.raises(ValueError):
        _report(title="分" * (MAX_REPORT_TITLE_CHARACTERS + 1))
    for bad in ("", "   ", " 标题", "标题 ", "两\n行", "含\x00空字节", "含\x07控制符", None):
        with pytest.raises(ValueError):
            _report(title=bad)


def test_status_must_be_a_report_status():
    with pytest.raises(ValueError):
        _report(status="published")


def test_created_at_must_be_aware():
    with pytest.raises(ValueError):
        _report(created_at=datetime(2026, 9, 22, 12, 0))

    with pytest.raises(ValueError):
        _report(created_at="2026-09-22T12:00:00Z")


def test_the_value_object_is_frozen():
    report = _report()

    with pytest.raises(FrozenInstanceError):
        report.title = "changed"  # type: ignore[misc]
