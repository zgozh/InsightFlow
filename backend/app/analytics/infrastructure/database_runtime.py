import asyncio
import inspect
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics.application import DatasourceQueryError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceDefinition,
    DatasourceEngine,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryCostEstimate,
    QueryExecutionResult,
)


@runtime_checkable
class EngineRuntime(Protocol):
    """方言 runtime：只负责方言 SQL、计划解析与结果解析。

    连接创建、超时与销毁由 gateway 统一负责，避免每个方言各自管理连接生命周期。
    """

    def connect_args(self, *, credential: object, limits: ExecutionLimits) -> dict: ...

    async def explain(self, *, connection, authorized: AuthorizedQuerySpec, limits: ExecutionLimits) -> QueryCostEstimate: ...

    async def execute(self, *, connection, authorized: AuthorizedQuerySpec, limits: ExecutionLimits) -> QueryExecutionResult: ...


@runtime_checkable
class DatasourceSecretResolver(Protocol):
    """凭证解析端口。

    允许同步或异步实现：V1 的 `env://` resolver 只是读环境变量（同步），
    而后续 Vault/云 Secret Manager resolver 必然是异步的，端口必须两者都能承载。
    """

    def resolve(self, *, datasource: DatasourceDefinition): ...


def _default_engine_factory(url: URL, **kwargs):
    return create_async_engine(url, **kwargs)


def _connection_url(credential: object) -> URL:
    """只接受 SQLAlchemy URL 对象；字符串 DSN 一律视为凭证不可用。"""

    url = getattr(credential, "url", None)
    if not isinstance(url, URL):
        raise DatasourceQueryError(ExecutionDecisionCode.SECRET_UNAVAILABLE)
    return url


async def _invalidate(connection: object) -> None:
    invalidate = getattr(connection, "invalidate", None)
    if invalidate is None:
        return
    try:
        await invalidate()
    except Exception:  # noqa: BLE001 - 清理失败不能掩盖原始的稳定错误码
        return


class SQLAlchemyDatasourceQueryGateway:
    """SQLAlchemy Async Core 网关：按 engine 分派方言 runtime。

    每次 EXPLAIN/execute 都创建短生命周期的 ``AsyncEngine``，配置 ``NullPool`` 与
    ``echo=False``，并在 finally 中 ``dispose()``。连接绝不跨数据源或跨调用复用：
    租户凭证、search_path、timeout 与 session 变量都可能互相串线。
    """

    def __init__(
        self,
        *,
        secret_resolver: DatasourceSecretResolver,
        runtimes: Mapping[DatasourceEngine, EngineRuntime],
        engine_factory=None,
    ) -> None:
        self._secret_resolver = secret_resolver
        self._runtimes = dict(runtimes)
        self._engine_factory = engine_factory or _default_engine_factory

    async def explain(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryCostEstimate:
        return await self._run("explain", datasource=datasource, authorized=authorized, limits=limits)

    async def execute(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryExecutionResult:
        return await self._run("execute", datasource=datasource, authorized=authorized, limits=limits)

    async def _run(
        self,
        operation: str,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ):
        runtime = self._runtimes.get(datasource.engine)
        if runtime is None:
            # 未知方言没有已验证的能力，默认拒绝而不是猜测。
            raise DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE)

        try:
            resolved = self._secret_resolver.resolve(datasource=datasource)
            credential = await resolved if inspect.isawaitable(resolved) else resolved
        except DatasourceQueryError:
            raise
        except Exception as error:  # noqa: BLE001 - 解析失败只能是 SECRET_UNAVAILABLE
            raise DatasourceQueryError(ExecutionDecisionCode.SECRET_UNAVAILABLE) from error

        url = _connection_url(credential)
        try:
            connect_args = runtime.connect_args(credential=credential, limits=limits)
            engine = self._engine_factory(url, poolclass=NullPool, echo=False, connect_args=connect_args)
        except Exception as error:  # noqa: BLE001 - 建 engine/driver kwargs 失败也不能泄漏 URL 或驱动文本
            raise DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE) from error
        # 客户端总时限固定为 statement_timeout + 取消宽限，给服务器返回取消结果和清理留出余量。
        budget_seconds = (limits.statement_timeout_ms + limits.cancellation_grace_ms) / 1000
        try:
            async with engine.connect() as connection:
                try:
                    async with asyncio.timeout(budget_seconds):
                        if operation == "explain":
                            return await runtime.explain(connection=connection, authorized=authorized, limits=limits)
                        return await runtime.execute(connection=connection, authorized=authorized, limits=limits)
                except TimeoutError as error:
                    # 超时后连接状态未知，必须销毁而不能回收复用。
                    await _invalidate(connection)
                    raise DatasourceQueryError(ExecutionDecisionCode.EXECUTION_TIMEOUT) from error
                except DatasourceQueryError:
                    raise
                except Exception as error:  # noqa: BLE001 - 驱动异常文本可能含 DSN/SQL，必须脱敏
                    raise DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE) from error
        except DatasourceQueryError:
            raise
        except Exception as error:  # noqa: BLE001 - 建连失败同样脱敏
            raise DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE) from error
        finally:
            await engine.dispose()
