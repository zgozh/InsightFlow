# Phase 6F3E7：在固定验收栈做一次完整分析 run

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e6-persistent-acceptance-stack-health.md` 与 `.reviews/phase-06f3e3-reviewer-observability-audit.md`。用户要求复用固定测试容器直到全局验收，不再每轮重建；本轮只用现存 `insightflow-acceptance-local`。主会话仍只做规划/审查。

## 已证明事实与目标

项目 `insightflow-acceptance-local` 现有 5 个 running 服务、3 个本 project 命名卷、1 网络，入口 `127.0.0.1:29384`；公开 setup-status 已用现有 `httpx` 返回真实 HTTP 200 JSON。旧 `insightflow-analytics-demo` 为 5/2/1，不动。目标是在该固定栈中用**最多一次** `deepseek-flash` run 取得结构化工具消息及 Reviewer 失败阶段，或证明报告发布/本人读取闭环。

## 准备（只做一次，不重建栈）

1. 确认本 project 与入口仍可用；若服务已停，仅用同一 Compose project 启动受影响服务，保留命名卷，不 `down --volumes`。不要拼写容器名，按 Compose service 查状态。不得触碰 `.reviews/phase-06f3c3-home-r26a9c2e`。
2. 使用后端已有 `httpx.Client`、`trust_env=False` 和同一个 cookie jar。生成**随机、仅本地验收用**管理员密码；先用 Windows 当前用户 DPAPI 将其加密保存于 `.reviews/` 被忽略的文件，再发初始化请求。明文只在短生命周期进程内存中；不得出现在命令行参数、日志、报告、Compose override、Git、响应打印或模型消息中。复用时同一 Windows 用户解密；最终验收时删除该凭据文件与本 project 全部卷。若无法可靠建立加密凭据，停止在创建账号前，不退化成明文落盘。
3. 依已验证的 API 契约完成 setup/login；所有写请求从同一 WebSession 的 CSRF cookie 提取 header。错误只记录 HTTP 状态，422 仅字段路径/类型，异常仅类名和阶段。不要输出响应体。设置合成 PostgreSQL datasource/schema/policy：仅开放非敏感 `region` 与 `amount` 聚合、`sum`，其余列默认拒绝；记录创建和 owner 匹配的布尔/状态，不记录凭据或行内容。服务/身份/策略不就绪则停止，不发模型 run。

## 唯一真实 run 与取证

4. 创建全新 `kind=analysis` thread，确认服务端 `analysis_mode=true`。向受控 run 提出明确、可证据支持且要求留存 Markdown 报告的中文请求。最多调用一次 `POST /api/langgraph/threads/{thread_id}/runs/stream`；从 `Content-Location` 严格取得对应 run ID，只消费 SSE 至结束，不保存/打印流正文，不自行解析 SSE 工具内容，不重试模型。
5. 同一 owner 会话调用现成 `GET /api/threads/{thread_id}/runs/{run_id}/messages`（`thread_runs.py:1533`），按分页取本 run 的结构化消息。只抽取工具名、稳定 code、query evidence 是否存在/数量、writer 调用次数和 run 状态；不得将 SQL、结果行、模型文字、报告正文、token/DSN 写入报告。若缺结构化证据，记录 HTTP 状态或异常类别并停止，不用 SSE 字符串代替。
6. 若 writer 返回 `analysis_review_unavailable`，按同 run ID 从该 Gateway 日志读取 `event=analysis_report_reviewer` 的固定 stage；记录 stage 或“未观测”，不猜测，不再发第二个 run。若 writer 成功，查 owner 报告索引的本 run 条数和 HTTP 状态；再只以 HTTP 状态验证 owner artifact 可读、异线程/异主体拒绝。任何一环不通，准确报告，不宣称闭环通过。

## 验证与交付

- V3 但仅此单场景：不跑全量 pytest、构建、Playwright 或额外模型 smoke。使用已有有效的 6F3E6 入口与隔离证据，不重复镜像哈希/全仓搜索。
- **保留**本 project 容器、命名卷和加密临时凭据，供后续审查与修复复用；不 `down --volumes`。完成时核对旧 6F1 仍为 5/2/1。若发现凭据明文落盘或隔离破坏，立即停止并向主会话报告，不能自行绕过。
- 报告写 `.reviews/phase-06f3e7-persistent-stack-single-analysis-run.md`，只含状态/计数/安全 ID/stage 和明确未知项；`.reviews/` 不提交。不得改生产代码、依赖、lockfile或永久测试；确诊产品缺陷时只给最小复现与候选位置，待主会话另发修复提示词。停在主会话复验，不自行进入下一阶段。
