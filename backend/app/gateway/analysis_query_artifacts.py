"""受当前 owner/thread/run 固定范围约束的查询结果 JSON 能力。"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.analytics.application.evidence_ports import StoredAnalysisEvidence
from app.analytics.domain.evidence import (
    MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES,
    canonical_json,
    validate_successful_query_result,
)
from app.gateway import path_utils
from deerflow.config.paths import Paths, get_paths
from deerflow.utils.file_io import run_file_io

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_OUTPUTS_VIRTUAL_ROOT = "/mnt/user-data/outputs"
_STAGING_DIRNAME = ".analysis-query-staging"
_MAX_PAYLOAD_BYTES = MAX_ANALYSIS_EVIDENCE_SNAPSHOT_BYTES + 64 * 1024


@dataclass(frozen=True, slots=True)
class AnalysisQueryArtifactCapability:
    """只能核验或 create-only 写入本 run 按 evidence ID 派生的 JSON。"""

    principal_id: str
    thread_id: str
    run_id: str
    _paths: Paths
    _output_root: Path

    def matches(self, principal_id: str, thread_id: str, run_id: str) -> bool:
        return (principal_id, thread_id, run_id) == (self.principal_id, self.thread_id, self.run_id)

    def virtual_path_for(self, evidence_id: str) -> str:
        if not isinstance(evidence_id, str) or not _SAFE_DIGEST.fullmatch(evidence_id):
            raise ValueError("analysis_evidence_unavailable")
        return f"{_OUTPUTS_VIRTUAL_ROOT}/query-result-{self.run_id}-{evidence_id}.json"

    async def write(self, record: StoredAnalysisEvidence) -> bool:
        """只写当前能力范围内的规范成功结果；相同字节重试幂等。"""

        try:
            body, virtual_path = self._record_bytes(record)
            return await run_file_io(self._write_create_only, virtual_path, body)
        except Exception:
            return False

    async def verify(self, record: StoredAnalysisEvidence) -> bool:
        """仅逐字节核验该记录对应的固定文件。"""

        try:
            body, virtual_path = self._record_bytes(record)
            return await run_file_io(self._verify_exact_file, virtual_path, body)
        except Exception:
            return False

    def _record_bytes(self, record: StoredAnalysisEvidence) -> tuple[bytes, str]:
        if not isinstance(record, StoredAnalysisEvidence) or not self.matches(record.principal_id, record.thread_id, record.run_id):
            raise ValueError("analysis_evidence_unavailable")
        evidence_id = record.evidence_id
        virtual_path = self.virtual_path_for(evidence_id)
        if record.artifact_path != virtual_path:
            raise ValueError("analysis_evidence_unavailable")
        validate_successful_query_result(record.result)
        try:
            body = canonical_json(record.result.to_payload()).encode("utf-8", errors="strict")
        except (UnicodeEncodeError, ValueError, TypeError):
            raise ValueError("analysis_evidence_unavailable") from None
        if len(body) > _MAX_PAYLOAD_BYTES:
            raise ValueError("analysis_evidence_unavailable")
        return body, virtual_path

    def _resolve_fixed_path(self, virtual_path: str) -> Path:
        raw_root = self._paths.sandbox_outputs_dir(self.thread_id, user_id=self.principal_id)
        raw_root.mkdir(parents=True, exist_ok=True)
        if raw_root.is_symlink() or not raw_root.is_dir() or raw_root.resolve(strict=True) != self._output_root:
            raise ValueError("analysis_query_outputs_root_invalid")
        destination = path_utils.resolve_outputs_confined_path(self.thread_id, virtual_path, user_id=self.principal_id)
        expected = self._output_root / Path(virtual_path).name
        if destination != expected or destination.parent != self._output_root:
            raise ValueError("analysis_query_path_invalid")
        return destination

    def _write_create_only(self, virtual_path: str, body: bytes) -> bool:
        destination = self._resolve_fixed_path(virtual_path)
        staging_dir = self._output_root / _STAGING_DIRNAME
        staging_dir.mkdir(mode=0o700, exist_ok=True)
        staging_stat = os.lstat(staging_dir)
        if not stat.S_ISDIR(staging_stat.st_mode) or stat.S_ISLNK(staging_stat.st_mode):
            raise ValueError("analysis_query_staging_invalid")
        if os.name != "nt":
            os.chmod(staging_dir, 0o700)

        descriptor, temporary_name = tempfile.mkstemp(prefix="query-", suffix=".part", dir=staging_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as staged:
                staged.write(body)
                staged.flush()
                os.fsync(staged.fileno())
            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                if not self._existing_file_matches(destination, body):
                    return False
                return self._resolve_fixed_path(virtual_path) == destination
            return self._resolve_fixed_path(virtual_path) == destination
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def _verify_exact_file(self, virtual_path: str, expected: bytes) -> bool:
        destination = self._resolve_fixed_path(virtual_path)
        return self._existing_file_matches(destination, expected)

    @staticmethod
    def _existing_file_matches(path: Path, expected: bytes) -> bool:
        """拒绝 symlink/特殊文件，并检测逐字节读取期间的替换或改写。"""

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
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                return False
            if (path_before.st_size, path_before.st_mtime_ns) != (path_after.st_size, path_after.st_mtime_ns):
                return False
            return b"".join(chunks) == expected
        finally:
            os.close(descriptor)


def create_analysis_query_artifact_capability(
    *,
    principal_id: str,
    thread_id: str,
    run_id: str,
    paths: Paths | None = None,
) -> AnalysisQueryArtifactCapability:
    """由 Gateway 在 analysis run admission 后签发固定范围文件能力。"""

    if (
        not isinstance(principal_id, str)
        or not principal_id
        or principal_id != principal_id.strip()
        or principal_id == "default"
        or not isinstance(thread_id, str)
        or not _SAFE_ID.fullmatch(thread_id)
        or not isinstance(run_id, str)
        or not _SAFE_ID.fullmatch(run_id)
    ):
        raise ValueError("analysis_query_artifact_unavailable")
    paths = paths or get_paths()
    try:
        output_root = paths.sandbox_outputs_dir(thread_id, user_id=principal_id).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        raise ValueError("analysis_query_artifact_unavailable") from None
    return AnalysisQueryArtifactCapability(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        _paths=paths,
        _output_root=output_root,
    )


__all__ = ["AnalysisQueryArtifactCapability", "create_analysis_query_artifact_capability"]
