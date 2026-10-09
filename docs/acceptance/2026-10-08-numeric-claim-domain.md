# 数字引用与固定算式领域基础

## 交付范围

新增纯领域合同 `backend/app/analytics/domain/claims.py`，并从 `domain` 包导出引用、claim、验证结果与 `verify_numeric_claims`。实现只读取同批通过 `validate_successful_query_result()` 校验的成功查询快照；没有新增 Agent、报告、API、数据库或前端接线。

`EvidenceCellReference` 绑定小写 SHA-256 evidence ID、非负行号和最多 256 字符的可打印结果列标签。列标签是快照中的字面字符串，只做 exact lookup；包括空格或 SQL 标点的真实别名可以被引用，但不会被解析、求值或拼入 SQL。重复列名只有在被引用时按歧义拒绝。

`NumericClaim` 只接受唯一的有界 slug、固定 operation enum、不可变 operand tuple、有界普通十进制字符串以及 0–12 位小数。cell、difference、ratio、percentage、mean、change_percentage 和 sum 使用闭合算式；sum/mean 最多 50 个 operand。单批最多 50 个 claim、20 个快照，快照总字节数沿用现有 16 MiB evidence 预算。引用的快照必须全部成功且 digest 有效，evidence ID 和 claim ID 均不得重复；任何一项失败都会拒绝整批结果。

数值源只接受 JSON int、有限 float 或有界普通十进制字符串；拒绝 bool、null、非有限值、指数格式文本以及超过 100 位或指数边界的值。固定算式在独立 512 位 Decimal context 中计算，不读取或修改进程全局 context。显示使用 `ROUND_HALF_UP` 和 claim 声明的小数位，claim 自报数值必须与该显示结果数值完全相等。ratio 与 change_percentage 的分母为零时拒绝。

unit 与 period 只能从同批证据快照的确切单元格绑定。标签必须是最多 128 字符、非空、trimmed 且无控制字符的文本；period 另外允许 1–9999 的整数年，并规范化为十进制年份字符串。没有来源时输出 `None`。结果保留 operand 引用、unit/period 原始引用、计算后定点字符串、是否实际发生舍入以及所引用快照是否被截断。

## 证据边界

验证只证明“这些引用单元格的计算”与服务端固定算式一致。unit/period 只证明标签来自绑定单元格，不证明物理单位或业务期间语义；正确查询语义、过滤条件和业务口径仍需后续角色/报告合同。即使快照未截断，也不由此推断完整业务数据完备。本切片未接入 roles/reports，不能表述为 AS10 已完成。

## 定点验证

在 backend 目录使用显式 PyPI index、禁用本机 uv 配置并锁定依赖：

~~~powershell
uv run --no-config --default-index https://pypi.org/simple --locked pytest tests/test_analytics_numeric_claims.py tests/test_analytics_boundaries.py::test_analytics_domain_uses_only_the_standard_library -q
~~~

结果：33 passed。

~~~powershell
uv run --no-config --default-index https://pypi.org/simple --locked ruff check app/analytics/domain/claims.py app/analytics/domain/__init__.py tests/test_analytics_numeric_claims.py
uv run --no-config --default-index https://pypi.org/simple --locked ruff format --check app/analytics/domain/claims.py app/analytics/domain/__init__.py tests/test_analytics_numeric_claims.py
~~~

结果：Ruff check 通过；3 个目标文件均已格式化。新测试覆盖固定算式、精确引用与歧义、失败/坏 digest、截断、标签来源、数值与 Decimal 边界、预算和稳定错误。

uv.lock 命令前后 SHA-256 均为 `46F170B56FBC3703FFFB4E8389274DD77488583E2D0804DE760B705E89F6E912`。未调用模型或真实数据，也未运行更广的后端套件。
