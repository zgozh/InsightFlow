"""结果规范化与配额的测试。

字节期望值全部写死，并在注释里写出对应的 canonical JSON 文档：期望值只能由 spec §11.3 的固定规则
（UTF-8、ensure_ascii=False、separators=(",", ":")、columns 加完整 rows）手工推导。
用生产 helper 计算 expected 会让"规则被改坏"和"测试跟着改坏"同时发生，因此这里完全不导入 json。
"""

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.analytics.domain import ExecutionDecisionCode, ExecutionLimits, QueryExecutionResult
from app.analytics.infrastructure.result_normalizer import (
    ResultAccumulator,
    ResultNormalizationError,
    normalize_cell,
)

_REPR_CALLS: list[str] = []
_STR_CALLS: list[str] = []
_FORMAT_CALLS: list[str] = []


class _HostileValue:
    """未知的驱动私有对象：任何 repr/str/format 调用都必须先被记录、再立即失败。"""

    def __repr__(self) -> str:
        _REPR_CALLS.append("repr")
        raise AssertionError("repr() must never be called on an unknown value")

    def __str__(self) -> str:
        _STR_CALLS.append("str")
        raise AssertionError("str() must never be called on an unknown value")

    def __format__(self, format_spec: str) -> str:
        _FORMAT_CALLS.append("format")
        raise AssertionError("format() must never be called on an unknown value")


class _StreamOnlyResult:
    """只支持 async 迭代的驱动结果：任何 fetchall/fetchmany 式属性访问都直接失败。"""

    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self._rows = rows

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the normaliser must not access result.{name}")

    async def __aiter__(self):
        for row in self._rows:
            yield row


def _limits(**overrides):
    values = {
        "connect_timeout_ms": 5_000,
        "statement_timeout_ms": 10_000,
        "cancellation_grace_ms": 500,
        "max_estimated_rows": 100_000,
        "max_engine_cost": Decimal("10000"),
        "max_explain_bytes": 1_048_576,
        "max_result_columns": 64,
        "max_result_rows": 1_000,
        "max_result_bytes": 4_194_304,
        "plan_ttl_seconds": 60,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


async def _stream(rows):
    for row in rows:
        yield row


async def _collect(columns, rows, **limit_overrides):
    accumulator = ResultAccumulator(columns=columns, limits=_limits(**limit_overrides))
    return await accumulator.collect(_stream(rows))


def _reset_hostile_calls() -> None:
    _REPR_CALLS.clear()
    _STR_CALLS.clear()
    _FORMAT_CALLS.clear()


def test_normalize_cell_passes_through_none_bool_int_str_and_finite_float():
    assert normalize_cell(None) is None
    assert normalize_cell(True) is True
    assert normalize_cell(7) == 7
    assert not isinstance(normalize_cell(7), str)
    assert normalize_cell("text") == "text"
    finite = normalize_cell(1.5)
    assert isinstance(finite, float)
    assert finite == 1.5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("10.50"), "10.50"),
        (Decimal("0.1"), "0.1"),
        (Decimal("-0.000"), "-0.000"),
        # 不做指数展开：极大指数若被展开成超长字符串会变成新的放大面。
        (Decimal("1E+2"), "1E+2"),
        (Decimal("123456789012345678901234567890.123456789"), "123456789012345678901234567890.123456789"),
    ],
)
def test_normalize_cell_renders_decimal_as_a_canonical_string(value, expected):
    rendered = normalize_cell(value)

    assert isinstance(rendered, str)
    assert rendered == expected


def test_normalize_cell_renders_temporal_values_as_iso8601_without_assuming_utc():
    assert normalize_cell(date(2024, 1, 2)) == "2024-01-02"
    assert normalize_cell(time(3, 4, 5)) == "03:04:05"
    assert normalize_cell(time(3, 4, 5, 6000)) == "03:04:05.006000"
    # 无时区 datetime 必须原样渲染：擅自补 Z 会把数据库的本地时间伪造成 UTC。
    assert normalize_cell(datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02T03:04:05"
    assert normalize_cell(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)) == "2024-01-02T03:04:05+00:00"
    assert normalize_cell(datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=8)))) == "2024-01-02T03:04:05+08:00"


