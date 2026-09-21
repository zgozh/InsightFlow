"""PostgreSQL 16 受控执行运行时：只读事务内的 JSON EXPLAIN 与流式结果读取。

为什么按这个形状实现：

- 只读事务与 `SET LOCAL statement_timeout` 都只在事务块内才有语义。控制语句必须严格排在事务开始之后、
  任何业务语句之前：顺序一旦被调整，PostgreSQL 只会给一个 warning 然后继续正常返回，失效的防线看起来
  仍然是"成功"的。
- `SET` 不接受绑定参数，timeout 只能内联整数。这里只接受领域层已校验范围的普通 `int`，不拼接其他文本。
- 业务 SQL 只允许原样取自 `authorized.prepared.sql`：任何追加（ORDER BY、LIMIT、绑定参数）都会让
  "已授权" 与 "实际执行" 分离。
- 结果必须走服务端游标逐行拉取。asyncpg 的非游标路径在 `_prepare_and_execute` 里一次性 `fetch()` 整个
  结果集，配额检查会在内存已经吃满之后才发生。
- 驱动异常可能携带 DSN、用户名、地址甚至 SQL 片段，因此对外只暴露稳定决定码；调试链用 `raise ... from`
  留在内部，绝不进入异常文本。
- 只读事务挡得住主要写命令，但它不是"绝不写磁盘"的底层沙箱：Phase 2A 的 AST allowlist 与数据库最小权限
  账号仍是主控制，这里只是第二层防线。
"""

import asyncio
import hashlib
import json
from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.analytics.application import DatasourceQueryError
from app.analytics.domain import (
    AuthorizedQuerySpec,
    DatasourceEngine,
    ExecutionDecisionCode,
    ExecutionLimits,
    QueryCostEstimate,
    QueryExecutionResult,
)
from app.analytics.infrastructure.datasource_secrets import DatasourceTlsMode
from app.analytics.infrastructure.result_normalizer import ResultAccumulator, ResultNormalizationError

__all__ = ["PostgreSQLRuntime"]

# PostgreSQL 服务端取消（含 statement_timeout 到期）的 SQLSTATE；只比对稳定码，不读驱动文本。
_QUERY_CANCELED_SQLSTATE = "57014"
# 计划体积与摘要规则固定在这里：改一处就会同时改变 plan_digest 的语义。
_CANONICAL_SEPARATORS = (",", ":")
_ERROR_CHAIN_LIMIT = 12


class PostgreSQLRuntime:
    """PostgreSQL 16 的 `EngineRuntime` 实现；engine 生命周期由 gateway 拥有。"""

    def connect_args(self, *, credential: object, limits: ExecutionLimits) -> dict[str, object]:
        """只返回驱动级 kwargs：连接超时与 TLS 语义，绝不返回 URL 或口令。"""

        # asyncpg 的 connect timeout 以秒为单位（允许小数），默认 ssl='prefer' 会先尝试一次 TLS 握手；
        # 明文凭证已由 resolver 限制在 loopback，这里仍需显式关闭，避免连接语义取决于服务器反应。
        args: dict[str, object] = {"timeout": limits.connect_timeout_ms / 1000}
        ssl_context = getattr(credential, "ssl_context", None)
        if ssl_context is not None:
            args["ssl"] = ssl_context
        elif getattr(credential, "tls_mode", None) is DatasourceTlsMode.DISABLE:
            args["ssl"] = False
        return args

    async def explain(self, *, connection: Any, authorized: AuthorizedQuerySpec, limits: ExecutionLimits) -> QueryCostEstimate:
        timeout_ms = _statement_timeout_ms(limits)
        transaction = await connection.begin()
        succeeded = False
        try:
            await _open_read_only_transaction(connection, timeout_ms)
            result = await connection.exec_driver_sql(_explain_statement(authorized))
            estimate = _parse_plan(result.fetchall(), limits)
            succeeded = True
            return estimate
        except DatasourceQueryError:
            raise
        except ResultNormalizationError as error:
            raise DatasourceQueryError(error.code) from error
        except Exception as error:
            raise _translate(error) from error
        finally:
            await _release(connection, transaction, grace_ms=limits.cancellation_grace_ms, destroy=not succeeded)

    async def execute(self, *, connection: Any, authorized: AuthorizedQuerySpec, limits: ExecutionLimits) -> QueryExecutionResult:
        timeout_ms = _statement_timeout_ms(limits)
        transaction = await connection.begin()
        succeeded = False
        try:
            await _open_read_only_transaction(connection, timeout_ms)
            # text() 不做任何改写；服务端游标让行在配额判定时才被拉取，而不是先全部物化。
            async with connection.stream(text(authorized.prepared.sql)) as streamed:
                accumulator = ResultAccumulator(columns=streamed.keys(), limits=limits)
                result = await accumulator.collect(streamed)
            succeeded = True
            return result
        except ResultNormalizationError as error:
            raise DatasourceQueryError(error.code) from error
        except DatasourceQueryError:
            raise
        except Exception as error:
            raise _translate(error) from error
        finally:
            await _release(connection, transaction, grace_ms=limits.cancellation_grace_ms, destroy=not succeeded)


def _statement_timeout_ms(limits: ExecutionLimits) -> int:
    """把领域层的已验证整数再核一遍：它会被内联进 `SET`，不接受任何其他类型。"""

    value = limits.statement_timeout_ms
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 60_000:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return value


