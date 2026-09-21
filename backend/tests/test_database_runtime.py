import asyncio
from decimal import Decimal

import pytest

from app.analytics.application import DatasourceQueryError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    ExecutionDecisionCode,
    ExecutionLimits,
    PreparedQuery,
    QueryCostEstimate,
    QueryExecutionResult,
    QueryRisk,
)
from app.analytics.infrastructure.database_runtime import SQLAlchemyDatasourceQueryGateway

_CREDENTIAL_URL = "postgresql+asyncpg://user:secret-value@127.0.0.1:5432/analytics"


def _datasource(engine=DatasourceEngine.POSTGRESQL):
    return DatasourceDefinition(
        id="ds-1",
        owner_id="user-1",
        name="Warehouse",
        engine=engine,
        secret_ref="env://ANALYTICS_DS",
        default_schema="public",
        status=DatasourceStatus.ACTIVE,
    )


def _authorized(engine=DatasourceEngine.POSTGRESQL):
    return AuthorizedQuerySpec(
        prepared=PreparedQuery(
            sql="SELECT id FROM orders LIMIT 10",
            engine=engine,
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
    )


def _limits(**overrides):
    values = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 200,
        "cancellation_grace_ms": 50,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 64,
        "max_result_rows": 10,
        "max_result_bytes": 4_194_304,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def _estimate():
    return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("1"), plan_digest="c" * 64)


def _result():
    return QueryExecutionResult(columns=("id",), rows=((1,),), row_count=1, byte_count=21, truncated=False)


class _FakeConnection:
    def __init__(self, *, enter_error=None):
        self._enter_error = enter_error
        self.invalidated = False
        self.rolled_back = False

    async def __aenter__(self):
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def invalidate(self):
        self.invalidated = True

    async def rollback(self):
        self.rolled_back = True


class _FakeEngine:
    def __init__(self, connection):
        self._connection = connection
        self.disposed = 0

    def connect(self):
        return self._connection

    async def dispose(self):
        self.disposed += 1


class _FakeEngineFactory:
    def __init__(self, engine):
        self.engine = engine
        self.calls: list[dict] = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.engine


class _FakeResolver:
    def __init__(self, credential=None, error=None):
        self._credential = credential
        self._error = error
        self.calls = 0

    async def resolve(self, *, datasource):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._credential


class _FakeCredential:
    """最小凭证替身：真实 resolver 返回的对象暴露 SQLAlchemy URL。"""

    def __init__(self, url=None):
        from sqlalchemy import make_url

        self.url = make_url(_CREDENTIAL_URL) if url is None else url

    def __repr__(self) -> str:
        return "<credential>"


class _FakeRuntime:
    def __init__(self, *, explain_result=None, execute_result=None, explain_error=None, execute_error=None, delay=0.0):
        self.explain_result = explain_result if explain_result is not None else _estimate()
        self.execute_result = execute_result if execute_result is not None else _result()
        self.explain_error = explain_error
        self.execute_error = execute_error
        self.delay = delay
        self.connect_args_calls: list[dict] = []
        self.explain_calls: list[dict] = []
        self.execute_calls: list[dict] = []

    def connect_args(self, *, credential, limits):
        self.connect_args_calls.append({"credential": credential, "limits": limits})
        return {"timeout": limits.connect_timeout_ms / 1000}

    async def explain(self, *, connection, authorized, limits):
        self.explain_calls.append({"connection": connection, "authorized": authorized, "limits": limits})
        if self.explain_error is not None:
            raise self.explain_error
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.explain_result

    async def execute(self, *, connection, authorized, limits):
        self.execute_calls.append({"connection": connection, "authorized": authorized, "limits": limits})
        if self.execute_error is not None:
            raise self.execute_error
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.execute_result


def _gateway(*, runtime=None, connection=None, resolver=None, engine=None):
    connection = connection if connection is not None else _FakeConnection()
    engine = engine if engine is not None else _FakeEngine(connection)
    factory = _FakeEngineFactory(engine)
    runtimes = {DatasourceEngine.POSTGRESQL: runtime} if runtime is not None else {}
    gateway = SQLAlchemyDatasourceQueryGateway(
        secret_resolver=resolver if resolver is not None else _FakeResolver(_FakeCredential()),
        runtimes=runtimes,
        engine_factory=factory,
    )
    return gateway, factory, engine, connection


@pytest.mark.asyncio
async def test_gateway_uses_nullpool_and_disables_echo():
    runtime = _FakeRuntime()
    gateway, factory, _engine, _connection = _gateway(runtime=runtime)

    await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert len(factory.calls) == 1
    from sqlalchemy.pool import NullPool

    assert factory.calls[0]["poolclass"] is NullPool
    assert factory.calls[0]["echo"] is False


@pytest.mark.asyncio
async def test_gateway_disposes_the_engine_on_success():
    runtime = _FakeRuntime()
    gateway, _factory, engine, _connection = _gateway(runtime=runtime)

    await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert engine.disposed == 1