def test_normalize_cell_renders_uuid_in_standard_string_form():
    assert normalize_cell(UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301")) == "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    # 大写输入落回标准小写形式，调用方不需要自己归一化。
    assert normalize_cell(UUID("3F2504E0-4F89-11D3-9A0C-0305E82C3301")) == "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_normalize_cell_rejects_non_finite_numbers(value):
    with pytest.raises(ResultNormalizationError) as caught:
        normalize_cell(value)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE


@pytest.mark.parametrize(
    "value",
    [b"raw", bytearray(b"raw"), memoryview(b"raw"), object(), {"a": 1}, [1, 2], (1, 2), {1, 2}, complex(1, 2), Decimal],
)
def test_normalize_cell_rejects_binary_driver_and_other_objects(value):
    with pytest.raises(ResultNormalizationError) as caught:
        normalize_cell(value)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE


def test_rejection_carries_only_the_stable_code():
    with pytest.raises(ResultNormalizationError) as caught:
        normalize_cell(b"secret-bytes")

    # 外发文本只有稳定码：既不回显被拒绝的值，也不携带驱动文本。
    assert str(caught.value) == "unsupported_result_type"
    assert "secret-bytes" not in str(caught.value)


def test_normalize_cell_never_formats_an_unknown_value():
    _reset_hostile_calls()

    with pytest.raises(ResultNormalizationError) as caught:
        normalize_cell(_HostileValue())

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE
    assert _REPR_CALLS == []
    assert _STR_CALLS == []
    assert _FORMAT_CALLS == []


@pytest.mark.asyncio
async def test_row_normalisation_never_formats_an_unknown_value():
    _reset_hostile_calls()

    with pytest.raises(ResultNormalizationError) as caught:
        await _collect(("id",), ((1,), (_HostileValue(),)))

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE
    assert _REPR_CALLS == []
    assert _STR_CALLS == []
    assert _FORMAT_CALLS == []


def test_the_domain_would_reject_an_unconverted_decimal_cell():
    # 规范化必须发生在构造领域值之前：领域只接受 JSON 标量。
    with pytest.raises(ValueError):
        QueryExecutionResult(columns=("amount",), rows=((Decimal("1"),),), row_count=1, byte_count=1, truncated=False)


@pytest.mark.asyncio
async def test_accumulator_preserves_duplicate_column_names_and_order():
    result = await _collect(("id", "id"), ((1, 2),))

    assert result.columns == ("id", "id")
    assert result.rows == ((1, 2),)
    assert result.row_count == 1
    # {"columns":["id","id"],"rows":[[1,2]]}
    assert result.byte_count == 38
    assert result.truncated is False


@pytest.mark.asyncio
async def test_accumulator_counts_utf8_bytes_without_ascii_escaping():
    result = await _collect(("名称",), (("值😀",),))

    assert result.columns == ("名称",)
    assert result.rows == (("值😀",),)
    # {"columns":["名称"],"rows":[["值😀"]]}
    assert result.byte_count == 43


@pytest.mark.asyncio
async def test_accumulator_uses_the_fixed_canonical_json_rule():
    result = await _collect(("id", "name"), ((1, "a"), (2, "b")))

    # {"columns":["id","name"],"rows":[[1,"a"],[2,"b"]]}
    assert result.byte_count == 50


@pytest.mark.asyncio
async def test_accumulator_normalises_decimal_temporal_and_uuid_cells_before_the_domain_sees_them():
    result = await _collect(
        ("amount", "day", "moment", "identifier"),
        ((Decimal("10.50"), date(2024, 1, 2), datetime(2024, 1, 2, 3, 4, 5), UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301")),),
    )

    assert result.rows == (("10.50", "2024-01-02", "2024-01-02T03:04:05", "3f2504e0-4f89-11d3-9a0c-0305e82c3301"),)
    # {"columns":["amount","day","moment","identifier"],"rows":[["10.50","2024-01-02","2024-01-02T03:04:05","3f2504e0-4f89-11d3-9a0c-0305e82c3301"]]}
    assert result.byte_count == 143


@pytest.mark.asyncio
async def test_next_row_over_the_row_cap_truncates_with_complete_rows_only():
    result = await _collect(("id",), ((1,), (2,), (3,)), max_result_rows=2)

    assert result.rows == ((1,), (2,))
    assert result.row_count == 2
    assert result.truncated is True
    # {"columns":["id"],"rows":[[1],[2]]}
    assert result.byte_count == 35


@pytest.mark.asyncio
async def test_row_count_exactly_at_the_cap_is_not_truncated():
    result = await _collect(("id",), ((1,), (2,)), max_result_rows=2)

    assert result.rows == ((1,), (2,))
    assert result.row_count == 2
    assert result.truncated is False
    # {"columns":["id"],"rows":[[1],[2]]}
    assert result.byte_count == 35


@pytest.mark.asyncio
async def test_next_row_over_the_byte_cap_truncates_at_the_last_complete_row():
    result = await _collect(("id",), ((1,), (2,), (3,)), max_result_bytes=35)

    assert result.rows == ((1,), (2,))
    assert result.truncated is True
    # {"columns":["id"],"rows":[[1],[2]]} 恰好等于上限；第三行会让文档变成 39 字节。
    assert result.byte_count == 35


@pytest.mark.asyncio
async def test_first_row_over_the_byte_cap_returns_zero_rows_and_truncation():
    result = await _collect(("id",), ((1,),), max_result_bytes=30)

    assert result.rows == ()
    assert result.row_count == 0
    assert result.truncated is True
    # 列头部分 {"columns":["id"],"rows":[]} 是 28 字节；首行会让文档变成 31 字节。
    assert result.byte_count == 28


@pytest.mark.asyncio
async def test_unsupported_cell_outranks_truncation():
    # 拒绝优先于截断：不能因为"这一行反正要丢"就把非法值静默吞掉。
    with pytest.raises(ResultNormalizationError) as caught:
        await _collect(("id",), ((1,), (b"raw",)), max_result_rows=1)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE


@pytest.mark.asyncio
async def test_column_cap_rejects_before_the_first_row_is_read():
    started: list[str] = []

    async def _rows():
        started.append("started")
        yield (1, 2, 3)

    stream = _rows()
    with pytest.raises(ResultNormalizationError) as caught:
        await ResultAccumulator(columns=("a", "b", "c"), limits=_limits(max_result_columns=2)).collect(stream)

    assert caught.value.code is ExecutionDecisionCode.UNSUPPORTED_RESULT_TYPE
    assert started == []
    await stream.aclose()


@pytest.mark.asyncio
async def test_column_count_exactly_at_the_cap_is_accepted():
    result = await _collect(("a", "b"), ((1, 2),), max_result_columns=2)

    assert result.columns == ("a", "b")
    assert result.rows == ((1, 2),)
    # {"columns":["a","b"],"rows":[[1,2]]}
    assert result.byte_count == 36


@pytest.mark.asyncio
async def test_collect_pulls_rows_one_at_a_time_and_stops_at_the_cap():
    pulled: list[int] = []

    async def _rows():
        for index in range(5):
            pulled.append(index)
            yield (index,)

    stream = _rows()
    result = await ResultAccumulator(columns=("id",), limits=_limits(max_result_rows=2)).collect(stream)
    await stream.aclose()

    # 逐行拉取：做出截断判定后立刻停止，不把 5 行全部读完。
    assert pulled == [0, 1, 2]
    assert result.rows == ((0,), (1,))
    assert result.truncated is True


@pytest.mark.asyncio
async def test_accumulator_iterates_the_driver_result_without_materialising_it():
    result = await ResultAccumulator(columns=("id",), limits=_limits()).collect(_StreamOnlyResult(((1,), (2,))))

    assert result.rows == ((1,), (2,))
    assert result.row_count == 2
    assert result.truncated is False


def test_add_row_reports_truncation_and_result_is_a_domain_value():
    accumulator = ResultAccumulator(columns=("id",), limits=_limits(max_result_rows=2))

    assert accumulator.add_row((1,)) is True
    assert accumulator.add_row((2,)) is True
    assert accumulator.add_row((3,)) is False
    # 截断判定之后继续喂入的行绝不能进入结果。
    assert accumulator.add_row((4,)) is False

    result = accumulator.result()
    assert type(result) is QueryExecutionResult
    assert result.rows == ((1,), (2,))
    assert result.row_count == 2
    assert result.truncated is True
    assert accumulator.result() == result
