# Phase 6F3E5：验收 HTTP 客户端离线预检

> 执行者：`gpt-6-luna`（max）。先读 `.reviews/phase-06f3e4b-existing-run-messages-probe.md`。本轮只修测试入口，不修产品；不启动/停止 Docker，不登录，不读密钥，不调模型。

## 目标与范围

6F3E4B 的唯一首个卡点是临时 HTTP helper 对公开 `/api/v1/auth/setup-status` 抛 `TypeError`，没有 HTTP 响应；原临时脚本已删除，不能再从其异常推断产品缺陷。后端已有 `httpx>=0.28.0`。在 `.reviews/insightflow-acceptance-http.py` 留下一份**最小、无凭据、可复用**的客户端片段：直接使用 `httpx.Client`，不造 request/response 包装层；只实现 GET setup-status 和返回 `{status, json_type}` 的安全摘要。不要打印响应体或请求头。

## 验证（V1，离线）

1. 用后端现有 `.venv` 的 Python 导入 `httpx`；若环境缺包，报告缺口，不运行会重新锁依赖的命令。
2. 以 `httpx.MockTransport` 给 `GET /api/v1/auth/setup-status` 返回一份合成 200 JSON，执行同一段客户端代码，断言路径、`status==200` 与 JSON 是 object。另给合成 503 JSON，断言状态原样返回而非伪造 `HTTP 0`。只需一个离线自检入口；不建永久产品测试。
3. 对 `httpx.RequestError` 只返回异常**类名和请求阶段**；对 `TypeError` 让离线预检直接失败并给出安全的本地栈帧位置，不把它转换成 HTTP 0。检查脚本语法和本轮文件 diff；不跑应用测试、Ruff 全仓、Docker 或 E2E。
4. 10 分钟内无法使离线两个场景通过就停线，报告精确异常类别与代码位置，绝不继续启动真实栈碰碰运气。

## 交付

报告写入 `.reviews/phase-06f3e5-http-client-offline-preflight.md`，列出离线命令、两个结果、脚本路径及下一步真实 GET 的调用方式。`.reviews/` 保持忽略，不提交脚本；跟踪工作树保持干净。完成后停在主会话复验，不擅自启动下一阶段。
