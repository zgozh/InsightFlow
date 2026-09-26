# Phase 6F2 Fix 01：补齐 AS-14 后端可复现门禁

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max）。GPT 主审发现的唯一阻断是**验收证据格式**，不是已证实的生产缺陷：`docs/acceptance/acceptance-scenarios.md` 第 9 行规定每个通过场景必须提交执行命令、退出码、关键输出与证据位置；6F2 文档引用旧后端测试 ID/计数，但旧摘要没有保存这些组的精确命令。起点为干净 `main`，包含 6F2 实现 `7045fff` 与文案修复 `5d61af5`，以及本勘误提示词提交。先核对起点与固定上游 tag/tree；不符即停。

## 唯一目标

以**一次相干的聚焦后端门禁**补齐 AS-14 的可复现执行记录，并据真实结果裁定状态。只涉及现有代码/测试和 `docs/acceptance/phase-06f2-as14-boundary-evidence.md`、必要的矩阵/PROGRESS 状态；不修改生产实现，不扩展安全承诺，不新增依赖。现有前端 route guard 6/6 与 6F1 真实模型/PostgreSQL 链证据仍有效，不重跑。

## 具体门禁

在 `backend/` 用已锁定环境运行以下相关测试，**记录实际命令、退出码、passed/failed/skipped 与必要 warning**：

1. `tests/test_analysis_tool_allowlist.py`：模型绑定/最终分发固定集合、MCP 热更新、普通聊天 MCP、不完整/错误来源拒绝。
2. `tests/test_gateway_services.py` 中名称包含 `analysis` 的准入、伪造 context、service/writer 失败关闭测试；以及 `tests/test_runtime_lifecycle_e2e.py::test_analysis_gateway_admission_runs_catalog_query_writer_and_owner_scoped_artifact_get`。
3. `tests/test_analytics_agent_reports.py` 与 `tests/test_analysis_report_writer_files.py` 中报告 writer capability、固定路径和 owner/thread/run 拒绝测试；`tests/test_stateless_runs_owner_isolation.py::test_stream_cross_user_returns_404`。若测试文件/ID 不存在，先只读定位同一契约的现有测试，记录精确替代，不制造占位测试。

可把上述 selector 合在一个 pytest 调用，或最多按 Gateway/Writer 两组调用；不要启动整个 `test_gateway_services.py`、14k 后端全套、Playwright、Docker、真实 MCP server 或模型。使用 `uv run --locked`，先按项目既有官方 PyPI 覆盖避免清华镜像 403；如果锁定 `.venv` 已具备依赖而索引仍阻塞，可用 `uv run --no-sync --locked` 或该 `.venv` 解释器运行同一 selector。不得改 lockfile、打印环境变量值或私密配置。仅在命令环境/代码发生变化或新诊断必要时重跑，不循环重复。

若门禁通过：把实际命令、退出码、计数和证据位置补入 6F2 文档；维持“AS-14 按批准边界验收，待 GPT 复验”的状态。若出现真实失败：按当前改动回归/既有失败/环境失败分类，先报 GPT，不为凑门禁扩大修复；必要时回退 6F2 的“已验收”措辞为“待验收”。AS-14 的边界仍是平台 Analytics Query Policy + 分析三工具隔离 + 普通聊天 operator MCP 独立，不承诺任意第三方 MCP 受平台 SQL 策略保护。marker-as-kind 与 out-of-band 删除限制不变。

这是安全发布边界 V3，但新增验证仅限上列缺失的后端证据。文档更正本身 V0：readback、精确差异与 `git diff --check`；不重跑仍有效的前端、6F1 或其他场景。做一个独立小提交，报告 parent/commit、变更文件、真实命令和结果，工作树干净后停在 GPT 复验，不启动下一阶段。
