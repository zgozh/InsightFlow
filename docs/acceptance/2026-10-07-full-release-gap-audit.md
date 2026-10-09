# 2026-10-07 完整发布差距与实施接口盘点

核对范围：AS-01～AS-15。只读源码和现有验收证据；没有运行测试、模型、数据库脚本或容器，也没有改产品代码。报告自身按 V0 回读、相对链接和 diff 检查。

## 当前结论

- AS-14 已按批准边界验收：分析 run 的模型 schema 与最终 dispatcher 使用同一正向集合，且恰为 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`。普通聊天保留 operator MCP；其 SQL 安全不在平台 Query Policy 保证范围。关键位置是 [tools.py](../../backend/packages/harness/deerflow/tools/tools.py) 的 `_get_analysis_tools`、[agent.py](../../backend/packages/harness/deerflow/agents/lead_agent/agent.py) 的 `_assemble_lead_agent`、[services.py](../../backend/app/gateway/services.py) 的 analysis admission 和 [6F2 边界证据](phase-06f2-as14-boundary-evidence.md)。不可通过增加 `task`、改名工具或 prompt 扮演专职角色来声称 AS-07 已完成。
- AS-07 仍是实现缺口。分析模式显式关闭普通子 Agent、task、Skills、Memory、plan mode、tool search 和非固定工具。保持 AS-14 约束的可行接缝只能是 App-owned 的服务端内部阶段/模型调用，不增加模型可见工具或执行 dispatcher 项。现有 [Reviewer capability](../../backend/app/analytics/agent/reviewer.py) 已用直接 `BaseChatModel.ainvoke` 做一次有界、零工具的内部复核，可复用其 run-owned 身份、超时、输出码和调用隔离模式；这不等于其他角色已存在。
- 没有 `MetricService` 或指标口径自然语言解析/解析调用。`AnalyticsServices.metrics` 是 `MetricCatalog`；接口只有 `list_accessible` / `get_accessible`。`inspect_business_catalog` 把可访问的 `MetricDefinition` 列出来，尚未把问题解析成口径对象。
- `query_business_data` 走现有 `PlanAnalyticsQuery` / `ExecuteQueryPlan`，把有界 `columns` / `rows` 和 evidence 返回给 Lead。`AnalysisRunEvidenceCollector` 按 owner/thread/run 在进程内保存成功结果快照，限每 run 20 条、合计 16 MiB；源码明确它不属于图状态、事件或回执，也不写固定 artifact。报告 artifact 是 [write_analysis_report](../../backend/app/analytics/agent/reports.py) 经 Gateway 签发的 run-scoped writer capability 写入固定 Markdown 路径后登记。
- Evidence ID、result digest、行/字节数和 run 归属有确定性校验；[Reviewer](../../backend/app/analytics/agent/reviewer.py) 对报告与 query snapshots 做零工具模型复核并返回封闭决定码。没有确定性逐数字运算/报告中数字与 query 单元格逐项匹配机制。复核通过是模型判断，不能写成数学证明。
- AS-06 至少有一个源码可见的实现差距：`AnalyticsConfig.execution_limits()` 按同一配置构造限额；SQL policy 对 MEDIUM 标注复杂查询，但没有按风险降低 timeout、行数或字节预算。示例默认值为连接 3000 ms、语句 5000 ms、取消宽限 500 ms、查询/结果 1000 行、结果 1 MiB、列 128、EXPLAIN 1 MiB。PostgreSQL 有服务端 `statement_timeout`；MySQL 流式查询的实测终止边界是客户端 timeout 后销毁连接，不能描述为服务端抢占。
- AS-01 多主体真实隔离尚缺。`POST /api/v1/auth/register` 在 `auth.local.allow_registration=true` 时只创建普通用户；`POST /api/v1/auth/initialize` 只在尚无 admin 时创建首个管理员。没有管理员创建/删除其他用户的 HTTP 路由，也没有用户删除 API。固定验收管理员的 DPAPI 文件与既有流程只能用于登录，不能覆盖或轮换它。

## AS-01～AS-15 逐项差距

### AS-01 认证和多主体 owner 隔离 — 部分实现，整项未验

已实现 Gateway 认证、thread/run/artifact owner gate、未认证 401；已有单管理员 Nginx 彩排及 owner 读取 200 / foreign-thread 404。证据见 [认证中间件](../../backend/app/gateway/auth_middleware.py)、[stateless run 隔离测试](../../backend/tests/test_stateless_runs_owner_isolation.py) 的 `test_stream_cross_user_returns_404`、[6F1/6F2记录](phase-06d-contract-reconciliation.md)。缺的是两个真实主体间 thread、run、SSE、datasource、artifact 的完整 HTTP/UI 矩阵。

下一次输入/期望：新建两个 slice-tagged 临时用户 A/B，在 A 名下创建 analysis thread、run 和 artifact；未登录请求工作台/API 应登录跳转或 401 且不返回数据；B 读取 A 的 thread/run/messages/events/artifact 均 404，不泄漏标题/标识/正文；A 读取自身对象成功。认证用浏览器 session 分开验证，不能仅以测试中伪造 `request.state.user` 代替真实主体。

创建/清理接口：首个临时管理员 `POST /api/v1/auth/initialize`；第二个普通临时主体 `POST /api/v1/auth/register`（需允许注册）。现有 API 没有 `DELETE /users/{id}`。安全做法是在独立 Compose project 和全新 SQLite volume 上创建；对象标识/email 带唯一 `as01-<slice-id>` 标签，结束时先核对 Compose project label 与精确 volume 清单，只销毁本切片新建的 project/volume。若复用固定栈/既有数据库，不能仅经 HTTP 精确删除临时用户，应停止并保留该栈，不能触碰既有账户或数据。

DPAPI 复用：既有验收凭据路径为 `.reviews/insightflow-acceptance-local.admin.dpapi`；当前安全读取范式在忽略目录的 `.reviews/phase-06f3f7-provenance.ps1`（同类 runner 见 `phase-06f3e7-run.ps1`）：当前用户 DPAPI 解封，明文仅经 stdin 交给 Python，释放 BSTR 并清空临时变量。它不是通用凭据库；本切片不读写旧凭据。若临时用户必须持久化认证，使用不同的、slice-id 命名的 DPAPI 文件和当前用户 ACL；完成后删除该精确文件。

代码门禁：`cd backend; uv run --locked pytest tests/test_auth_middleware.py tests/test_stateless_runs_owner_isolation.py tests/test_analytics_api.py -q`。它仅证明自动边界；真实接受仍需上述双 session HTTP/浏览器步骤。界面入口已有 `frontend/tests/e2e/analysis-entry-activation.spec.ts`，但它不覆盖多主体。

### AS-02 MySQL 业务库 — 适配器与集成测试已实现；真实模型链缺失

现有 [MySQL runtime](../../backend/app/analytics/infrastructure/mysql_runtime.py) 使用只读事务与执行限制；[MySQL integration tests](../../backend/tests/test_analytics_mysql_integration.py) 保护 SQL、只读账号、timeout、row/byte 路径。历史脚本记录 PostgreSQL 16.15 + MySQL 8.4.11 共 82 项通过（历史记录未保存退出码）；脚本 `scripts/test_analytics_databases.py --engine all` 会用一次性 Docker 数据库、临时数据目录、env 注入普通/只读凭据，结束 `compose down`，不复用应用 Compose 数据。

下一次输入/期望：使用 fixture 中合成订单，给只读 user 授 datasource/table/column allowlist；真实模型回答一个有唯一预期值的问题；观测 SQL 经 `mysql` dialect policy、EXPLAIN、只读执行，结果与同义直接只读 SQL 一致，受行/字节上限约束，成功 evidence 与唯一 run-scoped Markdown 报告引用一致。不要重复普通聊天小惊喜示例。模型 wording/SQL 候选属于非确定行为；断言应落在服务端 dialect、权限、只读、限额、evidence/hash、owner/run、report index 等稳定控制上。

建议定点门禁：`python scripts/test_analytics_databases.py --engine mysql`；真实模型 run 是单独的 V3 集成验收，不能由适配器测试替代。

### AS-03 PostgreSQL 业务库 — 单次受控样例已跑；完整方言/限额矩阵缺

现有 [PostgreSQL runtime](../../backend/app/analytics/infrastructure/postgresql_runtime.py) 与 [集成测试](../../backend/tests/test_analytics_postgresql_integration.py) 覆盖 read-only、timeout、EXPLAIN、row/byte。6F1 已用合成 PostgreSQL 和真实模型做过一次受控 query、evidence 和报告 artifact；不等同 AS-03 双库语义对照、方言边界或多主体验收。业务库与应用持久化库分开。

下一次输入/期望：与 AS-02 使用相同合成数据和问题，对 PostgreSQL 使用显式 `postgres` dialect；返回值与 MySQL 等价查询相同，标识符引用/分页语义分别正确；服务端 timeout 后无残留查询，结果 cap 和 audit/evidence 正确。建议命令 `python scripts/test_analytics_databases.py --engine postgresql`，之后一次受控合成真实模型 run。

### AS-04 datasource/table/column 越权 — 策略实现及自动证据已具备；真实 HTTP 矩阵缺

`SqlglotSemanticAuthorizer` / `PlanAnalyticsQuery` 拒绝无授权 datasource、relation、column，并写 audit、停止 plan/execute。现有测试：`test_semantic_authorizer.py::test_unknown_relation_is_rejected`、`test_relation_absent_from_the_policy_is_rejected`、`test_column_absent_from_the_policy_rule_is_rejected`、`test_denied_column_is_rejected`；`test_analytics_delivery.py::test_an_authorization_denial_writes_an_authorization_audit_and_stops`。下一次输入 D′/t′/c3，预期 BLOCKED + decision reason、无 plan ID、无业务库语句、审计只留 query hash 与主体/run/datasource 元数据。建议 `cd backend; uv run --locked pytest tests/test_semantic_authorizer.py tests/test_analytics_delivery.py -q`。

### AS-05 DDL/DML/多语句 — policy 自动测试已具备；无需重做全套历史扫描

`SqlglotQueryPolicy` fail closed。现有 `test_sql_policy.py` 包含 `test_policy_fails_closed`、`test_sql_comments_are_rejected`、`test_mysql_executable_comment_is_rejected`、`test_postgres_copy_is_unsupported`、`test_write_nested_inside_a_cte_is_forbidden`。下一次只需从 HTTP/真实 Gateway 补充代表性拒绝证明：DDL/DML/事务控制/多语句/导出都不发到业务库；审计无原始 SQL。建议 `cd backend; uv run --locked pytest tests/test_sql_policy.py tests/test_analytics_delivery.py -q`。

### AS-06 timeout 与结果预算 — 有基础实现，MEDIUM 分档预算缺实现

PG/MySQL adapter、结果归一化和 delivery 已覆盖 timeout、完整行截断、byte cap；关键测试见 `test_result_normalizer.py::test_next_row_over_the_row_cap_truncates_with_complete_rows_only`、`test_next_row_over_the_byte_cap_truncates_at_the_last_complete_row`、`test_analytics_delivery.py::test_only_the_result_row_cap_is_clamped_and_everything_else_matches_the_config`、PG `test_statement_timeout_cancels_the_query_and_leaves_no_residual_backend`、MySQL `test_streamed_execution_does_not_survive_the_client_timeout`。当前配置没有 LOW/MEDIUM 两套 limits：`AnalyticsConfig.execution_limits()` 回传统一值，policy 的 MEDIUM 只加 `COMPLEX_QUERY`。因此 AS-06 的“MEDIUM 更低 timeout/row/byte”是待实现，不只是待实测。

验收输入/期望：一个超时 SELECT、超过 row cap 和 byte cap 的合成查询、MEDIUM 查询与同一 LOW 查询、一个 HIGH 查询。预期 timeout 稳定错误类别 + audit；截断保留完整行且 event/audit 可见；MEDIUM 三项预算严格低于 LOW；HIGH `APPROVAL_REQUIRED`、无 plan、无执行。MySQL 服务端 `MAX_EXECUTION_TIME` 不保证中止 `connection.stream()`；断言须验证客户端 timeout 加连接销毁。建议先跑适配器/delivery 的定点测试，再真实 DB gate。

### AS-07 Lead→Reviewer 主链 — 目标角色图缺失

当前只有固定三工具和一个内部模型 Reviewer；没有 MetricService、专职 SQL Analyst、Data Analyst、Reporter 角色运行时或完整阶段事件。可复用：`AnalyticsServices.metrics` 的 `MetricCatalog` list/get；`PlanAnalyticsQuery` / `ExecuteQueryPlan`；`AnalysisRunEvidenceCollector` 的 owner/thread/run snapshots；Reviewer capability；`write_analysis_report` 与 Gateway writer capability；run event/journal/trace 投影。保持 AS-14 的实现界面应由 App 服务端内部阶段调用组成，不改变 `final_tools`。任何新阶段仍须把 SQL 送入现有 policy/authorization/execution，不可由 SQL Analyst 绕过 query tool 的安全服务。

真实输入：含指标、日期区间、分组与对照的合成经营问题。期望按阶段产生：澄清范围 → 明确 metric definition/version → SQL 候选经 policy 与 EXPLAIN → 串行只读执行 → 成功 evidence snapshot → 基于快照的数据分析 → Reviewer 决定 → 受控 Markdown writer 发布 → Lead 摘要/evidence/风险/下载路径。每个环节有独立结构化状态和稳定失败终态；子阶段不再创建子 Agent。自动基线 `tests/test_analysis_tool_allowlist.py::test_analysis_assembly_uses_server_context_and_one_set_for_model_and_dispatch` 保证工具数目不能因实现角色链而扩大。

### AS-08 子 Agent 故障恢复 — 通用机制存在；分析角色恢复链缺

`SubagentExecutor` 有 timeout/cancel/loop guard/token budget/receipt；`tests/test_subagent_executor.py` 保护通用 executor。分析模式不启用普通 `task`，所以当前 Reviewer rejection 样例（一次拒绝后再次提交通过）不证明角色子 Agent 故障恢复，也不证明 attempt limit 耗尽。

输入/期望：各内部角色模拟超时、取消、provider failure、loop/token budget 和 Reviewer 连续拒绝；run 不静默成功，结构化 event/receipt 给明确原因，取消终止底层调用，token/time 汇总正确；Reviewer attempt limit 耗尽后 writer 不发布且报告未通过。建议在 AS-07 角色调用接口冻结后，定点跑 `tests/test_subagent_executor.py` 与新增的该角色接口测试，不把普通 task MCP 开回分析图。

### AS-09 实时 SSE 轨迹且无思维链 — 历史卡片已见；完整 live contract 缺

已有 run events/messages API 与前端 trace projection；6F3F5 Chromium 看到 catalog/query/report step、Reviewer rejected/approved 卡片；6F3F9 仅证明 db events 下失败普通 run 重启后 2 messages/5 events 可读。它没有证明成功分析的实时 SSE 全阶段、结果 evidence 覆盖或自由文本无思维链。关键文件 `backend/app/gateway/routers/thread_runs.py::list_run_messages/list_run_events`、`frontend/src/core/analytics/trace.ts`、`analytics-trace-panel.tsx`；既有 unit IDs `frontend/tests/unit/core/analytics/trace.test.ts`、`analytics-trace-panel.dom.test.tsx`。

输入/期望：在一次成功受控分析中从首条 SSE 开始记录计划/阶段、Agent lifecycle、query policy/风险/EXPLAIN/耗时/行数、artifact/evidence、Reviewer decision、token/timeout/loop 状态；UI 只用结构化 event 投影。对 event metadata/serialized tool payload 做禁字段断言；不得将任意用户/模型最终文本保证延伸到平台结构化字段边界之外。AS-07 的事件契约稳定后做 targeted backend/frontend tests + 一次浏览器 live run。

### AS-10 报告 artifact — 发布、owner 读取和单次 Web 下载已验；数字正确性机制缺

6F1/6F3E10 已观察发布索引、owner artifact 200/foreign 404；6F3F5/6F3F6 已看到真实报告卡并完成同 owner Markdown 下载。现有 writer 会校验 owner/thread/run、固定路径、successful evidence IDs，并调用零工具 Reviewer；没有确定性验证 Markdown 中每一个数字/单位/分母/期间与 evidence 行值一致的算法。Reviewer 是模型非确定性判定。下一次用专门合成账本的已知数字，服务端断言 evidence IDs 全部属于该 run、写入/索引/download owner scoped、无证据数字被拒绝；若要求数学保证，需要明确实现确定性数字校验器，不能仅重跑模型。

代码基线 `test_analytics_agent_reports.py`、`test_analysis_report_writer_files.py`、`test_analytics_api.py::test_report_listing_is_exactly_principal_scoped`；前端目录列表下载测试 `frontend/tests/unit/components/analytics/analytics-catalog-views.dom.test.tsx::ReportCatalogList`。不再重复 6F3F20 普通聊天示例。

### AS-11 计划分析 — Scheduler 通用队列已实现；analysis 复用边界部分可行，artifact 闭环缺

`ScheduledTaskCreateRequest` 可 `context_mode=reuse_thread` 指定既有 thread；该 thread 的持久 `metadata.analysis_mode=true` 会经 `launch_scheduled_thread_run → start_run(require_existing_thread=True)` 进入正常 Gateway analysis admission，使用 server internal caller owner。Scheduler 不保存独立 kind 字段，也没有 `fresh_thread_per_run` 创建 analysis marker 的入口；fresh thread 会是普通 thread。结论：复用现有 analysis thread 的源码链存在，但尚无真实 scheduled analysis/evidence/artifact 验收。`scheduler.enabled=true` 才启动。相关 `tests/test_gateway_services.py::test_launch_scheduled_thread_run_marks_context_non_interactive`、`tests/test_scheduled_task_queue.py::test_queued_run_survives_single_instance_restart_sweep`。

下一次输入：一次性任务 `POST /api/scheduled-tasks`（Nginx 映射下使用 `/api/...`），`context_mode=reuse_thread` + 预建 analysis thread + 合成 prompt；到点后预期 queued→running→terminal，run 为 analysis、`non_interactive=true`、成功写唯一 artifact，重叠出现 durable queued 而非静默跳过。之后再决定是否需要 fresh-analysis kind contract。建议 targeted backend scheduler/router tests；浏览器侧 `frontend/tests/e2e/scheduled-tasks.spec.ts` 是任务 UI 而不是分析闭环。

### AS-12 PostgreSQL 应用库重启恢复 — 配置/持久化已实现；真实 PG 重启闭环未验

`database.backend` 支持 `sqlite|postgres`，示例默认 sqlite；独立 PostgreSQL 用 `database.backend: postgres` + `database.postgres_url: $DATABASE_URL`（URL 经 `.env` 环境变量解析）。它承载应用 ORM 与 checkpointer；`run_events.backend: db` 复用所选应用库。默认 Compose SQLite 路径是 `.deer-flow/data/deerflow.db`，部署持久目录为 `backend/.deer-flow`。配置参考 [database_config.py](../../backend/packages/harness/deerflow/config/database_config.py) 与 `config.example.yaml`。

尚缺在独立 PG 应用库上跑出“创建 thread/run/checkpoint/evidence/report metadata → Gateway/PG restart → owner 可读历史/evidence/report → 未完成 run 明确 interrupted 或从 checkpoint 恢复”的实证。不要拿 6F3F9 SQLite 失败 run event 读回冒充 PostgreSQL 或成功 analysis 恢复。可先用 `tests/test_persistence_engine_postgres_config.py`、`tests/test_analytics_persistence_postgresql.py`、`tests/test_scheduled_task_postgres.py` 定点覆盖；真实 restart 是 V3 独立应用 DB 环境。

### AS-13 Analytics 结构化输出边界 — 结构化投影有强自动证据；真实模型/外部 tracing 仍未验

已有 serialization/worker/journal/events/messages/checkpoint 投影覆盖，包括 6D evidence matrix 记录的 240 项定点测试。`test_serialization.py::test_analytics_message_projection_keeps_model_state_and_non_analytics_messages_unchanged`、`test_worker_stream_subgraph_namespace.py` 三个 projection tests、`test_run_journal.py::TestLlmCallbacks::test_analytics_structured_payloads_are_projected_for_journal_events`、`test_run_events_endpoint.py::test_list_run_events_projects_legacy_analytics_structures_without_mutating_store`、`test_thread_messages_page.py::test_thread_message_reads_project_legacy_analytics_rows`、`test_branch_history_seed.py::test_seed_projects_analytics_structures_without_mutating_checkpoint_messages`。输入的 HIGH/PII 拒绝路径已有 `test_analytics_delivery.py::test_high_risk_denial_is_never_executed_and_has_no_approval_path`。

真实验收须确认结构化 run/events/audit/metadata 没有 raw SQL、plan token、credential 或原始结果行；拒绝 HIGH/PII 时无计划/执行/结果。用户文本、模型最终回复、报告正文及可选 LangSmith/Langfuse/Monocle 导出不在平台结构化 projection 保证范围；关闭或单独治理 tracing。不要将其扩写成任意文本扫描承诺。

### AS-14 工具边界与 MCP 范围 — 按批准边界已验

工具集合精确三项，模型 schema 与最终 dispatch 同源；analysis admission 缺少可信 owner、marker、services 或 writer 时 fail closed，不回落普通 Lead。持久 kind 由 `metadata.analysis_mode` marker 表示；缺键的 legacy thread 是 chat，损坏 marker 拒绝，没有独立 `kind` 列。普通聊天 operator MCP 不受此策略保护。主要证据是 [phase-06f2-as14-boundary-evidence.md](phase-06f2-as14-boundary-evidence.md)、`tests/test_analysis_tool_allowlist.py`、`tests/test_gateway_services.py`、`tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get`、`frontend/tests/e2e/analysis-entry-activation.spec.ts` 与 6F1真实 run。此项已通过，不代表 AS01～15 整体通过。

### AS-15 默认四服务 Compose — 配置与历史启动局部通过；新鲜默认部署验收缺

根指南与 Compose 定义指定恰好 `nginx`、`frontend`、`gateway`、`redis`；Nginx 默认 loopback；Gateway/Redis 不发布宿主端口；默认 SQLite 挂载为 `backend/.deer-flow`；`make up` 等 Gateway readiness health 后才报告成功。已有 `backend/tests/test_compose_default_bind_host.py` 和 `test_compose_default_workers.py`；2026-09-24 记录验证容器健康、HTTP 路由、未登录保护。6F1/当前运行的五容器 overlay 不等同默认四服务启动。缺新鲜默认栈下管理员初始化/真实登录进入分析工作台、完整 readiness 和冷启动资源核对。

下一步入口：使用 repo 默认 `docker/docker-compose.yaml` / `make up`，不要传入 6F1/验收 overlay；唯一新建 project name 和未占用 loopback `PORT`，使用全新应用 volume；检查 `docker compose ... config --services` 精确四项、`up --wait` 成功、Nginx `/health` 和 auth setup/status、初始化临时 admin、真实浏览器登录与 workspace analysis route。无需模型请求。清理只针对新 project 标记的临时 volume；保留固定五容器、原有三卷、用户和业务数据。

## 建议的后续实施/验收里程碑

1. **AS-01 + AS-15 隔离认证与默认部署验收**：先做真实零模型 slice。独占资源为新的 acceptance script / `.reviews` 报告与本 acceptance 证据，不改固定栈或现有账号；用新 Compose project + 新 SQLite volume、初始化 admin、注册 slice-tagged user，测试 A/B 访问隔离与入口登录。先跑 `test_compose_default_bind_host.py`、`test_compose_default_workers.py` 和认证/owner targeted pytest，随后一次默认 Compose V3 手动验收。没有 user DELETE API，清理只可删除已核实的临时 project/volume。
2. **AS-07 + AS-10 指标、evidence 与报告正确性**：先由主会话冻结“内部 App workflow、三工具 schema 保持原样”的契约；实现范围限 analytics application/agent、run-scoped evidence/writer 接口及直接测试。V2 检查工具 schema=dispatcher=3、policy 不旁路、snapshot/run ownership、缺失 evidence 不发布；稳定后再做单次合成数据真实模型 V3。MetricService、角色阶段、数字校验是当前实现输入，不应假设已存在。
3. **AS-08 + AS-09 恢复与实时轨迹**：依赖里程碑 2 的 stage contract；运行事件/journal/前端 trace 的直接文件与接口。V2 验证每种失败终态、取消/timeout、token receipt、结构化实时事件及隐藏敏感结构字段；只在成功 analysis run 上做一次浏览器 SSE 验收。普通聊天模型文本/CoT 不归结为结构化字段保证。
4. **AS-02 + AS-03 + AS-06 双数据库与预算**：独占业务 DB integration fixture/runtime/query budget 及定点测试。复用 `scripts/test_analytics_databases.py --engine all` 的 PG16/MySQL8.4 一次性栈和只读账号；先 V2 adapter/policy/delivery gate，再以同一合成问题对两个 dialect 做单次模型 V3。AS06 先实现 MEDIUM risk 专属预算，再验 PG server timeout、MySQL 流式 client timeout/connection destroy、row/byte truncation/audit。
5. **AS-11 + AS-12 调度与 PG 恢复**：复用 Scheduler/应用库配置，隔离 application PostgreSQL DB 和 analysis thread；V2 跑 scheduler/repository/checkpoint/event contract tests，V3 做 scheduled analysis artifact + Gateway/PG restart readback，明确中断运行状态。AS15 已在里程碑 1 默认 SQLite Compose 验证，不把它当 PG application DB。

## 本轮验证与下一最小切片

本轮只进行 V0：本报告创建后检查回读、相对链接目标和 `git diff --check`；未跑测试/构建/数据库脚本/模型或容器，符合本切片边界。

下一最小切片建议按顺序做 AS-01/AS-15 的真实零模型验收：用全新 Compose project 和 SQLite volume，不覆盖现有配置或栈；经 `/api/v1/auth/initialize` 建立一次性首个 admin，经 `/api/v1/auth/register` 建立唯一 slice-tagged user；对两个真实 session 验证 owner 隔离和 Nginx workspace 登录。没有用户删除 API，因此仅在确认 project label/精确 volume 都属于此次 slice 后清理新资源。
