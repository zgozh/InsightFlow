# Analysis 内部角色与可验证报告接线验收

## 结果

本切片完成 AS07/08/10 的服务端调用链接线：Gateway 为已认证 analysis run 签发同 principal/thread/run 的
roles capability；Lead 将最终模型绑定给 roles 与 Reviewer，SDK 不支持安全隔离时 startup 失败。Worker 将能力
仅注入运行时并在结束时关闭、清除引用。analysis query 由 SQL Analyst 精化后仍经过既有授权 plan/execute，
串行覆盖查询和 durable evidence 写入，每 run 最多开始 4 次；Gateway 另将 analysis 的 `recursion_limit`
固定为 16，覆盖客户端高值，普通聊天沿用现有配置。

报告保持三个模型可见参数不变。服务端把标题和 markdown 当作非可信请求描述，读取 exact-scope evidence 和
一次 active metric 快照，依次执行数值声明验证、固定模板布局与独立 Reviewer，最后才写文件和索引。草稿标题、
正文和未验证数字不进入发布物；报告附公开指标目录快照，空目录明确标注缺少登记口径。

接线前，Gateway 已把普通 run 的 `recursion_limit` 按 AppConfig 默认值与上限夹紧（默认 100、上限默认 1000），
但没有 analysis 专用服务端步数上限；Lead 仅记录解析后的 recursion_limit。因此增加固定 16 的 analysis 上限。

## 定点验证

首批定点 pytest 覆盖工具 schema、query refine/plan/execute、角色作用域、4 次预算、并行串行化、报告重建与
失败门禁、MetricService、Gateway admission、worker 清理和 Lead 绑定。该批最初报告 26 passed、2 failed；两项
失败来自测试断言：ChatOpenAI 没有 `tools/functions` 属性，空目录正文中的 evidence hash 恰好含子串 `123`。
修正为检查实际 invocation kwargs 与草稿数字 `123%` 后，单独重跑两项均通过。后续变更仅为 Ruff 导入排序和
格式化；未改变运行逻辑。

首批命令在 `backend/` 执行：

```powershell
uv --no-config run --default-index https://pypi.org/simple --locked --no-sync python -m pytest -q tests/test_analytics_agent_tools.py::test_the_query_tool_takes_exactly_a_datasource_id_and_sql tests/test_analytics_agent_tools.py::test_the_catalog_tool_takes_no_identity_arguments tests/test_analytics_agent_tools.py::test_analysis_query_calls_the_independent_sql_role_before_one_plan_and_execution tests/test_analytics_agent_tools.py::test_analysis_role_scope_and_catalog_visibility_fail_before_model_or_plan tests/test_analytics_agent_tools.py::test_analysis_query_budget_rejects_before_role_or_plan tests/test_analytics_agent_tools.py::test_parallel_analysis_queries_hold_the_run_lock_through_planning tests/test_analytics_agent_reports.py::test_the_model_visible_schema_is_exactly_three_fields tests/test_analytics_agent_reports.py::test_report_writer_schema_has_only_content_and_evidence_fields tests/test_analytics_agent_reports.py::test_report_writer_writes_then_indexes_and_returns_only_a_safe_receipt tests/test_analytics_agent_reports.py::test_report_with_empty_metric_directory_states_the_missing_definition_limit tests/test_analytics_agent_reports.py::test_report_writer_reviewer_rejection_or_invalid_response_has_zero_writes tests/test_analytics_agent_reports.py::test_report_writer_rejects_oversized_review_input_without_model_or_writes tests/test_analytics_agent_roles.py::test_query_scope_serializes_work_and_caps_started_attempts_even_after_cancellation tests/test_analytics_agent_roles.py::test_query_scope_rechecks_identity_and_close_after_waiting_for_lock tests/test_analytics_metric_service.py tests/test_gateway_services.py::test_start_run_binds_writer_capability_before_analysis_agent_start tests/test_gateway_services.py::test_analysis_run_capability_failure_terminalizes_without_starting_graph[roles] tests/test_run_worker_delivery.py::test_runtime_context_carries_the_gateway_collector_by_identity_without_checkpoint_config_or_cleanup_leak tests/test_lead_agent_model_resolution.py::test_analysis_lead_binding_failure_stops_graph_assembly_with_only_safe_run_identity
```

修正后的两个节点命令与结果：

```powershell
uv --no-config run --default-index https://pypi.org/simple --locked --no-sync python -m pytest -q tests/test_analytics_agent_tools.py::test_analysis_query_calls_the_independent_sql_role_before_one_plan_and_execution tests/test_analytics_agent_reports.py::test_report_with_empty_metric_directory_states_the_missing_definition_limit
# 2 passed
uv --no-config run --default-index https://pypi.org/simple --locked --no-sync python -m pytest -q tests/test_analytics_agent_reports.py::test_report_writer_rejects_an_unverified_numeric_claim_before_review_or_write
# 1 passed
```

最终 Ruff 检查和格式检查均通过：`ruff check` 输出 `All checks passed!`，`ruff format --check` 输出 `16 files already formatted`。
检查文件为 `app/analytics/agent/{roles.py,tools.py,reports.py}`、`app/analytics/application/metric_service.py`、
`app/gateway/services.py`、`packages/harness/deerflow/constants.py`、`packages/harness/deerflow/runtime/runs/worker.py`、
`packages/harness/deerflow/agents/lead_agent/agent.py`，以及对应 8 个测试文件。
受影响文件的 `git diff --check` 通过；`uv.lock` 未修改。

没有运行完整后端测试、构建或真实 provider 验收。该结果验证本地离线双模型的受控调用链，不代表 AS07/08/10
真实业务与 provider 验收已通过；后续里程碑统一构建和真实验收。