@pytest.mark.asyncio
async def test_gateway_disposes_the_engine_when_the_runtime_fails():
    runtime = _FakeRuntime(explain_error=DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED))
    gateway, _factory, engine, _connection = _gateway(runtime=runtime)

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.EXPLAIN_REJECTED
    assert engine.disposed == 1


@pytest.mark.asyncio
async def test_gateway_disposes_the_engine_when_connecting_fails():
    connection = _FakeConnection(enter_error=OSError("connection refused"))
    runtime = _FakeRuntime()
    gateway, _factory, engine, _connection = _gateway(runtime=runtime, connection=connection)

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
    assert engine.disposed == 1


@pytest.mark.asyncio
async def test_gateway_does_not_create_an_engine_when_the_secret_is_unavailable():
    runtime = _FakeRuntime()
    gateway, factory, _engine, _connection = _gateway(runtime=runtime, resolver=_FakeResolver(error=RuntimeError("missing env")))

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.SECRET_UNAVAILABLE
    assert factory.calls == []


@pytest.mark.asyncio
async def test_gateway_rejects_an_unsupported_engine_without_creating_an_engine():
    from app.analytics.infrastructure.database_runtime import SQLAlchemyDatasourceQueryGateway as Gateway

    factory_holder: list[dict] = []

    def factory(url, **kwargs):
        factory_holder.append({"url": url, **kwargs})
        raise AssertionError("engine must not be created for an unsupported engine")

    gateway = Gateway(secret_resolver=_FakeResolver(_FakeCredential()), runtimes={}, engine_factory=factory)

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(engine=DatasourceEngine.MYSQL), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
    assert factory_holder == []


@pytest.mark.asyncio
async def test_gateway_maps_a_client_timeout_to_execution_timeout():
    runtime = _FakeRuntime(delay=2.0)
    gateway, _factory, engine, _connection = _gateway(runtime=runtime)

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.EXECUTION_TIMEOUT
    assert engine.disposed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE,
        ExecutionDecisionCode.EXECUTION_TIMEOUT,
        ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE,
        ExecutionDecisionCode.DATABASE_UNAVAILABLE,
    ],
)
async def test_gateway_propagates_stable_runtime_codes_for_execute(code):
    runtime = _FakeRuntime(execute_error=DatasourceQueryError(code))
    gateway, _factory, engine, _connection = _gateway(runtime=runtime)

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.execute(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is code
    assert engine.disposed == 1


@pytest.mark.asyncio
async def test_gateway_passes_the_creditential_connect_args_to_the_engine():
    runtime = _FakeRuntime()
    gateway, factory, _engine, _connection = _gateway(runtime=runtime)

    await gateway.execute(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert len(runtime.connect_args_calls) == 1
    assert factory.calls[0]["connect_args"] == {"timeout": 5.0}


@pytest.mark.asyncio
async def test_gateway_returns_runtime_results_unchanged():
    runtime = _FakeRuntime()
    gateway, _factory, _engine, _connection = _gateway(runtime=runtime)
    authorized = _authorized()

    estimate = await gateway.explain(datasource=_datasource(), authorized=authorized, limits=_limits())
    result = await gateway.execute(datasource=_datasource(), authorized=authorized, limits=_limits())

    assert estimate is runtime.explain_result
    assert result is runtime.execute_result
    # 传给 runtime 的授权值必须原样，SQL 只能来自 authorized.prepared.sql。
    assert runtime.explain_calls[0]["authorized"] is authorized


@pytest.mark.asyncio
async def test_gateway_errors_never_contain_the_connection_url_or_password():
    gateway, _factory, _engine, _connection = _gateway(runtime=_FakeRuntime(), resolver=_FakeResolver(error=OSError(_CREDENTIAL_URL)))

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    rendered = f"{caught.value!r} {caught.value}"
    assert "secret-value" not in rendered
    assert "asyncpg://" not in rendered
    assert "127.0.0.1" not in rendered


@pytest.mark.asyncio
async def test_gateway_rejects_a_credential_without_a_sqlalchemy_url():
    gateway, factory, _engine, _connection = _gateway(runtime=_FakeRuntime(), resolver=_FakeResolver(_FakeCredential(url="not-a-url")))

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.SECRET_UNAVAILABLE
    assert factory.calls == []


@pytest.mark.asyncio
async def test_gateway_maps_engine_construction_failure_without_leaking_the_url():
    runtime = _FakeRuntime()

    def exploding_factory(url, **kwargs):
        raise RuntimeError(f"cannot create engine for {url}")

    gateway = SQLAlchemyDatasourceQueryGateway(
        secret_resolver=_FakeResolver(_FakeCredential()),
        runtimes={DatasourceEngine.POSTGRESQL: runtime},
        engine_factory=exploding_factory,
    )

    with pytest.raises(DatasourceQueryError) as caught:
        await gateway.explain(datasource=_datasource(), authorized=_authorized(), limits=_limits())

    assert caught.value.code is ExecutionDecisionCode.DATABASE_UNAVAILABLE
    assert "secret-value" not in f"{caught.value!r} {caught.value}"
