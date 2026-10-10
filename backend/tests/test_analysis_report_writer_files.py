"""有界分析报告 writer 的合成文件系统契约。"""

from __future__ import annotations

import asyncio
import stat
from types import SimpleNamespace

import pytest
from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway import path_utils
from app.gateway.analysis_report_writer import AnalysisReportWriterCapability, create_analysis_report_writer_capability
from app.gateway.routers import artifacts as artifacts_router
from deerflow.config import paths as paths_module
from deerflow.config.paths import Paths


def _capability(monkeypatch, tmp_path, *, run_id="run_1"):
    paths = Paths(tmp_path)
    monkeypatch.setattr(paths_module, "get_paths", lambda: paths)
    monkeypatch.setattr(path_utils, "get_paths", lambda: paths)
    return create_analysis_report_writer_capability(
        principal_id="synthetic-user",
        thread_id="thread_1",
        run_id=run_id,
        paths=paths,
    )


@pytest.mark.asyncio
async def test_report_writer_is_create_only_and_same_body_is_idempotent(monkeypatch, tmp_path):
    writer = _capability(monkeypatch, tmp_path)
    markdown = "# 合成报告\n\nSQL_SENTINEL remains in the owner-only artifact.\n"

    first = await writer.write_markdown(markdown)
    retry = await writer.write_markdown(markdown)
    conflict = await writer.write_markdown("# Different report\n")

    assert first.code == "published"
    assert retry.code == "existing"
    assert conflict.code == "report_conflict"
    assert first.path == "/mnt/user-data/outputs/analysis-report-run_1.md"
    host_path = writer.output_path
    assert host_path.read_text(encoding="utf-8") == markdown


@pytest.mark.asyncio
async def test_report_writer_serializes_concurrent_create_only_attempts(monkeypatch, tmp_path):
    writer = _capability(monkeypatch, tmp_path)

    same_body = await asyncio.gather(
        writer.write_markdown("# Same\n"),
        writer.write_markdown("# Same\n"),
    )
    assert sorted(result.code for result in same_body) == ["existing", "published"]

    other_run = _capability(monkeypatch, tmp_path, run_id="run_2")
    conflicting = await asyncio.gather(
        other_run.write_markdown("# First\n"),
        other_run.write_markdown("# Second\n"),
    )
    assert sorted(result.code for result in conflicting) == ["published", "report_conflict"]
    assert other_run.output_path.read_text(encoding="utf-8") in {"# First\n", "# Second\n"}


@pytest.mark.asyncio
async def test_report_writer_rejects_nul_invalid_utf8_and_oversize_without_creating_artifact(monkeypatch, tmp_path):
    writer = _capability(monkeypatch, tmp_path)

    for invalid in ("contains\x00nul", "\ud800", "x" * (2 * 1024 * 1024 + 1)):
        result = await writer.write_markdown(invalid)
        assert result.code == "invalid_request"

    assert not writer.output_path.exists()


def test_report_writer_binds_authenticated_owner_thread_and_run(tmp_path):
    writer = create_analysis_report_writer_capability(
        principal_id="synthetic-user",
        thread_id="thread_1",
        run_id="run_1",
        paths=Paths(tmp_path),
    )

    assert writer.matches("synthetic-user", "thread_1", "run_1")
    assert not writer.matches("another-user", "thread_1", "run_1")
    assert not writer.matches("synthetic-user", "another-thread", "run_1")
    assert not writer.matches("synthetic-user", "thread_1", "run_2")


@pytest.mark.parametrize("run_id", ["../outside", "run/escape", "", "a" * 65])
def test_report_writer_rejects_untrusted_run_path_components(tmp_path, run_id):
    with pytest.raises(ValueError, match="analysis_report_writer_unavailable"):
        create_analysis_report_writer_capability(
            principal_id="synthetic-user",
            thread_id="thread_1",
            run_id=run_id,
            paths=Paths(tmp_path),
        )


@pytest.mark.asyncio
async def test_report_writer_rejects_existing_symlink_without_touching_target(monkeypatch, tmp_path):
    writer = _capability(monkeypatch, tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside sentinel", encoding="utf-8")
    writer.output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        writer.output_path.symlink_to(outside)
    except OSError:
        pytest.skip("当前平台无法创建 symlink")

    result = await writer.write_markdown("outside sentinel")

    assert result.code == "analysis_report_unavailable"
    assert result.path is None
    assert outside.read_text(encoding="utf-8") == "outside sentinel"


def test_report_writer_never_opens_existing_symlink_destination(monkeypatch, tmp_path):
    symlink_stat = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
    monkeypatch.setattr("app.gateway.analysis_report_writer.os.lstat", lambda _path: symlink_stat)
    monkeypatch.setattr(
        "app.gateway.analysis_report_writer.os.open",
        lambda *_args, **_kwargs: pytest.fail("the writer must reject a symlink before opening it"),
    )

    assert not AnalysisReportWriterCapability._existing_file_matches(tmp_path / "report.md", b"synthetic")


@pytest.mark.asyncio
async def test_report_writer_rejects_resolved_path_outside_its_fixed_target(monkeypatch, tmp_path):
    writer = _capability(monkeypatch, tmp_path)
    outside = tmp_path / "outside.md"
    monkeypatch.setattr(path_utils, "resolve_outputs_confined_path", lambda *_args, **_kwargs: outside)

    result = await writer.write_markdown("synthetic")

    assert result.code == "analysis_report_unavailable"
    assert result.path is None
    assert not outside.exists()


@pytest.mark.asyncio
async def test_published_report_is_readable_through_owner_scoped_artifact_get(monkeypatch, tmp_path):
    paths = Paths(tmp_path)
    monkeypatch.setattr(paths_module, "get_paths", lambda: paths)
    monkeypatch.setattr(path_utils, "get_paths", lambda: paths)
    monkeypatch.setattr(path_utils, "get_effective_user_id", lambda: "synthetic-user")
    monkeypatch.setattr(artifacts_router, "get_trusted_internal_owner_user_id", lambda _request: None)

    writer = create_analysis_report_writer_capability(
        principal_id="synthetic-user",
        thread_id="thread_1",
        run_id="run_1",
        paths=paths,
    )
    markdown = "# Synthetic analysis\n\nNo real business data.\n"
    result = await writer.write_markdown(markdown)
    assert result.code == "published"

    app = make_authed_test_app()
    app.include_router(artifacts_router.router)
    with TestClient(app) as client:
        response = client.get("/api/threads/thread_1/artifacts/mnt/user-data/outputs/analysis-report-run_1.md")
        cross_thread = client.get("/api/threads/other_thread/artifacts/mnt/user-data/outputs/analysis-report-run_1.md")

    assert response.status_code == 200
    assert response.text == markdown
    assert response.headers["content-type"].split(";", 1)[0].startswith("text/")
    assert cross_thread.status_code == 404
