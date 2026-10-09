"""Analytics 独立迁移链的 SQLite 测试（Phase 2C1 任务 3）。

这条链必须证明四件事：

1. 空库可以 `upgrade head`，重复执行是幂等的，且 downgrade/upgrade 可往返；
2. 它只管自己的 Analytics `analytics_*` 表与 `analytics_alembic_version`，绝不触碰 Harness
   的表或 `alembic_version`；
3. 未知 revision、空版本表、多版本行、有表无版本表一律 fail closed，绝不自动重建或重 stamp；
4. 迁移产出的表结构与 `AnalyticsBase.metadata` 逐列一致。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.infrastructure.persistence import bootstrap as _bootstrap_module
from app.analytics.infrastructure.persistence.bootstrap import bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.models import AnalyticsBase

_MIGRATIONS_DIR = Path(_bootstrap_module.__file__).parent / "migrations"
_VERSION_TABLE = "analytics_alembic_version"
# 与 `versions/0001_analytics_control_plane.py` 的 revision id 逐字一致。
_REVISION = "0001_analytics_control_plane"
# 与 `versions/0002_analytics_analysis_reports.py` 的 revision id 逐字一致。
_REVISION_0002 = "0002_analytics_analysis_reports"
_REVISION_0003 = "0003_analytics_query_evidence"
_REVISION_0004 = "0004_metric_grants"
_ANALYTICS_TABLES = (
    "analytics_access_policies",
    "analytics_analysis_reports",
    "analytics_datasources",
    "analytics_execution_plans",
    "analytics_metrics",
    "analytics_metric_grants",
    "analytics_query_audits",
    "analytics_query_evidence",
    "analytics_schema_snapshots",
)


def _engine(path):
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool, echo=False)


async def _bootstrap(engine) -> None:
    await bootstrap_analytics_schema(engine, backend="sqlite")


async def _run_alembic(engine, *, direction: str, revision: str = "head") -> None:
    """测试侧的迁移驱动：复用与 bootstrap 相同的「注入已有连接」约定。"""

    config = AlembicConfig()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))

    # SQLite 的 transactional_ddl 为 False：迁移事务必须由调用方提交。
    async with engine.begin() as conn:

        def _run(sync_conn):
            config.attributes["connection"] = sync_conn
            if direction == "upgrade":
                alembic_command.upgrade(config, revision)
            else:
                alembic_command.downgrade(config, revision)

        await conn.run_sync(_run)


async def _scalar(engine, sql: str):
    async with engine.connect() as conn:
        return (await conn.exec_driver_sql(sql)).scalar()


async def _execute(engine, sql: str) -> None:
    async with engine.begin() as conn:
        await conn.exec_driver_sql(sql)


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: set(sa_inspect(sync_conn).get_table_names()))


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: {column["name"] for column in sa_inspect(sync_conn).get_columns(table)})


async def _index_names(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: {index["name"] for index in sa_inspect(sync_conn).get_indexes(table)})


# --- 基本路径 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_creates_exactly_the_analytics_tables_from_an_empty_database(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)

        names = await _table_names(engine)
        assert set(_ANALYTICS_TABLES) <= names
        assert _VERSION_TABLE in names
        assert await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}") == _REVISION_0004
        # 这条链绝不创建 Harness 自己的版本表。
        assert "alembic_version" not in names
        # 空库直连 upgrade head，而不是 create_all + stamp 的捷径：结构与版本表都存在。
        assert await _scalar(engine, f"SELECT count(*) FROM {_VERSION_TABLE}") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_keeps_the_same_revision(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)
        first = await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}")

        await _bootstrap(engine)
        second = await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}")

        assert first == second
        assert first
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revision_0003_only_adds_evidence_and_preserves_0002_report_data(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _run_alembic(engine, direction="upgrade", revision=_REVISION_0002)
        await _execute(
            engine,
            "INSERT INTO analytics_analysis_reports "
            "(id, principal_id, thread_id, run_id, artifact_path, title, status, evidence_ids_json, created_at) "
            "VALUES ('old-report', 'user-1', 'thread-1', 'run-1', '/mnt/user-data/outputs/old.md', '旧报告', 'published', '[\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"]', '2026-10-07 12:00:00')",
        )
        before = await _table_names(engine)

        await _run_alembic(engine, direction="upgrade", revision=_REVISION_0003)

        assert await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}") == _REVISION_0003
        assert await _table_names(engine) - before == {"analytics_query_evidence"}
        assert await _scalar(engine, "SELECT id FROM analytics_analysis_reports") == "old-report"

        await _run_alembic(engine, direction="downgrade", revision=_REVISION_0002)
        assert "analytics_query_evidence" not in await _table_names(engine)
        assert await _scalar(engine, "SELECT id FROM analytics_analysis_reports") == "old-report"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revision_0004_only_adds_grants_and_preserves_metrics_and_evidence(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _run_alembic(engine, direction="upgrade", revision=_REVISION_0003)
        await _execute(
            engine,
            "INSERT INTO analytics_metrics "
            "(owner_id, key, name, description, expression, dimensions_json, version, status, created_at, updated_at) "
            "VALUES ('owner-1', 'revenue', 'Revenue', 'Total revenue', 'sum(amount)', '[]', 1, 'active', '2026-10-08 12:00:00', '2026-10-08 12:00:00')",
        )
        await _execute(
            engine,
            "INSERT INTO analytics_query_evidence "
            "(principal_id, thread_id, run_id, evidence_id, payload_version, payload_json, snapshot_bytes, artifact_path, created_at) "
            "VALUES ('user-1', 'thread-1', 'run-1', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 1, '{}', 2, '/mnt/user-data/outputs/evidence.json', '2026-10-08 12:00:00')",
        )
        before = await _table_names(engine)

        await _bootstrap(engine)

        assert await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}") == _REVISION_0004
        assert await _table_names(engine) - before == {"analytics_metric_grants"}
        assert await _scalar(engine, "SELECT key FROM analytics_metrics WHERE owner_id = 'owner-1'") == "revenue"
        assert await _scalar(engine, "SELECT run_id FROM analytics_query_evidence") == "run-1"
        await _execute(
            engine,
            "INSERT INTO analytics_metric_grants (metric_owner_id, metric_key, principal_id, created_at) VALUES ('owner-1', 'revenue', 'user-2', '2026-10-08 12:00:00')",
        )

        await _run_alembic(engine, direction="downgrade", revision=_REVISION_0003)
        assert "analytics_metric_grants" not in await _table_names(engine)
        assert await _scalar(engine, "SELECT key FROM analytics_metrics WHERE owner_id = 'owner-1'") == "revenue"
        assert await _scalar(engine, "SELECT run_id FROM analytics_query_evidence") == "run-1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_bootstrap_calls_serialize_on_one_engine(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await asyncio.gather(*(_bootstrap(engine) for _ in range(4)))

        assert await _scalar(engine, f"SELECT count(*) FROM {_VERSION_TABLE}") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_then_upgrade_round_trips(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)
        await _run_alembic(engine, direction="downgrade", revision="base")

        names = await _table_names(engine)
        assert not set(_ANALYTICS_TABLES) & names

        await _run_alembic(engine, direction="upgrade", revision="head")
        assert set(_ANALYTICS_TABLES) <= await _table_names(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase_4_report_table_is_a_pure_forward_addition(tmp_path):
    """Phase 4 的报告索引必须是纯前向迁移：停在 0001 的库升级到 head 只新增一张表。"""

    engine = _engine(tmp_path / "analytics.db")
    try:
        await _run_alembic(engine, direction="upgrade", revision=_REVISION)
        assert await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}") == _REVISION
        before = await _table_names(engine)
        assert "analytics_analysis_reports" not in before

        await _run_alembic(engine, direction="upgrade", revision=_REVISION_0002)

        after = await _table_names(engine)
        assert await _scalar(engine, f"SELECT version_num FROM {_VERSION_TABLE}") == _REVISION_0002
        assert after - before == {"analytics_analysis_reports"}

        # 单步 downgrade 只撤掉 0002，0001 的六张表原样保留。
        await _run_alembic(engine, direction="downgrade", revision=_REVISION)
        reverted = await _table_names(engine)
        assert "analytics_analysis_reports" not in reverted
        assert set(_ANALYTICS_TABLES) - {"analytics_analysis_reports", "analytics_query_evidence", "analytics_metric_grants"} <= reverted
    finally:
        await engine.dispose()


# --- 所有权边界 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_analytics_chain_never_touches_host_owned_tables(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        # 迁移之前先造一张「Harness 拥有」的表与它自己的版本表。
        await _execute(engine, "CREATE TABLE runs (run_id VARCHAR(64) PRIMARY KEY, status VARCHAR(16))")
        await _execute(engine, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        await _execute(engine, "INSERT INTO runs (run_id, status) VALUES ('run-1', 'running')")

        await _bootstrap(engine)

        assert await _scalar(engine, "SELECT status FROM runs WHERE run_id = 'run-1'") == "running"
        assert await _scalar(engine, "SELECT count(*) FROM alembic_version") == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migrated_tables_match_the_orm_metadata_column_for_column(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)

        for table_name, table in AnalyticsBase.metadata.tables.items():
            migrated = await _columns(engine, table_name)
            declared = {column.name for column in table.columns}
            assert migrated == declared, f"{table_name} drifted: {migrated ^ declared}"

            # 迁移必须建出 ORM 声明的每一条 ix_* 索引。
            declared_indexes = {index.name for index in table.indexes}
            assert declared_indexes <= await _index_names(engine, table_name), f"{table_name} is missing {declared_indexes - await _index_names(engine, table_name)}"
    finally:
        await engine.dispose()


# --- fail closed ------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_revision_is_rejected(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)
        await _execute(engine, f"UPDATE {_VERSION_TABLE} SET version_num = 'nope_not_a_revision'")

        with pytest.raises(RuntimeError, match="revision_unknown"):
            await _bootstrap(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_empty_version_table_is_rejected(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        await _bootstrap(engine)
        await _execute(engine, f"DELETE FROM {_VERSION_TABLE}")

        with pytest.raises(RuntimeError, match="version_table_empty"):
            await _bootstrap(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_multiple_version_rows_are_rejected(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        # Alembic 自建的版本表在 version_num 上有主键，塞不进第二行；这里手工造一个
        # 无主键的版本表来构造「多版本行」这个必须 fail closed 的状态。
        await _execute(engine, f"CREATE TABLE {_VERSION_TABLE} (version_num VARCHAR(32) NOT NULL)")
        await _execute(engine, f"INSERT INTO {_VERSION_TABLE} (version_num) VALUES ('{_REVISION}')")
        await _execute(engine, f"INSERT INTO {_VERSION_TABLE} (version_num) VALUES ('{_REVISION}')")

        with pytest.raises(RuntimeError, match="multiple_versions"):
            await _bootstrap(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_analytics_tables_without_a_version_table_are_rejected(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        # 只建表、不建版本表：这正是「未知来源的 analytics 表」形态，不能自动 stamp。
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: AnalyticsBase.metadata.create_all(sync_conn))

        with pytest.raises(RuntimeError, match="without_version_table"):
            await _bootstrap(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_rejects_an_unknown_backend(tmp_path):
    engine = _engine(tmp_path / "analytics.db")
    try:
        with pytest.raises(ValueError):
            await bootstrap_analytics_schema(engine, backend="mysql")
    finally:
        await engine.dispose()


# --- env.py 约定 ------------------------------------------------------------


def test_analytics_env_uses_its_own_version_table_and_a_supplied_connection():
    """env.py 不能被 import（会直接驱动 alembic），所以按源码固定它的约定。"""

    env_py = Path(_MIGRATIONS_DIR) / "env.py"
    source = env_py.read_text(encoding="utf-8")

    assert "analytics_alembic_version" in source
    assert 'attributes.get("connection")' in source
    # 生产 bootstrap 不得由 DSN 另建 engine。
    assert "create_async_engine" not in source
    assert "create_engine" not in source


def test_analytics_alembic_ini_has_no_hardcoded_url():
    ini = (Path(_MIGRATIONS_DIR) / "alembic.ini").read_text(encoding="utf-8")

    assert "%(here)s" in ini
    assert "postgresql://" not in ini and "sqlite:///" not in ini
