# Phase 6E3A Fix 01：流式工具身份不明确时只遮盖外发副本

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max）。先读全局、根目录和相关 backend `AGENTS.md`，以及 `docs/prompts/phase-06e3a-analytics-output-projection.md`。基线为已提交的 `eb4aea8`，先核对 HEAD 和干净工作树。本修复不解除 `analysis_mode_unavailable`，不启动后续阶段。

## 已确认的问题

独立只读审查发现 `AnalyticsToolCallChunkProjector` 在每个普通 run 的 `messages` 流中也被调用。`serialization.py` 中「参数块先于名称」「缺少稳定 chunk 身份」「曾是 Analytics 名称前缀而后变为其他工具」会抛 `AnalyticsToolCallCorrelationError`，从而中止普通聊天。精确名称 `query_business_data` 又被 `_name_state` 过早视为不可变，后续名称增量可能形成 `query_business_data_export` 等非 Analytics 工具，造成误遮盖。不能以“受控分析模式目前禁用”为由忽略普通聊天回归；Analytics 工具在普通 Lead 工具表中仍可能可用。

## 修复边界

1. 对外发/持久化副本继续实行最小必要的保守投影：身份未知或仍可能是 `query_business_data` 的**参数增量**不得原样外发；可仅遮盖该模糊块的 `args` 与同一块中可归因的派生 `tool_calls` / `invalid_tool_calls` 参数。不得修改内部模型消息、实际工具调用、非参数内容或已明确为其他工具的正常参数。
2. 模糊增量不应因为身份缺失而中止整个 run。对于缺 message ID/index、参数先于名称、多工具解析壳等情形，在无法安全关联时遮盖外发副本中存在泄露可能的参数并继续；不得靠无条件清空所有工具参数来过关。若某形状无法既保持运行又守住 SQL 不外发，停止并报告确切形状，不提交假修复。
3. 名称状态允许从 `query_business_data` 继续收到后缀并确定为其他工具；对前缀/精确名仍可能继续增长的早期参数，可以暂时遮盖，已明确为其他工具后的后续参数须保留。不得让后缀工具继续被误认作 Analytics。无需为已发出的保守遮盖做补发或增加缓冲基础设施。
4. 完整 `AIMessage.tool_calls`、ToolMessage、RunJournal、历史读取、AS-13 边界继续保持上一提交的安全行为；不要借此扩大 AS-13 对任意文本/artifact/第三方 tracing 的承诺。

## 证据与门禁

用**合成 SQL 与结果哨兵**增加最少的永久回归：普通 run 在无名称参数块、缺稳定身份及名称分叉时继续并完成；外发 SSE/历史副本不含哨兵；内部消息不变；已明确的非 Analytics 工具参数仍可见。至少包含 `query_business_data_export` 的前缀碰撞和一个真实 worker 流入口，不只测私有函数。先跑相关定点测试；若发现回归，修复后重跑受影响文件即可。Ruff check/format 与 `git diff --check` 检查改动范围。不要机械重跑已有 240 项、大套件、Docker 或 E2E；只有改动确实影响对应契约时才扩大。

只做一个独立 Fix 提交，不 amend `eb4aea8`。记录 commit/parent、文件范围、门禁、仍有的局限；`docs/PROGRESS.md` 保持 Phase 6E3A 待 GPT 复验，不宣称 AS-13 最终验收。工作树干净后停下，等 GPT 审查。
