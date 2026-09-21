"""MySQL runtime 测试：fake connection 单元测试 + 真实 MySQL 8.4 集成测试。

本文件刻意承载两类测试：

- 不依赖 Docker 的单元测试固定 `@@lower_case_table_names` 门禁、session 超时与 `START TRANSACTION
  READ ONLY` 的命令顺序、JSON v1 计划解析（顶层 `query_block.cost_info.query_cost` + 递归行数求和）
  以及每一条拒绝路径。这些测试在任何环境都必须通过。
- 集成测试只在 `ANALYTICS_TEST_MYSQL=1` 时运行（由 `scripts/test_analytics_databases.py` 注入），
  证明真实 MySQL 8.4 上的只读事务、`MAX_EXECUTION_TIME`、取消后 processlist 无残留、流式截断与错误脱敏。

计划摘要的期望值不调用生产 helper：规范化规则（UTF-8、`ensure_ascii=False`、紧凑分隔符、`sort_keys`）
在本文件里重写一遍，避免"规则被改坏"和"测试跟着改坏"同时发生。
"""

import asyncio
import hashlib
import json
import os
import time
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.analytics.application import DatasourceQueryError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceEngine,
    ExecutionDecisionCode,
    ExecutionLimits,
    PreparedQuery,
    QueryRisk,
)
from app.analytics.infrastructure.mysql_runtime import MySQLRuntime

_INTEGRATION_ENV = "ANALYTICS_TEST_MYSQL"

_APPROVED_SQL = "SELECT id FROM orders LIMIT 10"

_PLAN_TEXT = """{
  "query_block": {
    "select_id": 1,
    "cost_info": {"query_cost": "12.35"},
    "table": {
      "table_name": "orders",
      "access_type": "ALL",
      "rows_examined_per_scan": 420,
      "rows_produced_per_join": 420,
      "filtered": "100.00",
      "cost_info": {"read_cost": "1.00", "eval_cost": "84.00", "prefix_cost": "85.00", "data_read_per_join": "6K"}
    }
  }
}"""


def _canonical_digest(document: object) -> str:
    """测试侧独立实现的规范化摘要：规则写死在本文件里，不借用生产 helper。"""

    canonical = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _limits(**overrides: Any) -> ExecutionLimits:
    values: dict[str, Any] = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 250,
        "cancellation_grace_ms": 100,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 8,
        "max_result_rows": 3,
        "max_result_bytes": 262_144,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def _authorized(sql: str = _APPROVED_SQL) -> AuthorizedQuerySpec:
    return AuthorizedQuerySpec(
        prepared=PreparedQuery(sql=sql, engine=DatasourceEngine.MYSQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
        datasource_id="ds-1",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=("analytics.orders",),
        columns=("analytics.orders.id",),
        functions=(),
        risk=QueryRisk.LOW,
    )


class _FakeResult:
    """驱动结果替身：只暴露 adapter 允许访问的成员。"""

    def __init__(self, *, columns: tuple[str, ...] = ("EXPLAIN",), rows: tuple[tuple[object, ...], ...] = ()) -> None:
        self._columns = columns
        self._rows = rows

    def keys(self) -> list[str]:
        return list(self._columns)

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def __aiter__(self):
        async def _iterate():
            for row in self._rows:
                yield row

        return _iterate()


class _FakeStreamContext:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def __aenter__(self) -> Any:
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeTransaction:
    def __init__(self, connection: "_FakeConnection") -> None:
        self._connection = connection
        self.rolled_back = 0

    async def rollback(self) -> None:
        self.rolled_back += 1
        self._connection.events.append("rollback")


class _FakeConnection:
    """可观测 AsyncConnection 替身：记录控制语句顺序，并把队列里的异常原样抛出。"""

    def __init__(self, *, results: tuple[object, ...] = (), stream_result: object | None = None) -> None:
        self.events: list[str] = []
        self.stream_calls: list[str] = []
        self.invalidated = 0
        self.transactions: list[_FakeTransaction] = []
        self._results = list(results)
        self._stream_result = stream_result

    async def begin(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self)
        self.transactions.append(transaction)
        self.events.append("begin")
        return transaction

    async def exec_driver_sql(self, statement: object, parameters: object = None, execution_options: object = None) -> Any:
        self.events.append(str(statement))
        if not self._results:
            raise AssertionError(f"unexpected statement: {statement}")
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def stream(self, statement: object, parameters: object = None, *, execution_options: object = None) -> _FakeStreamContext:
        self.stream_calls.append(str(statement))
        self.events.append(str(statement))
        return _FakeStreamContext(self._stream_result)

    async def invalidate(self) -> None:
        self.invalidated += 1


class _DriverError(Exception):
    """带 MySQL 错误号的驱动异常替身；3024 是 MAX_EXECUTION_TIME 超时。"""

    def __init__(self, message: str, *, errno_code: int | None = None) -> None:
        if errno_code is None:
            super().__init__(message)
        else:
            super().__init__(errno_code, message)


def _mode_result(value: object = 0) -> _FakeResult:
    return _FakeResult(columns=("@@lower_case_table_names",), rows=((value,),))


def _explain_connection(plan_text: str = _PLAN_TEXT, *, mode: object = 0, **overrides: Any) -> _FakeConnection:
    return _FakeConnection(results=(_mode_result(mode), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=((plan_text,),))), **overrides)


