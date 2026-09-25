"""受认证线程与运行绑定的 Markdown 报告文件写入能力。"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app.gateway import path_utils
from deerflow.config.paths import Paths, get_paths
from deerflow.constants import ANALYSIS_REPORT_STAGING_DIRNAME
from deerflow.utils.file_io import run_file_io

MAX_ANALYSIS_REPORT_BYTES = 2 * 1024 * 1024
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_OUTPUTS_VIRTUAL_ROOT = "/mnt/user-data/outputs"


@dataclass(frozen=True, slots=True)
class AnalysisReportWriteResult:
    """文件写入的稳定结果，不携带文件正文或系统异常文本。"""

    code: str
    path: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisReportWriterCapability:
    """只写当前 run 唯一固定 Markdown 路径的 Gateway 能力。"""

    principal_id: str
    thread_id: str
    run_id: str
    _paths: Paths
    _output_root: Path

    @property
    def virtual_path(self) -> str:
        return f"{_OUTPUTS_VIRTUAL_ROOT}/analysis-report-{self.run_id}.md"

    @property
    def output_path(self) -> Path:
        return self._output_root / f"analysis-report-{self.run_id}.md"

    def matches(self, principal_id: str, thread_id: str, run_id: str) -> bool:
        """确认工具运行时身份与 Gateway 创建能力时绑定的身份逐字一致。"""

        return (principal_id, thread_id, run_id) == (self.principal_id, self.thread_id, self.run_id)

    async def write_markdown(self, markdown: str) -> AnalysisReportWriteResult:
        """UTF-8 校验后 create-only 写入；相同字节可重试，异文绝不覆盖。"""

        if not isinstance(markdown, str) or "\x00" in markdown:
            return AnalysisReportWriteResult("invalid_request")
        try:
            body = markdown.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            return AnalysisReportWriteResult("invalid_request")
        if len(body) > MAX_ANALYSIS_REPORT_BYTES:
            return AnalysisReportWriteResult("invalid_request")

        try:
            code = await run_file_io(self._write_create_only, body)
        except (HTTPException, OSError, ValueError, RuntimeError):
            return AnalysisReportWriteResult("analysis_report_unavailable")
        except Exception:  # noqa: BLE001 - 对外只返回稳定失败码
            return AnalysisReportWriteResult("analysis_report_unavailable")
        return AnalysisReportWriteResult(code, self.virtual_path if code in {"published", "existing"} else None)

    def _write_create_only(self, body: bytes) -> str:
        """在专用 file-I/O 池内完成完整暂存与原子 no-overwrite 发布。"""

        raw_root = self._paths.sandbox_outputs_dir(self.thread_id, user_id=self.principal_id)
        raw_root.mkdir(parents=True, exist_ok=True)
        if raw_root.is_symlink() or not raw_root.is_dir() or raw_root.resolve(strict=True) != self._output_root:
            raise ValueError("analysis_report_outputs_root_invalid")

        virtual_path = self.virtual_path
        destination = path_utils.resolve_outputs_confined_path(
            self.thread_id,
            virtual_path,
            user_id=self.principal_id,
        )
        expected_path = self.output_path
        if destination != expected_path or destination.parent != self._output_root:
            raise HTTPException(status_code=400, detail="analysis_report_path_invalid")

        staging_dir = self._output_root / ANALYSIS_REPORT_STAGING_DIRNAME
        try:
            staging_dir.mkdir(mode=0o700, exist_ok=True)
        except FileExistsError:
            pass
        staging_stat = os.lstat(staging_dir)
        if not stat.S_ISDIR(staging_stat.st_mode) or stat.S_ISLNK(staging_stat.st_mode):
            raise ValueError("analysis_report_staging_invalid")
        if os.name != "nt":
            os.chmod(staging_dir, 0o700)

        descriptor, temporary_name = tempfile.mkstemp(prefix="report-", suffix=".part", dir=staging_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as staged:
                staged.write(body)
                staged.flush()
                os.fsync(staged.fileno())

            # 同目录硬链接是原子 create-only 发布：若目标已存在，绝不跟随或替换它。
            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                if self._existing_file_matches(destination, body):
                    resolved_existing = path_utils.resolve_outputs_confined_path(
                        self.thread_id,
                        virtual_path,
                        user_id=self.principal_id,
                    )
                    if resolved_existing != expected_path:
                        raise HTTPException(status_code=400, detail="analysis_report_path_invalid")
                    return "existing"
                return "report_conflict"

            resolved_after_link = path_utils.resolve_outputs_confined_path(
                self.thread_id,
                virtual_path,
                user_id=self.principal_id,
            )
            if resolved_after_link != expected_path:
                raise HTTPException(status_code=400, detail="analysis_report_path_invalid")
            return "published"
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _existing_file_matches(path: Path, expected: bytes) -> bool:
        """只接受普通文件逐字节相同的重试，不读取 symlink 或特殊文件。"""

        try:
            path_before = os.lstat(path)
        except OSError:
            return False
        if not stat.S_ISREG(path_before.st_mode):
            return False

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError:
            return False
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or not os.path.samestat(path_before, before) or before.st_size != len(expected):
                return False
            chunks: list[bytes] = []
            remaining = len(expected) + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            try:
                path_after = os.lstat(path)
            except OSError:
                return False
            if not stat.S_ISREG(path_after.st_mode) or not os.path.samestat(path_after, after):
                return False
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                return False
            if (path_before.st_size, path_before.st_mtime_ns) != (path_after.st_size, path_after.st_mtime_ns):
                return False
            return b"".join(chunks) == expected
        finally:
            os.close(descriptor)


def create_analysis_report_writer_capability(
    *,
    principal_id: str,
    thread_id: str,
    run_id: str,
    paths: Paths | None = None,
) -> AnalysisReportWriterCapability:
    """由 Gateway 在认证持久线程和已创建 run 上下文中发行能力。"""

    if not isinstance(principal_id, str) or not principal_id or principal_id != principal_id.strip() or principal_id == "default" or not isinstance(thread_id, str) or not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("analysis_report_writer_unavailable")
    paths = paths or get_paths()
    try:
        output_root = paths.sandbox_outputs_dir(thread_id, user_id=principal_id).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        raise ValueError("analysis_report_writer_unavailable") from None
    return AnalysisReportWriterCapability(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        _paths=paths,
        _output_root=output_root,
    )


__all__ = [
    "MAX_ANALYSIS_REPORT_BYTES",
    "AnalysisReportWriteResult",
    "AnalysisReportWriterCapability",
    "create_analysis_report_writer_capability",
]
