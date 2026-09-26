# Phase 6F3E3：Reviewer 诊断可见性只读审计

> 执行者：实施子 Agent。先读本文件及 `.reviews/phase-06f3e2-reviewer-safe-diagnostics.md`。本轮只定位观测缺口，不修改生产代码、不启动 Gateway/模型 run、不创建临时账号或业务数据。

## 背景与目标

当前 `main` 应为 `626d46a`，6F3E2 的定点测试通过；唯一隔离实测的 SSE 中出现 `analysis_review_unavailable`，但专属 Gateway 容器日志中未见 `analysis_report_reviewer` 事件，且 SSE 未被解析为结构化 ToolMessage。不能据此断定 Reviewer 已调用，也不能将零日志直接解释成某个失败阶段。本轮要用最小只读证据确认“运行的是哪份代码、日志应该从哪里取、该稳定码可能从哪些分支产生”，并给出下一次最小探针的明确观测方法。

## 范围与方法（V0，只读）

1. 核对 HEAD、干净工作树、固定 tag；不重跑已经有效的 17 项定点测试或全套测试。
2. 用 `rg` 定位 `analysis_review_unavailable` 的全部生产返回路径及 `analysis_report_reviewer` 的日志发出点，画出当前受控分析 run 从 Gateway 到实际执行进程、Lead 绑定、writer、Reviewer 的最短调用链。特别区分“writer 真实工具结果”“Lead 文本复述”“SSE 历史消息”三种来源；没有原始结构化 SSE 证据时明确写未证实。
3. 核查 6F3E2 临时 Compose 项目所构建的 Gateway 镜像是否能被**唯一且可信地**识别。若能，仅读取镜像内相关 Python 文件的源码或哈希，与 `626d46a` 逐点比对诊断语句；允许 `docker image inspect` 或不联网、不挂载私有目录、不运行应用的短生命周期只读容器。若不能唯一识别，停止这一步并记录原因；绝不猜一个相似镜像。
4. 从仓库代码与 Compose 配置核对运行进程/日志路由：`logger.warning` 到哪个进程的 stdout/stderr，`docker compose logs gateway` 是否覆盖实际工具执行进程，日志是否可能被过滤、采样或写入其他容器。不要为找日志启动新的服务，也不要读取、输出或保存 `.env` / 私有 `config.yaml` 的凭据值。
5. 检查 6F3E2 的临时实测脚本/报告为何只做了字符串观察、报告回读为何在 HTTP 状态前失败；只分析现存证据，不恢复已删除的临时数据，也不重新运行模型。提出**一个**下一轮单 run 的最小取证契约：必须记录安全的 run ID、结构化工具名/稳定码、Reviewer stage 所在进程、报告列表 HTTP 状态与 owner artifact GET 结果；敏感正文、SQL、token、凭据和结果行不得进入诊断记录。若尚不能指定正确日志源，先给更窄的本地探针，不直接提议实测。

## 边界与交付

- 只在 `.reviews/phase-06f3e3-reviewer-observability-audit.md` 写调查报告；该目录被忽略，报告不得包含敏感值。提交仅在发现**必须修订的跟踪文档错误**时才考虑，否则不提交。
- 不修复推测中的 Reviewer 问题，不扩大日志字段，不重试 DeepSeek，不动 6F1 容器/卷/网络，不触碰 `.reviews/phase-06f3c3-home-r26a9c2e`。
- 报告分清“已证明 / 可能 / 未知”，列出确切文件与行号、镜像身份、日志路由、下一轮最小探针与是否需代码改动。未定位根因时如实停止，不把 6F3E2 或全局验收标为通过。
- 用简短中文报告回主会话，随后等待复验；不要擅自进入下一阶段。
