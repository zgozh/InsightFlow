# Phase 6F3A：受控分析 run-owned evidence 边界

你是 InsightFlow 实施者。先读 `.reviews/phase-06f3-reviewer-feasibility.md` 与本提示词，再只读核对相关源码/测试。此切片只解决 Reviewer 所需的前置事实：**报告引用的 evidence 必须来自同一认证 analysis run 内真实成功的受控查询**。不新增 Reviewer、模型调用、工具、MCP、数据库表或前端页面；不宣称 AS-07/08/10 已验收。固定上游 tag `upstream-v2.1.0-rc0` 不变。

## 架构边界

1. Gateway 在 analysis run 准入后创建私有、run-scoped evidence collector，绑定可信 principal/thread/run；与现有 writer capability 一样只经服务端 runtime context 传递，不接受客户端或模型参数。先用最窄合成测试确认该对象确实从 Gateway 到查询工具和报告工具保持同一身份、不会进入 checkpoint/结构化事件/对外回执。若这一点无法证明，停止并报告，勿改用进程全局字典、任意历史 ToolMessage 或模型自报 ID。
2. 只有 `query_business_data` 的 plan→execute 成功、生成规范 `AnalyticsQueryEvidence` 和有界结果后，才记录其 evidence ID 与必要的有界结果快照。拒绝、异常、被取消、失败结果不得登记。保留普通聊天原有受控查询行为；只有携带 run-scoped capability 的 analysis run 才有报告资格。不要额外执行查询，也不要把 plan token/raw SQL/凭据存入 collector。
3. `write_analysis_report` 在现有领域预检之后、任何 `write_markdown`/`publish_report` 之前，验证其 `evidence_ids` 非空、无重复且全部属于**同一绑定 run** 的成功记录；未知、跨 run、模型伪造或没有 collector 一律稳定拒绝且零文件/索引写入。现有 create-only 文件/索引顺序和幂等语义保持不变。collector 不是通用 evidence 持久库，不对外暴露 rows、SQL 或自由文本。
4. 保持 AS-14 的模型可见及最终 dispatcher **精确三工具**，普通聊天 MCP 原行为不变；保持 AS-13 的结构化输出禁敏边界。不要把 collector 放在模块全局可按 ID 查询，不经由任意 ToolMessage 反向重建。上下文若会被序列化或跨进程复制，先停下报告可行性，不用更重基础设施自行绕过。
5. 仅更新直接受此行为影响的中文注释/文档（尤其当前报告 evidence 语义）；不改 acceptance 场景状态或承诺。用户/模型文本和 artifact 正文仍不作“绝无敏感内容”保证。

## 验证与交付

这是 V3 安全边界，但按比例只需定点合成检查：Gateway 同一 run 的 capability 传递、真实工具成功/失败登记、伪造/跨 run/无记录拒绝且 write/index spy 为零、报告正常发布及重复同内容语义、原三工具集合不变、结构化输出不泄漏 collector。先写最关键安全负例作为回归，再做一个相干实现和一次针对性门禁；只在证据显示影响更广时升级。受影响 Python 文件做 Ruff/格式与 `git diff --check`。不要跑全量后端/前端、Docker、真实数据库、DeepSeek，且不得读取或输出密钥与真实结果行。

产出一个清晰的实现提交；在 `.reviews/phase-06f3a-run-owned-evidence-report.md` 记录调用链、文件清单、实跑命令/退出码/计数、失败分类、剩余局限与为何未跑广义门禁。工作树干净后返回 GPT 复验并停止；不启动 6F3B Reviewer、Phase 5C 或发布验收。如发现必须改变固定工具集、审计/持久化模式或产品契约，先报告并停止，不自行扩权。
