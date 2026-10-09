# 固定内部分析角色能力基础

实施 gpt-6-luna / max。本切片只实现角色能力与定点测试，下一切片才接 Gateway/工具。已冻结依赖：domain/claims.py 与 domain/verified_report.py。读取适用 AGENTS、agent/reviewer.py 的 base-model 绑定与调用边界；不要读取整仓历史。

## 所有权

新增 `backend/app/analytics/agent/roles.py`、`backend/tests/test_analytics_agent_roles.py`、`docs/acceptance/2026-10-08-analysis-role-capability.md`。不改 Reviewer、工具、Harness、Gateway、数据库、领域或其他文件。不要抽取共享调用器或重构既有 Reviewer。

## 架构与冻结接口

`AnalysisRolesCapability` 由服务端以 principal_id/thread_id/run_id 构造，matches/bind_lead_model/close 沿用 Reviewer 同等边界。只绑定未经过 bind_tools 的可信 BaseChatModel，不接受 RunnableBinding。重复同一 model 绑定幂等，不同对象重绑定 fail closed。对支持 token 限制字段的模型调用 ainvoke，显式 callbacks/tags/metadata 为空，禁止工具调用、递归、provider 重试。沿用 Reviewer 已验证的 deepseek-flash token 字段兼容与关闭 thinking 方式，分别设置该角色上限。

固定独立角色：SQLAnalyst、DataAnalyst、ReportWriter（Reviewer 仍由现有能力独立承担）。职责提示使用中文；每个角色一次真实独立 ainvoke，不能由 Lead 角色标签替代。三者各自锁、尝试计数、缓存；每 run 每角色最多2次不同输入尝试，provider失败/无效输出/取消也消耗已开始的尝试。相同成功输入可以缓存，不缓存失败；close 后全部调用/缓存命中均拒绝。匹配身份失败必须在模型调用前拒绝。CancelledError 原样传播，其余只稳定脱敏错误。若供应商模型存在 max_retries 字段，角色专用 model_copy 固定为0，不能修改 Lead 原实例；清除角色复制实例中的工具/functions/default tool choice 配置。未知模型不能证明供应商重试被禁用时明确拒绝，不静默承诺。

接口（必须明确类型，结果只含安全 DTO）：

- `refine_sql(principal_id, thread_id, run_id, datasource_id, candidate_sql, metrics)`：metrics 为调用方从受权目录取得的 MetricDefinition 不可变 tuple。输入只投影指标 key/name/description/expression/dimensions/version/status，不提供 owner/secret/policy。SQLAnalyst 只输出 `{"sql": "..."}`，原样受控单条候选，非空、最长20000字符；此处不执行SQL，真正授权仍由下一切片原 plan→execute。返回 frozen SQLAnalystResult(sql)。datasource_id/candidate_sql须有界、trimmed、非空。
- `analyze(principal_id, thread_id, run_id, snapshots, metrics)`：snapshots 仅接 exact-scope durable collector 已解析的 tuple。入口再次成功快照验证、最多20份、总16MiB；在序列化前检查快照字节总下界，明显超过模型64KiB预算立即拒绝。DataAnalyst 只输出 `{"claims": [...], "labels": [...]}`。claims 每项精确 `id/operation/operands/value/decimal_places/unit_reference/period_reference`，reference 精确 `evidence_id/row_index/column_name`，optional refs用null；labels每项精确 `claim_id/label`。1至20项，类型严格，不做字符串/布尔数值强转。调用已冻结 NumericClaim 构造及 verify_numeric_claims，再构造 ReportClaimLabel；labels与claims ID恰好一一对应。任何数值、来源或标签失败整批拒绝。返回 frozen DataAnalystResult(verified_claims, labels)，不得返回任意 Markdown、原始 provider response 或推理。
- `layout(principal_id, thread_id, run_id, verified_claims, labels)`：只输入已验证数字、关联标签、operation和truncated等必要安全投影，不给原始行/SQL；ReportWriter 只输出 `{"sections":[{"kind":"summary|details|comparison","claim_ids":[...]}]}`，构造 VerifiedReportLayout，并用 render_verified_report 复核一一覆盖与32KiB上限，再返回该 layout。它是独立模型选择布局，实际文本/数值由确定性渲染器生成。

metrics须严格 MetricDefinition、active、唯一key、最多50条，投影有界；expression是登记的业务文本，不执行、不假装可由其证明SQL单位/期间/分母。无指标时允许空tuple，报告后续必须标明没有登记口径，不能凭空绑定版本。

模型输入（含系统prompt）每角色最多64KiB UTF-8；SQL/Data分别30秒、Writer20秒。输出 tokens SQL2048/Data4096/Writer1024；响应文本最多 SQL16KiB/Data32KiB/Writer8KiB。不得忽略供应商 tools_calls；有工具调用即拒绝。JSON拒绝额外字段、duplicate keys、NaN/Infinity、非object顶层、Markdown代码围栏；允许标准AIMessage字符串或纯text content blocks，与Reviewer当前处理一致。明确缓存指纹包含全部角色输入且互相独立。

错误用一个 AnalysisRoleError.reason 的闭合稳定集合（unavailable/input_too_large/attempt_limit/invalid_response/numeric_validation_failed），不回显SQL、行、供应商异常。日志最多role/stage/run_id，禁止提示/输出/原始行/SQL。不要在本切片添加事件投影或公开接口。

## 验证

V2：角色执行与信任接口。用直接受影响单元测试和 Ruff/format，既有 Reviewer 关键绑定/取消测试选取必要合同即可；不跑全套、不构建、不调用真实模型、uv.lock不变。uv使用 --no-config --default-index https://pypi.org/simple --locked。

测试必须证明三个实际独立 ainvoke、无工具/ambient callbacks、各自预算缓存、异身份/未绑定/关闭拒绝、provider失败与无效输出消耗尝试、超时/取消、严格JSON/工具调用拒绝、Data错数/缺来源不进Writer、真实verify→layout→render的固定fake模型成功链及缺口径诚实边界。模拟模型可复用既有BaseChatModel测试模式；不要写仅返回固定字符串的假合同wrapper测试。

交付实际diff、准确检查命令/结果和冻结报告。不得声称AS07/08/10已完成，尚待服务端接线和真实集成。
