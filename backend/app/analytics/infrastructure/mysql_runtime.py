"""MySQL 8.4 受控执行运行时：`lower_case_table_names` 门禁、JSON v1 EXPLAIN 与流式结果读取。

为什么按这个形状实现：

- MySQL 的对象名解析取决于服务器初始化时的 `@@lower_case_table_names`。只有 `0`（大小写敏感、按原样存储）
  才与 Phase 2B1 的精确标识符语义一致；`1`/`2` 会把不同大小写的名称折叠到同一个物理对象上，而 2B1 的
  授权血缘按真实元数据名称精确比对。与其猜测数据目录所在文件系统的语义，不如拒绝。
- `MAX_EXECUTION_TIME` 是会话级、只对只读 SELECT 生效，因此必须在 `START TRANSACTION READ ONLY` 之前设置；
  连接用完即回滚并销毁，会话变量不需要恢复。
- 业务 SQL 只允许原样取自 `authorized.prepared.sql`：任何追加（ORDER BY、LIMIT、绑定参数）都会让
  "已授权" 与 "实际执行" 分离。
- 结果必须走服务端游标逐行拉取：默认游标会把整个结果集先物化，配额检查就失去意义。
- 驱动异常可能携带 DSN、用户名、地址甚至 SQL 片段，因此对外只暴露稳定决定码；调试链用 `raise ... from`
  留在内部，绝不进入异常文本。
- 只读事务仍允许临时表变更，但 Phase 2A 只放行单条 SELECT 并禁止赋值与危险语法，所以这个例外无法被用来
  构造写入。
"""

import asyncio
import hashlib
import json
import math
from collections.abc import Iterator, Sequence
from decimal import ROUND_CEILING, Decimal
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
from app.analytics.infrastructure.result_normalizer import ResultAccumulator, ResultNormalizationError

__all__ = ["MySQLRuntime"]

# MySQL 8.4 的 JSON EXPLAIN 默认是 v1：成本在 query_block.cost_info.query_cost，行数散落在各访问节点。
_IDENTIFIER_MODE_SQL = "SELECT @@lower_case_table_names"
_ROW_COUNT_FIELDS = ("rows_examined_per_scan", "rows_produced_per_join")
# MAX_EXECUTION_TIME 到期的错误号；只比对稳定错误号，不读驱动文本。
_EXECUTION_TIMEOUT_ERRNO = 3024
_SUPPORTED_IDENTIFIER_MODE = 0
# 计划体积与摘要规则固定在这里：改一处就会同时改变 plan_digest 的语义。
_CANONICAL_SEPARATORS = (",", ":")
_ERROR_CHAIN_LIMIT = 12


class MySQLRuntime:
    """MySQL 8.4 的 `EngineRuntime` 实现；engine 生命周期由 gateway 拥有。"""

    def connect_args(self, *, credential: object, limits: ExecutionLimits) -> dict[str, object]:
        """只返回驱动级 kwargs：连接超时与 TLS 语义，绝不返回 URL 或口令。"""

        # asyncmy 的 connect_timeout 只接受 >= 1 的整数秒，向上取整避免把超时设得比领域层更宽松。
        args: dict[str, object] = {"connect_timeout": max(1, math.ceil(limits.connect_timeout_ms / 1000))}
        ssl_context = getattr(credential, "ssl_context", None)
        if ssl_context is not None:
            args["ssl"] = ssl_context
        return args

    async def explain(self, *, connection: Any, authorized: AuthorizedQuerySpec, limits: ExecutionLimits) -> QueryCostEstimate:
        timeout_ms = _statement_timeout_ms(limits)
        transaction = await connection.begin()
        succeeded = False
        try:
            await _require_case_sensitive_identifiers(connection)
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
            await _require_case_sensitive_identifiers(connection)
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


async def _require_case_sensitive_identifiers(connection: Any) -> None:
    """连接的第一个语句就是标识符语义门禁；读不到或不是 0 一律拒绝。"""

    try:
        rows = (await connection.exec_driver_sql(_IDENTIFIER_MODE_SQL)).fetchall()
    except Exception as error:
        # 无法确认语义时安全拒绝；原始驱动文本不进入对外码。
        raise DatasourceQueryError(ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE) from error
    if len(rows) != 1 or len(rows[0]) != 1:
        raise DatasourceQueryError(ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE)
    mode = rows[0][0]
    # bool 是 int 的子类：把 true 当成 1 会静默接受一个不支持的语义。
    if isinstance(mode, bool) or not isinstance(mode, int) or mode != _SUPPORTED_IDENTIFIER_MODE:
        raise DatasourceQueryError(ExecutionDecisionCode.UNSUPPORTED_IDENTIFIER_MODE)


