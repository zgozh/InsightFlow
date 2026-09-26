# Phase 6F3E8：报告 writer 未调用的只读归因

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e7-fix-02-existing-admin-role-contract.md`。本轮只分析该唯一 run `fbd321b7-6724-4c2a-880b-6953ffffe45a`，不重发模型、不改产品、不重建固定验收栈。

## 已证事实

固定栈中的受控 analysis run 成功结束；同 run 的 AI tool_calls 为 catalog 1 次、query 6 次、writer 0 次；query 仅 1 次返回 evidence，其他出现策略拒绝类稳定码；本 run 报告索引匹配 0。原用户请求包含“若查询证据足以支持结论，请生成并留存简短 Markdown 分析报告”。代码 `backend/packages/harness/deerflow/tools/tools.py::_ANALYSIS_TOOL_SOURCES` 固定包含 writer，但尚未证明该 run 最终实际暴露给模型的工具集合。

## 最小只读核对（V0）

1. 复用现存 owner DPAPI 凭据与 `insightflow-acceptance-local`，只对既有 run 调 `GET /api/threads/{thread_id}/runs/{run_id}/messages`；不输出或保存模型正文、SQL、结果行。只在进程内查看**最后一条 AI 回复**，报告一个封闭分类：`claims_report_saved`、`states_insufficient_evidence`、`states_no_report`、`other`；不可从文本安全判定就记 `unknown`。同时只报告成功 evidence 的 `row_count>0` 布尔值、是否 truncated、结果列名是否包含非预期敏感列的布尔值（不输出列名）。
2. 只读核对受控模式的工具组装与本次有效配置：`get_available_tools(analysis_mode=True)` 经授权过滤后 writer 是否在最终模型工具名集合。可用现存配置和短生命周期本地/容器内探针，只输出三个固定工具名的可见性布尔值；不得读取/打印私有配置值、工具参数、模型响应或自由文本。若无法证明**该 run** 的实际模型工具集合，区分“当前组装代码可见”与“当次可见未知”。不要为此增加生产日志或表。
3. 查阅当次用户请求的条件句与 Lead 分析模式指引，结合 tool_calls/evidence 分类，给出已证实、可能、未知各项；不要把 writer=0 直接归因于模型能力，也不要把一次成功 evidence 直接判定为足以支撑整份报告。

## 边界与交付

仅写 `.reviews/phase-06f3e8-writer-noninvocation-audit.md`，列最短证据路径和**一个**下一步建议（例如更明确的一次性请求、定点 prompt 修正，或暴露工具的真实缺陷），说明为何选择它。不跑全量测试、Docker 重建、模型、永久代码改动；验收栈及当前 DPAPI 凭据保留，旧 6F1 不动。完成后停在主会话复验。
