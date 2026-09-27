# Phase 6F3F10：现有普通聊天 run.error 的定点归因

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。6F3F9 `4be7ef5` 的事件持久化子范围已通过 GPT 复验；本切片先复用其两条已失败的普通 chat run，**不先发新的模型请求**。读 `.reviews/phase-06f3f9-durable-run-events.md` 与直接相关的 run/error 投影、模型请求装配、Gateway 日志定位代码即可。

## 问题

两条最小普通 chat run 均返回 HTTP 200 stream、最终 `status=error`。有效 db-config run `29e167f1-44d3-4ba7-8c03-39b5889d12c8` 在 `run.error` 前有 `llm.ai.response:1`、`run.delivery:1`，因此不能仅凭 `error` 推断 DeepSeek 请求失败，也不能凭 AI response 推断完整 run 成功。其 messages/events 现已持久化，足够做只读错误归因。模型配置名必须是 `deepseek-flash`，不得写错或泄露密钥。

## 有界诊断与处理

1. 只在短生命周期进程内读取上述两个 run 的同 owner 稳定错误字段、异常类型、阶段/来源、可安全归类的 HTTP 状态（如存在）；必要时看 Gateway 同 run 的**脱敏类别**日志。输出只允许 `provider_request / model_response_parse / runtime_after_response / delivery / persistence / auth_config / unknown` 等稳定分类及布尔，不输出自由异常文本、提示词、模型正文、SQL、URL 参数、凭据、header、cookie 或事件原始 JSON。
2. 沿最短相关调用链确定最先失败点，并与 6F3E10 已成功的 `deepseek-flash` 分析 run 的**配置形状**作结构比较，不读取其业务正文。区分：外部 API 暂时失败、当前普通聊天配置失配、RunEventStore 切换引入的错误，或 Gateway 运行/交付阶段错误。不要因同现象重复跑未变化的请求。
3. 若能证明是一个明确、局部的产品代码或样例配置缺陷，可在同一切片做最小修复、加一条有长期价值的回归测试并跑直接相关检查；只有改动后才允许**最多一个**新的小 chat run 验证，且不重建全栈。若是 Provider 401/429/网络或证据不足，停在线路分类与下一项最便宜检查，不试错改代码、不轮换 key、不重试模型。
4. 不修改受控分析 SQL/授权、报告、数据库 schema 或前端；固定 5 容器/3 卷不删除、不重新构建。若修复是启动期配置，只在确认精确配置和可恢复备份后 Gateway-only 重启；其它服务不动。

验证级别 V1 的诊断/局部修复；仅在确实触及共享模型装配或启动配置时升级为 V2 对应测试。无需全套后端、浏览器、Docker build 或新的业务查询。已通过的 6F3F9 事件持久化证据保持有效，不机械重跑。

脱敏报告写 `.reviews/phase-06f3f10-existing-chat-run-error-triage.md`，记录最先失败阶段、分类依据、是否与 db event store 有关、修复与定点证据或明确未解决项。若无 tracked 改动不做空提交；若有产品/文档改动则独立提交、工作树干净、不 push。完成后停 GPT 复验。
