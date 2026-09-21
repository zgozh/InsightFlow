import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.application import ExecutionPlanStoreError, StoredExecutionPlan
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionLimits,
    PreparedQuery,
    QueryCostEstimate,
    QueryRisk,
)
from app.analytics.infrastructure import InMemoryExecutionPlanStore, SecurePlanTokenIssuer, SystemClock

_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
_DIGEST = "a" * 64


def _plan(*, digest=_DIGEST, principal_id="user-1", issued_at=_NOW, ttl_seconds=60):
    return StoredExecutionPlan(
        token_digest=digest,
        principal_id=principal_id,
        datasource=DatasourceDefinition(
            id="ds-1",
            owner_id="user-1",
            name="Warehouse",
            engine=DatasourceEngine.POSTGRESQL,
            secret_ref="env://ANALYTICS_DS",
            default_schema="public",
            status=DatasourceStatus.ACTIVE,
        ),
        authorized=AuthorizedQuerySpec(
            prepared=PreparedQuery(
                sql="SELECT id FROM orders LIMIT 10",
                engine=DatasourceEngine.POSTGRESQL,
                relations=("orders",),
                row_limit=10,
                query_hash="b" * 64,
            ),
            datasource_id="ds-1",
            principal_id="user-1",
            schema_version="s1",
            policy_version="p1",
            relations=("public.orders",),
            columns=("public.orders.id",),
            functions=(),
            risk=QueryRisk.LOW,
        ),
        estimate=QueryCostEstimate(
            engine=DatasourceEngine.POSTGRESQL,
            estimated_rows=10,
            engine_cost=Decimal("1"),
            plan_digest="c" * 64,
        ),
        limits=ExecutionLimits(
            connect_timeout_ms=5_000,
            statement_timeout_ms=10_000,
            cancellation_grace_ms=500,
            max_estimated_rows=100_000,
            max_engine_cost=Decimal("10000"),
            max_explain_bytes=1_048_576,
            max_result_columns=64,
            max_result_rows=10,
            max_result_bytes=4_194_304,
            plan_ttl_seconds=60,
        ),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )


def _store(max_entries=8):
    return InMemoryExecutionPlanStore(max_entries=max_entries)


# --- token 与时钟 -----------------------------------------------------------


def test_secure_plan_token_issuer_returns_high_entropy_distinct_tokens():
    issuer = SecurePlanTokenIssuer()

    first = issuer.issue()
    second = issuer.issue()

    # token_urlsafe(32) 的 32 字节熵编码后至少 32 个字符。
    assert isinstance(first, str)
    assert len(first) >= 32
    assert first != second


def test_system_clock_returns_timezone_aware_utc():
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_system_clock_now_is_monotonic_enough_for_ttl():
    clock = SystemClock()

    assert clock.now() <= clock.now()


# --- store 容量与冲突 -------------------------------------------------------


def test_store_requires_a_positive_capacity():
    with pytest.raises(ValueError):
        _store(max_entries=0)
    with pytest.raises(ValueError):
        _store(max_entries=True)


@pytest.mark.asyncio
async def test_store_puts_and_claims_a_plan_once():
    store = _store()
    await store.put(_plan())

    claimed = await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW)

    assert claimed is not None
    # 再次领取必须失败：token 是单次的。
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_store_rejects_a_duplicate_digest():
    store = _store()
    await store.put(_plan())

    with pytest.raises(ExecutionPlanStoreError):
        await store.put(_plan())


@pytest.mark.asyncio
async def test_store_rejects_a_plan_when_capacity_is_reached():
    store = _store(max_entries=1)
    await store.put(_plan(digest="a" * 64))

    with pytest.raises(ExecutionPlanStoreError):
        await store.put(_plan(digest="b" * 64))


@pytest.mark.asyncio
async def test_store_purges_expired_entries_before_the_capacity_check():
    store = _store(max_entries=1)
    await store.put(_plan(digest="a" * 64, issued_at=_NOW, ttl_seconds=60))

    # 60 秒后再写入：旧记录已过期，应先被惰性清理再占用容量。
    later = _NOW + timedelta(seconds=61)
    await store.put(_plan(digest="b" * 64, issued_at=later, ttl_seconds=60))

    assert await store.claim(token_digest="a" * 64, principal_id="user-1", now=later) is None
    assert await store.claim(token_digest="b" * 64, principal_id="user-1", now=later) is not None


