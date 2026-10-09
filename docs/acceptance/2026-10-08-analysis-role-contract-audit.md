# AS07/08/10 下一切片有限源码取证

取证只覆盖 analytics agent、Reviewer、metric/evidence 契约、Gateway 发行点、Lead 绑定点与 ADR 0005。没有改源码或运行 checks；以下把当前代码与 ADR 中待实现角色分开。

## 当前执行链

- 当前没有 `SQLAnalyst`、`DataAnalyst` 或 LLM `ReportWriter` class/function。`agent/` 中实际相关入口是 `inspect_business_catalog`、`query_business_data`、旧索引工具 `publish_analysis_report`、报告工具 `write_analysis_report`，以及 `AnalysisReportReviewerCapability`（`tools.py:69,188`、`reports.py:69,118`、`reviewer.py:110`）。ADR 0005 §决策描述固定内部角色，是方向而非已有实现。
- `MetricCatalog` 是只读数据端口，只有 `list_accessible` / `get_accessible`（`application/ports.py:14-17`），不是 Agent/role。
- Lead 使用已选 `lead_model` 建图（`lead_agent/agent.py:1120-1155`）；图可因工具轮次多次调用 Lead，源码不能给出固定调用次数。`query_business_data` 在一次工具调用里 plan 一次、execute 一次，不调用模型，执行失败不重 plan（`tools.py:106-139,187-253`）。
- Reviewer 是当前唯一独立的零工具模型调用：Lead assembly 把同一个未绑定 `BaseChatModel` 绑定到当前 run 的 Reviewer（`lead_agent/agent.py:1127-1148`、`reviewer.py:156-186`），之后 `review()` 直接 `ainvoke`（`reviewer.py:275-321`）。成功解析的决定按报告指纹缓存；run 内最多两次模型尝试，失败也消耗额度。拒绝后 Lead 若修订会产生新的 Lead 调用。
- `write_analysis_report(title, markdown, evidence_ids, ...)` 接收 Lead 已生成的 Markdown，先从当前 durable collector 解析 evidence，再调用 Reviewer，最后经 writer capability 写固定 artifact 并登记索引（`reports.py:118-130,179-237`）。它本身没有 ReportWriter 模型调用；`publish_analysis_report` 是仅登记索引的旧工具（`reports.py:68-116`）。

## 可复用边界与最小接线候选

- 可复用 Reviewer 的直接 base-model 绑定、显式空 `callbacks/tags/metadata`、零工具 `ainvoke`、闭合响应解析、run-local 锁/预算/缓存与取消传播（`reviewer.py:156-186,241-321`）。当前有 64 KiB 输入、请求 256 输出 tokens、2 KiB 返回体、20 秒 timeout、每 run 两个不同内容尝试；没有 provider 重试。未能强制输出 token 字段的模型会 fail closed（`reviewer.py:20-24,175-179`）。不要用 `RunnableBinding` 包模型调用，现有代码说明它会合并回 ambient callbacks。
- Gateway 已把 Reviewer、durable evidence collector、report writer 三个 `__analysis_*` context key 列入 server-owned 清洗集合；准入时按 principal/thread/run 发行，缺任一能力即拒绝 analysis run（`constants.py:14-20`、`gateway/services.py:610-633,1838-1901`）。Lead assembly 只负责把 server 选定的 base model 绑定给 Reviewer。新增需要调用模型的内部角色若经 worker context 取能力，必须沿用这条服务端发行、清洗、run-scope 与 Lead 绑定边界；不要复用 Reviewer 的 attempts/decision 状态作为其他角色状态。
- Data Analyst 可直接消费 `DurableAnalysisRunEvidenceCollector.resolve_successful_queries_durable()` 给出的本 run 快照，无须新查询/文件权限或第二份 evidence store（`evidence_bridge.py:94-131`）。Report Writer 可复用现有固定文件 capability 与发布用例（`reports.py:149-177,218-237`）。SQL Analyst 只能产出候选 SQL；要执行仍经现有 `query_business_data` 受控 plan→execute 路径，不能获得数据库能力。
- 最小 owner 候选：role 输入/输出与有界调用放在 `backend/app/analytics/agent/`；Gateway capability 发行/清洗在 `backend/app/gateway/services.py`，内部 key 在 `backend/packages/harness/deerflow/constants.py`，base-model 绑定在 `backend/packages/harness/deerflow/agents/lead_agent/agent.py`；确定性 claim 类型放在 analytics `domain/`。这些是文件所有权候选，不是已存在 API 名称。