async def _run_explain(connection: _FakeConnection, **limit_overrides: Any):
    return await MySQLRuntime().explain(connection=connection, authorized=_authorized(), limits=_limits(**limit_overrides))


# ---------------------------------------------------------------------------
# fake connection 单元测试：大小写模式门禁、命令顺序与拒绝路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explain_reads_the_identifier_mode_then_sets_timeout_read_only_and_explains():
    connection = _explain_connection()

    estimate = await _run_explain(connection)

    assert connection.events == [
        "begin",
        "SELECT @@lower_case_table_names",
        "SET SESSION MAX_EXECUTION_TIME = 250",
        "START TRANSACTION READ ONLY",
        f"EXPLAIN FORMAT=JSON {_APPROVED_SQL}",
        "rollback",
    ]
    assert estimate.engine is DatasourceEngine.MYSQL
    assert estimate.engine_cost == Decimal("12.35")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [1, 2, None, "0", 0.0, True])
async def test_explain_rejects_every_identifier_mode_except_zero(mode: object):
    connection = _explain_connection(mode=mode)

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE
    # 拒绝必须发生在任何业务 SQL 之前：门禁失效时不能有 EXPLAIN 已经跑过。
    assert not any(event.startswith("EXPLAIN") for event in connection.events)
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_explain_rejects_an_unreadable_identifier_mode():
    connection = _FakeConnection(results=(_DriverError("SHOW VARIABLES denied for user"),))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE
    assert not any(event.startswith("EXPLAIN") for event in connection.events)


@pytest.mark.asyncio
async def test_explain_never_emits_explain_analyze():
    connection = _explain_connection()

    await _run_explain(connection)

    executed = " ".join(connection.events).upper()
    assert "ANALYZE" not in executed
    assert connection.events[4] == f"EXPLAIN FORMAT=JSON {_APPROVED_SQL}"


@pytest.mark.asyncio
async def test_explain_sums_nested_work_rows_and_parses_the_top_level_cost():
    connection = _explain_connection()

    estimate = await _run_explain(connection)

    assert estimate.estimated_rows == 840
    assert estimate.engine_cost == Decimal("12.35")
    assert estimate.plan_digest == _canonical_digest(json.loads(_PLAN_TEXT))


