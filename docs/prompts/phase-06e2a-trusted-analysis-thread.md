# Phase 6E2A：可信分析线程标记与未就绪运行门禁

你是 InsightFlow 的实施模型 `gpt-6-luna`（max）；GPT 负责架构审查。本切片只建立受控分析模式的**服务端来源**，不实现 MCP/沙箱工具隔离。实施前先读本文件、仓库根及直接涉及模块的 `AGENTS.md`、`D:\codexData\AGENTS.md`，以及 `.reviews/phase-06e2-trusted-analysis-mode-design-report.md`。起点应为本提示词提交后的 `main`，工作树干净；先核对，若不符即停。固定 `upstream-v2.1.0-rc0` tag/tree 不得改。

## 已批准边界与本片安全状态

用户已批准：平台托管的经营分析数据源强制经过 Query Policy；第三方 MCP 是由操作者赋权的独立扩展，不宣称受同一 SQL 策略保护；受控分析运行必须隔离第三方 MCP。6E1 已把 LocalSandbox 自动继承 Gateway 环境改为精确白名单，但 LocalSandbox 仍是同主机命令执行，不能据此宣称文件系统或网络隔离。

本片完成后，允许持久化 `kind=analysis` 的线程意图，但**所有这类线程的运行必须在进入 Agent/工具装配之前稳定拒绝**，直至 6E2B 的工具隔离完整验收。不要仅依赖前端隐藏入口、URL、提示词或客户端 context。普通聊天运行保持现状。不要开放新的分析前端入口，不修改 Harness 工具列表，也不要修改 AS-14 发布契约为“已满足”。

## 实施范围

1. 复用既有线程持久 metadata（若实际源码证明不适合，先报告，不新建迁移）。在创建线程的服务端入口接受受限顶层 `kind`（默认普通聊天，仅允许明确的 `analysis` 值），把模式写入**服务端保留字段**。普通可写 metadata、PATCH、分支入参、客户端 `body.context` 和 `body.config.configurable` 均不得创建、清除或伪造该字段。分支只继承真实源线程的模式，不接受请求体重写。既有线程记录没有该字段时按普通聊天处理；记录不存在、字段值损坏或无法确定真实模式时拒绝，不能把错误降级为普通模式。
2. 核对普通、无状态、scheduler/internal、通知、checkpoint 恢复等 run admission 实际调用链。在可信入口从持久线程记录派生模式，剥离客户端同名键；对于 `analysis` 线程，进入 Lead/tool graph 前返回稳定、脱敏的 `analysis_mode_unavailable`（或仓库已有同义稳定码），绝不继续成普通聊天。无法统一封住某条入口时，停止提交并给出精确旁路与最小修复设计。普通线程的伪造 `analysis_mode=true` 不得改变工具或权限。禁止从 analysis URL、`agent_name`、配置热更新等非持久来源推断模式。
3. 只更新直接相关的 Gateway thread/run 模块、对应测试、必要的项目指导/进度文档。无权实施 6E2B 的 MCP、durable MCP、bash、tool_search、子 Agent 或前端路由调整；不动 Docker、依赖、锁文件、Analytics SQL 安全链。若可靠闭合需要清单外一个直接相关接缝，可最小扩展并在报告列明，不为预算掩盖旁路。

## 验证与止损

级别 V3（安全敏感的共享 run admission），但验证要按最小充分证据执行：先用合成输入写高价值的伪造/清除、分支继承和分析运行拒绝回归；确认 RED 是目标缺陷后完成一个连贯实现，再运行受影响 Gateway/thread/run 测试与必要静态检查。无需机械重跑 14k 全套、Docker、前端构建或 E2E。只在目标检查不足以证明某条真实入口时扩大到该入口的聚焦测试。不要对真实 `os.environ` 做会在失败时展开字典的断言；不要读取、打印或保存真实 `.env`/`config.yaml` 值。测试只用合成值。

提交前检查受影响 diff、`git diff --check`、工作树状态。若发现分析运行仍能到达任何 Agent/工具绑定、客户端可伪造/清除标记，或记录读取/解码错误会隐式降级，停止并报告，不以“前端暂未开放”放行。完成时只做一个实现提交；`docs/PROGRESS.md` 记录 6E1 已验收、6E2A 待 GPT 复验，Phase 6/AS-14 仍未完成。报告 commit/parent、文件集合、真实执行的定点门禁与结果、未验证入口和偏差；停在 GPT 复验，不自行启动 6E2B/5C。
