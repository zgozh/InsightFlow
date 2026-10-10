# 后端 CI 修复验收记录

日期：2026-10-10

## 原始 CI 失败与修复

GitHub Unit Tests run `38019134148` 在四个分片报告 17 项失败。日志保存在 `.reviews/ci-20261010/`。失败均已定位并修复：

**分片一（2 项）**

- `tests/test_client_live_policy.py::test_documentation_matches_live_test_commands`：贡献指南漏写 opt-in live 测试命令；补充 `make test-live` 说明。
- `tests/test_dockerignore_excludes_runtime_data.py::test_build_inputs_are_still_included[.env.example]`：Docker 构建需要的模板被通用 `.env` 规则排除；精确放行 `.env.example`，真实 `.env` 仍排除。

**分片三（4 项）**

- `tests/test_lead_agent_model_resolution.py::test_empty_allowed_subagents_disables_requested_delegation`：工具装配调用已新增 `analysis_mode` 参数；测试期望补齐 `analysis_mode=False`。
- `tests/test_makefile_shell_script_invocation.py::test_posix_run_shell_script_names_an_interpreter`：测试只识别两个平台分支，实际 Makefile 有 MSYS、原生 Windows、POSIX 三种；改为分别核对三种解释器选择。
- `tests/test_skill_export.py::test_public_skill_real_install_roundtrip[code-documentation]`：测试假设仓库内安装了未随产品分发的公开 Skill；改用合成目录覆盖归档、安装与嵌套文件保真。
- `tests/test_thread_run_query_validation.py::test_read_endpoints_accept_positive_limits_and_hit_store`：owner-scoped store 查询新增 `user_id` 参数；补齐调用断言。

**分片四（5 项）**

- `tests/test_analysis_report_writer_files.py::test_published_report_is_readable_through_owner_scoped_artifact_get`：系统 MIME 数据库可将 Markdown 标为不同的 `text/*` 类型；断言改为文件类别，同时保留内容与跨线程隔离检查。
- `tests/test_analysis_tool_allowlist.py::test_analysis_assembly_adds_dedicated_chinese_work_instructions`：分析能力依赖服务端绑定的 runtime capability；合成 fixture 提供该绑定，不放宽 fail-closed 路径。
- `tests/test_analytics_agent_tools.py::test_analysis_query_emits_persisted_stages_in_phase_order_and_finishes_workflow`：`finish()` 也会持久化终态阶段；断言现同时覆盖实时阶段及终态事件。
- `tests/test_run_events_endpoint.py::test_list_run_events_reads_analysis_stages_from_sqlite_only_for_the_authenticated_owner[asyncio]`：SQLite 查询包含终态阶段；断言包含 emitter 的终态事件并继续核验 owner 隔离。
- `tests/test_skill_export.py::test_public_skill_real_install_roundtrip[skill-creator]`：与 code-documentation 用例相同，依赖缺失的仓库 Skill；改为合成 Skill 树并执行真实安装验证脚本。

**分片二（6 项）**

- `tests/test_analysis_tool_allowlist.py::test_analysis_assembly_uses_server_context_and_one_set_for_model_and_dispatch`：fixture 未提供分析能力绑定，导致 fail-closed 装配不可用；使用合成服务端 runtime capability，继续核对模型与 dispatch 共用工具集。
- `tests/test_configuration_quickstart.py::test_local_trial_explains_the_configuration_layers_in_chinese`：配置说明已迁至 `Install.md`；测试改为验证当前安装指南及配置层次。
- `tests/test_lead_agent_model_resolution.py::test_make_lead_agent_reads_runtime_options_from_context`：同分片二，更新新增的 `analysis_mode=False` 调用契约。
- `tests/test_run_event_stream_contract.py::test_run_end_backend_storage_semantics_match_contract[asyncio]`：内存 run.end 的消息对象需在安全投影后保留类型，JSONL/SQLite 继续使用序列化字符串；`journal.py` 与 serialization 投影按该边界处理，三种后端均断言私有工具参数、结果和附属字段已脱敏。
- `tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get`：旧 fixture 使用已移除的 ephemeral collector，并 patch `_agenerate` 却走入流式 mock transport；改用 durable evidence、可工作的 non-streaming lead fixture 及符合当前 Catalog/数据合同的 fake，保留计划、执行、报告、artifact 与 owner 隔离验证。
- `tests/test_web_fetch_error_shell_meta.py::TestRenderedByRealProducer::test_jina_content_only_classification`：默认 Nginx 404 正文包含版本行，精确前缀断言过窄；按实际错误正文分类，同时保留链路负控。

