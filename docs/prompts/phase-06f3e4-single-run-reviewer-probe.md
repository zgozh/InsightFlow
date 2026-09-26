# Phase 6F3E4：一次可观测的真实报告链路探针

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e3-reviewer-observability-audit.md` 和 `.reviews/phase-06f3e2-reviewer-safe-diagnostics.md`，仅补读本轮调用点。此任务是诊断切片，不是修复或全局验收。

## 目标与现有事实

`626d46a` 的安全阶段日志已在镜像源码中，Reviewer/writer 与 Gateway 同进程；上一轮只有 SSE 文本里的 `analysis_review_unavailable`，缺结构化 ToolMessage、可关联 run ID、Reviewer stage 和报告回读状态。用**最多一次**新的隔离真实 `deepseek-flash` run 区分这些路径。不要再仅凭字符串出现次数判断工具调用，也不要在不知道根因时改 Reviewer。

## 范围和验证级别

这是 V3 的单条真实集成探针，充分验证是“本地夹具语法/合成 SSE 解析预检 + 一次 Gateway run + 同 run 安全观测”，不是全量 pytest、构建、E2E 或重复模型请求。若预检或 setup 在 20 分钟内仍无法可靠完成，停止并交报告，别继续临时猜参数。

1. 确认 HEAD 至少包含 `626d46a`，工作树干净；固定 tag、lockfile、旧 `insightflow-analytics-demo` 的容器/卷/网络不动。绝不触碰 `.reviews/phase-06f3c3-home-r26a9c2e`。使用唯一的新 Compose project、唯一 loopback 端口、**project 命名卷**装临时 app-home/SQLite/artifact、PostgreSQL 和 Redis；不得用 host 目录存临时管理员状态。
2. 把复用夹具写为 `.reviews/phase-06f3e4-single-run-harness.py`（可配一个无凭据临时 Compose override）。夹具只在进程内生成临时管理员密码，使用一个 CookieJar/WebSession；setup/login 后同一会话从 CSRF cookie 生成写请求 header。所有 HTTP 结果按状态和结构化 JSON 处理。422 只可打印字段路径及类型，错误体、Cookie、凭据和模型内容不得落盘或输出。预先用纯合成 SSE 帧校验解析器能够按 event/data 得到当前 run 的工具名、稳定 code 和结束标志；解析失败不得启动模型 run。
3. 沿用已批准的合成 PostgreSQL schema/policy、受控 analysis thread 和 DeepSeek 配置；服务启动、身份、策略或日志条件不满足就停止，**不发 run**。在 run 前只记录 Gateway warning 是否有效的布尔判断及 Docker 日志驱动是否支持 `docker logs`，不输出其他私有配置。不要为了日志可见性永久改配置或扩大日志字段。
4. 最多发送一次真实 `POST /api/langgraph/threads/{thread_id}/runs/stream`。从受信 header/响应契约获取 run ID；结构化解析 SSE，只保存/报告该 run 的工具名、工具稳定码、run 结束状态及安全计数，不保存原始 SSE、SQL、行、prompt、token、报告正文或异常文本。若 `write_analysis_report` 返回 unavailable，立即按 run ID 在**同一个 Gateway 容器日志**中取白名单 `event=analysis_report_reviewer` stage；若没有，写明日志级别/驱动的观测结果与缺口，不再试第二个 run。
5. 用同一 owner 会话做 `GET /api/analytics/reports`，记录 HTTP 状态和该 run 的报告数量；仅当得到发布回执时，继续验证 owner artifact GET 成功和异线程/异主体拒绝（只记状态码，不读取或保存正文）。若 GET 在 HTTP 前失败，至少记录本地异常**类别**和发生步骤，不能再写笼统 `no_http_status`。不得把 SSE 结束或普通 API 200 当作报告发布成功。
6. `finally` 只对**本轮精确 project** 执行 `down --volumes --remove-orphans`，核对它的容器/卷/网络都为零、旧 6F1 不变；只清理本轮无凭据临时文件，不删旧项目或其镜像。若自动清理被策略拒绝，停止并向主会话报告确切剩余资源，不绕过策略。

## 交付和停止条件

- 在 `.reviews/phase-06f3e4-single-run-reviewer-probe.md` 记录：预检、唯一 run ID（安全 opaque 值）、结构化 ToolMessage 结果、同 run Reviewer stage、报告 GET/owner artifact 状态、临时资源回收、凭据与正文零落盘。夹具可保留供后续复用，但不得含任何真实私密值；`.reviews/` 不提交。
- 不修改生产 Python、API、配置模板、lockfile、前端或测试；本切片无实现提交。若确诊产品缺陷，只报告最小修复位置与可复现条件，等待主会话审查并另写修复提示词。若链路通过，也只报告该场景通过，不擅自宣告全局验收。
- 下列任一情况立即停止模型操作：预检失败、日志源不明、run 已发送一次、凭据可能泄漏、权限/策略异常、无法精确隔离回收。不要靠重复发送请求消除不确定性。
