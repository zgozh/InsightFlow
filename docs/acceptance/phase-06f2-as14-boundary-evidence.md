# Phase 6F2：AS-14 受控分析边界证据

日期：2026-09-26（Asia/Shanghai）  
基线：`main` / `40cb4d1`；6F1 终点 `1bae353` 为祖先；工作树起始干净；固定上游 tag/tree 未变。

## 结论与口径

AS-14 按用户批准的范围验收：平台托管 Analytics 查询受平台策略链约束；普通聊天保留 operator 配置的 MCP，但不承诺第三方 MCP 遵循该策略；受控分析只暴露固定的三个 Analytics 工具，并要求可信 Gateway admission 和 run-scoped writer capability。该结论不代表任意第三方 MCP 安全、AS-01..AS-15 全部完成或 Phase 6/发布完成。6F1 的单条真实彩排只作为窄范围运行证据，不替代多主体认证、MySQL、默认 Compose 或全部拒绝路径验收。

线程 kind 的现行持久化契约是 `metadata.analysis_mode` 这个 Gateway 保留标记本身；存储模型没有另一列独立 `kind`。服务端创建 `kind=analysis` 时写入 `analysis_mode=true`，普通写入、PATCH 与 run 请求不能伪造或清除。依据 6E2A 已批准语义，缺少该键的既有记录是 legacy chat；显式损坏的标记 fail closed。analysis 新建遇到已有无标记 ID 返回 `thread_kind_conflict`，现有 analysis 路由仅在持久标记严格为 `true` 时挂载聊天运行时。本轮补充了 metadata 对象存在但缺失标记的路由断言。

剩余数据完整性边界：如果绕过应用写路径直接从数据库删除某个原 analysis 记录的标记，当前 schema 无法把它与 legacy chat 区分；本轮未添加独立 kind 字段或迁移，也不声称能检测这种 out-of-band 篡改。应用 API/前端的受控分析路径不会因此静默把该记录挂载为分析运行。

## 条款—证据表

