"""PostgreSQL runtime 测试：fake connection 单元测试 + 真实 PostgreSQL 16 集成测试。

本文件刻意承载两类测试：

- 不依赖 Docker 的单元测试用可观测的 connection 替身固定**控制语句顺序**（begin → read only →
  local timeout → EXPLAIN/SELECT → rollback）、禁止 `ANALYZE`、以及计划解析的每一条拒绝路径。
  这些测试在任何环境都必须通过，因此 `pytest tests/` 在没有数据库时不会失败。
- 集成测试只在 `ANALYTICS_TEST_POSTGRESQL=1` 时运行（由 `scripts/test_analytics_databases.py` 注入），
  证明真实 PostgreSQL 16 上的只读事务、服务端超时、取消后无残留活跃查询、流式截断与错误脱敏。

计划摘要的期望值不调用生产 helper：本文件自己写出规范化规则（UTF-8、`ensure_ascii=False`、
紧凑分隔符、`sort_keys`）并据此计算，避免"规则被改坏"和"测试跟着改坏"同时发生。
"""

import asyncio
import hashlib
import json
import os
import time
from decimal import Decimal
from typing import Any

import pytest

from app.analytics.application import DatasourceQueryError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceEngine,
    ExecutionDecisionCode,
    ExecutionLimits,
    PreparedQuery,
    QueryRisk,
)
from app.analytics.infrastructure.postgresql_runtime import PostgreSQLRuntime

_INTEGRATION_ENV = "ANALYTICS_TEST_POSTGRESQL"

_APPROVED_SQL = "SELECT id FROM orders LIMIT 10"

_PLAN_TEXT = """[
  {
    "Plan": {
      "Node Type": "Seq Scan",
      "Relation Name": "orders",
      "Startup Cost": 0.00,
      "Total Cost": 12.35,
      "Plan Rows": 420,
      "Plan Width": 8
    }
  }
]"""

# 规范化后的计划文档必须逐字节等于这一行；摘要是它的 SHA-256。
_CANONICAL_PLAN_TEXT = '[{"Plan":{"Node Type":"Seq Scan","Plan Rows":420,"Plan Width":8,"Relation Name":"orders","Startup Cost":0.0,"Total Cost":12.35}}]'


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
        prepared=PreparedQuery(sql=sql, engine=DatasourceEngine.POSTGRESQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
        datasource_id="ds-1",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=("public.orders",),
        columns=("public.orders.id",),
        functions=(),
        risk=QueryRisk.LOW,
    )


class _FakeResult:
    """驱动结果替身：只暴露 adapter 允许访问的成员，多访问一个就失败。"""

    def __init__(self, *, columns: tuple[str, ...] = ("QUERY PLAN",), rows: tuple[tuple[object, ...], ...] = ()) -> None:
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
    """带 SQLSTATE 的驱动异常替身：真实 asyncpg 异常也通过这个属性识别取消。"""

    def __init__(self, message: str, *, sqlstate: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def _explain_connection(plan_text: str = _PLAN_TEXT, **overrides: Any) -> _FakeConnection:
    # 两条控制语句各消费一个空结果，之后才是计划结果。
    return _FakeConnection(results=(_FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=((plan_text,),))), **overrides)


async def _run_explain(connection: _FakeConnection, **limit_overrides: Any):
    return await PostgreSQLRuntime().explain(connection=connection, authorized=_authorized(), limits=_limits(**limit_overrides))


# ---------------------------------------------------------------------------
# fake connection 单元测试：控制语句顺序与拒绝路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explain_orders_read_only_timeout_explain_and_rollback():
    connection = _explain_connection()

    estimate = await _run_explain(connection)

    assert connection.events == [
        "begin",
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 250",
        f"EXPLAIN (FORMAT JSON) {_APPROVED_SQL}",
        "rollback",
    ]
    assert estimate.engine is DatasourceEngine.POSTGRESQL
    assert estimate.estimated_rows == 420
    assert estimate.engine_cost == Decimal("12.35")


@pytest.mark.asyncio
async def test_explain_never_emits_analyze():
    connection = _explain_connection()

    await _run_explain(connection)

    executed = " ".join(connection.events).upper()
    assert "ANALYZE" not in executed
    assert connection.events[3] == f"EXPLAIN (FORMAT JSON) {_APPROVED_SQL}"


@pytest.mark.asyncio
async def test_explain_digest_is_the_sha256_of_the_canonical_plan():
    connection = _explain_connection()

    estimate = await _run_explain(connection)

    assert json.dumps(json.loads(_PLAN_TEXT), ensure_ascii=False, separators=(",", ":"), sort_keys=True) == _CANONICAL_PLAN_TEXT
    assert estimate.plan_digest == hashlib.sha256(_CANONICAL_PLAN_TEXT.encode("utf-8")).hexdigest()
    assert estimate.plan_digest == _canonical_digest(json.loads(_PLAN_TEXT))


