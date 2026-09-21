import asyncio
import secrets
from datetime import UTC, datetime

from app.analytics.application import ExecutionPlanStoreError, StoredExecutionPlan


class SecurePlanTokenIssuer:
    """生产 token 发行者：32 字节 URL-safe 熵。"""

    def issue(self) -> str:
        return secrets.token_urlsafe(32)


class SystemClock:
    """生产时钟：时区感知 UTC。测试通过 Clock 端口注入确定性时间，不 monkeypatch 全局时间。"""

    def now(self) -> datetime:
        return datetime.now(UTC)


class InMemoryExecutionPlanStore:
    """进程内单次 plan store（Phase 2B2 范围）。

    明确的边界：不跨进程、不跨重启、不启动后台清理线程。Phase 2C 在对外暴露 plan 之前
    必须换成基于应用持久化数据库的原子 claim 实现，并补充多 worker 竞争测试。

    put/claim/purge 全部由同一个 ``asyncio.Lock`` 保护：claim 的「校验并删除」必须是一个
    临界区，否则并发请求可以同时通过校验拿到同一份能力。
    """

    def __init__(self, *, max_entries: int) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self._max_entries = max_entries
        self._plans: dict[str, StoredExecutionPlan] = {}
        self._lock = asyncio.Lock()

    def _purge_expired_locked(self, now: datetime) -> None:
        expired = [digest for digest, plan in self._plans.items() if plan.expires_at <= now]
        for digest in expired:
            del self._plans[digest]

    async def put(self, plan: StoredExecutionPlan) -> None:
        async with self._lock:
            # 容量判断前先清理过期项，避免过期记录长期占用容量。
            self._purge_expired_locked(plan.issued_at)
            if plan.token_digest in self._plans:
                raise ExecutionPlanStoreError("digest_conflict")
            if len(self._plans) >= self._max_entries:
                raise ExecutionPlanStoreError("capacity_exceeded")
            self._plans[plan.token_digest] = plan

    async def claim(self, *, token_digest: str, principal_id: str, now: datetime) -> StoredExecutionPlan | None:
        async with self._lock:
            plan = self._plans.pop(token_digest, None)
            if plan is None:
                return None
            # 摘要匹配即消费记录：错 principal 或已过期的探测同样消耗能力，防止枚举后重试。
            if plan.expires_at <= now or plan.principal_id != principal_id:
                return None
            return plan

    async def purge_expired(self, *, now: datetime) -> None:
        async with self._lock:
            self._purge_expired_locked(now)
