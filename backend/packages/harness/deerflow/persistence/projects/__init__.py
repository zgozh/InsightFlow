"""Project persistence — ORM models + the assignment error.

Phase 5 删除了 Projects/Documents/Trash 产品面：repository 实现随之删除，只保留
ORM model 以维持 `Base.metadata` 与 Alembic 历史链一致。

`ProjectNotAssignableError` 仍然保留，因为 thread_meta 的 `project_id` 列
（`threads_meta.project_id`，由 0020 迁移建立）在写入一个不存在的 project 时
必须继续抛同一个类型；删除它会把这条例外路径变成 ImportError。
"""

from __future__ import annotations

from deerflow.persistence.projects.model import ProjectDocumentRow, ProjectRow


class ProjectNotAssignableError(ValueError):
    """Raised when a thread cannot be assigned to a project.

    The project is missing, foreign to the caller, or archived — the
    atomicity rules (RFC v2 §5.2) make these indistinguishable inside the
    mutating statement, so callers get one signal and map it to 404 (explicit
    API) or a dropped key (run admission).
    """

    def __init__(self, project_id: str) -> None:
        super().__init__(f"project_not_assignable:{project_id}")
        self.project_id = project_id


__all__ = ["ProjectDocumentRow", "ProjectNotAssignableError", "ProjectRow"]
