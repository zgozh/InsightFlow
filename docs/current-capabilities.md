# InsightFlow 当前功能与架构

核对日期：2026-10-09。本页按当前源码和有日期的验收记录区分实现状态、已完成实测与未完成发布门禁；不把目标架构当现状，也不以代码存在推断发布验收已完成。源码链接使用仓库中的真实模块和符号名称。

## 最新 PostgreSQL 正例与当前验收边界

- 最新 PostgreSQL 报告通过重启、19-field、hash 和报告 UI 检查；真实 PostgreSQL checkpoint/evidence producer 复用及原 artifact hash 有 proof，未完成运行也已通过独立 PG 与新 Gateway lifespan 进程验证为 `error/orphan_recovered`。相关记录见[报告验收](acceptance/2026-10-09-label-repair-api-acceptance.md)、[checkpoint 与取消验收](acceptance/2026-10-09-live-checkpoint-and-cancel.md)及[未完成运行恢复](acceptance/2026-10-09-unfinished-run-recovery.md)。受控查询 API/SQL 安全、风险预算和真实 HTTP statement timeout/audit 已通过，见[查询安全](acceptance/2026-10-09-direct-query-security.md)、[风险门禁](acceptance/2026-10-09-query-risk-gates.md)及[HTTP timeout 验收](acceptance/2026-10-09-http-timeout-cancel-gates.md)。这些结果不代表 Phase 6 或整体发布验收完成。
- 数据源/指标两步预填修复的 4 项定点测试和浏览器探针已通过。产品仍允许编辑预填草稿，不会自动提交分析请求；当前 Gateway 实例与交互证据分别记录，见[最终交付状态](acceptance/2026-10-09-final-delivery.md)。
- 最新 scheduled run 在 server-computation1109 Gateway 上通过 AS-11：无历史 analysis thread，单次 once occurrence / attempt 完成查询、Data、Writer、Reviewer approved 与 Publish，并生成 owner report。详细安全摘要见[最终交付记录](acceptance/2026-10-09-final-delivery.md)；之前的失败 run 与 fail-closed 拒绝记录继续保留。
- 功能与部署门禁按批准范围均已通过，包括 Windows 7 项门禁、合并后的 14 项候选检查、`sharedproxy=True` 复验和 29384 原入口独立后验收。Root 已接受最终源码与暂存审查；本状态记录截于发布提交前，commit/push 状态以 Git 记录为准，远程 CI 结果以 Actions 为准（本记录形成时尚未运行）。详细证据见[最终发布矩阵](acceptance/2026-10-09-final-release-matrix.md)与[最终交付记录](acceptance/2026-10-09-final-delivery.md)。

## 通用 Agent 运行时