## Metric 与 AS10 可证明范围

- `MetricDefinition` 当前是 `key/owner_id/name/description/expression/dimensions/version/status`，没有 unit、期间或分母语义字段（`domain/metric.py:16-41`）；持久化注释明确 `expression` 是不可执行的业务文本（`persistence/models.py:103-120`）。Agent 目录只投影 `key/name/description/dimensions/version/status`，连 expression 也不提供（`agent/tools.py:58-66`）。
- 管理 API create/update/view 同样只有 expression 与 dimensions 等既有字段（`api/models.py:116-136,188-199`）。若 unit、period grain 或 numerator/denominator 成为登记指标语义，至少要改 `MetricDefinition`、API DTO/router mapper、`MetricRow`/codec 与新增 Analytics migration，并让 `MetricCatalog` 消费端及 `tools.py::_metric_view` 得到同一版本字段；不应把自由文本 expression 当数学定义。
- Durable evidence 的结果载体是有界 `columns + rows + truncated`，行列 digest 与 evidence 元数据绑定；元数据含 datasource/query hash、schema/policy version、风险、行数/字节数与 result digest（`domain/evidence.py:58-76,211-262`）。因此它可证明某 evidence 下被引用单元格的精确值及其属于成功受控查询快照；若 validator 按显式公式重算，也可证明该公式对这些单元格的结果。它不能从 opaque `query_hash` 证明 SQL 语义、列单位、时间筛选、总体完整性、业务分母或指标口径；`truncated=true` 时也不能把可见部分当完整总体。
- 最小 typed claim 候选（仅供裁决）：`CellRef(evidence_id, row_index, column_name)`；`NumericClaim(value: Decimal, unit_code, period_start, period_end, metric_key/version, source_cells, operation)`；`operation` 为固定 enum/有序 cell operands，比例另有显式 numerator 与 denominator 引用及舍入规则。validator 只从 exact-scope durable snapshots 解析 cell、校验单位/期间来源并用 Decimal 重算；报告中的 Markdown 数字必须对应这些 claim，不能靠“数字曾出现在任意结果”放行。是否将 unit/period/denominator 存入 MetricDefinition、是否改公开 API，留给主会话裁决。

## 验证落点与后续切片

- 角色/math 切片的直接既有测试：`test_analytics_agent_reviewer.py::test_reviewer_uses_the_bound_lead_model_without_tools_or_inherited_run_callbacks`、`test_reviewer_limits_input_before_model_invocation`、`test_reviewer_timeout_fails_closed_and_cancellation_propagates`；新增最值钱断言是每个角色均零工具、各自预算/run scope 独立，以及 claim 精确解析来源 cell 并拒绝单位/期间/分母或截断不匹配。工具与报告接线分别沿用 `test_analytics_agent_tools.py::test_a_successful_query_plans_once_executes_once_and_returns_evidence`、`test_analytics_agent_reports.py::test_report_writer_reviewer_rejection_or_invalid_response_has_zero_writes`。
- 角色/math 先冻结 typed role result、claim 与 consumer 合同。后续 event/SSE 可复用 `deerflow.utils.custom_events.aemit_custom_event`（`custom_events.py:45-61`）；Harness 约定要求通过该 helper 同时投递 custom stream 与 callback。事件 schema 与 Gateway/frontend 投影属于后续独立切片，串行冻结接口，不混入本次 role/math 生产文件集。
