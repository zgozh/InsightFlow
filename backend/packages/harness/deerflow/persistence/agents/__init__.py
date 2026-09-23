"""Custom agent definition persistence — ORM model only.

Phase 5 删除了 Custom/Managed Agent 产品面：定义存储（抽象 store、file/db 后端与
`get_agent_store` 入口）随之删除，只保留 ORM model，因为 `Base.metadata` 的表集合
必须与 Alembic 历史链一致（见 `backend/tests/test_persistence_bootstrap.py`）。
"""

from __future__ import annotations

from deerflow.persistence.agents.model import AgentRow

__all__ = ["AgentRow"]
