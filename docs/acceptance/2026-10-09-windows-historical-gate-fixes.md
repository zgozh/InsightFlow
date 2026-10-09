# Windows 历史门禁测试修正

## 修复与验证

子进程采集明确使用 UTF-8，并在隔离环境中保留 Windows `SYSTEMROOT`、`WINDIR`、`COMSPEC`、`TEMP`、`TMP`；扩展回滚测试选择平台对应的 venv Python；静态 JSON 路径断言使用 POSIX 规范。Studio 子进程启用 UTF-8，失败日志以替换策略读取；assistant POST/PATCH 后在首个 server context 内等待 ops 文件 mtime 反映最后一次更新，最多 15 秒，然后保留原文件存在断言及第二次启动后的 ID/版本检查。Sandbox 测试 mock 实际平台 runner，仍验证 timeout 标记和映射路径；Parallel 测试清理代理变量并将 loopback 加入大小写两种 NO_PROXY；MCP retry 测试按至少 5 秒检查边界。

先前 14 个 B4 候选在第一轮修复后为 **7 failed、7 passed、8 warnings，exit 1，94.23 秒**。按剩余失败节点修复后，仅定点重跑这 7 项：**7 passed、6 warnings，exit 0，72.26 秒**。八个受影响测试文件 `ruff check` 通过，`ruff format --check` 显示 8 个文件均已格式化。未重跑全部 14 项；其中 Parallel `[True]` 在前一轮通过，但共享代理 fixture 的最终变更后没有重跑，因此不宣称完整 14 项最终全绿。

本轮通过的七个 node IDs：`tests/test_client_live_policy.py::test_config_alone_does_not_enable_live_collection`、`tests/test_client_live_policy.py::test_explicit_opt_in_collects_live_tests`、`tests/test_client_live_policy.py::test_ci_blocks_live_collection_even_with_opt_in`、`tests/test_client_live_policy.py::test_opt_in_without_config_reports_missing_config`、`tests/test_langgraph_studio_routes.py::test_persisted_legacy_assistants_survive_cross_version_restart`、`tests/test_mcp_task_service.py::test_run_once_releases_claim_when_driver_is_missing_or_fails`、`tests/test_parallel_mcp_user_agent.py::test_parallel_example_user_agent_reaches_tool_requests[False]`。

B5 精确 13 项 node IDs / 原始日志仍缺，本轮不是 B5 精确复核；Linux CI 未运行。未改生产代码，未 build、部署、调用模型或 stage。
