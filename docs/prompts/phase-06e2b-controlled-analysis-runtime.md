# Phase 6E2B：受控分析运行的工具隔离与前端启用

你是 InsightFlow 的实施模型 `gpt-6-luna`（max），GPT 负责架构审查。先读本文件、全局/根/涉及模块 `AGENTS.md`、`.reviews/phase-06e2-trusted-analysis-mode-design-report.md`、6E2A 与 Fix 01 的提交差异，以及 AS-14 两份验收文档。预期起点为本提示词提交后的干净 `main`；先核对，不符即停。固定 `upstream-v2.1.0-rc0` tag/tree、依赖和 lockfile 不动。禁止读取、打印或测试断言展开真实 `.env`、`config.yaml`、`os.environ` 的值。

## 唯一安全目标

用户已裁决：平台托管 Analytics 数据源必须经 Query Policy；通用聊天保留操作者配置的第三方 MCP，但第三方 MCP 不受同一 SQL 策略保证；**受控分析运行必须在模型可见工具与最终执行两处隔离普通/durable MCP 及其他业务数据旁路**。6E2A/Fix 01 已建立可信线程 `analysis_mode` 标记和未就绪运行门禁。只有整条工具隔离链可证明闭合，才能解除 `analysis_mode_unavailable` 并启用前端分析入口；否则保留拒绝态，不提交“半启用”的实现。

## 一个连贯实施切片

1. 从 6E2A 的持久线程标记派生的服务端运行上下文识别分析模式；客户端 context/configurable、URL、`agent_name`、checkpoint 文本均不得开启或关闭它。普通聊天的 MCP/工具行为不变，旧无标记线程只属于普通聊天。若分析模式标记来源不可靠，停止。
2. 在 Lead 工具装配、延迟 `tool_search`、`task_tool` 的普通/受限委派、general-purpose 与 bash 两类子 Agent 的实际工具绑定和最终执行处，按**可信来源/正向允许集合**筛选。分析 Lead 仅暴露 Analytics 已批准工具、受约束的虚拟路径读写/报告工具和必要的安全委派；子 Agent 只拿其职责所需的虚拟文件工具，不拿 Analytics、MCP、durable MCP、bash/命令执行、未知动态工具或第三方扩展。普通与 durable MCP 必须在 discovery/模型展示前排除，也不能由热更新、tool search、历史 tool_call 或子 Agent 恢复；不要仅做提示词警告、工具名 denylist 或“可见但调用时拒绝”。若现有装配面无法可靠识别来源，应采用更小的正向安全集合并说明取舍，不放宽默认拒绝。
3. 受控分析不得暴露 LocalSandbox 同主机 bash、AIO 命令会话、环境读取或等价命令工具。6E1 环境白名单只阻止自动继承，不构成文件系统/网络隔离；AIO 的 `sandbox.environment` 和 MCP stdio 的显式环境映射仍是运维赋权。虚拟文件工具只有在现有路径约束能证明不会读 Gateway 任意文件/环境时才保留；否则本片保持运行拒绝，并报告所缺的最小接缝。目标仍是可写安全报告 artifact，不要用关闭所有工具冒充功能闭环。面向分析线程的 MCP task notification/结果注入要在受信入口拒绝或证明完全不可达。
4. 完整隔离经测试后，才解除 6E2A 的临时运行拒绝。前端 `/workspace/analysis/new` 用同一 thread UUID 调用可信创建 API `kind=analysis`，确认响应持久标记匹配后才发起原有聊天流；旧分析路由若指向无标记线程，展示明确非受控状态或转普通聊天，绝不静默升级或降级。保持原聊天页主交互，不额外重做视觉设计。
5. 将 AS-14 发布契约与 UI/运维说明改为准确的已批准边界：平台托管 Analytics 数据源经 Query Policy；受控分析双层隔离第三方普通/durable MCP 与命令旁路；普通聊天仍可使用 operator MCP，**不保证任意第三方 MCP 访问遵循 Analytics SQL 策略**。旧绝对承诺必须删除；不要顺带宣称 AS-13 或完整 Phase 6 验收完成。`docs/PROGRESS.md` 记录 6E1、6E2A+Fix 01 的复验状态及本片待 GPT 复验。

## 定点证据与停止条件

这是安全敏感的 V3 集成切片，但仍遵循最小充分验证。先用合成配置/哨兵设计高价值 RED：普通聊天仍见 MCP；分析 Lead、tool_search、最终 tool dispatch、普通和 bash 子 Agent、durable task、热更新均不能看见/执行 MCP 或命令；Analytics 仅 Lead 可见；伪造标记不能改权限；前端新线程请求与旧线程行为。完成连贯实现后跑直接受影响的 Harness/Gateway/前端定点测试、必要 type/lint/build 检查；仅当目标证据不足以证明真实装配链时扩展到受影响集成测试。不要机械跑 14k 全套、所有 Playwright、Docker 或真实模型/数据库；若运行真实 E2E 有必要，先说明它证明的独有边界。沿用仍有效的 6E2A 证据，不因新一轮而重跑无关测试。

如果任一分析工具旁路仍可达、隔离只停留在 model-visible 而执行层未封、虚拟文件工具可越过授权路径，或前端可能把旧 chat 线程标作受控分析，则不要解除 `analysis_mode_unavailable`；保留安全停止状态，报告精确缺口与下一最小切片。生产与测试文件按上述直接接缝最小修改，不引入新中间件、数据库、迁移、依赖或通用插件框架。一次实现提交，提交后工作树干净；报告 commit/parent、文件范围、真实运行的门禁与计数、源码可证的隔离点、未验证项和偏差。停在 GPT 复验，不自行启动 5C 或下一阶段。
