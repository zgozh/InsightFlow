"""Analytics 独立 Alembic 环境（Phase 2C1）。

三条硬约束：

1. `target_metadata` 是 `AnalyticsBase.metadata`，**只**管理 `analytics_*` 表；
2. 版本表是 `analytics_alembic_version`，与 Harness 的 `alembic_version` 互不干涉；
3. 连接只能由调用方注入（`config.attributes["connection"]`）。这里绝不根据 DSN 另建
   engine —— 生产 bootstrap 必须复用应用数据库已经建立的连接，否则 search path、
   事务与 advisory lock 都会落到另一条会话上。

`include_object` 只放行 `analytics_*` 表与版本表：即便有人直接在本目录运行
`alembic revision --autogenerate`，Harness 的表也不会被反射成 `drop_table`。
"""

from __future__ import annotations

from alembic import context

from app.analytics.infrastructure.persistence.models import VERSION_TABLE_NAME, AnalyticsBase

config = context.config
target_metadata = AnalyticsBase.metadata


def _is_analytics_owned(name: object) -> bool:
    return isinstance(name, str) and (name == VERSION_TABLE_NAME or name.startswith("analytics_"))


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ARG001
    """只放行 Analytics 自己的表及其索引/约束。"""

    if type_ == "table":
        return _is_analytics_owned(name)
    parent_table = getattr(object_, "table", None)
    parent_name = getattr(parent_table, "name", None) if parent_table is not None else None
    if parent_name is not None:
        return _is_analytics_owned(parent_name)
    return True


def _configure(connection=None, **overrides) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE_NAME,
        include_object=include_object,
        # SQLite 的 ALTER 需要 batch 模式；这条链初始只有建表，但保持设置以免未来加列时踩坑。
        render_as_batch=True,
        **overrides,
    )


def run_migrations_offline() -> None:
    _configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("analytics alembic requires config.attributes['connection']: the Analytics chain never creates its own engine from a DSN")
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