| 能力 | 实现模块与关键源码 | 实现状态与真实验收范围 |
| --- | --- | --- |
| LangGraph Lead、工具调用 | [`_assemble_lead_agent`](../backend/packages/harness/deerflow/agents/lead_agent/agent.py) 通过 `create_agent` 装配模型、工具与中间件；[`RunManager`](../backend/packages/harness/deerflow/runtime/runs/manager.py) 接入 Gateway | 已实现；[PROGRESS 的6F3F11记录](PROGRESS.md) 一次真实普通聊天成功，刷新后消息可见；不证明所有模型/工具组合。 |
| 普通 task 子 Agent | 普通委派与隔离治理；[`SubagentExecutor`](../backend/packages/harness/deerflow/subagents/executor.py)、[`registry`](../backend/packages/harness/deerflow/subagents/registry.py)、[`SubagentRuntimeConfig`](../backend/packages/harness/deerflow/config/subagent_runtime_config.py) | 已实现通用委派、独立 execution_id/外部 tool_call_id、线程上下文、隔离事件循环、取消/超时/token budget/receipt；进程容量默认 running=3、queued=64、等待300秒，可配置。FakeAgent HTTP 定点测试验证 interrupt 会终止 worker 并恢复 thread idle；真实 PostgreSQL unfinished-run proof 验证新 Gateway 进程把 orphan run 恢复为 `error/orphan_recovered` 并写入零交付 receipt。分析模式当前禁用普通委派。 |
| MCP 工具和耐久异步任务 | Gateway 集成；[`get_mcp_tools`](../backend/packages/harness/deerflow/mcp/tools.py)、[`McpTaskService`](../backend/app/mcp_tasks/service.py)、[`mcp_tasks`](../backend/packages/harness/deerflow/persistence/mcp_tasks/sql.py) | 已实现 operator 工具加载、提交、数据库任务状态、租约恢复、取消 fencing、通知重试/死信；当前会话未连接真实 MCP task server。普通聊天 MCP 不受 Analytics SQL Policy 保证。 |
| Skills 与安装检查 | [`catalog`](../backend/packages/harness/deerflow/skills/catalog.py)、[`installer`](../backend/packages/harness/deerflow/skills/installer.py)、[`SkillScan`](../backend/packages/harness/deerflow/skills/skillscan/orchestrator.py) | 已实现发现、加载、延迟工具/技能搜索和安装扫描；扫描不是任意技能代码安全证明。分析模式不加载 Skills，旧 surprise-me 技能已删除。 |
| Local / AIO 沙箱 | 运行时组件与安全边界改造；[`LocalSandboxProvider`](../backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py)、[`AIO`](../backend/packages/harness/deerflow/community/aio_sandbox)、[`sandbox tools`](../backend/packages/harness/deerflow/sandbox/tools.py) | 已实现文件/命令工具。Local 以 Gateway 主机权限运行，不能宣称强容器安全隔离；AIO 为外部服务客户端。[6F3F17](acceptance/phase-06f3f17-surprise-toolchain-diagnosis.md) 真实 write_file/present_files 产物链；[6F3F19](acceptance/phase-06f3f19-artifact-ui-projection.md) 既有 HTML 真实预览/交互。 |
| 持久记忆 | [`DeerMem`](../backend/packages/harness/deerflow/agents/memory/backends/deermem/deer_mem.py)、[`memory middleware`](../backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py) | 已实现可配置记忆管理、提取/更新与召回；当前表不宣称真实长期记忆效果评测通过。记忆召回不等同知识库 RAG；分析模式禁用记忆。 |
| 上下文压缩 | [`DeerFlowSummarizationMiddleware`](../backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py)、[`summarization config`](../backend/packages/harness/deerflow/config/summarization_config.py) | 已实现阈值、摘要、锚点和压缩前 hooks；是否启用取决于运行配置。本轮无长会话模型评测，不写“无限上下文”。 |
| 规划和澄清 | [`Lead`](../backend/packages/harness/deerflow/agents/lead_agent/agent.py) 的 `is_plan_mode`、[`clarification`](../backend/packages/harness/deerflow/tools/builtins/clarification_tool.py) | 已实现交互式澄清与普通聊天规划开关；内部 non_interactive 运行排除澄清。分析模式当前禁用通用 plan mode，受控查询步骤仍存在。 |
| SSE 与耐久运行状态 | Gateway 持久化集成；[`StreamBridge`](../backend/packages/harness/deerflow/runtime/stream_bridge)、[`checkpointer`](../backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py)、[`events store`](../backend/packages/harness/deerflow/runtime/events/store)、[`config`](../config.example.yaml) | 已实现流式消息、子任务事件、checkpoint 与可配置数据库事件存储；模板 `run_events.backend=db`。[契约矩阵](acceptance/phase-06d-contract-reconciliation.md)和[PROGRESS](PROGRESS.md)记录6F3F9：失败普通 run 的 SQLite 事件重启持久性已实测；成功聊天刷新已实测，完整分析实时 SSE/自由文本边界仍缺。 |
| Scheduler | Gateway 耐久队列实现；[`ScheduledTaskService`](../backend/app/scheduler/service.py)、[`scheduler config`](../backend/packages/harness/deerflow/config/scheduler_config.py) | 已实现配置 gated 调度、queued/launching/running、租约与预算；等待不占并发，忙时不跳过。AS-11 最新 once run 在 server-computation1109 Gateway 成功并发布 owner report；AS-12 PostgreSQL checkpoint/evidence producer 复用及 unfinished-run 恢复有独立 proof。此前失败 run 仍保留。 |
| 认证与 owner 隔离 | 认证与 App 集成；[`auth middleware`](../backend/app/gateway/auth_middleware.py)、[`Gateway services`](../backend/app/gateway/services.py)、[`artifacts router`](../backend/app/gateway/routers/artifacts.py) | 已实现认证、线程/run/artifact owner gate；[6F1](acceptance/phase-06f1-real-analysis-rehearsal.md)及后续单例证明 owner GET 200 / 异线程404，多真实主体完整验收仍缺。 |
| 可观测、receipt、guardrails | 运行时能力与安全投影集成；[`ToolReceiptMiddleware`](../backend/packages/harness/deerflow/agents/middlewares/tool_receipt_middleware.py)、[`guardrails`](../backend/packages/harness/deerflow/guardrails/middleware.py)、[`trace middleware`](../backend/app/gateway/trace_middleware.py) | 已实现可配置 guardrails、工具回执与运行关联；启用状态由配置决定。结构化 metadata/审计安全边界不等于任意模型正文或 artifact 无敏感信息保证（AS-13）。 |
| 分析角色与阶段事件 | [`roles`](../backend/app/analytics/agent/roles.py)、[`stages`](../backend/app/analytics/agent/stages.py)、[`stage panel`](../frontend/src/components/analytics/analysis-stage-panel.tsx) | 分析由 Lead 驱动，独立 SQL Analyst/Data 调用与 run-scoped evidence 受限阶段合同管理；数值声明由 domain verifier 核验，阶段 UI 只展示合同允许字段。离线声明解析、角色检查、实时阶段事件合同和 PostgreSQL 报告链均有验收证据；不外推为任意输入组合均通过。 |

