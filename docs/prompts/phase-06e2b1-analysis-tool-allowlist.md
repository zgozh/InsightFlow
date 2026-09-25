# Phase 6E2B1：受控分析工具正向白名单（暂不开放运行）

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max）。先读全局、仓库根及直接相关模块 `AGENTS.md`、`.reviews/phase-06e2-trusted-analysis-mode-design-report.md`、`docs/prompts/phase-06e2b-controlled-analysis-runtime.md`。后者的“一片完成并启用”方案已在可行性门禁被暂停：现有虚拟文件工具未能证明路径隔离，前端旧 `ChatPage` 会退化到普通聊天。保护性前端停用页和 6E2A 运行拒绝必须保留。当前基线应是 6E3A Fix 01 已复验后的干净 main；先核对。固定上游 tag/tree、依赖、lockfile 不动。不得读取或输出真实 `.env`、`config.yaml`、`os.environ` 值。

## 本片唯一目标

建立可独立验证的**受信 analysis 模式工具边界**，但**不解除** `analysis_mode_unavailable`，不启用分析入口，不宣称 AS-14 完整验收。用户已批准的产品边界是：平台托管 Analytics 数据源经过 Query Policy；普通聊天保留操作者赋权的第三方 MCP，但不承诺其受同一 SQL 策略；受控分析将来开放时必须隔离第三方普通/durable MCP 和其他数据旁路。

1. 从 6E2A 的服务端线程标记与运行上下文取得 analysis 模式，不信任客户端 `context`、`configurable`、URL、模型文本或工具自报。若 Harness 内部目前只能接收到可伪造值，先定位最小可信传递接缝；无法证明时停下报告，不把仅靠请求字段的过滤当安全实现。
2. 为 analysis 模式构造**固定来源的正向工具集合**，最小集合只含平台 Analytics 的 `inspect_business_catalog`、`query_business_data`；必要的框架内部非模型工具可保留并说明。暂不暴露 `publish_analysis_report`（它只登记路径，尚无安全写入闭环）、普通/durable MCP、命令/bash/AIO shell、任意读写文件、dynamic plugin、`tool_search`、`task`/子 Agent 委派或未知新工具。普通聊天原有工具与 MCP 行为保持不变。不要靠名称 denylist 或仅隐藏模型 schema：模型可见列表与最终 ToolNode/dispatch 都必须从相同的允许集合导出；分析模式热更新、延迟工具发现、历史伪造 tool_call 不能绕过。若跨层执行门禁需要大量通用 Harness 改造，先报告最小可行接缝，不做半成品。
3. 仅在直接相关的 Harness/Gateway 接缝增量实现。现有 `analysis_mode_unavailable` 检查须继续先于 Agent/tool 构造，前端分析停用页保持。可为白名单在隔离的构图/执行测试中注入合成受信标记，不可把这些测试表述为真实分析运行已经开放。
4. AS-14 文档只可更新为准确的**目标与已实现分界**，不提前写成完整隔离已上线。`docs/PROGRESS.md` 记下 6E3A+Fix 01 已通过定点复验、本片待 GPT 复验、分析功能仍停用。

## 验证与停止

这是安全边界切片，按比例工程政策做 V3 的**定点**验证：合成配置下证明 analysis 工具可见与最终可执行集完全一致且精确为允许集合；普通聊天仍有原 MCP；伪造请求字段不能升级；热更新/延迟发现/历史 tool_call 不恢复被禁工具。以最少有持久价值的测试覆盖实际装配与执行，不仅测过滤函数。直接受影响的 pytest、Ruff、`git diff --check` 即可；无须机械跑 14k 全套、Docker、Playwright、真实模型/数据库。若缺少上述任一证明，保留运行拒绝，明确阻塞点，不提交宣称完成的实现。

成功则一个独立提交，工作树干净，报告 commit/parent、变更范围、真实门禁结果、白名单来源与执行处证据、未完成的安全 artifact 写入/前端启用项；停在 GPT 复验，不启动后续阶段。