@pytest.mark.asyncio
async def test_explain_rejects_a_plan_over_the_byte_budget():
    connection = _explain_connection()

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection, max_explain_bytes=32)

    assert caught.value.code is ExecutionDecisionCode.COST_LIMIT_EXCEEDED
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan_text",
    [
        # 缺少 Total Cost
        '[{"Plan": {"Plan Rows": 10}}]',
        # 缺少 Plan Rows
        '[{"Plan": {"Total Cost": 1.0}}]',
        # NaN / Infinity 不是有限数
        '[{"Plan": {"Total Cost": NaN, "Plan Rows": 10}}]',
        '[{"Plan": {"Total Cost": Infinity, "Plan Rows": 10}}]',
        # 负成本
        '[{"Plan": {"Total Cost": -1.0, "Plan Rows": 10}}]',
        # 行数不是整数
        '[{"Plan": {"Total Cost": 1.0, "Plan Rows": 1.5}}]',
        # 负行数
        '[{"Plan": {"Total Cost": 1.0, "Plan Rows": -1}}]',
        # 顶层 Plan 缺失
        '[{"Planning Time": 0.1}]',
        # 不是单元素数组
        "[]",
        # 不是 JSON
        "not json at all",
        # 不是计划对象
        '"a string"',
    ],
)
async def test_explain_rejects_a_missing_or_non_finite_cost(plan_text: str):
    connection = _explain_connection(plan_text)

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_explain_rejects_a_result_set_that_is_not_a_single_row():
    connection = _FakeConnection(results=(_FakeResult(rows=()), _FakeResult(rows=()), _FakeResult(rows=((_PLAN_TEXT,), (_PLAN_TEXT,)))))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED


@pytest.mark.asyncio
async def test_explain_maps_a_statement_timeout_to_execution_timeout():
    connection = _FakeConnection(results=(_FakeResult(rows=()), _DriverError("canceling statement due to statement timeout", sqlstate="57014")))

    with pytest.raises(DatasourceQueryError) as caught:
        await _run_explain(connection)

    assert caught.value.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
    # 连接状态未知：必须是销毁而不是回滚后复用。
    assert connection.invalidated >= 1


@pytest.mark.asyncio
async def test_explain_maps_an_unexpected_driver_failure_without_leaking_text():
    connection = _FakeConnection(results=(_FakeResult(rows=()), _DriverError(f"connection to server failed for {_APPROVED_SQL} at 127.0.0.1")))

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
        results=(_FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_FakeResult(columns=("id", "name"), rows=((1, "a"), (2, "b"))),
    )

    result = await PostgreSQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert connection.events == [
        "begin",
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 250",
        _APPROVED_SQL,
        "rollback",
    ]
    assert connection.stream_calls == [_APPROVED_SQL]
    assert result.columns == ("id", "name")
    assert result.rows == ((1, "a"), (2, "b"))
    assert result.row_count == 2
    assert result.truncated is False


@pytest.mark.asyncio
async def test_execute_truncates_a_stream_that_exceeds_the_row_budget():
    connection = _FakeConnection(
        results=(_FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_FakeResult(columns=("id",), rows=((1,), (2,), (3,), (4,), (5,))),
    )

    result = await PostgreSQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits(max_result_rows=3))

    assert result.row_count == 3
    assert result.rows == ((1,), (2,), (3,))
    assert result.truncated is True
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_execute_rejects_a_result_with_too_many_columns_before_reading_rows():
    connection = _FakeConnection(
        results=(_FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_FakeResult(columns=("a", "b", "c"), rows=((1, 2, 3),)),
    )

    with pytest.raises(DatasourceQueryError) as caught:
        await PostgreSQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits(max_result_columns=2))

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_execute_maps_a_driver_failure_and_destroys_the_connection():
    connection = _FakeConnection(
        results=(_FakeResult(rows=()), _FakeResult(rows=())),
        stream_result=_DriverError("permission denied for relation orders"),
    )

    with pytest.raises(DatasourceQueryError) as caught:
        await PostgreSQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
    assert connection.invalidated >= 1
    assert connection.transactions[0].rolled_back == 1


@pytest.mark.asyncio
async def test_execute_propagates_cancellation_and_destroys_the_connection():
    class _CancellingConnection(_FakeConnection):
        def stream(self, statement: object, parameters: object = None, *, execution_options: object = None) -> _FakeStreamContext:
            self.stream_calls.append(str(statement))
            self.events.append(str(statement))
            raise asyncio.CancelledError()

    connection = _CancellingConnection(results=(_FakeResult(rows=()), _FakeResult(rows=())))

    with pytest.raises(asyncio.CancelledError):
        await PostgreSQLRuntime().execute(connection=connection, authorized=_authorized(), limits=_limits())

    assert connection.invalidated >= 1


