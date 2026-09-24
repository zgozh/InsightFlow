# Phase 6D1：发布契约与现行实现证据矩阵

日期：2026-09-24。该矩阵只记录当前可追溯的代码、自动测试和已有本机记录，不将设计、skill 提示、mock 或局部测试扩写为端到端验收。状态是逐项契约判断，整条场景未跑通时会在残差中明确说明。

状态只能取以下值：

- `代码/自动测试已证实`：表中列出的具体代码行为已有自动测试覆盖；不代表整个发布级场景已完成端到端验收。
- `仅设计/尚未真实验收`：存在实现或设计证据，但当前没有覆盖整条契约的真实验收。
- `与现行实现矛盾`：发布场景承诺的行为与当前实现不同，或存在尚未受平台策略约束的路径。

## 逐项矩阵

| 场景 | 状态 | 当前实现与最强证据 | 实测结果及边界 |
| --- | --- | --- | --- |
| AS-01 认证 | 仅设计/尚未真实验收 | `backend/app/gateway/auth_middleware.py`；`backend/tests/test_auth_middleware.py::test_protected_path_no_cookie_returns_401`；`backend/tests/test_analytics_api.py::test_unauthenticated_requests_are_rejected`、`test_audits_are_exact_principal_and_never_cross_tenant`、`test_report_listing_is_exactly_principal_scoped` | 未认证拒绝及 Analytics principal 隔离有自动测试；没有创建管理员并走完浏览器登录、thread/run/artifact 多主体隔离的整链验收。 |
| AS-02 MySQL 业务数据源 | 仅设计/尚未真实验收 | `backend/app/analytics/infrastructure/mysql_runtime.py`；`backend/tests/test_analytics_mysql_integration.py`；历史命令 `scripts/test_analytics_databases.py --engine all` | `docs/LOCAL_TRIAL.md` 留存 PostgreSQL 16.15 + MySQL 8.4.11 共 82 passed；历史记录未记退出码。本切片未重跑数据库脚本；该记录验证适配器/迁移/受控查询，不包含真实模型自然语言分析、artifact 写入或 Reviewer 闭环。 |
| AS-03 PostgreSQL 业务数据源 | 仅设计/尚未真实验收 | `backend/app/analytics/infrastructure/postgresql_runtime.py`；`backend/tests/test_analytics_postgresql_integration.py`；历史命令 `scripts/test_analytics_databases.py --engine all` | 历史数据库门禁结果同 AS-02：82 passed，未保存退出码；未证明模型分析链、真实 artifact/evidence 复核或完整用户流。业务 PostgreSQL 与应用持久化数据库是不同用途。 |
| AS-04 datasource/table/column 越权拒绝 | 代码/自动测试已证实 | `backend/app/analytics/infrastructure/semantic_authorizer.py`、`backend/app/analytics/application/delivery.py`；`backend/tests/test_semantic_authorizer.py::test_unknown_relation_is_rejected`、`test_relation_absent_from_the_policy_is_rejected`、`test_column_absent_from_the_policy_rule_is_rejected`、`test_denied_column_is_rejected`；`backend/tests/test_analytics_delivery.py::test_an_authorization_denial_writes_an_authorization_audit_and_stops` | 授权拒绝、审计并停止后续计划/执行的代码路径有自动测试。测试用例不是接入真实业务数据库的完整 HTTP/自然语言端到端场景。 |
| AS-05 DDL/DML/多语句阻断 | 代码/自动测试已证实 | `backend/app/analytics/infrastructure/sql_policy.py`；`backend/tests/test_sql_policy.py::test_policy_fails_closed`、`test_sql_comments_are_rejected`、`test_mysql_executable_comment_is_rejected`、`test_postgres_copy_is_unsupported`、`test_write_nested_inside_a_cte_is_forbidden` | SQL policy 对非法语法、写操作、注释绕过及不支持的 COPY 形态有确定性拒绝测试。实际拒绝证据是解析/策略测试，不表示任意第三方 MCP 受同一策略约束；该范围见 AS-14。 |
| AS-06 超时与结果上限 | 仅设计/尚未真实验收 | `backend/app/analytics/infrastructure/postgresql_runtime.py`、`mysql_runtime.py`、`result_normalizer.py`、`backend/app/analytics/application/delivery.py`；`backend/tests/test_result_normalizer.py::test_next_row_over_the_row_cap_truncates_with_complete_rows_only`、`test_next_row_over_the_byte_cap_truncates_at_the_last_complete_row`；`backend/tests/test_analytics_delivery.py::test_only_the_result_row_cap_is_clamped_and_everything_else_matches_the_config` | 行/字节预算、适配器 timeout 和服务端 row cap 有局部测试；历史 PG/MySQL 82 项门禁已记录但退出码未保存。本轮没有重跑真实数据库，也没有证明 MEDIUM 风险预算、超时审计、事件和结果截断在完整 Gateway/run 链上的契约。HIGH 在 V1 是 fail-closed 拒绝，见 AS-13。 |
| AS-07 Lead→Reviewer 分析主链 | 与现行实现矛盾 | `skills/public/business-analysis/SKILL.md`；`config.example.yaml` 的 `subagents.agents`；`backend/packages/harness/deerflow/subagents/builtins/__init__.py`；`backend/tests/test_business_analysis_skill.py` | skill 指导 Lead 用 `task` 委派 `general-purpose` 扮演 Data Analyst / Reviewer；没有专职 SQL Analyst、Reviewer、Report Writer 子 Agent。受控查询工具存在，但目标角色分工和完整分析/复核链不是当前产品事实。 |
| AS-08 子 Agent 故障恢复 | 仅设计/尚未真实验收 | `backend/packages/harness/deerflow/subagents/executor.py`；`backend/tests/test_subagent_executor.py` | executor 有取消、loop guard、预算与 receipt 等一般能力及自动测试；未找到覆盖本场景中 Reviewer 拒绝后有界修订、全部事件/receipt/结论不伪造的真实业务分析链验收。 |
| AS-09 SSE 结构化轨迹且无思维链 | 仅设计/尚未真实验收 | `frontend/src/core/analytics/trace.ts`、`frontend/src/components/analytics/analytics-trace-panel.tsx`；`frontend/tests/unit/core/analytics/trace.test.ts`、`frontend/tests/unit/components/analytics/analytics-trace-panel.dom.test.tsx`；`frontend/tests/e2e/insightflow-workspace.spec.ts` | 前端有结构化 trace 投影与组件测试；现有工作台 E2E 使用合成/模拟事件。没有真实 Agent SSE 全链证据证明本契约列出的阶段、结果、evidence 与无思维链约束同时成立。 |
| AS-10 报告 artifact | 与现行实现矛盾 | `backend/app/analytics/agent/reports.py::publish_analysis_report`、`backend/app/analytics/infrastructure/persistence/reports.py`；`backend/tests/test_analytics_agent_reports.py::test_the_agent_report_module_never_touches_the_filesystem_or_the_database`；`backend/tests/test_analytics_api.py::test_a_report_response_only_carries_index_fields` | 工具只登记报告索引 metadata，不打开或读取 artifact，不核验报告数字与 evidence 的对应关系。skill 指示 Lead 另行写文件并调用 `present_files`；没有真实分析 artifact 发布/下载链验收。 |
| AS-11 计划分析 | 仅设计/尚未真实验收 | `backend/app/gateway/services.py`；`backend/tests/test_gateway_services.py::test_launch_scheduled_thread_run_marks_context_non_interactive`；`backend/tests/test_scheduled_task_queue.py::test_queued_run_survives_single_instance_restart_sweep` | Scheduler 有通用非交互 Gateway run、持久队列及恢复测试；未用真实业务问题、受控 SQL、evidence 和报告 artifact 完成计划任务闭环。 |
| AS-12 PostgreSQL 应用库重启恢复 | 仅设计/尚未真实验收 | `backend/packages/harness/deerflow/config/database_config.py`；`config.example.yaml`；`docker/docker-compose.yaml`；`backend/app/gateway/services.py` | 应用数据库默认 SQLite，默认目录 `.deer-flow/data`、文件 `deerflow.db`；Gateway Compose 将 `backend/.deer-flow` 持久挂载。`database.backend: postgres` 是外部实例的可选配置；PostgreSQL restart 后 thread/run/checkpoint/artifact 恢复没有完整验收证据。 |
| AS-13 凭据与 PII 不进入日志和事件 | 仅设计/尚未真实验收 | `backend/app/analytics/infrastructure/semantic_authorizer.py`、`backend/app/analytics/application/delivery.py`、`backend/app/analytics/agent/tools.py`；`backend/tests/test_semantic_authorizer.py::test_sensitive_and_pii_columns_require_approval`、`test_no_high_decision_is_ever_allowed`；`backend/tests/test_analytics_delivery.py::test_high_risk_denial_is_never_executed_and_has_no_approval_path`、`test_raw_sql_only_reaches_the_audit_as_a_query_hash` | 自动测试已证明 HIGH/PII `APPROVAL_REQUIRED` fail-closed、无可执行计划/业务查询/结果行，并证明审计不保存 raw SQL（授权阶段只留 query hash）。但完整 AS-13 还要求覆盖工具响应、Gateway events、receipt、artifact 与报告投影的凭据/PII 扫描；本轮没有跨这些通道的集成证据，因此整项仍未验收。V1 也没有人工批准或动态结果脱敏。 |
| AS-14 MCP 统一 Query Policy | 与现行实现矛盾 | `backend/packages/harness/deerflow/mcp/tools.py::get_mcp_tools`；平台自有路径 `backend/app/analytics/agent/tools.py::query_business_data` | 平台自有 Analytics 查询工具执行 Query Policy；任意第三方 MCP 工具可提供独立数据访问能力，未被强制经该策略或同等审计。**发布阻塞**；不得用“管理员不会配置危险 MCP”声称系统通用安全。仅 6D2 的平台自有受控查询验证不依赖解除此阻塞。 |
| AS-15 四服务默认 Compose 启动 | 仅设计/尚未真实验收 | `docker/docker-compose.yaml`、`docker/docker-compose-dev.yaml`、`backend/tests/test_compose_default_bind_host.py`、`backend/tests/test_compose_default_workers.py`；`docs/LOCAL_TRIAL.md` 的 2026-09-24 实机记录 | 两份 Compose 定义 `nginx`、`frontend`、`gateway`、`redis`；此前本机 `make up` 退出码 0，健康与入口路由通过，但未创建管理员或认证后进入工作台。该记录不证明 AS-01 登录链完成。 |

