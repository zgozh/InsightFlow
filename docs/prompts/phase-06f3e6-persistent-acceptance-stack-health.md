# Phase 6F3E6：建立可复用验收栈并验证入口

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e5-http-client-offline-preflight.md`，复用 `.reviews/insightflow-acceptance-http.py` 的已验证 `httpx.Client` 直接请求方式。用户已明确提出复用固定测试容器以减少耗时；本轮成功后**保留**专用验收栈，不再每次 `down --volumes`。本轮不创建管理员、不配置业务数据、不调用模型。

## 一次性启动边界

- 验证级别 V2：只做 Compose 渲染、启动健康、公开 setup-status 真 HTTP 请求与隔离确认。无需全量 pytest、前端构建或 E2E。
- 使用稳定且专用的 project 名 `insightflow-acceptance-local`，唯一 loopback 端口 `127.0.0.1:29384`（若已占用，停止报告，不自动换端口）；所有 app-home/SQLite/artifact、合成 PostgreSQL 和 Redis 状态必须在该 project 的命名卷。不得挂宿主机私有目录，也不得复制密钥到 Compose override/镜像。旧 `insightflow-analytics-demo` 的容器、卷、网络均不变；绝不触碰 `.reviews/phase-06f3c3-home-r26a9c2e`。
- 从当前仓库 Compose 与已核实的 6F3E4B 隔离形状出发；`docker compose config --quiet` 后只启动**一次**。用 Compose service/status 和实际挂载信息检查健康，**不要拼接或猜测容器名、物理卷名**。镜像/服务需要重建时只重建受影响服务；成功后保留整个栈供后续切片复用。

## 最短真 HTTP 探针

1. 用后端现有 `.venv` 的 `httpx.Client(base_url='http://127.0.0.1:29384', timeout=10, trust_env=False)`，调用离线预检同一 `setup_status_summary(client)`，只输出状态与 JSON 顶层类型。成功标准是得到真正的 HTTP 200 JSON object；不能把 Docker healthy 或 HTTP 0 当成通过。不要自写新的 urllib helper。
2. 若 `httpx.RequestError`，只记异常类别、请求阶段，以及 Nginx/Gateway 两服务的健康布尔值；允许健康刚变 true 后仅一次短暂重试。若 `TypeError`，停止并给出本地无敏感值的栈帧文件/行号，**不做 20 次同命令轮询**。响应非 200 时仅记状态码，不输出响应体。
3. 成功后记录 project 名、loopback 发布端口、5 个服务健康与命名卷前缀、旧 6F1 不变；**保留**新栈，不做 setup/login、不写入账号或业务数据。失败则只对该精确新 project 做 `down --volumes --remove-orphans` 并核对目标资源为零；策略拒绝清理时报告剩余资源，不绕过。

## 交付

在 `.reviews/phase-06f3e6-persistent-acceptance-stack-health.md` 写脱敏证据与下一阶段可复用入口信息。临时 Compose override 只能含无凭据配置，并应保留在 `.reviews/` 供下次相同 project 使用；不要把密码、Cookie、token、模型正文或私有配置值写入其中。跟踪工作树保持干净。本轮不改产品代码或提交实现；完成后停在主会话复验，不能自行开展管理员设置或真实 run。