def test_connect_args_carry_only_the_connect_timeout():
    class _Credential:
        ssl_context = None
        tls_mode = None

    args = PostgreSQLRuntime().connect_args(credential=_Credential(), limits=_limits(connect_timeout_ms=4_000))

    assert args == {"timeout": 4.0}


# ---------------------------------------------------------------------------
# 真实 PostgreSQL 16 集成测试
# ---------------------------------------------------------------------------

_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_CREDENTIAL"
_READONLY_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_READONLY_CREDENTIAL"
_DEMO_READONLY_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_DEMO_READONLY_CREDENTIAL"
_OBSERVER_CREDENTIAL_ENV = "ANALYTICS_TEST_PG_OBSERVER_CREDENTIAL"
_TIMEOUT_MARKER = "insightflow_timeout_probe"


def _integration_enabled() -> bool:
    return os.environ.get(_INTEGRATION_ENV, "").strip() == "1"


def _datasource(variable: str):
    """`variable` 是环境变量名；`secret_ref` 的唯一合法形式是 `env://NAME`。"""

    from app.analytics.domain import DatasourceDefinition

    return DatasourceDefinition(id="ds-pg-int", owner_id="user-1", name="PostgreSQL integration", engine=DatasourceEngine.POSTGRESQL, secret_ref=f"env://{variable}")


def _credential(variable: str = _CREDENTIAL_ENV):
    from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver

    return EnvironmentDatasourceSecretResolver().resolve(datasource=_datasource(variable))


def _engine(runtime: PostgreSQLRuntime, *, variable: str = _CREDENTIAL_ENV, limits: ExecutionLimits | None = None):
    """按 gateway 的方式建 engine：NullPool、echo=False、connect_args 只来自 runtime。"""

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    resolved_limits = limits or _limits()
    credential = _credential(variable)
    return create_async_engine(credential.url, poolclass=NullPool, echo=False, connect_args=runtime.connect_args(credential=credential, limits=resolved_limits))


def _integration_authorized(sql: str):
    return AuthorizedQuerySpec(
        prepared=PreparedQuery(sql=sql, engine=DatasourceEngine.POSTGRESQL, relations=("orders",), row_limit=10, query_hash="b" * 64),
        datasource_id="ds-pg-int",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=("public.orders",),
        columns=("public.orders.id",),
        functions=(),
        risk=QueryRisk.LOW,
    )


async def _call(runtime: PostgreSQLRuntime, operation: str, connection, authorized: AuthorizedQuerySpec, limits: ExecutionLimits):
    """完全按 gateway 的方式套客户端总时限：statement_timeout + cancellation_grace。"""

    budget_seconds = (limits.statement_timeout_ms + limits.cancellation_grace_ms) / 1000
    try:
        async with asyncio.timeout(budget_seconds):
            if operation == "explain":
                return await runtime.explain(connection=connection, authorized=authorized, limits=limits)
            return await runtime.execute(connection=connection, authorized=authorized, limits=limits)
    except TimeoutError as error:
        # 超时后连接状态未知：与 gateway 一样显式销毁。
        try:
            await connection.invalidate()
        except Exception:
            pass
        raise DatasourceQueryError(ExecutionDecisionCode.EXECUTION_TIMEOUT) from error


async def _fetch_all(connection, sql: str) -> list[tuple]:
    return [tuple(row) for row in (await connection.exec_driver_sql(sql)).fetchall()]


async def _count_residual_timeout_backends(connection) -> int:
    """统计仍在跑测试查询的后端；排除自己，否则监控语句会匹配到它自己。"""

    rows = await _fetch_all(
        connection,
        f"SELECT count(*) FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND backend_type = 'client backend' AND query LIKE '%{_TIMEOUT_MARKER}%'",
    )
    return int(rows[0][0])


async def _wait_for_no_residual_timeout_backend(connection, *, timeout_seconds: float) -> int:
    """有界重试：取消返回与后端真正退出之间存在一个很短的窗口。"""

    deadline = time.monotonic() + timeout_seconds
    observed = -1
    while True:
        observed = await _count_residual_timeout_backends(connection)
        if observed == 0:
            return 0
        if time.monotonic() >= deadline:
            return observed
        await asyncio.sleep(0.2)


