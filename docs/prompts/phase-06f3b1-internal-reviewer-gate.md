# Phase 6F3B1：报告写入前的无工具 Reviewer 门禁

你是 InsightFlow 实施者。基线应为 6F3A `f861e02`，先读 `.reviews/phase-06f3-reviewer-feasibility.md`、`.reviews/phase-06f3a-run-owned-evidence-report.md` 与当前源码。本切片只增加**服务端内部、无工具的 Reviewer 复核**，不恢复 `task`/subagent、MCP、命令或任意文件工具，不新增前端/数据库/配置项，也不宣称 AS-07/08/09/10 整体验收。固定 tag 不变。

## 不变量与最小实现

1. 在 `write_analysis_report` 已完成身份/领域/evidence 校验后、任何文件写入或索引发布前，调用服务端签发的当前 run Reviewer 能力。输入只能是本 run collector 已解析的有界成功查询快照、标题、Markdown 草稿和所引 evidence ID；不可从模型自报 ID、任意 ToolMessage 或 checkpoint 历史重建。Reviewer 是一次独立的**零工具模型调用**，不得通过 Lead 的 ToolNode、`task` 或 MCP 运行；AS-14 对 Lead 模型 schema 和最终 dispatcher 的精确三工具集合必须维持。
2. 使用现有**服务端选定的 Lead 模型配置**，不接受客户端/模型提交模型名或参数，不增加专门配置面。模型输入、输出设明确的小上限；超限、格式无效、模型异常或超时均 fail closed，绝不写文件/索引。若现有模型工厂不能在不附加普通 RunJournal 的 raw prompt/completion 回调下安全进行 no-tool 调用，先停下报告证据，不用临时全局开关。可选第三方 tracing 仍按既有运维边界管理，不在本切片宣称任意外部导出无敏感信息。
3. Reviewer 输出只解析封闭结构：`approved` 布尔值、有限稳定 `reason_code`；不记录或回传自由文本、推理链、原始响应、SQL、行或报告正文。它是流程复核，不是数学正确性的确定性证明；不能把“模型说通过”写成“每个数字已被证明”。拒绝返回稳定码及可供 Lead 定向修订的安全 reason，**最多一次修订复核**，次数由服务端 run-scoped 状态约束而非 prompt。取消传播；超时/模型失败停止发布。对相同已通过的 title+markdown+evidence 的重试，可复用安全摘要对应的通过决定，维持现有 create-only `existing` 幂等；不同内容必须按尝试预算处理。并发 writer 调用不得绕过预算或同时发布两个异文报告。
4. Reviewer 能力沿 Gateway 已验证的 run-scoped server-owned runtime context seam 传递并在结束时清理；不能放进 `configurable`、checkpoint、普通结构化事件或对外回执。只把安全的状态/attempt/reason 留给下一切片的 trace 设计，本轮不扩事件协议。保留 6F3A evidence 校验与所有既有报告路径安全约束。更新直接相关的中文模块指南，明确 Reviewer 只提供模型复核而不保证数字正确。

## 验证、停止条件与交付

这是 V3 安全/运行时变更，**定点合成**验证足够：无工具绑定、run 身份与客户端伪造键剥除、成功才写/发布、拒绝/无效响应/超时/取消零写入、最多两次复核、同内容重试、并发预算、AS-14 三工具不变、AS-13 结构化事件不带 Reviewer 原文。用 fake model/spy，不跑真实 DeepSeek、Docker、真实数据库、全量后端或全量前端。必要的受影响 Ruff/format、`git diff --check`。先写一个关键安全负例，再完成相干切片并一次定点门禁；局部修复只复验受影响的证明。

若发现必须把全部 16 MiB 结果无上限地送进模型、必须放宽 AS-14、无法让审核调用与原始 payload 脱离持久 journal、或必须重构通用 Agent runtime 才能实现，**停止并报告具体阻塞与最小替代方案**，不自行扩权。真实模型质量和数值忠实度属于后续合成/实测验收，本切片不要伪称已证明。

完成一个实现提交，写 `.reviews/phase-06f3b1-reviewer-gate-report.md`（文件集合、实跑命令/退出码/计数、设计偏差与剩余局限）；工作树干净后交 GPT 复验并停止，不启动 6F3B2、Phase 5C 或发布验收。