async def _open_read_only_transaction(connection: Any, timeout_ms: int) -> None:
    await connection.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}")
    await connection.exec_driver_sql("START TRANSACTION READ ONLY")


def _explain_statement(authorized: AuthorizedQuerySpec) -> str:
    """唯一允许的 EXPLAIN 形式：JSON、无 ANALYZE、SQL 原样取自授权值。"""

    return f"EXPLAIN FORMAT=JSON {authorized.prepared.sql}"


def _parse_plan(rows: Sequence[Sequence[object]], limits: ExecutionLimits) -> QueryCostEstimate:
    # EXPLAIN 的契约是恰好一行一列；多行说明结果形状不是我们认识的计划。
    if len(rows) != 1 or len(rows[0]) != 1:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    document = _decode_plan(rows[0][0], limits)
    canonical = _canonical_plan_bytes(document, limits)
    if not isinstance(document, dict):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    block = document.get("query_block")
    if not isinstance(block, dict):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    cost_info = block.get("cost_info")
    if not isinstance(cost_info, dict) or "query_cost" not in cost_info:
        # 缺少成本字段绝不填零：填零会让成本门禁在最需要它的查询上失效。
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return QueryCostEstimate(
        engine=DatasourceEngine.MYSQL,
        estimated_rows=int(_collect_work_rows(document).to_integral_value(rounding=ROUND_CEILING)),
        engine_cost=_require_non_negative_number(cost_info["query_cost"]),
        plan_digest=hashlib.sha256(canonical).hexdigest(),
    )


def _collect_work_rows(document: object) -> Decimal:
    """递归收集每个访问节点的行数并求和，得到保守的工作行数上界。

    求和而不是取最大值：nested loop、subquery 与 union 的访问节点会相乘级联，逐节点累加不会低估工作量。
    `rows_examined_per_scan` 与 `rows_produced_per_join` 同时出现时都计入，宁可高估。
    """

    total = Decimal(0)
    pending: list[object] = [document]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for field in _ROW_COUNT_FIELDS:
                if field in current:
                    total += _require_non_negative_number(current[field])
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return total


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


def _require_non_negative_number(value: object) -> Decimal:
    """JSON 数字或数字字符串；bool、null、非数字字符串、非有限值与负数一律拒绝。

    接受数字字符串是因为 MySQL 的 JSON v1 会把成本渲染成带引号的字符串（`"query_cost": "12.35"`）；
    这仍然是一次真实读取，不是"缺失时填零"。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    # 先转文本再转 Decimal：把 float 直接交给 Decimal 会把二进制误差带进成本比较。
    try:
        amount = Decimal(str(value).strip())
    except ArithmeticError:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED) from None
    if not amount.is_finite() or amount < 0:
        raise DatasourceQueryError(ExecutionDecisionCode.EXPLAIN_REJECTED)
    return amount


def _translate(error: BaseException) -> DatasourceQueryError:
    """把驱动异常收敛成稳定决定码；绝不保留任何原始文本。"""

    if isinstance(error, TimeoutError) or _has_errno(error, _EXECUTION_TIMEOUT_ERRNO):
        return DatasourceQueryError(ExecutionDecisionCode.EXECUTION_TIMEOUT)
    return DatasourceQueryError(ExecutionDecisionCode.DATABASE_UNAVAILABLE)


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    """遍历异常链与 SQLAlchemy 的 `orig`：MySQL 错误号藏在最内层。"""

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


def _has_errno(error: BaseException, errno_code: int) -> bool:
    for candidate in _error_chain(error):
        # MySQL 的 errno 是 DBAPI 异常的第一个位置参数；bool 不能当成整数错误号。
        args = getattr(candidate, "args", ())
        if args and isinstance(args[0], int) and not isinstance(args[0], bool) and args[0] == errno_code:
            return True
        errno = getattr(candidate, "errno", None)
        if isinstance(errno, int) and not isinstance(errno, bool) and errno == errno_code:
            return True
    return False


async def _release(connection: Any, transaction: Any, *, grace_ms: int, destroy: bool) -> None:
    """回滚，并在失败/超时路径上销毁连接。

    为什么超时后必须销毁：`asyncio.timeout()` 取消的是客户端等待，服务端可能仍在收尾；状态未知的连接
    一旦被复用，下一次请求就会看到上一次的会话变量（`MAX_EXECUTION_TIME`）与事务状态。
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