## 生命周期隐私发现

修正 lifecycle fixture 后，catalog、query 与 report 均成功，事件脱敏哨兵仍发现 `workspace_changes.metadata.workspace_changes.files[].diff` 曾包含 outputs 下 `query-result-*.json` 正文。原因是 recorder 将该产物按普通文本生成 diff，Analytics 工具消息投影不会覆盖 workspace 事件。现复用 workspace 的敏感路径机制：新扫描不读取 query-result 正文；历史事件投影和独立 workspace API 读取均在外发副本中清空敏感 diff、标记 `sensitive`，并清零对应行数及汇总。普通 `report.md` diff 保持可见，持久化记录不被改写。lifecycle 的私有哨兵断言保留。

## 定点验证

- 前一轮本机批次为 14 passed、2 skipped；两个 skip 来自 Windows `requires_safe_capture` 平台条件。按要求未重跑。
- 本轮 workspace/serialization 定点命令（6 passed）：

  ```text
  .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp=./.pytest-ci-workspace-evidence-20261010 tests/test_workspace_changes.py::test_sensitive_workspace_path_covers_common_secret_names tests/test_workspace_changes.py::test_compare_snapshots_hides_sensitive_and_binary_file_content tests/test_workspace_changes.py::test_query_result_snapshot_hides_content_while_report_diff_remains_visible tests/test_workspace_changes.py::test_workspace_changes_response_returns_summary_only_and_full_payload tests/test_workspace_changes.py::test_workspace_changes_response_masks_historical_query_result_diff_without_mutating_event tests/test_serialization.py::test_history_workspace_change_projection_masks_old_query_result_diffs_without_mutating_rows
  ```

- 唯一 lifecycle node：`tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get`，1 passed。
- 对本轮 6 个 Python 文件运行 `ruff check` 与 `ruff format --check`，均通过。
- 初次 Ruff 调用的缓存写入被 workspace sandbox 拒绝；按权限流程批准后检查通过。`git diff --check` 通过。
- 最终覆盖本轮全部 18 个已修改后端 Python 文件（工作目录 `backend/`）：

  ```text
  .\.venv\Scripts\ruff.exe check packages/harness/deerflow/runtime/journal.py packages/harness/deerflow/runtime/serialization.py packages/harness/deerflow/workspace_changes/api.py packages/harness/deerflow/workspace_changes/scanner.py tests/test_analysis_report_writer_files.py tests/test_analysis_tool_allowlist.py tests/test_analytics_agent_tools.py tests/test_configuration_quickstart.py tests/test_lead_agent_model_resolution.py tests/test_makefile_shell_script_invocation.py tests/test_run_event_stream_contract.py tests/test_run_events_endpoint.py tests/test_runtime_lifecycle_e2e.py tests/test_serialization.py tests/test_skill_export.py tests/test_thread_run_query_validation.py tests/test_web_fetch_error_shell_meta.py tests/test_workspace_changes.py
  ```
  输出：`All checks passed!`

  ```text
  .\.venv\Scripts\ruff.exe format --check packages/harness/deerflow/runtime/journal.py packages/harness/deerflow/runtime/serialization.py packages/harness/deerflow/workspace_changes/api.py packages/harness/deerflow/workspace_changes/scanner.py tests/test_analysis_report_writer_files.py tests/test_analysis_tool_allowlist.py tests/test_analytics_agent_tools.py tests/test_configuration_quickstart.py tests/test_lead_agent_model_resolution.py tests/test_makefile_shell_script_invocation.py tests/test_run_event_stream_contract.py tests/test_run_events_endpoint.py tests/test_runtime_lifecycle_e2e.py tests/test_serialization.py tests/test_skill_export.py tests/test_thread_run_query_validation.py tests/test_web_fetch_error_shell_meta.py tests/test_workspace_changes.py
  ```
  输出：`18 files already formatted`。

完整 backend suite、前端检查及 GitHub Linux CI 未在本机重跑；Linux CI 待提交后验证。本次未提交或推送。

## CI 原始日志

- `.reviews/ci-20261010/job-114115994285.txt`：分片一，2 项失败。
- `.reviews/ci-20261010/job-114115994295.txt`：分片二，6 项失败。
- `.reviews/ci-20261010/job-114115994212.txt`：分片三，4 项失败。
- `.reviews/ci-20261010/job-114115994196.txt`：分片四，5 项失败。