| AS-14 批准条款 | 代码与既有测试证据 | 证据性质与结论 |
| --- | --- | --- |
| 平台 `query_business_data` 必须经过 Query Policy、授权、限额、超时与审计 | `backend/app/analytics/agent/tools.py::query_business_data` → `backend/app/analytics/application/delivery.py` → policy / authorizer / runtime / audit；`test_analytics_delivery.py::test_a_policy_denial_writes_a_policy_audit_and_stops`、`test_an_authorization_denial_writes_an_authorization_audit_and_stops`、`test_high_risk_denial_is_never_executed_and_has_no_approval_path`、`test_an_audit_start_failure_stops_before_the_denial_continues`、`test_an_audit_finish_failure_returns_audit_unavailable_instead_of_the_denial`、`test_a_small_query_limit_clamps_the_transport_row_cap_and_still_creates_a_plan`、`test_a_query_limit_above_the_cap_keeps_the_configured_cap`；`test_analytics_postgresql_integration.py::test_explain_orders_read_only_timeout_explain_and_rollback`、`test_explain_maps_a_statement_timeout_to_execution_timeout` | 自动化合成/适配器测试覆盖拒绝、审计失败关闭、服务端限额与只读/timeout 顺序；6F1 另在隔离 PostgreSQL 真实模型链观察到受控计划/执行 audit 与一次受控查询。不是 MySQL 实模型链、全方言负例矩阵，也不覆盖第三方 MCP。 |
| 普通聊天保留 operator MCP；不承诺其遵循平台 SQL 策略 | 普通分支在 `deerflow/tools/tools.py::get_available_tools` 使用常规工具配置与 MCP cache；`test_analysis_tool_allowlist.py::test_ordinary_tool_loader_keeps_synthetic_mcp_tools` | 合成测试保护普通 MCP 路径未被分析白名单误禁。未连接任意真实第三方 MCP；这是明确的保证边界，不将其称为 AS-14 缺陷或安全证明。 |
| 受控分析模型 schema 与最终执行精确限于三个工具 | `_get_analysis_tools` 返回固定来源；`_assemble_lead_agent` 把同一 `final_tools` 传给 Agent/执行图，并在分析模式关闭延迟工具发现、子 Agent 与 middleware 扩展。`test_analysis_tool_allowlist.py::test_analysis_assembly_uses_server_context_and_one_set_for_model_and_dispatch` | 合成模型记录的绑定 schema 与实际 dispatcher 使用集合一致，精确为 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`；恶意模型调用未执行 poison tool。6F1 真实 run 也仅观察到这三个分析工具事件。 |
| MCP 缓存/热更新、未知工具、历史/伪造 `tool_call`、`tool_search`、命令及委派不得扩展集合 | `test_analysis_tool_allowlist.py::test_analysis_tool_loader_ignores_later_catalog_and_mcp_updates`、`test_analysis_tool_loader_fails_closed_when_approved_source_is_missing`、`test_analysis_tool_loader_fails_closed_when_source_returns_a_different_tool`，以及上述装配/执行测试；`launch_mcp_task_notification_run` 通过 `start_run(... require_existing_thread=True)` 进入同一 Gateway 准入与 Lead 装配链 | MCP cache/config update 不参与分析工具装配；notification 没有独立 graph/tool path。Notification 有普通行为测试，但未单独用真实 MCP server 在 analysis thread 上做端到端；静态调用图证明其只能复用 `start_run` 和固定分析 graph，未发现旁路。 |
| `write_analysis_report` 只能用 Gateway server-owned per-run capability，写固定受控 Markdown 并登记安全回执 | `backend/app/gateway/services.py` 在分析 admission 后创建并绑定 owner/thread/run capability；`backend/app/gateway/analysis_report_writer.py` 固定路径、create-only 与内容/尺寸约束；`backend/app/analytics/agent/reports.py::write_analysis_report` 校验匹配身份与 capability。测试：`test_gateway_services.py::test_start_run_binds_writer_capability_before_analysis_agent_start`、`test_analysis_writer_capability_failure_terminalizes_without_starting_graph`；`test_analytics_agent_reports.py::test_report_writer_schema_has_only_content_and_evidence_fields`、`test_report_writer_fails_closed_without_matching_gateway_capability`、`test_the_tool_is_unavailable_when_no_control_plane_is_bound`；`test_analysis_report_writer_files.py` 的 create-only、owner/thread/run、symlink 与固定目标拒绝用例 | 自动化测试覆盖能力绑定/失败关闭和文件边界；6F1 观察到一条真实报告登记、Markdown artifact 生成与所有者读取 200，另一线程读取 404。没有 Reviewer、通用任意文本扫描或所有者间完整 AS-01 证明。 |
| 认证、owner、持久 kind、Analytics services 任一不满足都不得运行普通 Lead 作为降级 | `read_thread_analysis_mode` 与 `start_run`；线程创建/PATCH 保留字段保护。测试：`test_start_run_keeps_analysis_closed_without_bound_services_or_real_principal`、`test_start_run_fails_closed_on_corrupt_analysis_thread_mode`、`test_start_run_fails_closed_when_thread_mode_cannot_be_read`、`test_start_run_ignores_client_analysis_mode_for_ordinary_thread`、`test_run_metadata_cannot_create_analysis_mode_on_new_thread`；`test_create_thread_analysis_kind_is_server_owned_and_patch_cannot_clear_it`、`test_thread_kind_defaults_to_chat_and_metadata_cannot_create_analysis_mode`、`test_thread_creation_fails_closed_on_corrupt_persisted_kind`、同 kind 幂等/冲突/竞态测试；owner admission 由 `test_stateless_runs_owner_isolation.py::test_stream_cross_user_returns_404` 覆盖；Analytics API authentication 有 `test_analytics_api.py::test_unauthenticated_requests_are_rejected` | 普通客户端上下文不能升级；显式坏标记、读取失败、未认证/default identity、foreign owner、services 缺失/错绑、writer 签发失败都在 Agent 构造/执行前拒绝。owner 与未认证测试是共享 Gateway/API gate 的边界测试，不是多真实主体分析 E2E。缺键遵循 marker-as-kind 契约：legacy chat；analysis UI 与重复 `kind=analysis` 创建不会静默升级它。没有独立 kind 列，out-of-band 删除标记的限制如上。 |
| 首条分析消息同一 UUID 先持久预建、SDK create、thread-scoped stream；普通聊天请求不变 | `frontend/tests/e2e/analysis-entry-activation.spec.ts` 覆盖预建/冲突/普通线程/报告导航；普通聊天 `chat-page.tsx` 不设置 analysis kind。6F1 记录了浏览器请求 URL、SDK create、Gateway server record、stream 使用同 UUID，以及服务端持久 marker | 前端先校验 `POST /api/threads kind=analysis` 响应再 stream；失败不流。此前 Playwright 记录分析入口 4/4、普通聊天首次发送 1/1。6F1 是真实 NGINX/认证/SDK/stream 正向样例。不是多用户 E2E。 |
| 旧 chat/缺失标记不得从分析路由降级；普通 chat 语义维持 | `frontend/src/app/workspace/analysis/[thread_id]/page.tsx` 只在 `metadata.analysis_mode === true` 时挂载 `ChatPage(mode="analysis")`；本轮新增 `analysis-route-stopgap.dom.test.tsx::does not mount analysis for a legacy thread without a persisted marker`，既有测试覆盖显式普通线程与 metadata 不可读 | 本轮单测实测 metadata 存在但 marker 缺键时展示非分析线程状态且不挂载运行时；未改普通 chat 行为。服务端把缺键记录视为 chat 是既有持久契约，而不是分析 UI 的 fallback。 |

## 验证记录

### 6F2 原始验收切片（commit `7045fff`）

- UI guard 定点测试：在 `frontend/` 执行 `pnpm rstest run unit/app/analysis-route-stopgap.dom.test.tsx`，退出码 **0**；1 file / **6 passed** / 0 failed / 0 skipped。覆盖 legacy chat 缺标记、显式普通标记、分析标记正确时挂载、线程缺失与元数据读取失败。
- 受影响文件格式检查：`pnpm exec prettier --check tests/unit/app/analysis-route-stopgap.dom.test.tsx` 首次退出码 1，报告新增断言格式需调整；执行 `pnpm exec prettier --write tests/unit/app/analysis-route-stopgap.dom.test.tsx` 后，重新执行 `--check` 退出码 **0**。该提交的 `git diff --check` 退出码 **0**、无空白错误。
- 该切片当时未运行后端测试、`pnpm check`、全量 Playwright、Docker、模型或数据库门禁。历史 `docs/PROGRESS.md` 摘要记录 6E2B2B 定点安全/Gateway 用例 20 passed、线程 kind 3 passed、Rstest 13/13、Playwright 分析入口 4/4 与普通聊天首发 1/1；摘要没有保存这些组的精确命令。
- Query/authorization 等更早的可复用后端记录见 `docs/LOCAL_TRIAL.md`：聚焦 pytest 命令退出码 0，817 passed、0 failed、0 skipped、2 warnings；其覆盖 Query Policy/API/Gateway 子路径，不替代本次 6F2 后端隔离门禁。
- 6F1 的请求、审计、artifact 与限制原始记录见[真实链路彩排](phase-06f1-real-analysis-rehearsal.md)。

### Fix 01 可复现后端安全门禁

以下两条命令均在 `backend/` 的锁定环境运行。按项目既有 Windows 解决方式将 `UV_DEFAULT_INDEX` 指向官方 PyPI；未读取或输出任何私密配置/环境变量值。

1. Gateway、工具集合、持久身份与 owner admission：

   ```powershell
   $env:UV_DEFAULT_INDEX = 'https://pypi.org/simple'
   uv run --locked pytest tests/test_analysis_tool_allowlist.py tests/test_gateway_services.py::test_start_run_rejects_analysis_thread_before_agent_factory tests/test_gateway_services.py::test_start_run_keeps_analysis_closed_without_bound_services_or_real_principal tests/test_gateway_services.py::test_start_run_binds_writer_capability_before_analysis_agent_start tests/test_gateway_services.py::test_analysis_writer_capability_failure_terminalizes_without_starting_graph tests/test_gateway_services.py::test_start_run_fails_closed_on_corrupt_analysis_thread_mode tests/test_gateway_services.py::test_start_run_fails_closed_when_thread_mode_cannot_be_read tests/test_gateway_services.py::test_start_run_ignores_client_analysis_mode_for_ordinary_thread tests/test_gateway_services.py::test_run_metadata_cannot_create_analysis_mode_on_new_thread tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get tests/test_stateless_runs_owner_isolation.py::test_stream_cross_user_returns_404 -q
   ```

   退出码 **0**；**21 passed**、0 failed、0 skipped，33.01 秒。1 条既有 `StarletteDeprecationWarning`：Starlette `TestClient` 与当前 `httpx` 集成将弃用；不是本次测试失败。

2. Report writer capability、固定路径和 owner/thread/run 约束：

   ```powershell
   $env:UV_DEFAULT_INDEX = 'https://pypi.org/simple'
   uv run --locked pytest tests/test_analytics_agent_reports.py tests/test_analysis_report_writer_files.py -q
   ```

   退出码 **0**；**59 passed**、0 failed、1 skipped，8.54 秒。1 条同类既有 `StarletteDeprecationWarning`。唯一 skip 是 `test_report_writer_rejects_existing_symlink_without_touching_target`：当前 Windows 环境不能创建 symlink；同文件的“打开前拒绝现存 symlink”测试仍执行并通过。

两组共 **80 passed、0 failed、1 skipped、2 warnings**。本门禁仅使用合成测试输入，不连接真实 MCP、模型、业务数据库或容器；不重复 6F1/前端门禁。测试代码与安全运行路径未改，仅补可复现命令及输出记录。

## 剩余限制

- 不证明任意第三方 operator MCP 的 SQL 安全或审计；其明确不在平台 Query Policy 保证范围。
- 不把单一真实 PostgreSQL/模型彩排外推为 MySQL、AS-01 多主体、AS-10 通用报告校验、AS-15 默认 Compose 或 AS-01..AS-15 整体验收。
- 不提供独立 `kind` 数据库列；直接篡改数据库删除 `analysis_mode` 后的历史语义不可恢复。已验证的应用路径不能由普通 metadata/PATCH/client context 清除标记，也不能把无标记 legacy chat 从分析入口提升。
- 没有单独通过真实 MCP task server 向 analysis thread 投递通知；源码调用图确认该通知复用 Gateway `start_run` 和同一分析装配链。

本证据支持 AS-14 按已批准边界验收；Phase 6 与发布整体仍未完成，提交后待 GPT 独立复验。