@pytest.mark.asyncio
async def test_explain_sums_rows_across_nested_loops_and_subqueries():
    plan = {
        "query_block": {
            "select_id": 1,
            "cost_info": {"query_cost": "9.00"},
            "nested_loop": [
                {"table": {"table_name": "a", "rows_examined_per_scan": 10, "rows_produced_per_join": 5}},
                {"table": {"table_name": "b", "rows_examined_per_scan": 20}},
            ],
            "subqueries": [{"query_block": {"select_id": 2, "cost_info": {"query_cost": "1.00"}, "table": {"table_name": "c", "rows_produced_per_join": 7}}}],
        }
    }
    connection = _explain_connection(json.dumps(plan))

    estimate = await _run_explain(connection)

    assert estimate.estimated_rows == 42
    assert estimate.engine_cost == Decimal("9.00")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan",
    [
        # 顶层 query_block 缺失
        {"message": "No tables used"},
        # cost_info 缺失：绝不填零
        {"query_block": {"select_id": 1, "message": "No tables used"}},
        {"query_block": {"select_id": 1, "cost_info": {}, "table": {"table_name": "t"}}},
        # cost 非有限 / 负数 / 非数值
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "NaN"}}},
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "-1.00"}}},
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": True}}},
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "abc"}}},
        # 行数字段出现但非法
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "1.00"}, "table": {"rows_examined_per_scan": None}}},
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "1.00"}, "table": {"rows_examined_per_scan": -3}}},
        {"query_block": {"select_id": 1, "cost_info": {"query_cost": "1.00"}, "table": {"rows_produced_per_join": "many"}}},
    ],
)
async def test_explain_rejects_a_missing_or_non_finite_cost(plan: dict[str, Any]):
    connection = _explain_connection(json.dumps(plan))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_explain_rejects_a_plan_over_the_byte_budget():
    connection = _explain_connection()

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection, max_explain_bytes=32)

    assert caught.value.code is ExecutionDecisionCode.COST_LIMIT_EXCEEDED
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_explain_rejects_a_result_set_that_is_not_a_single_row():
    connection = _FakeConnection(results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=((_PLAN_TEXT,), (_PLAN_TEXT,)))))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED


@pytest.mark.asyncio
async def test_explain_maps_the_server_execution_timeout_to_execution_timeout():
    connection = _FakeConnection(results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _DriverError("Query execution was interrupted", errno_code=3024)))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
    assert connection.invalidated >= 1


@pytest.mark.asyncio
async def test_explain_maps_an_unexpected_driver_failure_without_leaking_text():
    connection = _FakeConnection(results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _DriverError(f"Access denied for user 'analytics'@'127.0.0.1' running {_APPROVED_SQL}")))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
    rendered = f"{caught.value!r} {caught.value}"
    assert _APPROVED_SQL not in rendered
    assert "127.0.0.1" not in rendered
    assert connection.invalidated >= 1


@pytest.mark.asyncio
async def test_execute_streams_the_approved_sql_unchanged_and_rolls_back():
    connection = _FakeConnection(
        results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_FakeResult(columns=("id", "name"), rows=((1, "a"), (2, "b"))),
    )

    result = await MySQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert connection.events == [
        "begin",
        "SELECT @@lower_case_table_names",
        "SET SESSION MAX_EXECUTION_TIME = 250",
        "START TRANSACTION READ ONLY",
        _APPROVED_SQL,
        "rollback",
    ]
    assert connection.stream_calls == [_APPROVED_SQL]
    assert result.rows == ((1, "a"), (2, "b"))
    assert result.truncated is False


@pytest.mark.asyncio
async def test_execute_truncates_a_stream_that_exceeds_the_row_budget():
    connection = _FakeConnection(
        results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_FakeResult(columns=("id",), rows=((1,), (2,), (3,), (4,), (5,))),
    )

    result = await MySQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits(max_result_rows=3))

    assert result.row_count == 3
    assert result.truncated is True
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_execute_refuses_to_run_before_the_identifier_gate_passes():
    connection = _FakeConnection(results=(_mode_result(1),), stream_result=_FakeResult(columns=("id",), rows=((1,),)))

    with pytest.raises(DatasourceQueryError) as caught:
        await MySQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE
    assert connection.stream_calls == []


@pytest.mark.asyncio
async def test_execute_maps_the_server_execution_timeout_and_destroys_the_connection():
    connection = _FakeConnection(
        results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_DriverError("Query execution was interrupted", errno_code=3024),
    )

    with pytest.raises(DatasourceQueryError) as caught:
        await MySQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
    assert connection.invalidated >= 1