@pytest.mark.asyncio
async def test_store_purge_expired_is_public_and_idempotent():
    store = _store()
    await store.put(_plan(ttl_seconds=60))

    await store.purge_expired(now=_NOW + timedelta(seconds=60))
    await store.purge_expired(now=_NOW + timedelta(seconds=60))

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_store_revoke_removes_the_plan_and_is_idempotent():
    # revoke 是「审计 finish 失败必须作废已插入 plan」的实现前提，两种 store 语义一致。
    store = _store()
    await store.put(_plan())

    await store.revoke(token_digest=_DIGEST)
    await store.revoke(token_digest=_DIGEST)

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_store_revoke_leaves_other_plans_untouched():
    store = _store()
    await store.put(_plan(digest="a" * 64))
    await store.put(_plan(digest="b" * 64))

    await store.revoke(token_digest="a" * 64)

    assert await store.claim(token_digest="a" * 64, principal_id="user-1", now=_NOW) is None
    assert await store.claim(token_digest="b" * 64, principal_id="user-1", now=_NOW) is not None


# --- 领取语义：统一不可用 ---------------------------------------------------


@pytest.mark.asyncio
async def test_store_returns_none_for_an_unknown_digest():
    store = _store()

    assert await store.claim(token_digest="f" * 64, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_store_expiry_boundary_is_inclusive_of_expiry():
    store = _store()
    await store.put(_plan(ttl_seconds=60))

    # 恰好到期即视为过期，避免边界上多给一个时钟刻度的能力。
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW + timedelta(seconds=60)) is None


@pytest.mark.asyncio
async def test_store_just_before_expiry_still_claims():
    store = _store()
    await store.put(_plan(ttl_seconds=60))

    claimed = await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW + timedelta(seconds=59, milliseconds=999))

    assert claimed is not None


@pytest.mark.asyncio
async def test_a_wrong_principal_consumes_the_token():
    store = _store()
    await store.put(_plan())

    assert await store.claim(token_digest=_DIGEST, principal_id="user-2", now=_NOW) is None
    # 错 principal 的尝试也必须消费记录，防止枚举后重试。
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_an_expired_token_is_consumed():
    store = _store()
    await store.put(_plan(ttl_seconds=60))
    later = _NOW + timedelta(seconds=120)

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=later) is None
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=later) is None


@pytest.mark.asyncio
async def test_a_successful_claim_consumes_the_token():
    store = _store()
    await store.put(_plan())

    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is not None
    assert await store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) is None


@pytest.mark.asyncio
async def test_one_hundred_concurrent_claims_yield_exactly_one_winner():
    store = _store()
    await store.put(_plan())

    results = await asyncio.gather(*(store.claim(token_digest=_DIGEST, principal_id="user-1", now=_NOW) for _ in range(100)))

    assert sum(result is not None for result in results) == 1


@pytest.mark.asyncio
async def test_concurrent_puts_of_the_same_digest_yield_exactly_one_winner():
    store = _store()

    results = await asyncio.gather(*(store.put(_plan()) for _ in range(50)), return_exceptions=True)

    assert sum(isinstance(result, ExecutionPlanStoreError) for result in results) == 49


@pytest.mark.asyncio
async def test_store_keeps_plans_private_to_their_digest():
    store = _store()
    await store.put(_plan(digest="a" * 64))
    await store.put(_plan(digest="b" * 64, principal_id="user-2"))

    assert await store.claim(token_digest="b" * 64, principal_id="user-2", now=_NOW) is not None
    assert await store.claim(token_digest="a" * 64, principal_id="user-1", now=_NOW) is not None


@pytest.mark.asyncio
async def test_store_rejects_a_plan_with_a_non_hex_digest():
    with pytest.raises(ValueError):
        replace(_plan(), token_digest="not-a-digest")