## 部署与存储事实

- 默认 Docker Compose 是四服务 `nginx`、`frontend`、`gateway`、`redis`；Redis 是必需服务，不是可选 profile，Compose 不向宿主机发布其端口。`make dev` 的本地编排运行三个面向用户的进程；默认 memory StreamBridge 不改变 Docker Compose 拓扑。
- 应用持久化默认 SQLite，`database.backend` 默认值为 `sqlite`，相对 `backend` 工作目录的文件是 `backend/.deer-flow/data/deerflow.db`；默认 Compose 持久挂载 `backend/.deer-flow`。可选 `database.backend: postgres` 指向运维提供的外部应用 PostgreSQL，不由默认 Compose 启动。
- Analytics 管理的 PostgreSQL/MySQL 是业务数据源，与应用数据库分离，也不由默认 Compose 启动。
- AS-14 是发布阻塞；对平台自有受控查询路径的验证不等同于任意 MCP 的统一安全保证。
- V1 HIGH/PII 查询采用 fail-closed 拒绝且不向结果通道写入查询结果；没有 HIGH 人工批准或动态 PII 结果脱敏。

## 本切片验证记录

实际执行命令、退出码、通过/失败/跳过计数和失败 ID 由 `docs/LOCAL_TRIAL.md` 的“Phase 6D1 契约复核补记”记录。历史 PostgreSQL/MySQL `82 passed` 的记录没有保存退出码，故不推定为本切片新运行或用来声称全链验收。此切片未运行全量后端或 Playwright，也没有读取 `.env`、发起模型请求或创建数据库测试容器。
