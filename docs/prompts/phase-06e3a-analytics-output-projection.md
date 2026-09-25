# Phase 6E3A：Analytics 运行输出的安全投影

你是 InsightFlow 的实施模型 `gpt-6-luna`（max），GPT 负责架构审查。先读全局/根与直接相关模块 `AGENTS.md`、`.reviews/phase-06e3-as13-output-boundary-report.md`、AS-13 两份验收文档及本文件。预期起点为本提示词提交后的干净 `main`；不符即停。此切片只关闭**平台对外/持久化运行事件中的 Analytics SQL 与结果行泄露**，不解除 `analysis_mode_unavailable`、不启动完整 6E2B，也不宣称 AS-13/Phase 6 最终验收。用户对 AS-13 任意文本/artifact 范围的裁决正在等待，未批准前不得改写发布承诺。

## 目标边界

`query_business_data` 的原始 SQL 必须留在模型调用→Query Policy 的内部执行路径；行值也必须留在模型内部推理所需的 ToolMessage。**只对外发与持久化的副本做投影**：Gateway SSE、运行事件 journal/查询、thread/run state/history DTO、可读的 trace/receipt 不得从该工具的结构化调用/结果字段携带 SQL 原文、plan token、原始 `columns`/`rows`。保留稳定决定码、必要的安全 evidence、计数与状态；不要把工具结果清空到无法诊断，也不要改变非 Analytics 工具和普通聊天的既有合同。模型最终回复、任意用户文本与 artifact 正文不在本切片的结构化字段保证中，不能据此声称全文内容安全。HTTP `/api/analytics/query-plans` 对认证调用者有意返回一次性 plan token，属于执行接口，不要误删；Analytics 审计既有 hash/metadata 也不改。

按真实调用链选择最少的投影接缝：重点检查 `runtime/serialization.py`、`runs/worker.py::_publish_stream_item`、`RunJournal.on_llm_end`/工具结果持久化、Gateway events/state/history 读取。对于 SSE 增量 `AIMessageChunk`、完整 `AIMessage.tool_calls`、`ToolMessage` 及历史事件都要有可验证的工具身份关联；若 chunk 阶段无法可靠关联，采用只在受控分析运行中生效的保守投影或明确停止，不使用全局清空工具参数的办法。序列化副本投影不得原地修改传回模型/图状态的消息。历史已有含敏感字段的事件需在读取端同样投影；不能仅保护新写入。

先以**合成** SQL/结果哨兵做高价值回归：模型内部参数与 ToolMessage 仍完整，外发 SSE 和持久/历史 event/state 全无哨兵，安全 evidence/decision 保留，非 Analytics 工具不变；覆盖增量 chunk 的真实形状或止损并报告。按全局比例工程政策这是安全敏感 V3，但仅运行能证明相关序列化、journal、Gateway endpoint 的定点测试与改动文件静态检查；无须机械跑 14k 全套、Docker、Playwright、真实模型/数据库。不得读取/输出真实 `.env`、`config.yaml`、`os.environ` 或真实业务行；失败断言也不可展开它们。

若无法区分内部与外发副本、跨 chunk/历史无法可靠关联工具、会破坏既有非 Analytics 行为，或任一既有输出路径仍漏 SQL/行值，则保留现有代码并给出精确阻塞，不提交“只遮一条路径”的假修复。成功时一个独立实现提交；`docs/PROGRESS.md` 只记录本切片待 GPT 复验及剩余 AS-13 未验收项。报告 commit/parent、文件范围、真实门禁结果、各输出路径的证据和未验证项；停在 GPT 复验，不启动 5C 或后续阶段。
