# Phase 6F3E4B：复用现成 run 消息接口完成一次 Reviewer 实测

> 执行者：`gpt-6-luna`（max）。本文件取代 6F3E4 中“自制 SSE 解析器”的要求；6F3E4 已按 20 分钟准备上限停线，未启动项目或模型。先读其停线报告与 6F3E3 只读审计，复用已确认的配置/隔离事实，不重新做全仓审计。

## 为什么缩短方案

`POST /api/langgraph/threads/{thread_id}/runs/stream` 的 `Content-Location` 给出当前 run ID（`backend/app/gateway/routers/thread_runs.py:943-994`，`backend/docs/API.md:490-493`）。已有 `GET /api/threads/{thread_id}/runs/{run_id}/messages` 返回该 run 的结构化消息（`thread_runs.py:1533-1564`）。因此 SSE 只需读到正常结束；**工具名和稳定码从 run 消息接口提取**，不造 SSE parser，也不按原始文本子串计数。

## 单切片任务与门禁

1. V3 单条真实集成探针。使用 6F3E4 已核实的 `deepseek-flash`、warning 有效、effective SQLite/app-home 位置、隔离端口/候选 project 事实；这些证据未失效就不重跑。仅新建一个唯一隔离 Compose project；临时 app-home/SQLite/artifact、合成 PostgreSQL、Redis 都用 project 命名卷。旧 `insightflow-analytics-demo` 和 `.reviews/phase-06f3c3-home-r26a9c2e` 绝不触碰。不得把任何密钥、临时管理员密码、Cookie 或报告正文写入文件/命令行参数/日志。
2. 不开发通用测试框架。复用仓库现有 Python HTTP 客户端和已验证的 setup/login+CSRF 顺序，在 `.reviews/` 放**一个最短的无凭据临时脚本**；先做 Python 语法检查、Compose 渲染和目标 project/端口隔离检查。准备若再次超过 20 分钟且未能启动 run，停止并报告确切单一卡点，不进入新一轮广泛搜索。422 只记录字段路径与类型，HTTP 异常只记录异常类别/阶段。
3. 建立已批准的合成 datasource/schema/policy 和一个新的 analysis thread，最多发送**一次**真实 run。读取 `Content-Location` 并严格核对 thread ID；流体只需完整消费并确认结束，不保存或打印正文。之后以 owner 会话调用 `GET /api/threads/{thread_id}/runs/{run_id}/messages`，按接口分页取齐本 run 的消息，从结构化 `tool` 结果中只提取工具名、稳定 code、evidence 是否存在和计数。若接口权限或解析失败，记录 HTTP 状态/异常类别并停止，绝不用 SSE 字符串替代证据。
4. 若 writer 的结构化 code 是 `analysis_review_unavailable`，仅在本轮 Gateway 容器日志中按同一 run ID 读取 `event=analysis_report_reviewer` 固定 stage；若没有，报告“未观测”及 warning/日志驱动条件，不猜根因，不发第二个 run。若 writer 成功，检查同一 owner 的报告索引 HTTP 状态与本 run 条数，并以状态码验证 owner artifact GET 及异线程/异主体拒绝；不读取或保存正文。无论成败都不能把 run 结束当作报告发布成功。
5. `finally` 对**精确本轮 project** 执行 `down --volumes --remove-orphans`，核实目标容器/卷/网络全为零、旧 6F1 未变化；若策略阻止清理，报告剩余资源并停止，不绕过。删除本轮可能含状态的临时文件，保留仅含无凭据代码的复用片段。

## 交付

只写 `.reviews/phase-06f3e4b-existing-run-messages-probe.md`：记录一次 run 的安全 ID、各步骤状态、结构化工具稳定码/Reviewer stage、报告及 artifact 状态、回收结果和未知项。`.reviews/` 不提交。本轮不改生产代码、依赖、lockfile、前端或永久测试；若发现确定性产品缺陷，只报告最小复现与候选修复位置，等待主会话审查后另发提示词。不跑全量测试/构建/E2E，不重试模型。