@pytest.mark.asyncio
async def test_execute_propagates_cancellation_and_destroys_the_connection():
    class _CancellingConnection(_FakeConnection):
        def stream(self, statement: object, parameters: object = None, *, execution_options: object = None) -> _FakeStreamContext:
            self.stream_calls.append(str(statement))
            self.events.append(str(statement))
            raise asyncio.CancelledError()

    connection = _CancellingConnection(results=(_mode_result(), _FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=())))

    with pytest.raises(asyncio.CancelledError):
        await MySQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert connection.invalidated >= 1


def test_connect_args_carry_only_the_bounded_connect_timeout():
    class _Credential:
        ssl_context = None
        tls_mode = None

    args = MySQLRuntime().connect_args(credential=_Credential(), limits=_limits(connect_timeout_ms=4_000))

    assert args == {"connect_timeout": 4}


# ---------------------------------------------------------------------------
# 真实 MySQL 8.4 集成测试
# ---------------------------------------------------------------------------

_CREDENTIAL_ENV = "ANALYTICS_TEST_MYSQL_CREDENTIAL"
_READONLY_CREDENTIAL_ENV = "ANALYTICS_TEST_MYSQL_READONLY_CREDENTIAL"
_TIMEOUT_MARKER = "insightflow_timeout_probe"
_ORDERS = "analytics_test.orders"


def _integration_enabled() -> bool:
    return os.environ.get(_INTEGRATION_ENV, "").strip() == "1"


def _datasource(variable: str):
    """`variable` 是环境变量名；`secret_ref` 的唯一合法形式是 `env://NAME`。"""

    from app.analytics.domain import DatasourceDefinition

    return DatasourceDefinition(id="ds-mysql-int", owner_id="user-1", name="MySQL integration", engine=DatasourceEngine.MYSQL, secret_ref=f"env://{variable}")


def _credential(variable: str = _CREDENTIAL_ENV):
    from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver

    return EnvironmentDatasourceSecretResolver().resolve(datasource=_datasource(variable))


def _engine(runtime: MySQLRuntime, *, variable: str = _CREDENTIAL_ENV, limits: ExecutionLimits | None = None):
    """按 gateway 的方式建 engine：NullPool、echo=False、connect_args 只来自 runtime。"""

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    resolved_limits = limits or _limits()
    credential = _credential(variable)
    return create_async_engine(credential.url, poolclass=NullPool, echo=False, connect_args=runtime.connect_args(credential=credential, limits=resolved_limits))


