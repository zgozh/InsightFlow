# Phase 6F3E10：Reviewer `invalid_response` 定因并修复

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。主会话只规划与复验；本文件是本切片实施依据。不要重做 6F3E1–9，不启动下一阶段。

## 目标与已知证据

固定栈 `insightflow-acceptance-local` 的唯一真实 run `dcbabb67-bf31-48e3-8537-1f0010ed277e` 已证明：Lead 可见并两次调用 `write_analysis_report`，有两条成功查询 evidence；两次 writer 均返回 `analysis_review_unavailable`，Gateway 安全日志的 Reviewer stage 均为 `invalid_response`。见 `.reviews/phase-06f3e9-fix-01-explicit-report-run.md`。不能由此推断模型输出的具体内容，也不能把失败归咎于工具可见性。当前 `backend/app/analytics/agent/reviewer.py::_parse_review_response` 把多种不同的拒绝合并为 `None`；DeepSeek 分支的 256 token 限额仍是既有安全契约。

本切片目标是用**不持久化或输出 Reviewer 自由文本**的安全形状诊断，找到真实拒绝原因，做最小正确修复，并证明一条报告链路。不要通过放开严格 JSON、忽略额外字段、抽取正文中的 JSON、关闭 Reviewer 或绕过其门禁来追求通过。

## 边界与计划

验证级别：安全门禁与真实运行接线属于 V3，但只执行一条受影响的端到端场景；离线代码和解析器用 V1 定点检查。若单次真实诊断表明缺陷跨越模型工厂、provider 兼容层或报告持久化边界，才扩大到直接受影响的契约；不默认跑全量 pytest、前端、Playwright、Docker 数据库测试。

1. 先核对 `HEAD`、干净工作区、固定验收栈 5 个运行容器、原 tag/tree、当前 Reviewer 实现与直接相关测试。只读分析既有日志与响应元数据；不再次读取或打印 Reviewer 原始正文、SQL、行、token、凭据。不要拿 `.env` 值做调试输出。
2. 在 Reviewer 解析处加入**仅内部使用**的封闭失败分类，并让现有安全 stage 日志能额外区分其固定枚举值；至少区分：非 AIMessage/工具调用、非字符串或编码问题、空/超字节、JSON 语法或重复键、对象字段或类型错误、`reason_code`/`approved` 不一致。可按必要性区分 Markdown fence 与截断 JSON，但只能输出固定类别，不能输出正文片段、首尾字符、哈希、异常文本、自由文本 metadata。供应商 `finish_reason` 如用于诊断，必须映射到本地固定白名单（如 stop/length/tool_calls/other），不得直接记原值。对外稳定决定码及 Writer/HTTP/持久化事件契约不变；解析仍严格 fail-closed。更新对应安全日志测试，包含植入敏感哨兵的断言。
3. 定点跑 `backend/tests/test_analytics_agent_reviewer.py` 与直接受影响的 writer 测试，Ruff 仅检查改动文件。离线证明：已有合法 JSON 仍通过；各类别不泄漏；无工具、回调隔离、输入/输出/超时/次数上限均未放宽。这一轮不为分类增加无关的重复测试。
4. 若当前镜像不是代码挂载，**仅重建/重启必要的 Gateway 服务**以加载诊断，保留同一 Compose project 的 Redis/DB/前端、命名卷与现有合成数据；不反复重建整个栈。复用 DPAPI admin 和已验证的 `httpx` runner，发起**最多一次**明确报告的 `deepseek-flash` 真实 Gateway run。只记录同 run 的 tool 调用计数、稳定 code、成功 evidence 数、Reviewer 固定 stage+分类、固定 `finish_reason` 类别、报告索引/artifact 的状态；不保存模型正文、工具参数、SQL 或结果行。如果连模型前置门禁都失败，停止并报告，不把它算成模型解析证据。
5. 根据这次可复核分类修根因。若证明只是响应受 256 token 截断，先检查是否能通过更简洁的既有提示词/JSON 约束在原上限内解决；若必须改变上限或供应商 `response_format`，提供明确的 provider/SDK 证据、相应安全预算与文档更新，再做最小变更。若是模型输出了 fence/额外文本，不要静默放宽解析器；优先收紧请求格式或安全地重试有限一次，但必须保持总尝试上限、无内容外泄，并解释为何有效。若证据不足或需改产品安全承诺，停下报告，不盲试。
6. 修复后复跑直接受影响的定点检查；若第 4 步 run 未发布，**最多再执行一次**真实报告 run 验证修复。成功门槛：至少一条成功 evidence、writer 返回 `published` 或合法 `existing`、owner 报告索引可见、owner artifact 可访问、越权访问仍拒绝；不得把单纯模型 HTTP 200/Writer 被调用认作闭环。若第二次仍失败，停止并给出分类与下一步，不循环重试。

## 交付

- 生产变更限于 Reviewer 及其直接测试、确有必要的最小模型请求配置/说明；任何额外文件列明理由。新注释、测试场景说明、实施报告中文优先。`backend/uv.lock`、前端、业务数据库策略、MCP 与固定上游 tag 不动。保留固定栈与 DPAPI；旧 6F1 资源及历史残留目录不碰。
- 如果产生代码修复，一个独立提交；提示词原样保留，不 amend 已验收提交。提交后工作区干净。报告放 `.reviews/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`，含根因证据、改动范围、实际命令/结果、真实 run 数、闭环状态、未验证项与资源状态；只汇报安全枚举，不贴自由文本。
- **如果单次诊断已证明需要用户裁决，或实现仍不能达到闭环，停在 GPT 复验，不启动下一阶段。**不要用一系列微型 Fix 循环消耗模型与测试预算。
