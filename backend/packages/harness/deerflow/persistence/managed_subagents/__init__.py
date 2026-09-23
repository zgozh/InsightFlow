"""Deployment-level managed subagent persistence — ORM model only.

Phase 5 删除了 Custom/Managed Agent 产品面：managed subagent 的 store 抽象与
file/db 后端随之删除，只保留 ORM model 以维持 `Base.metadata` 与 Alembic 历史链一致。
"""

from __future__ import annotations

from deerflow.persistence.managed_subagents.model import ManagedSubagentRow

__all__ = ["ManagedSubagentRow"]