def _integration_authorized(sql: str):
    return AuthorizedQuerySpec(
        prepared=PreparedQuery(sql=sql, engine=DatasourceEngine.MYSQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
        datasource_id="ds-mysql-int",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=(_ORDERS,),
        columns=(f"{_ORDERS}.id",),
        functions=(),
        risk=QueryRisk.LOW,
    )


async def _fetch_all(connection, sql: str, parameters: dict | None = None) -> list[tuple]:
    if parameters is None:
        return [tuple(row) for row in (await connection.exec_driver_sql(sql)).fetchall()]
    return [tuple(row) for row in (await connection.execute(text(sql), parameters)).fetchall()]


def _mysql_errno(error: BaseException) -> int | None:
    """沿 SQLAlchemy 的 `orig` 与异常链取 MySQL 错误号；只看稳定错误号，不解析文本。"""

    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        args = getattr(current, "args", ())
        if args and isinstance(args[0], int) and not isinstance(args[0], bool):
            return args[0]
        for attribute in ("orig", "__cause__", "__context__"):
            candidate = getattr(current, attribute, None)
            if isinstance(candidate, BaseException):
                pending.append(candidate)
    return None


async def _count_residual_timeout_sessions(connection) -> int:
    """统计仍在跑测试查询的会话；排除自己，否则监控语句会匹配到它自己。

    LIKE 的 % 必须作为绑定参数传入：asyncmy 走 format 参数风格，SQL 文本里的裸 % 会被当成
    占位符并抛 `TypeError: not enough arguments for format string`。PostgreSQL 的 asyncpg 用
    `$n`，没有这个陷阱——这正是两个方言在测试夹具层的真实差异。
    """

    rows = await _fetch_all(
        connection,
        "SELECT COUNT(*) FROM information_schema.processlist WHERE ID <> CONNECTION_ID() AND INFO LIKE :pattern",
        {"pattern": f"%{_TIMEOUT_MARKER}%"},
    )
    return int(rows[0][0])


async def _wait_for_no_residual_timeout_session(connection, *, timeout_seconds: float) -> int:
    """有界重试：取消返回与服务器真正结束该语句之间存在一个很短的窗口。"""

    deadline = time.monotonic() + timeout_seconds
    observed = -1
    while True:
        observed = await _count_residual_timeout_sessions(connection)
        if observed == 0:
            return 0
        if time.monotonic() >= deadline:
            return observed
        await asyncio.sleep(0.2)


@pytest.mark.integration
@pytest.mark.skipif(not _integration_enabled(), reason=f"set {_INTEGRATION_ENV}=1 (see scripts/test_analytics_databases.py)")
class TestMySQLAgainstRealDatabase:
    pytestmark = pytest.mark.asyncio

    async def test_identifier_mode_on_the_test_stack_is_zero(self):
        runtime = MySQLRuntime()
        engine = _engine(runtime)
        try:
            async with engine.connect() as connection:
                rows = await _fetch_all(connection, "SELECT @@lower_case_table_names")
        finally:
            await engine.dispose()

        # 只有 0 才能与 Phase 2B1 的精确标识符比对一致；不为任何其他值提供后备路径。
        assert rows == [(0,)]

    async def test_explain_parses_the_json_v1_cost_and_matches_an_independent_digest(self):
        runtime = MySQLRuntime()
        limits = _limits()
        sql = f"SELECT id FROM {_ORDERS} WHERE amount > 0 LIMIT 10"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                estimate = await runtime.explain(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                assert connection.in_transaction() is False
            async with engine.connect() as monitor:
                raw = (await monitor.exec_driver_sql(f"EXPLAIN FORMAT=JSON {sql}")).fetchall()[0][0]
        finally:
            await engine.dispose()

        assert estimate.engine is DatasourceEngine.MYSQL
        assert estimate.engine_cost > 0
        assert estimate.estimated_rows > 0
        assert estimate.plan_digest == _canonical_digest(json.loads(raw))
        # JSON v1 的成本是带引号的字符串；解析后仍必须是精确的十进制值。
        assert isinstance(json.loads(raw)["query_block"]["cost_info"]["query_cost"], str)

    async def test_explain_rejects_a_plan_without_a_cost_field(self):
        runtime = MySQLRuntime()
        limits = _limits()
        # "No tables used" 的 SELECT 没有 cost_info：绝不填零，必须拒绝。
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError) as caught:
                    await runtime.explain(connection=connection, authorized=_integration_authorized("SELECT 1 LIMIT 1"), limits=limits)
        finally:
            await engine.dispose()

        assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED

    async def test_execute_returns_normalised_rows_and_rolls_back(self):
        runtime = MySQLRuntime()
        limits = _limits(max_result_rows=5)
        sql = f"SELECT id, customer, amount, created_at FROM {_ORDERS} ORDER BY id LIMIT 5"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await runtime.execute(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                assert connection.in_transaction() is False
        finally:
            await engine.dispose()

        assert result.columns == ("id", "customer", "amount", "created_at")
        assert result.row_count == 5
        assert result.truncated is False
        assert result.rows[0][0] == 1
        assert isinstance(result.rows[0][2], str)
        assert isinstance(result.rows[0][3], str)

    async def test_execute_truncates_at_the_row_budget(self):
        runtime = MySQLRuntime()
        limits = _limits(max_result_rows=3)
        sql = f"SELECT id FROM {_ORDERS} ORDER BY id LIMIT 10"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await runtime.execute(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                assert connection.in_transaction() is False
        finally:
            await engine.dispose()

        assert result.row_count == 3
        assert result.rows == ((1,), (2,), (3,))
        assert result.truncated is True

    async def test_read_only_transaction_rejects_an_injected_write_and_changes_nothing(self):
        runtime = MySQLRuntime()
        limits = _limits()
        injected = f"INSERT INTO {_ORDERS} (id, customer, amount) VALUES (999999, 'injected', 1.00)"
        engine = _engine(runtime, limits=limits)
        reported_code = None
        try:
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError) as caught:
                    await runtime.execute(connection=connection, authorized=_integration_authorized(injected), limits=limits)
                reported_code = caught.value.code
                assert connection.in_transaction() is False
            async with engine.connect() as monitor:
                remaining = await _fetch_all(monitor, f"SELECT COUNT(*) FROM {_ORDERS} WHERE id = 999999")
        finally:
            await engine.dispose()

        assert reported_code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
        assert remaining[0][0] == 0

    async def test_a_case_mismatched_relation_is_not_executed(self):
        runtime = MySQLRuntime()
        limits = _limits()
        # lower_case_table_names=0 下 ORDERS 与 orders 是两个不同对象：授权血缘指向 orders，
        # 因此大小写不一致的物理对象必须根本不存在。
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError) as caught:
                    await runtime.execute(connection=connection, authorized=_integration_authorized("SELECT id FROM analytics_test.ORDERS LIMIT 1"), limits=limits)
                assert connection.in_transaction() is False
        finally:
            await engine.dispose()

        assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE

    async def test_max_execution_time_is_armed_for_buffered_reads(self):
        """证明 `MAX_EXECUTION_TIME` 确实被设置，并且对缓冲读取生效。

        EXPLAIN 走的就是缓冲路径，所以这条断言是 EXPLAIN 服务端超时的证据；它也防止
        「服务端超时其实从未生效」被静默放过。
        """

        runtime = MySQLRuntime()
        limits = _limits(statement_timeout_ms=400, cancellation_grace_ms=600)
        sql = f"SELECT SLEEP(0.2) AS {_TIMEOUT_MARKER} FROM {_ORDERS} LIMIT 5000"
        engine = _engine(runtime, limits=limits)
        observed: BaseException | None = None
        try:
            async with engine.connect() as connection:
                await connection.exec_driver_sql("SET SESSION MAX_EXECUTION_TIME = 400")
                await connection.exec_driver_sql("START TRANSACTION READ ONLY")
                try:
                    async with asyncio.timeout(10):
                        (await connection.exec_driver_sql(sql)).fetchall()
                except Exception as error:  # noqa: BLE001 - 这里就是要观察驱动的错误号
                    observed = error
                try:
                    await connection.exec_driver_sql("ROLLBACK")
                except Exception:  # noqa: BLE001
                    pass
        finally:
            await engine.dispose()

        assert observed is not None, "MAX_EXECUTION_TIME did not interrupt a buffered scan"
        assert _mysql_errno(observed) == 3024, f"expected MySQL errno 3024, got {_mysql_errno(observed)}"

    async def test_streamed_execution_does_not_survive_the_client_timeout(self):
        """流式执行路径的真实语义（Phase 2B2 记录在案的偏差）。

        MySQL 的 `max_execution_time` 不会抢占 `connection.stream()` 打开的服务端游标：
        服务端超时在这条路径上不生效，真正终止查询的是客户端 `asyncio.timeout()` 与随后
        的连接销毁。这里刻意断言"客户端超时确实发生"，把这个行为**钉住**而不是掩盖——
        将来若某个版本让服务端超时生效，这条断言会失败并提醒重新评估偏差。
        安全断言保持不变：超时返回后服务端不得存在仍在运行的查询。
        """

        runtime = MySQLRuntime()
        limits = _limits(statement_timeout_ms=400, cancellation_grace_ms=600)
        sql = f"SELECT SLEEP(0.2) AS {_TIMEOUT_MARKER} FROM {_ORDERS} LIMIT 5000"
        engine = _engine(runtime, limits=limits)
        budget = (limits.statement_timeout_ms + limits.cancellation_grace_ms) / 1000
        client_timed_out = False
        try:
            async with engine.connect() as connection:
                try:
                    async with asyncio.timeout(budget):
                        await runtime.execute(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                except DatasourceQueryError:
                    pass
                except TimeoutError:
                    client_timed_out = True
                    try:
                        await connection.invalidate()
                    except Exception:  # noqa: BLE001
                        pass
            async with engine.connect() as monitor:
                residual = await _wait_for_no_residual_timeout_session(monitor, timeout_seconds=15)
        finally:
            await engine.dispose()

        assert client_timed_out is True, "the streaming path honoured the server-side timeout; revisit the recorded deviation"
        assert residual == 0, "the timed-out query is still visible in information_schema.processlist"

    async def test_client_timeout_destroys_the_connection_and_stops_the_query(self):
        runtime = MySQLRuntime()
        # 服务端超时故意放宽，让客户端时限先到：这条路径证明的是"连接被销毁"而不是"服务端取消"。
        limits = _limits(statement_timeout_ms=3_000, cancellation_grace_ms=500)
        sql = f"SELECT SLEEP(0.2) AS {_TIMEOUT_MARKER} FROM {_ORDERS} LIMIT 5000"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                try:
                    async with asyncio.timeout(0.4):
                        await runtime.execute(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                except TimeoutError:
                    try:
                        await connection.invalidate()
                    except Exception:
                        pass
            async with engine.connect() as monitor:
                # 服务端 MAX_EXECUTION_TIME=3s 最终会终止语句；客户端连接早已被销毁。
                residual = await _wait_for_no_residual_timeout_session(monitor, timeout_seconds=20)
        finally:
            await engine.dispose()

        assert residual == 0, "the client-timed-out query is still visible in information_schema.processlist"

    async def test_read_only_business_user_can_select_but_its_write_is_refused(self):
        runtime = MySQLRuntime()
        limits = _limits()
        engine = _engine(runtime, variable=_READONLY_CREDENTIAL_ENV, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await runtime.execute(connection=connection, authorized=_integration_authorized(f"SELECT id FROM {_ORDERS} ORDER BY id LIMIT 1"), limits=limits)
                assert result.rows == ((1,),)
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError):
                    await runtime.execute(connection=connection, authorized=_integration_authorized(f"INSERT INTO {_ORDERS} (id, customer, amount) VALUES (999998, 'reader', 1.00)"), limits=limits)
        finally:
            await engine.dispose()

    async def test_gateway_executes_end_to_end_and_maps_a_bad_password(self):
        from app.analytics.infrastructure.database_runtime import SQLAlchemyDatasourceQueryGateway
        from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver

        gateway = SQLAlchemyDatasourceQueryGateway(
            secret_resolver=EnvironmentDatasourceSecretResolver(),
            runtimes={DatasourceEngine.MYSQL: MySQLRuntime()},
        )
        limits = _limits()
        authorized = _integration_authorized(f"SELECT id FROM {_ORDERS} ORDER BY id LIMIT 2")

        result = await gateway.execute(datasource=_datasource(_CREDENTIAL_ENV), authorized=authorized, limits=limits)
        assert result.rows == ((1,), (2,))

        os.environ["ANALYTICS_TEST_MYSQL_BAD_PASSWORD"] = json.dumps(
            {
                "engine": "mysql",
                "host": "127.0.0.1",
                "port": int(os.environ.get("ANALYTICS_MYSQL_PORT", "53306")),
                "database": "analytics_test",
                "username": "analytics_tester",
                "password": "definitely-not-the-password",
                "tls_mode": "disable",
            }
        )
        try:
            with pytest.raises(DatasourceQueryError) as caught:
                await gateway.explain(datasource=_datasource("ANALYTICS_TEST_MYSQL_BAD_PASSWORD"), authorized=authorized, limits=limits)
        finally:
            del os.environ["ANALYTICS_TEST_MYSQL_BAD_PASSWORD"]

        assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
        rendered = f"{caught.value!r} {caught.value}"
        assert "analytics_tester" not in rendered
        assert "127.0.0.1" not in rendered
        assert "definitely-not-the-password" not in rendered