async def _open_read_only_transaction(connection: Any, timeout_ms: int) -> None:
    await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    await connection.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")


def _explain_statement(authorized: AuthorizedQuerySpec) -> str:
    """唯一允许的 EXPLAIN 形式：JSON、无 ANALYZE、SQL 原样取自授权值。"""

    return f"EXPLAIN (FORMAT JSON) {authorized.prepared.sql}"


def _parse_plan(rows: Sequence[Sequence[object]], limits: ExecutionLimits) -> QueryCostEstimate:
    # EXPLAIN (FORMAT JSON) 的契约是恰好一行一列；多行说明结果形状不是我们认识的计划。
    if len(rows) != 1 or len(rows[0]) != 1:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    document = _decode_plan(rows[0][0], limits)
    canonical = _canonical_plan_bytes(document, limits)
    if not isinstance(document, list) or len(document) != 1 or not isinstance(document[0], dict):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    plan = document[0].get("Plan")
    if not isinstance(plan, dict):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return QueryCostEstimate(
        engine=DatasourceEngine.POSTGRESQL,
        estimated_rows=_require_row_count(plan.get("Plan Rows")),
        engine_cost=_require_cost(plan.get("Total Cost")),
        plan_digest=hashlib.sha256(canonical).hexdigest(),
    )


def _decode_plan(raw: object, limits: ExecutionLimits) -> object:
    if isinstance(raw, str):
        # 原始文本是解析前的体积门禁：先拒绝超限文本，避免为一份被拒的计划分配解析内存。
        if len(raw.encode("utf-8")) > limits.max_explain_bytes:
            raise DatasourceQueryError(ExecutionDecisionCode.COST_LIMIT_EXCEEDED)
        try:
            return json.loads(raw)
        except ValueError:
            raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED) from None
    if isinstance(raw, (list, dict)):
        return raw
    raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)


def _canonical_plan_bytes(document: object, limits: ExecutionLimits) -> bytes:
    """规范化计划 JSON 的字节形式；摘要与体积都只以这份文档为准。"""

    try:
        # allow_nan=False 是纵深防御：非有限浮点绝不进入摘要文档。
        encoded = json.dumps(document, ensure_ascii=False, separators=_CANONICAL_SEPARATORS, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED) from None
    if len(encoded) > limits.max_explain_bytes:
        raise DatasourceQueryError(ExecutionDecisionCode.COST_LIMIT_EXCEEDED)
    return encoded


def _require_cost(value: object) -> Decimal:
    # bool 是 int 的子类，JSON 的 true/false 不能当成 1/0 成本。
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    # 先转文本再转 Decimal：把 float 直接交给 Decimal 会把二进制误差带进成本比较。
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return amount


def _require_row_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return value


def _translate(error: BaseException) -> DatasourceQueryError:
    """把驱动异常收敛成稳定决定码；绝不保留任何原始文本。"""

    if isinstance(error, TimeoutError) or _has_sqlstate(error, _QUERY_CANCELED_SQLSTATE):
        return DatasourceQueryError(ExecutionDecisionCode.EXECUTION_TIMEOUT)
    return DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE)


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    """遍历异常链与 SQLAlchemy 的 `orig`：asyncpg 的 SQLSTATE 藏在最内层。"""

    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending and len(seen) < _ERROR_CHAIN_LIMIT:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attribute in ("orig", "__cause__", "__context__"):
            candidate = getattr(current, attribute, None)
            if isinstance(candidate, BaseException):
                pending.append(candidate)


def _has_sqlstate(error: BaseException, sqlstate: str) -> bool:
    for candidate in _error_chain(error):
        for attribute in ("sqlstate", "pgcode"):
            if getattr(candidate, attribute, None) == sqlstate:
                return True
    return False


async def _release(connection: Any, transaction: Any, *, grace_ms: int, destroy: bool) -> None:
    """回滚，并在失败/超时路径上销毁连接。

    为什么超时后必须销毁：`asyncio.timeout()` 取消的是客户端等待，服务端可能仍在收尾；状态未知的连接
    一旦被复用，下一次请求就会看到上一次的会话状态（事务、timeout、只读标志）。
    `engine.dispose()` 之后仍会物理关闭连接，所以这里的清理只需有时限，不需要无限等待。
    """

    rolled_back = await _wait_bounded(asyncio.ensure_future(_rollback_quietly(transaction)), grace_ms)
    if rolled_back and not destroy:
        return
    await _wait_bounded(asyncio.ensure_future(_invalidate_quietly(connection)), grace_ms)


async def _wait_bounded(task: asyncio.Future, grace_ms: int) -> bool:
    """等待清理任务，最多 grace_ms 毫秒；超时不取消它，也不吞掉外层取消。"""

    done, _pending = await asyncio.wait({task}, timeout=grace_ms / 1000)
    return task in done


async def _rollback_quietly(transaction: Any) -> None:
    try:
        await transaction.rollback()
    except BaseException:
        # 回滚失败没有对外语义：决定已经做出，剩余清理交给 invalidate 与 engine.dispose()。
        return


async def _invalidate_quietly(connection: Any) -> None:
    try:
        await connection.invalidate()
    except BaseException:
        return
