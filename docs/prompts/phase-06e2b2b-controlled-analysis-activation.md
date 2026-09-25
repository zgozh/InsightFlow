# Phase 6E2B2B：受控分析入口接通与可信线程闭环

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max），GPT 负责方案与复验。先读全局/根/涉及模块 `AGENTS.md`、`.reviews/phase-06e2b2-safe-report-artifact-feasibility.md`、`docs/prompts/phase-06e2b-controlled-analysis-runtime.md`，以及 6E2A、6E2B1、6E2B2A+Fix 01、6E3A+Fix 01 的直接接口。当前起点应为本提示词提交后的干净 main；不符即停。固定上游 tag/tree，不改依赖、lockfile、迁移或 Docker 拓扑；不要读取/输出真实 `.env`、`config.yaml`、`os.environ` 或业务行值。

## 目标与不可放宽的边界

将当前明确停用的 `/workspace/analysis/new` 接通为**受控经营分析**，复用原聊天页主交互，不重做 UI。只有服务端持久化的 `kind=analysis` 线程能进入分析运行；此运行只拥有固定来源的 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`。平台数据源仍须经过 Query Policy、权限、成本、一次性计划和审计；普通聊天仍可用其操作者赋权 MCP，不宣称第三方 MCP 受同一 SQL 策略。受控分析不得获得 MCP/durable MCP、bash/AIO shell、通用文件工具、动态插件、tool_search、task/子 Agent 或旧 `publish_analysis_report`。本切片不恢复原 business-analysis skill 的 Data Analyst/Reviewer 子代理步骤；保留普通聊天的子 Agent 能力，并在产品文档中如实写明受控分析 V1 由 Lead + 平台治理链完成，不把尚未实现的 Reviewer 写成已上线。

1. 前端首次发送前，使用同一个 thread UUID 调用现有 `POST /api/threads` 并显式提交 `kind: "analysis"`，确认成功/返回的持久标记后才启动流；失败不得先流到普通聊天。后续沿用原聊天组件和 streaming 状态机，但 `onStart`/历史继续留在 `/workspace/analysis/{thread_id}`。已存在的普通线程、不存在/损坏的分析标记或 `409 thread_kind_conflict` 必须显示明确状态，引导新建分析线程，不得暗中升级、降级或跳转 chats。普通 `/workspace/chats` 行为不变。分析 UI 的中英切换与既有响应式/可访问性模式保持。
2. Gateway 仅从已认证用户及持久线程元数据派生 analysis 标记，清除客户端 `context/configurable` 同名输入；只有 services 可用、持久标记可信、server-owned writer capability 成功绑定时，才移除 6E2A 的两处 `analysis_mode_unavailable` 暂停门禁。Analytics disabled、memory backend、迁移/服务不可用、匿名/default 用户或标记损坏时稳定 fail closed，不得回退为普通 Lead 图。构图和运行最终 ToolNode 仍须使用 6E2B1/2A 精确正向白名单；异常 tool_call、热更新、MCP notification、历史调用或旧线程均不能恢复旁路。
3. 为分析 Lead 提供简短中文优先的专用工作指引：确认用户口径、按需 inspect catalog、经平台 query 工具查询、仅引用实际返回的 evidence ID、用安全 writer 生成 Markdown 报告、回答中说明结论和限制。指引不取代代码权限边界，不包含固定表名/真实 SQL/凭据；模型可选择只回答而不写报告，但 UI 不得把未写成的文件显示为已发布。writer 产物继续通过现有 owner-check artifact GET/Markdown viewer 展示，不签发不受限直链或 HTML 执行路径。
4. AS-14 文档和 `docs/PROGRESS.md` 只根据真实证据更新：受控运行在模型可见与最终执行两处隔离第三方工具；普通 MCP 独立且不受统一 Query Policy 保证。AS-13 仍仅承诺平台派生结构化 metadata/审计/外发及持久化事件投影，不保证任意模型文本或 artifact 正文没有敏感内容。若完整运行/预览的关键边界不能证明，保留停用门禁，不提交半启用状态。

## 比例验证与交付

这是跨 Gateway/Harness/前端的安全敏感 V3 切片，但**不机械跑全仓**。先用合成身份、数据源、SQL/结果哨兵和 fake model 做一个真实 Gateway admission→Agent 图→catalog/query/writer→artifact GET 的定点闭环；证明未授权用户/线程、伪造上下文、禁用服务与被禁工具调用均 fail closed，普通聊天仍走旧路径。前端用最少组件/Playwright 用例证明 `kind=analysis` 预创建、同 UUID 首次流、路由不跳 chats、旧 chat ID/409 明确拒绝、报告链接受所有者保护；对应 type/lint/build 只跑受影响的检查。保留 6E2B1/2A 和 6E3A 仍有效的既有证据，不因新提交重跑 14k 后端、全量 Playwright、Docker 或真实模型。真实 PostgreSQL/MySQL+模型+Compose 的业务闭环留到下一独立验收切片，不能以 fake model 冒充。

成功后一个独立实现提交、工作树干净，报告 commit/parent、变更文件与真实门禁、可复现的合成闭环、未验证项/偏差；Phase 6 仍 `In progress`，不自行宣称最终验收，也不启动 5C/后续阶段。若任何关键门禁失败或需扩大产品承诺，停止并给 GPT 精确阻塞，不做“先开放再补安全”。
