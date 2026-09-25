# Phase 6E2B2A Fix 01：结构化事件中的敏感工具名前缀

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max）。先读全局/根/相关 backend `AGENTS.md`、`docs/prompts/phase-06e2b2a-safe-report-writer.md`，核对当前干净 main；实施基线为 `adcaa821185189a582f08d79da9bcd6c96a2fafb`，本提示词提交可能位于其后。本轮只修下面已确认的投影漏洞，独立 Fix 提交，不 amend 原提交，不解除 `analysis_mode_unavailable`。

独立只读审查的最小复现：`AIMessage(tool_calls=[{name:"write_analysis_", args:{markdown:"BODY_SENTINEL"}}])` 经 `project_analytics_structured_value` 后仍含全文。`serialization.py::_is_analytics_call` 只识别精确名称/已知 ID；不完整名称绕过 `_project_analytics_message`，而该结构化投影用于 RunJournal 持久事件及历史/checkpoint 读取。模型产生未完成或错误的工具名时，报告正文因此泄入平台事件副本；对 `query_business_data` 的同类前缀也须保持原 SQL 安全边界。

## 精确修复

1. 在**外发/持久化副本**中，把仍可能发展为 `write_analysis_report` 或 `query_business_data` 的非空工具名前缀视作敏感候选，对该调用的参数保守遮盖。完整精确名称继续用已有安全投影；完整且已明确为其他工具的名称（例如 `query_business_data_export`、`write_analysis_report_preview`）不得继续误认。`tool_calls`、`invalid_tool_calls`、`tool_call_chunks`、`additional_kwargs` 原始调用都按已有结构化遍历覆盖；同 ID 的工具结果关联不得因候选名泄露正文。若遇没有可靠名称/ID但携带参数的解析壳，只遮盖该模糊调用的参数，不中止普通 run、不过度清空其他已明确工具的参数。
2. 不改变模型内部消息和真实工具执行；不改 Gateway capability、文件 create-only/索引、白名单、前端或依赖。普通聊天的已明确非 Analytics 工具参数仍可见。对已明确为其他工具的后续名称，不因早期前缀而永久误遮盖。
3. 用合成 `BODY_SENTINEL` 和 SQL 哨兵加最少回归：先让复现 RED，再证实结构化 projector、RunJournal 持久事件、历史读取（含 invalid/raw 形状）均无哨兵；内部消息不变；非敏感完整名称与前缀分叉后参数保留。只跑直接受影响的序列化/journal/history 测试、Ruff 和 `git diff --check`，不重跑已有 407 项、全仓、Docker 或 E2E，除非补丁实际影响更宽边界。

若增量/结构化投影无法同时保住“敏感候选不外发”和“普通流不异常中止”，保留分析运行拒绝并报告确切阻塞，不提交假修复。成功后一个独立提交、工作树干净，`docs/PROGRESS.md` 仍写本切片待 GPT 复验，AS-13/14 与分析完整闭环仍未完成。报告 commit/parent、文件范围、真实门禁及残余限制，停在 GPT 复验。