@pytest.mark.integration
@pytest.mark.skipif(not _integration_enabled(), reason=f"set {_INTEGRATION_ENV}=1 (see scripts/test_analytics_databases.py)")
class TestPostgreSQLAgainstRealDatabase:
    pytestmark = pytest.mark.asyncio

    async def test_explain_parses_the_json_plan_and_matches_an_independent_digest(self):
        runtime = PostgreSQLRuntime()
        limits = _limits()
        sql = "SELECT id FROM public.orders LIMIT 10"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                estimate = await _call(runtime, "explain", connection, _integration_authorized(sql), limits)
                assert connection.in_transaction() is False
            # 独立重跑一次原始 EXPLAIN：摘要只能来自数据库真实返回的计划文本。
            async with engine.connect() as monitor:
                raw = (await monitor.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {sql}")).fetchall()[0][0]
                # asyncpg 方言会把 json/jsonb 直接解成 Python 对象；两种形态都要能规范化。
                document = json.loads(raw) if isinstance(raw, str) else raw
        finally:
            await engine.dispose()

        assert estimate.engine is DatasourceEngine.POSTGRESQL
        assert estimate.estimated_rows > 0
        assert estimate.engine_cost > 0
        assert estimate.plan_digest == _canonical_digest(document)

    async def test_synthetic_dataset_is_readable_by_the_restricted_demo_principal(self):
        """演示主体只能用真实 column grants 读取合成订单的白名单字段。"""

        engine = _engine(PostgreSQLRuntime(), variable=_DEMO_READONLY_CREDENTIAL_ENV)
        try:
            async with engine.connect() as connection:
                first_order = (await connection.exec_driver_sql("SELECT order_id FROM demo.orders ORDER BY order_id LIMIT 1")).scalar_one()
        finally:
            await engine.dispose()

        assert first_order == 1

    async def test_demo_reader_cannot_read_outside_its_columns_or_change_data(self):
        from sqlalchemy.exc import DBAPIError

        engine = _engine(PostgreSQLRuntime(), variable=_DEMO_READONLY_CREDENTIAL_ENV)
        denied_sql = (
            "SELECT id FROM public.orders LIMIT 1",
            "SELECT internal_margin FROM demo.internal_margin LIMIT 1",
            "SELECT customer_email FROM demo.orders LIMIT 1",
            "INSERT INTO demo.orders (order_id, order_date, region, product, status, amount, customer_email, internal_note) VALUES (99991, DATE '2026-01-01', 'North', 'Atlas', 'paid', 1.00, 'fake@invalid', 'synthetic')",
            "UPDATE demo.orders SET amount = 999.00 WHERE order_id = 1",
            "CREATE TABLE demo.d6d2_direct_ddl_probe (id integer)",
            "CREATE TEMP TABLE d6d2_direct_temp_probe (id integer)",
        )
        try:
            for sql in denied_sql:
                async with engine.connect() as connection:
                    with pytest.raises(DBAPIError) as caught:
                        await connection.exec_driver_sql(sql)
                assert getattr(caught.value.orig, "sqlstate", None) == "42501", sql
        finally:
            await engine.dispose()

    async def test_postgresql_records_statements_for_no_execution_rejection_proofs(self):
        engine = _engine(PostgreSQLRuntime())
        try:
            async with engine.connect() as connection:
                installed = (await connection.exec_driver_sql("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')")).scalar_one()
        finally:
            await engine.dispose()

        assert installed is True

    async def test_january_paid_revenue_runs_through_registered_services_and_tool(self, tmp_path):
        """经服务和 Agent tool 实际 plan→execute；本用例不启动模型或 HTTP Agent run。"""

        import json
        from types import SimpleNamespace

        from langgraph.prebuilt.tool_node import ToolRuntime
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.analytics.agent.runtime import bind_analytics_services, clear_analytics_services
        from app.analytics.agent.tools import inspect_business_catalog, query_business_data
        from app.analytics.composition import build_analytics_services
        from app.analytics.domain import (
            ColumnAccess,
            ColumnAccessRule,
            ColumnSchema,
            ColumnSensitivity,
            DatasourceEngine,
            MetricDefinition,
            MetricStatus,
            RelationAccessRule,
            RelationSchema,
        )

        control_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analytics-control.db'}", poolclass=NullPool, echo=False)
        services = await build_analytics_services(
            config=SimpleNamespace(database=SimpleNamespace(backend="sqlite")),
            engine=control_engine,
            session_factory=async_sessionmaker(control_engine, expire_on_commit=False),
            backend="sqlite",
        )
        assert services is not None
        try:
            datasource = await services.administration.create_datasource(
                owner_id="demo-owner",
                name="合成订单库",
                engine=DatasourceEngine.POSTGRESQL,
                secret_ref=f"env://{_DEMO_READONLY_CREDENTIAL_ENV}",
                default_schema="demo",
            )
            await services.administration.replace_schema(
                owner_id="demo-owner",
                datasource_id=datasource.id,
                version="demo-schema-v1",
                default_schema="demo",
                relations=(
                    RelationSchema(
                        name="orders",
                        schema="demo",
                        columns=(
                            ColumnSchema(name="order_id", data_type="integer"),
                            ColumnSchema(name="order_date", data_type="date"),
                            ColumnSchema(name="region", data_type="text"),
                            ColumnSchema(name="product", data_type="text"),
                            ColumnSchema(name="status", data_type="text"),
                            ColumnSchema(name="amount", data_type="numeric(12,2)"),
                            ColumnSchema(name="customer_email", data_type="text", sensitivity=ColumnSensitivity.PII),
                            ColumnSchema(name="internal_note", data_type="text", sensitivity=ColumnSensitivity.SENSITIVE),
                        ),
                    ),
                ),
                expected_version=None,
            )
            await services.administration.replace_policy(
                owner_id="demo-owner",
                datasource_id=datasource.id,
                principal_id="demo-user",
                version="demo-policy-v1",
                relations=(
                    RelationAccessRule(
                        name="orders",
                        schema="demo",
                        columns=(
                            ColumnAccessRule(name="order_id", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="order_date", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="region", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="product", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="status", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="amount", access=ColumnAccess.ALLOW),
                            ColumnAccessRule(name="customer_email", access=ColumnAccess.ALLOW),
                        ),
                    ),
                ),
                allowed_functions=("and", "cast", "count", "sum"),
                expected_version=None,
            )
            for metric in (
                MetricDefinition(
                    key="january_paid_revenue",
                    owner_id="demo-user",
                    name="1 月已支付收入",
                    description="统计 2026 年 1 月 paid 状态订单的金额。",
                    expression="sum(amount)",
                    dimensions=("order_date", "status"),
                    version=1,
                    status=MetricStatus.ACTIVE,
                ),
                MetricDefinition(
                    key="january_paid_revenue_by_region",
                    owner_id="demo-user",
                    name="1 月各地区已支付收入",
                    description="按地区统计 2026 年 1 月 paid 状态订单的金额。",
                    expression="sum(amount)",
                    dimensions=("region", "order_date", "status"),
                    version=1,
                    status=MetricStatus.ACTIVE,
                ),
                MetricDefinition(
                    key="january_refund_order_ratio",
                    owner_id="demo-user",
                    name="1 月退款订单占比",
                    description="2026 年 1 月 refunded 订单数占当月全部订单的比例。",
                    expression="count(refunded orders) / count(orders)",
                    dimensions=("order_date", "status"),
                    version=1,
                    status=MetricStatus.ACTIVE,
                ),
            ):
                await services.administration.save_metric(owner_id="demo-user", metric=metric)
            bind_analytics_services(services)
            runtime = ToolRuntime(state={}, context={"user_id": "demo-user"}, config={}, stream_writer=lambda _: None, tool_call_id=None, store=None, tools=[])
            catalog = json.loads(await inspect_business_catalog.ainvoke({"runtime": runtime}))
            question_sql = (
                "SELECT SUM(amount) AS revenue FROM demo.orders WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01' AND status = 'paid' LIMIT 1",
                "SELECT region, SUM(amount) AS paid_revenue FROM demo.orders WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01' AND status = 'paid' GROUP BY region ORDER BY region LIMIT 10",
                "SELECT COUNT(*) FILTER (WHERE status = 'refunded') AS refunded_orders, COUNT(*) AS total_orders FROM demo.orders WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01' LIMIT 1",
            )
            payloads = [json.loads(await query_business_data.ainvoke({"datasource_id": datasource.id, "sql": sql, "runtime": runtime})) for sql in question_sql]
            repeated = json.loads(await query_business_data.ainvoke({"datasource_id": datasource.id, "sql": question_sql[0], "runtime": runtime}))
            from sqlalchemy import event, text
            from sqlalchemy.engine import Engine

            observer_engine = _engine(PostgreSQLRuntime(), variable=_OBSERVER_CREDENTIAL_ENV)
            denied_cases = (
                ("SELECT internal_margin AS d6d2_unlisted_relation FROM demo.internal_margin LIMIT 1", "d6d2_unlisted_relation", "unknown_relation"),
                ("SELECT internal_note AS d6d2_unlisted_column FROM demo.orders LIMIT 1", "d6d2_unlisted_column", "column_not_allowed"),
                (
                    "INSERT INTO demo.orders (order_id, order_date, region, product, status, amount, customer_email, internal_note) "
                    "VALUES (99992, DATE '2026-01-01', 'North', 'Atlas', 'paid', 1.00, 'fake@invalid', 'synthetic') "
                    "RETURNING order_id AS d6d2_denied_insert",
                    "d6d2_denied_insert",
                    "unsupported_statement",
                ),
                ("UPDATE demo.orders SET amount = 888.00 WHERE order_id = 1 RETURNING order_id AS d6d2_denied_update", "d6d2_denied_update", "unsupported_statement"),
                ("CREATE TABLE demo.d6d2_denied_ddl (id integer)", "d6d2_denied_ddl", "unsupported_statement"),
                ("SELECT order_id AS d6d2_multi_probe FROM demo.orders LIMIT 1; SELECT order_id AS d6d2_multi_probe FROM demo.orders LIMIT 1", "d6d2_multi_probe", "multiple_statements"),
                ("SELECT customer_email AS d6d2_pii_probe FROM demo.orders LIMIT 1", "d6d2_pii_probe", "sensitive_column"),
            )

            submitted_markers: set[str] = set()
            markers = {marker.casefold() for _, marker, _ in denied_cases}

            def record_submitted_postgresql_statement(connection, cursor, statement, parameters, context, executemany):
                del cursor, parameters, context, executemany
                if connection.dialect.name != "postgresql":
                    return
                normalized = statement.casefold()
                submitted_markers.update(marker for marker in markers if marker in normalized)

            event.listen(Engine, "before_cursor_execute", record_submitted_postgresql_statement)

            async def calls_for(marker: str) -> int:
                async with observer_engine.connect() as connection:
                    value = await connection.execute(
                        text("SELECT COALESCE(SUM(calls), 0) FROM pg_stat_statements WHERE query ILIKE :needle"),
                        {"needle": f"%{marker}%"},
                    )
                    return int(value.scalar_one())

            try:
                denial_results = []
                for sql, marker, expected_code in denied_cases:
                    before_calls = await calls_for(marker)
                    denial = json.loads(await query_business_data.ainvoke({"datasource_id": datasource.id, "sql": sql, "runtime": runtime}))
                    after_calls = await calls_for(marker)
                    assert denial["code"] == expected_code, (marker, denial)
                    assert denial == {"code": expected_code, "columns": [], "rows": [], "row_count": 0, "truncated": False}, (marker, denial)
                    assert marker not in repr(denial), denial
                    assert "analytics_demo_reader_pw" not in repr(denial), denial
                    assert "fake@invalid" not in repr(denial), denial
                    assert "evidence" not in denial and "raw_sql" not in denial and "plan_token" not in denial
                    assert marker not in submitted_markers, f"rejected statement was sent to PostgreSQL: {marker}"
                    assert after_calls == before_calls, f"rejected statement reached PostgreSQL: {marker} ({before_calls}->{after_calls})"
                    denial_results.append((sql, marker, expected_code, denial))
                audit_records = await services.audit_reader.list_for_principal(principal_id="demo-user", limit=100)
            finally:
                event.remove(Engine, "before_cursor_execute", record_submitted_postgresql_statement)
                await observer_engine.dispose()
        finally:
            clear_analytics_services()
            await control_engine.dispose()

        assert catalog["code"] == "ok"
        assert {metric["key"] for metric in catalog["metrics"]} == {"january_paid_revenue", "january_paid_revenue_by_region", "january_refund_order_ratio"}
        assert {metric["key"]: metric["name"] for metric in catalog["metrics"]} == {
            "january_paid_revenue": "1 \u6708\u5df2\u652f\u4ed8\u6536\u5165",
            "january_paid_revenue_by_region": "1 \u6708\u5404\u5730\u533a\u5df2\u652f\u4ed8\u6536\u5165",
            "january_refund_order_ratio": "1 \u6708\u9000\u6b3e\u8ba2\u5355\u5360\u6bd4",
        }
        assert [(item["columns"], item["rows"], item["row_count"], item["truncated"]) for item in payloads] == [
            (["revenue"], [["540.00"]], 1, False),
            (["region", "paid_revenue"], [["North", "300.00"], ["South", "150.00"], ["West", "90.00"]], 3, False),
            (["refunded_orders", "total_orders"], [[2, 8]], 1, False),
        ], payloads
        first_evidence = payloads[0]["evidence"]
        repeated_evidence = repeated["evidence"]
        assert payloads[0]["code"] == "executed" and repeated["code"] == "executed"
        assert first_evidence["risk"] == "low"
        assert first_evidence["schema_version"] == "demo-schema-v1"
        assert first_evidence["policy_version"] == "demo-policy-v1"
        assert first_evidence["query_hash"] == repeated_evidence["query_hash"]
        assert first_evidence["result_digest"] == repeated_evidence["result_digest"] == _canonical_digest({"columns": ["revenue"], "rows": [["540.00"]]})
        assert first_evidence["evidence_id"] == repeated_evidence["evidence_id"]
        assert len(first_evidence["query_hash"]) == len(first_evidence["plan_digest"]) == len(first_evidence["result_digest"]) == len(first_evidence["evidence_id"]) == 64
        assert payloads[1]["row_count"] <= 10 and payloads[1]["truncated"] is False
        assert payloads[2]["row_count"] <= 1 and payloads[2]["truncated"] is False
        assert repeated["evidence"]["estimated_rows"] == first_evidence["estimated_rows"]
        assert repeated["evidence"]["engine_cost"] == first_evidence["engine_cost"]
        assert repeated["evidence"]["plan_digest"] == first_evidence["plan_digest"]
        expected_evidence_id = _canonical_digest(
            {
                "datasource_id": first_evidence["datasource_id"],
                "query_hash": first_evidence["query_hash"],
                "risk": first_evidence["risk"],
                "schema_version": first_evidence["schema_version"],
                "policy_version": first_evidence["policy_version"],
                "plan_digest": first_evidence["plan_digest"],
                "estimated_rows": first_evidence["estimated_rows"],
                "engine_cost": first_evidence["engine_cost"],
                "row_count": first_evidence["row_count"],
                "byte_count": first_evidence["byte_count"],
                "truncated": first_evidence["truncated"],
                "result_digest": first_evidence["result_digest"],
                "decision_code": first_evidence["decision_code"],
            }
        )
        assert first_evidence["evidence_id"] == expected_evidence_id
        successful_audits = [record for record in audit_records if record.query_hash == first_evidence["query_hash"]]
        successful_plan_audits = [record for record in successful_audits if record.phase.value == "plan"]
        successful_execute_audits = [record for record in successful_audits if record.phase.value == "execute"]
        assert len(successful_plan_audits) == 2
        assert len(successful_execute_audits) == 2
        assert all(
            record.status.value == "completed"
            and record.decision_code == "plan_created"
            and record.risk.value == "low"
            and record.schema_version == first_evidence["schema_version"]
            and record.policy_version == first_evidence["policy_version"]
            and record.plan_digest == first_evidence["plan_digest"]
            for record in successful_plan_audits
        ), [(record.status.value, record.decision_code, record.risk, record.schema_version, record.policy_version, record.plan_digest) for record in successful_plan_audits]
        assert all(
            record.status.value == "completed"
            and record.decision_code == "executed"
            and record.risk.value == "low"
            and record.schema_version == first_evidence["schema_version"]
            and record.policy_version == first_evidence["policy_version"]
            and record.row_count == first_evidence["row_count"] == 1
            and record.truncated is False
            for record in successful_execute_audits
        ), [(record.status.value, record.decision_code, record.risk, record.schema_version, record.policy_version, record.plan_digest, record.row_count, record.truncated) for record in successful_execute_audits]
        denied_codes = {code for _, _, code, _ in denial_results}
        denial_audits = [record for record in audit_records if record.decision_code in denied_codes]
        assert {record.decision_code for record in denial_audits} == denied_codes
        assert all(record.status.value == "completed" and record.phase.value in {"policy", "authorization"} for record in denial_audits)
        assert any(record.decision_code == "sensitive_column" and record.risk.value == "high" for record in denial_audits)
        authorization_hashes = {record.query_hash for record in denial_audits if record.phase.value == "authorization"}
        assert authorization_hashes
        assert not any(record.phase.value in {"plan", "execute"} and record.query_hash in authorization_hashes for record in audit_records)
        rendered_audits = repr(audit_records)
        for sql, marker, _, _ in denial_results:
            assert sql not in rendered_audits
            assert marker not in rendered_audits
        for forbidden in ("analytics_demo_reader_pw", "fake@invalid", "540.00", "300.00"):
            assert forbidden not in rendered_audits
        assert all(not hasattr(record, "raw_sql") and not hasattr(record, "plan_token") for record in audit_records)

    async def test_execute_returns_normalised_rows_and_rolls_back(self):
        runtime = PostgreSQLRuntime()
        limits = _limits(max_result_rows=5, max_result_bytes=262_144)
        sql = "SELECT id, customer, amount, created_at FROM public.orders ORDER BY id LIMIT 5"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await _call(runtime, "execute", connection, _integration_authorized(sql), limits)
                # 正常路径也必须回滚，连接不能停留在事务里。
                assert connection.in_transaction() is False
        finally:
            await engine.dispose()

        assert result.columns == ("id", "customer", "amount", "created_at")
        assert result.row_count == 5
        assert result.truncated is False
        assert result.rows[0][0] == 1
        # numeric 与 timestamptz 必须规范化为字符串，而不是驱动私有对象。
        assert isinstance(result.rows[0][2], str)
        assert isinstance(result.rows[0][3], str)

    async def test_execute_truncates_at_the_row_budget(self):
        runtime = PostgreSQLRuntime()
        limits = _limits(max_result_rows=3)
        sql = "SELECT id FROM public.orders ORDER BY id LIMIT 10"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await _call(runtime, "execute", connection, _integration_authorized(sql), limits)
                assert connection.in_transaction() is False
        finally:
            await engine.dispose()

        assert result.row_count == 3
        assert result.rows == ((1,), (2,), (3,))
        assert result.truncated is True

    async def test_read_only_transaction_rejects_an_injected_write_and_changes_nothing(self):
        runtime = PostgreSQLRuntime()
        limits = _limits()
        # 故意绕过 Phase 2A/2B1 直接注入写语句：只读事务必须自己挡住它。
        injected = "INSERT INTO public.orders (id, customer, amount) VALUES (999999, 'injected', 1.00)"
        engine = _engine(runtime, limits=limits)
        reported_code = None
        try:
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError) as caught:
                    await _call(runtime, "execute", connection, _integration_authorized(injected), limits)
                reported_code = caught.value.code
                assert connection.in_transaction() is False
            async with engine.connect() as monitor:
                remaining = await _fetch_all(monitor, "SELECT count(*) FROM public.orders WHERE id = 999999")
        finally:
            await engine.dispose()

        assert reported_code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
        assert remaining[0][0] == 0

    async def test_statement_timeout_cancels_the_query_and_leaves_no_residual_backend(self):
        runtime = PostgreSQLRuntime()
        limits = _limits(statement_timeout_ms=300, cancellation_grace_ms=500)
        sql = f"SELECT pg_sleep(30) AS {_TIMEOUT_MARKER}"
        engine = _engine(runtime, limits=limits)
        started = time.monotonic()
        try:
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError) as caught:
                    await _call(runtime, "execute", connection, _integration_authorized(sql), limits)
            elapsed = time.monotonic() - started
            async with engine.connect() as monitor:
                residual = await _wait_for_no_residual_timeout_backend(monitor, timeout_seconds=10)
        finally:
            await engine.dispose()

        assert caught.value.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
        # 服务端 timeout 必须在客户端总时限之前终止查询，而不是等满 30 秒。
        assert elapsed < 5.0, f"statement_timeout did not terminate the query (elapsed={elapsed:.2f}s)"
        assert residual == 0, "the timed-out query is still active in pg_stat_activity"

    async def test_client_timeout_destroys_the_connection_and_stops_the_query(self):
        runtime = PostgreSQLRuntime()
        # 服务端超时故意放宽，让客户端时限先到：这条路径证明的是"连接被销毁"而不是"服务端取消"。
        limits = _limits(statement_timeout_ms=3_000, cancellation_grace_ms=500)
        sql = f"SELECT pg_sleep(20) AS {_TIMEOUT_MARKER}"
        engine = _engine(runtime, limits=limits)
        try:
            async with engine.connect() as connection:
                try:
                    async with asyncio.timeout(0.4):
                        await runtime.execute(connection=connection, authorized=_integration_authorized(sql), limits=limits)
                except TimeoutError as error:
                    try:
                        await connection.invalidate()
                    except Exception:
                        pass
                    reported = DatasourceQueryError(ExecutionDecisionCode.EXECUTION_TIMEOUT)
                    assert reported.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
                    assert isinstance(error, TimeoutError)
            async with engine.connect() as monitor:
                # 服务端 statement_timeout=3s 最终会终止查询；客户端连接早已被销毁。
                residual = await _wait_for_no_residual_timeout_backend(monitor, timeout_seconds=15)
        finally:
            await engine.dispose()

        assert residual == 0, "the client-timed-out query is still active in pg_stat_activity"

    async def test_read_only_business_user_can_select_but_its_write_is_refused(self):
        runtime = PostgreSQLRuntime()
        limits = _limits()
        engine = _engine(runtime, variable=_READONLY_CREDENTIAL_ENV, limits=limits)
        try:
            async with engine.connect() as connection:
                result = await _call(runtime, "execute", connection, _integration_authorized("SELECT id FROM public.orders ORDER BY id LIMIT 1"), limits)
                assert result.rows == ((1,),)
            async with engine.connect() as connection:
                with pytest.raises(DatasourceQueryError):
                    await _call(runtime, "execute", connection, _integration_authorized("INSERT INTO public.orders (id, customer, amount) VALUES (999998, 'reader', 1.00)"), limits)
        finally:
            await engine.dispose()

    async def test_gateway_executes_end_to_end_and_maps_a_bad_password(self):
        from app.analytics.infrastructure.database_runtime import SQLAlchemyDatasourceQueryGateway
        from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver

        gateway = SQLAlchemyDatasourceQueryGateway(
            secret_resolver=EnvironmentDatasourceSecretResolver(),
            runtimes={DatasourceEngine.POSTGRESQL: PostgreSQLRuntime()},
        )
        limits = _limits()
        authorized = _integration_authorized("SELECT id FROM public.orders ORDER BY id LIMIT 2")

        result = await gateway.execute(datasource=_datasource(_CREDENTIAL_ENV), authorized=authorized, limits=limits)
        assert result.rows == ((1,), (2,))

        # 口令错误必须在 gateway 边界收敛成稳定码，且不含地址、用户名或 DSN。
        os.environ["ANALYTICS_TEST_PG_BAD_PASSWORD"] = json.dumps(
            {
                "engine": "postgresql",
                "host": "127.0.0.1",
                "port": int(os.environ.get("ANALYTICS_PG_PORT", "55432")),
                "database": "analytics_test",
                "username": "analytics_tester",
                "password": "definitely-not-the-password",
                "tls_mode": "disable",
            }
        )
        try:
            with pytest.raises(DatasourceQueryError) as caught:
                await gateway.explain(datasource=_datasource("ANALYTICS_TEST_PG_BAD_PASSWORD"), authorized=authorized, limits=limits)
        finally:
            del os.environ["ANALYTICS_TEST_PG_BAD_PASSWORD"]

        assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
        rendered = f"{caught.value!r} {caught.value}"
        assert "analytics_tester" not in rendered
        assert "127.0.0.1" not in rendered
        assert "definitely-not-the-password" not in rendered
