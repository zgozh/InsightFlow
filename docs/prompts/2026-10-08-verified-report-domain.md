# 可验证报告结构与确定性渲染

实施：gpt-6-luna / max。读取适用 AGENTS、`domain/claims.py`、现有 domain 边界测试；不要读取整仓历史。

## 所有权与依赖

仅新增 `backend/app/analytics/domain/verified_report.py`、对应 `backend/tests/test_analytics_verified_report.py`、`docs/acceptance/2026-10-08-verified-report-domain.md`。若需要导出，仅追加 domain/__init__.py，不动既有导出。依赖已冻结的 NumericClaim/VerifiedNumericClaim；不得修改 claims、现有 reports 工具、Gateway、数据库、其他人员文件。当前另一个实施者只操作隔离授权验收目录与独立文档，互不共享输出。

## 冻结合同

本切片建立 AS10 报告的安全 consumer，不接模型与工具。使用 frozen dataclass 和闭合 enum，领域仅 stdlib。

- `ReportClaimLabel`：claim_id 对应 NumericClaim.id，label 最长80字符、trimmed、单行可打印、非空；禁止任何 Unicode isnumeric 字符，防止模型在标签中夹带未验证数值。label 仅用于描述，不承担指标语义证明。
- `ReportSectionKind`：summary、details、comparison 三个闭合展示章节。
- `VerifiedReportSection`：kind 与 claim_ids 不可变 tuple，最多50项；不接受自由 Markdown、HTML、SQL、URL、叙述或模型给出的数值。
- `VerifiedReportLayout`：1至3个 section；kind 不重复；所有 claim IDs 在整份布局恰好出现一次。
- `render_verified_report(layout, labels, verified_claims)` 返回 Markdown。三者必须严格对应同一非空1至50个唯一 claim ID，未知、遗漏、重复或非预期类型全体拒绝，以稳定 `VerifiedReportError.reason` 报错，不包含内容。
- 输入只接收本模块正确类型，以及 `type(...) is VerifiedNumericClaim` 的结果。验证 VerifiedNumericClaim 的结构约束，但不得声称该 DTO 自身是签名能力；调用方仍须先 `verify_numeric_claims` 且只把该返回值传入渲染器。文档说明这一进程内信任边界。
- 标题固定为“经营分析报告”，章节标题由 enum 生成。表格展示标签、**calculated_value**、证据绑定的 unit/period；缺失显示“未提供”，不猜测单位和期间。计算方式文字由 operation 生成，必要时说明舍入、局部结果被截断。自动添加边界提示：证据与算式验证不等于业务口径或总体完整性证明。
- 每个显示数值有 claim ID 与所有 exact source reference；包括 unit/period 引用。去重后可用固定证据引用块显示 evidence_id、row_index、column_name。这些索引/编号是机器来源元数据，与分析数值区别清楚。所有可变文本转义，禁止注入链接、HTML、Markdown表格或代码块；既有列标签含空格、括号、反引号仍按字面安全显示。
- 渲染结果 UTF-8 最多32 KiB，超过拒绝，不静默截断报告。空 claims 不得发布。

## 验证

V1：新增纯领域 consumer，定点测试 + stdlib边界 + 新文件Ruff/format即可，不构建、不调用模型、不修改 uv.lock。uv 使用 `--no-config --default-index https://pypi.org/simple --locked`。

测试保护实际合同：数值来自 calculated_value；与两份合法快照通过 verify_numeric_claims 的真实组合；错配/遗漏/重复拒绝；伪造自由数字标签拒绝（含 Unicode数字）；HTML/表格/反引号来源标签安全；unit/period缺省、rounding/truncated警示；响应上限与稳定错误。不要只测试函数名或 getters。

完成后冻结文件，返回实际 diff与准确执行命令/结果。明确只是确定性报告基础，尚未完成 AS10 集成验收。
