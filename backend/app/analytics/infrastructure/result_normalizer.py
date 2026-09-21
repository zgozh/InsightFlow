"""结果规范化与配额：把驱动返回值收敛成领域可接受的 JSON 标量。

为什么按这个形状实现：

- 驱动可以返回任意私有对象，其中一部分自带 `__repr__` / `__str__` / `__format__`。规范化只对闭集内的
  已知类型做转换，未知对象一律用稳定码直接拒绝，且拒绝路径上绝不格式化该对象：格式化等于执行驱动提供的
  代码，也会让被拒绝的值进入异常文本或日志。
- `fetchall()` 会把整个结果集先物化进内存，配额就失去意义；所以累计器只接受可 async 迭代的驱动结果，
  逐行推进，并在配额判定成立时立刻停止拉取。
- 行只有整行接收或整行丢弃两种结局：绝不返回半行或半个 cell。
- `PreparedQuery.row_limit` 是 SQL 层上限，由应用层保证；`limits.max_result_rows` 是独立的传输层上限，
  由本模块执行，两者互不替代。

字节规则固定为一份 canonical JSON 文档：UTF-8、`ensure_ascii=False`、紧凑分隔符 `(",", ":")`，
`schema` 为列数组、`rows` 为完整行数组（不使用列名到值的 dict，重复列名会被 dict 静默覆盖）。
`byte_count` 就是这份文档的 UTF-8 字节数，因此它同时覆盖列头的结构开销——列头是必须返回的元数据，
不因为它而放宽上限。
"""

import json
import math
from collections.abc import AsyncIterable, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.analytics.domain import ExecutionDecisionCode, ExecutionLimits, JsonScalar, QueryExecutionResult

# 紧凑分隔符固定为元组常量：任何一处改动都会同时改变 byte_count 的语义。
_CANONICAL_SEPARATORS: Final = (",", ":")
_DOCUMENT_PREFIX_BYTES: Final = len('{"columns":')
_DOCUMENT_BRIDGE_BYTES: Final = len(',"rows":[')
_DOCUMENT_SUFFIX_BYTES: Final = len("]}")
_ROW_SEPARATOR_BYTES: Final = 1


class ResultNormalizationError(Exception):
    """结果规范化拒绝。

    只携带稳定 `ExecutionDecisionCode`：驱动异常文本可能包含 DSN、地址或值本身，不能向上穿透；
    调用方拿到码后自行映射为对外决定。
    """

    def __init__(self, code: ExecutionDecisionCode) -> None:
        super().__init__(code.value)
        self.code = code


def _canonical_json_bytes(value: object) -> int:
    """canonical JSON 文本的 UTF-8 字节数；这是唯一允许的字节度量入口。"""

    # allow_nan=False 是纵深防御：即便上游漏过非有限浮点，也不会生成非法 JSON 文本。
    text = json.dumps(value, ensure_ascii=False, separators=_CANONICAL_SEPARATORS, allow_nan=False)
    return len(text.encode("utf-8"))


def normalize_cell(value: object) -> JsonScalar:
    """把单个驱动 cell 转成 JSON 标量，未知类型用稳定码拒绝。

    只对闭集内的类型调用转换方法（`Decimal.__str__`、`date.isoformat`、`UUID.__str__`）；其他对象
    直接拒绝，绝不触碰它们自己的钩子。
    """

    # bool 必须先于 int 判断：它是 int 的子类。
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # NaN/Infinity 无法稳定 JSON 化，必须在进入结果前拒绝。
        if not math.isfinite(value):
            raise ResultNormalizationError(ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE)
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        # 不转 float（二进制误差会改写金额）；也不展开指数（极大指数会变成超长字符串）。
        if not value.is_finite():
            raise ResultNormalizationError(ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE)
        return str(value)
    if isinstance(value, datetime):
        # datetime 必须先于 date 判断：它是 date 的子类。无时区值原样渲染，不擅自假设 UTC。
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise ResultNormalizationError(ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE)


class ResultAccumulator:
    """逐行累计的 async 结果规范化器；最终只返回领域值 `QueryExecutionResult`。

    两种等价的调用方式：

        accumulator = ResultAccumulator(columns=result.keys(), limits=limits)
        async for row in result:
            if not accumulator.add_row(row):
                break
        return accumulator.result()

        return await ResultAccumulator(columns=result.keys(), limits=limits).collect(result)

    连接、游标、事务的关闭与回滚属于调用方（数据库运行时）；本模块只负责停止拉取行，不替调用方关闭流。
    """

    __slots__ = ("_byte_count", "_columns", "_limits", "_rows", "_truncated")

    def __init__(self, *, columns: Sequence[str], limits: ExecutionLimits) -> None:
        # 列数在读取首行之前判定：超限时一行数据都不会从驱动拉取。
        if len(columns) > limits.max_result_columns:
            raise ResultNormalizationError(ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE)
        for column in columns:
            # 列名来自驱动元数据。形状异常必须在这里用稳定码拒绝，否则领域构造会在末尾抛自由文本 ValueError。
            if not isinstance(column, str) or not column.strip() or column != column.strip():
                raise ResultNormalizationError(ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE)
        self._columns = tuple(columns)
        self._limits = limits
        self._rows: list[tuple[JsonScalar, ...]] = []
        # 空文档（列头 + 空 rows 数组）就是 byte_count 的起点，列头开销始终计入。
        self._byte_count = _DOCUMENT_PREFIX_BYTES + _canonical_json_bytes(self._columns) + _DOCUMENT_BRIDGE_BYTES + _DOCUMENT_SUFFIX_BYTES
        self._truncated = False

    def add_row(self, row: Sequence[object]) -> bool:
        """整行追加；返回 False 表示配额已到，调用方应停止拉取。

        已决定截断后继续喂入的行一律忽略：结果只能包含完整的、已提交的行。
        """

        if self._truncated:
            return False
        if len(row) != len(self._columns):
            # 行宽与列数不一致是驱动契约违反，不是可映射的对外决定，因此不用稳定码伪装成拒绝。
            raise ValueError("each row must have one cell per column")
        # 先规范化再判定配额：字节数只能用规范形式度量，且"非法 cell 拒绝"必须优先于"行被截断"，
        # 否则一行里的未知类型会因为"反正要丢"而被静默吞掉。
        normalised = tuple(normalize_cell(cell) for cell in row)
        row_bytes = _canonical_json_bytes(normalised) + (_ROW_SEPARATOR_BYTES if self._rows else 0)
        if len(self._rows) + 1 > self._limits.max_result_rows or self._byte_count + row_bytes > self._limits.max_result_bytes:
            self._truncated = True
            return False
        self._rows.append(normalised)
        self._byte_count += row_bytes
        return True

    async def collect(self, rows: AsyncIterable[Sequence[object]]) -> QueryExecutionResult:
        """逐行消费驱动结果；一旦做出截断判定就停止拉取。"""

        async for row in rows:
            if not self.add_row(row):
                break
        return self.result()

    def result(self) -> QueryExecutionResult:
        """当前已提交行构成的领域值快照。"""

        return QueryExecutionResult(
            columns=self._columns,
            rows=tuple(self._rows),
            row_count=len(self._rows),
            byte_count=self._byte_count,
            truncated=self._truncated,
        )
