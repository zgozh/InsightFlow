# Phase 6F3：受控分析 Reviewer 链路可行性调查（只读）

你是 InsightFlow 的实施调查员。本轮只调查，不改生产代码、测试、架构承诺或验收状态，不启动 Docker、模型调用或全量门禁。先核对 `main` 工作树及 6F2 的最新提交；如已有他人改动，保持原状并报告。固定上游 tag `upstream-v2.1.0-rc0` 不得改动。

## 问题与现行边界

`docs/acceptance/acceptance-scenarios.md` 的 AS-07/08/09/10 要求 Analyst、Reviewer、报告和可追溯事件；`docs/acceptance/phase-06d-contract-reconciliation.md` 已说明其中部分仍与实现不符。6F1 已证明 Lead 经真实模型、受控查询和 writer 生成可读取报告，但**没有 Reviewer**。6F2 已验收的 AS-14 边界要求 analysis run 在模型可见和最终 dispatch 两层都只能得到 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`；普通 `task`、文件、命令、MCP 等不得借 Reviewer 名义回到受控运行。`skills/public/business-analysis/SKILL.md` 的旧 `task`/sandbox/`present_files` 流程也不能当成当前可用能力。

请只读核实调用链、数据与能力边界，比较以下三条最小方案，不预设哪条成立：

1. 在受控分析内部增加独立、无工具的 Reviewer 模型步骤，输入仅为有界查询结果/evidence 与待审报告草稿；明确其是否能满足 AS-07/08/10 的字面角色要求，以及失败/取消/最多一次修订的事件语义。
2. 使用现有 subagent runtime，但 Reviewer 只能获得固定、可证明的最小能力且不得再委派、查询、读任意文件、调用普通 MCP；检查这是否会破坏 AS-14 的“双层固定工具集”承诺，以及所需的精确 seam。
3. 将 V1 产品契约明确收窄为“单 Lead、证据锚定的报告”，把 Reviewer 留到后续版本；说明这会改变哪些已承诺的 AS-07/08/10 条款，不能自行修改验收文档。

重点找出：实际报告正文及 evidence 在哪个边界可被 Reviewer 读取；模型草稿和 artifact 正文如何避免被误当可信审计；Reviewer 通过/拒绝能否在**写入报告和发布索引之前**阻断；AS-13 对结构化元数据的禁敏边界如何维持；AS-09 现有 SSE/trace 是否已有适合的事件或需新契约；超时、取消、幂等、一次修订如何复用现有机制。对每个关键结论给出文件、符号和相关测试 ID，而非只引用文档。

## 输出与门禁

在忽略的 `.reviews/phase-06f3-reviewer-feasibility.md` 写简短中文报告：现状调用图、三方案的可行/不可行点与预估改动文件、推荐方案及其不可回避的产品裁决、最小实施切片与相应 V1/V2/V3 定点验收建议、仍未知的事实。不要打印或写入 `.env`、密钥、真实 SQL、结果行。调查只需 V0：阅读相关源码、报告 readback、`git status --short`；不为“增加信心”运行测试。若发现需实际试验才能判断的关键事实，先列出最窄实验并停止，不自行实施。

完成后向 GPT 返回报告路径、精要结论和工作树状态，停在 GPT 设计审查；不得启动 6F3 实现、Phase 5C 或发布验收。中文优先，避免重读无关仓库历史。
