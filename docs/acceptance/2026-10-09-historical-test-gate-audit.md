# 历史后端失败门禁定点复核

## 结论

`docs/PROGRESS.md:36` 记录 Phase 5B5 为 13 failed / 14260 passed / 295 skipped / 3 deselected，并说明 13 项属于 B4 的 14 项残差子集；仓库现有记录中未找到 B5 的精确 13 个 node IDs 或原始完整日志。因此本次按 Root 授权，只运行 B4 记录的 14 个候选项；结果不能冒称为 B5 精确 13 项复核。

在 `backend/` 定点执行以下 14 个 B4 候选 node IDs。退出码 1，47.12 秒：12 failed、2 passed、4 warnings。完整输出：[b4-residual-14-targeted-current.log](../../.reviews/final-postgres-runtime-20261008/final-review/historical-gates/b4-residual-14-targeted-current.log)。未改产品代码或测试，也未运行完整 suite 或触发 CI。

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_client_live_policy.py::test_config_alone_does_not_enable_live_collection `
  tests/test_client_live_policy.py::test_explicit_opt_in_collects_live_tests `
  tests/test_client_live_policy.py::test_ci_blocks_live_collection_even_with_opt_in `
  tests/test_client_live_policy.py::test_opt_in_without_config_reports_missing_config `
  tests/test_detect_blocking_io_static.py::test_json_output_uses_concise_review_record_schema `
  tests/test_extension_manager.py::test_failed_entry_point_discovery_rolls_back_dependency_and_lock `
  tests/test_extension_manager.py::test_install_uses_one_controlled_uv_project_and_deferred_sync `
  tests/test_extension_manager.py::test_remove_rolls_back_package_lock_config_source_and_environment_when_config_write_fails `
  tests/test_langgraph_studio_routes.py::test_persisted_legacy_assistants_survive_cross_version_restart `
  tests/test_local_sandbox_command_timeout.py::test_timeout_output_carries_authoritative_failure_marker `
  tests/test_local_sandbox_provider_mounts.py::TestMultipleMounts::test_execute_command_path_replacement `
  tests/test_mcp_task_service.py::test_run_once_releases_claim_when_driver_is_missing_or_fails `
  'tests/test_parallel_mcp_user_agent.py::test_parallel_example_user_agent_reaches_tool_requests[False]' `
  'tests/test_parallel_mcp_user_agent.py::test_parallel_example_user_agent_reaches_tool_requests[True]' `
  -q
```

| 当前失败 node ID | 实际签名 | 最小建议 / 分类 |
| --- | --- | --- |
| `tests/test_client_live_policy.py::test_config_alone_does_not_enable_live_collection`<br>`tests/test_client_live_policy.py::test_explicit_opt_in_collects_live_tests`<br>`tests/test_client_live_policy.py::test_ci_blocks_live_collection_even_with_opt_in`<br>`tests/test_client_live_policy.py::test_opt_in_without_config_reports_missing_config` | Windows 子进程读取 UTF-8 输出时按本机 GBK 解码，reader thread 抛 `UnicodeDecodeError`；随后 `stdout + stderr` 因 `stderr is None` 抛 `TypeError`，断言未执行。 | 测试 subprocess 显式使用 `encoding="utf-8"`（必要时显式错误策略）。Windows 测试辅助代码/编码兼容问题；未证明策略实现失败。 |
| `tests/test_detect_blocking_io_static.py::test_json_output_uses_concise_review_record_schema` | JSON 实际路径使用正斜杠（实现 `as_posix()`）；断言使用 Windows 原生反斜杠路径。 | 将期望值按 JSON 路径契约规范化为 `source_file.as_posix()`。Windows 路径断言不一致。 |
| `tests/test_extension_manager.py::test_failed_entry_point_discovery_rolls_back_dependency_and_lock`<br>`tests/test_extension_manager.py::test_remove_rolls_back_package_lock_config_source_and_environment_when_config_write_fails` | 回滚断言尝试启动临时环境 `.venv/bin/python`，Windows 上文件不存在，报 `FileNotFoundError [WinError 2]`。 | 按平台选 `.venv/Scripts/python.exe` 或 `.venv/bin/python`。环境回滚断言没有运行到。 |
| `tests/test_langgraph_studio_routes.py::test_persisted_legacy_assistants_survive_cross_version_restart` | Studio 子进程未通过启动检查；失败诊断读取日志时，`read_text(encoding="utf-8")` 又遇到 `UnicodeDecodeError`，掩盖了启动失败原因。 | 先保证子进程日志为 UTF-8，或诊断读取使用可替换错误策略；再判断真实启动/路由契约。当前证据不足以判为产品回归或过时功能契约。 |
| `tests/test_local_sandbox_command_timeout.py::test_timeout_output_carries_authoritative_failure_marker` | Windows 分支实际调用 `_run_windows_command`，测试只 patch `_run_posix_command`，于是尝试启动 `/bin/sh` 并报 `FileNotFoundError [WinError 2]`。 | 像相邻跨平台用例一样 patch 当前平台的 runner，或明确限定 POSIX。Windows 测试平台选择问题。 |
| `tests/test_local_sandbox_provider_mounts.py::TestMultipleMounts::test_execute_command_path_replacement` | 测试用 POSIX `cat`、`/bin/sh` 命令；Windows runner 仍尝试启动 `/bin/sh`，报 `FileNotFoundError [WinError 2]`。 | 为 Windows 写等价命令/断言，或将 POSIX shell 用例限定为 POSIX。测试平台假设问题。 |
| `tests/test_parallel_mcp_user_agent.py::test_parallel_example_user_agent_reaches_tool_requests[False]`<br>`tests/test_parallel_mcp_user_agent.py::test_parallel_example_user_agent_reaches_tool_requests[True]` | `extensions_config.example.json` 为 UTF-8 文件；无参数 `Path.read_text()` 使用 Windows GBK 并报 `UnicodeDecodeError`。 | 显式 `read_text(encoding="utf-8")`。Windows 默认编码兼容问题。 |

本次通过的两项是 `tests/test_extension_manager.py::test_install_uses_one_controlled_uv_project_and_deferred_sync` 和 `tests/test_mcp_task_service.py::test_run_once_releases_claim_when_driver_is_missing_or_fails`。当前失败签名主要是 Windows 路径、shell 或默认编码差异；这些结果不能证明 Ubuntu CI 上对应测试失败，也不能代替 Linux CI 结果。

## CI 适用性与未闭合项

`.github/workflows/backend-unit-tests.yml` 在推送到 `main` 或 `2.0.x-dev`，以及 PR 的 `opened`、`synchronize`、`reopened`、`ready_for_review` 事件时触发；无路径过滤。非 draft PR 运行默认依赖收集任务和 Ubuntu 3.12 上的四分片后端测试（含 PostgreSQL extra）。本次没有触发或观察该 workflow，也没有 branch protection 状态证据。

仍缺：B5 精确 13 项 node IDs/原始日志，以及对应当前 Linux CI 结果。故不能据本次 Windows 定点结果宣称历史 13 项已消失、B5 精确复核完成或当前 CI 全绿。没有证据表明这些失败属于已删除功能的过时契约；Studio 测试被日志解码错误遮蔽，应先修诊断后再判断。