## InsightFlow 分析应用

| 能力 | 当前源码 / 关键符号 | 已实现与验收边界 |
| --- | --- | --- |
| App / Harness 分层 | [`backend/app`](../backend/app)、[`packages/harness`](../backend/packages/harness)、[`extension-api`](../backend/packages/extension-api) | 分离产品应用与通用运行时，Harness 不反向依赖 App；公共扩展契约单独成包。Analytics 分层规则与依赖门禁见[模块指南](../backend/app/analytics/AGENTS.md)。 |
| Analytics 五层 | [`domain`](../backend/app/analytics/domain)、[`application`](../backend/app/analytics/application)、[`infrastructure`](../backend/app/analytics/infrastructure)、[`agent`](../backend/app/analytics/agent)、[`api`](../backend/app/analytics/api)及[`composition`](../backend/app/analytics/composition.py) | 已实现领域契约、用例/ports、数据库/策略适配、工具和 HTTP 交付；不是把所有逻辑塞入提示词。 |
| SQL / 语义授权 | [`SqlglotQueryPolicy`](../backend/app/analytics/infrastructure/sql_policy.py)、[`SqlglotSemanticAuthorizer`](../backend/app/analytics/infrastructure/semantic_authorizer.py) | 已实现 AST 正向检查、关系/列/函数 default-deny、schema/policy 对齐；HIGH 风险当前拒绝，无人工批准执行分支。更早定点门禁见[6F2](acceptance/phase-06f2-as14-boundary-evidence.md)引用的817项记录，本轮不重复测试。 |
| 指标目录与显式授权 | [`GET /metrics`](../backend/app/analytics/api/router.py)、[`MetricView`](../frontend/src/core/analytics/types.ts)、[`指标目录与管理`](../frontend/src/app/workspace/metrics/page.tsx)、[`grant hooks`](../frontend/src/core/analytics/hooks.ts) | 普通目录只列出当前主体拥有或有确切授权的 active 定义；草稿可提前授权，启用后才可见，下线后从普通目录消失。指标授权只开放定义，数据源查询仍由独立策略控制；同 key 多 owner 产生歧义时服务端隐藏该定义。 |
| 只读 PG/MySQL、限额与审计 | [`CreateQueryExecutionPlan` / `ExecuteQueryPlan`](../backend/app/analytics/application/execution.py)、[`PostgreSQL`](../backend/app/analytics/infrastructure/postgresql_runtime.py)、[`MySQL`](../backend/app/analytics/infrastructure/mysql_runtime.py)、[`audit`](../backend/app/analytics/infrastructure/persistence/audit_log.py) | 已实现短期一次性 plan、授权重检、只读事务、行/字节/时限与审计 fail-closed。PostgreSQL API/查询安全、风险预算、adapter timeout 和真实 HTTP plan/execute timeout/audit 门禁已通过，证据见本页顶部链接。MySQL 流式路径依靠客户端 timeout + 连接销毁，不能称服务端抢占保证。 |
| evidence、writer 与 Reviewer | [`evidence`](../backend/app/analytics/agent/evidence.py)、[`write_analysis_report`](../backend/app/analytics/agent/reports.py)、[`AnalysisReportReviewerCapability`](../backend/app/analytics/agent/reviewer.py)、[`writer`](../backend/app/gateway/analysis_report_writer.py) | 已实现确定性证据标识、同 run 查询结果注册、固定 Markdown 产物与发布索引；Reviewer 绑定本次 Lead 模型，零工具、20秒、最多2次、封闭决定码，并拒绝坏响应。最新 PostgreSQL 报告链已通过[对应验收](acceptance/2026-10-09-label-repair-api-acceptance.md)；它不构成逐数字数学正确性证明或独立通用 Reviewer 子 Agent。 |
| 可信分析 kind / 固定工具链 | [`start_run`](../backend/app/gateway/services.py)、[`_get_analysis_tools`](../backend/packages/harness/deerflow/tools/tools.py)、[`Lead`](../backend/packages/harness/deerflow/agents/lead_agent/agent.py) | 已实现服务端持久 marker + 认证 owner + services/writer 绑定 admission，fail-closed；精确工具集仅 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`。AS-14 按[6F2批准边界](acceptance/phase-06f2-as14-boundary-evidence.md)验收，不承诺任意 operator MCP；无独立 kind 列，数据库外部删 marker 有明确限制。 |
| 安全轨迹与报告 UI | [`trace`](../frontend/src/core/analytics/trace.ts)、[`trace panel`](../frontend/src/components/analytics/analytics-trace-panel.tsx)、[`reports`](../frontend/src/core/analytics) | 已实现消息纯投影、稳定码 i18n、审核状态和 owner 下载。[契约矩阵](acceptance/phase-06d-contract-reconciliation.md)记录6F3F5真实历史卡片与6F3F6下载单例；不等于全部实时 SSE 或通用 evidence 正确性。 |
| 受控工作台与产品裁剪 | [`workspace`](../frontend/src/app/workspace)、[`AGENTS`](../AGENTS.md)、[`README`](../README.md) | 当前保留分析、普通聊天、数据源/指标/报告/历史/定时任务；新建分析页使用通用 composer，没有数据源或指标 picker。移除 IM、Custom/Managed 管理、Projects/Documents/Trash、Browser及 provider zoo。删 Custom 管理不等于删 task 委派；Phase5文件数量目标尚未完成，不继续为减数量删安全测试。 |
| 黑洞首页 | [`Hero / BlackHole`](../frontend/src/components/landing/black-hole.tsx)、[资源署名](../frontend/public/images/BLACK-HOLE-CREDITS.md) | 原创全屏粒子、静态/减动效退化、手机适配与真实照片favicon；[6F3F21](acceptance/phase-06f3f21-immersive-black-hole-landing.md)本地 checks及主会话独立目视接受。固定栈仅前端部署成功；主会话已独立目视部署双尺寸截图，并只读核对五容器running、三项health healthy、health/favicon200，接受本地与部署首页。 |

## 分析角色与调用流程

受控分析由 Lead 接收问题并驱动 run。Lead 先通过目录工具了解当前主体可访问的数据源和 active 指标；SQL Analyst 独立整理查询，再经既有 Gateway 授权计划和只读执行。成功查询结果以 evidence 绑定到当前 run；Data role 输出绑定证据单元格的 `NumericClaimPlan` 运算与引用，Gateway domain verifier 解析快照并使用 `Decimal` 计算和校验数字声明，模型不负责提供权威算术结果。Report Writer 使用 run-scoped 写入能力构建固定格式报告，Reviewer 再执行有界零工具复核。Metric Service 提供指标口径快照。普通聊天仍可通过 `task` 委派通用子 Agent，并可按运维配置使用 MCP、Skills、Memory 和计划模式；这些普通聊天能力不改变 Analytics 固定工具和授权路径。

## 当前验收与交付状态

| 优先级 | 已有证据 / 尚缺证据 | 说明 |
| --- | --- | --- |
| 1 数据源与指标两步预填 | 草稿修复的 4 项定点测试及浏览器探针通过，见[修复记录](acceptance/2026-10-09-prefilled-analysis-draft-fix.md)。 | 当前 Gateway 部署由独立交付摘要记录；UI 探针本身不替代服务端部署证据。 |
| 2 Scheduler 与重启恢复 | AS-11 最新 once run 已成功并产生 owner report；AS-12 PostgreSQL checkpoint/evidence producer 复用与 unfinished-run 恢复有独立 proof。 | 旧失败 run 与 Reviewer 拒绝保留；不以其替代最新成功 run，也不作任意输入保证。 |
| 3 未承诺的输入范围 | 平台合同范围内的报告、查询、安全与阶段证据按矩阵通过。 | 任意自由文本敏感内容、任意第三方 MCP/RAG 行为及未约定输入变体不在此结论内。 |
| 4 交付收尾 | 功能与部署门禁按批准范围均已通过，含 29384 原入口独立后验收。 | Root 已接受最终源码与暂存审查；本记录截于发布提交前，commit/push 状态以 Git 记录为准，远程 CI 结果以 Actions 为准（形成时尚未运行）。 |

## 个人项目描述

**InsightFlow｜个人维护的受控经营分析工作台**

- 将 LangGraph 通用 Agent 运行时与产品 App 分层，建立 Analytics 的 domain/application/infrastructure/agent/api 边界，集成 Next.js 工作台、流式会话、产物与定时任务。
- 实现 SQLGlot AST 检查与表/列/函数语义授权，结合只读 PostgreSQL/MySQL、一次性执行计划、限额超时和 fail-closed 审计，约束平台 Analytics 数据访问。
- 实现可信分析线程准入、固定工具集合及 run-scoped 报告能力，以查询 evidence、有限零工具 Reviewer 和 owner 产物下载形成可复核发布链；已完成窄范围真实 PostgreSQL/模型样例与浏览器历史报告验证。
- 保留并整合上游 task 委派、MCP/Skills、沙箱、记忆、压缩与持久运行机制，收缩无关产品入口；完成原创响应式颗粒黑洞首页与静态/减动效适配。

受控分析由 Lead 接收问题并驱动 run：SQL Analyst 整理查询，Gateway 执行授权的只读查询；Data role 只选择证据单元格引用和运算，domain verifier 使用 `Decimal` 在服务端完成计算与核验；Report Writer 生成固定格式报告，Reviewer 执行有界零工具复核。当前 PostgreSQL 报告、安全预算、HTTP timeout/audit、checkpoint/evidence producer 复用、unfinished-run 恢复、预填交互、AS-11 scheduled report 及 29384 原入口部署均有验收证据。功能与部署门禁按批准范围通过；Root 已接受最终源码/暂存审查。本段截于发布提交前，commit/push 状态以 Git 记录为准，远程 CI 结果以 Actions 为准（本记录形成时尚未运行）。详见[最终交付记录](acceptance/2026-10-09-final-delivery.md)。
