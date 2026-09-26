# Phase 6F3C Fix 01：DeepSeek Reviewer 出站 token 字段

你是 InsightFlow 的实施者。起点 `8ba15b1`，先读 `.reviews/phase-06f3c-real-reviewer-probe.md` 的“用户取消暂停后的续跑”与 `backend/app/analytics/agent/reviewer.py`；只扩展到直接关联的模型序列化与测试。Docker 隔离项目 `insightflow-analytics-demo` 已启动且专用卷保留。上轮真实 Provider 请求数为 **0**，Gateway 彩排数为 **0**；不要把本地 SDK 拦截说成远端拒绝。

## 已确认事实与目标

- Reviewer 传 `max_tokens=256`，当前 `ChatOpenAI` 在出站序列化时改为 `max_completion_tokens=256`。DeepSeek 官方说明明确要求 `max_tokens` 而非 `max_completion_tokens`：<https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/>；API 字段定义：<https://api-docs.deepseek.com/api/create-chat-completion/>。
- 在当前配置的 `deepseek-flash` Reviewer 调用中，实际 HTTP 请求体必须只携带 `max_tokens=256` 作为输出上限，不携带 `max_completion_tokens` 或无界默认值；保持无工具、同一 server-selected Lead base model、空 callbacks/tags/metadata、20 秒超时、严格 JSON、失败关闭、一次初审最多一次定向修订等现有契约。
- 只做最小的 Reviewer 专用兼容修复，不改全局模型工厂、不改普通聊天或其他提供方的语义，不为未来模型建立 provider zoo/通用适配层。若当前 SDK 无法在该局部可靠控制出站字段，先给出只读证据与最小备选方案并停止，不凭猜测调用真实 API。

## 一个连贯切片

1. 先用当前 venv 的离线序列化核对解释字段改写位置；选现有库支持的最小局部修复。新增/更新**一项有持久价值**的回归断言：用真实 SDK 序列化结果钉住 DeepSeek Reviewer 的请求体 `max_tokens=256` 且无 `max_completion_tokens`、无 `tools`；其他模型既有路径不变。不要仅测传给 `ainvoke` 的 kwargs。
2. 修改 Reviewer 的最小代码与直接关联测试。验证级别 V2：只跑 Reviewer 定点测试、该文件 Ruff check/format、离线序列化回读和 `git diff --check`；若变动触及共享工厂/配置则停下报告而不是扩大范围。不要重跑已有效的全量套件、前端、Playwright 或 Docker 数据库测试。
3. 当离线请求体已正确后，使用隔离项目中现有私有配置和 `deepseek-flash` 做**最多一次**真实 Reviewer 直连请求（当前预算尚未消耗）；凭据不打印、不写报告、不记录原始请求/响应、SQL、行或报告正文。记录远端是否接受、严格 JSON/usage 是否可读、稳定错误类别。不要自动重试；若失败，停止并报告第一个失败点。
4. 直连成功后才按 `docs/prompts/phase-06f3c-real-reviewer-probe.md` 做**最多一次**真实 Gateway 合成数据彩排：认证 → 同一 run 的工具 evidence → Reviewer → report writer → owner artifact GET，以及安全轨迹可见性。只使用隔离项目和已有卷，不动别的 Docker 项目。失败时停止，不现场扩大修复。
5. 在 `.reviews/phase-06f3c-fix-01-report.md` 记录精准文件范围、离线/定点门禁命令和结果、真实请求次数、Gateway 结果、未验证范围及容器状态；更新 `.reviews/phase-06f3c-real-reviewer-probe.md` 的最终续跑事实。修复代码、测试与本提示词形成**一个独立提交**；验收文档状态仍待 GPT 审查，不自行宣布 6F3 整体完成。

## 安全与停线

只报告安全元数据、稳定代码、计数、HTTP 状态、摘要；不得输出 API Key、原始 SQL、结果行、plan token、DSN、报告正文或模型自由文本。`uv` 一律 `--locked`，不要重写 lockfile。工作区若不干净，先判断归属。任何实测与本提示词不一致，停在明确的第一个边界并如实报告，不进行盲目重试或大范围重构。
