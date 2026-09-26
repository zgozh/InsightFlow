# Phase 6F3C：真实模型 Reviewer 最小彩排（调查，不改代码）

你是 InsightFlow 的执行调查员。起点应为 6F3B2 Fix 01 `44d6057`，工作树干净。先读 `docs/acceptance/phase-06f1-real-analysis-rehearsal.md`、`.reviews/phase-06f3b1-reviewer-gate-report.md` 和本提示词，复用已有合成经营数据及隔离环境，不重做 6F1 的无关门禁。本轮是 **Spike**：只验证新 Reviewer 在真实 OpenAI 兼容模型上的可运行性，产出证据与建议；不改生产代码、测试、配置模板或验收状态，不提交实现。用户已批准用 `deepseek-flash` 做少量测试；模型 API Key 只从现有环境/私有配置读取，不打印值、不写入报告。

## 最小探针

1. 先只读核对当前 `main`、工作树、相关服务和现有合成环境是否可用。只检查密钥**是否存在**，不回显值；若不可用或模型凭证失败，停止并给出需要用户做的具体动作，不猜测/替换密钥。不修改 `backend/uv.lock` 或前端锁文件；需要 `uv` 时用 `--locked` 和官方 PyPI 索引，镜像 403 时可用现成 venv，不为这件事重锁。
2. 先做一次最小、受限的模型工厂 Reviewer 直连调用：服务端选择的 `deepseek-flash`、无工具、合成且很短的 title/Markdown/evidence 快照，验证 `max_tokens` 请求参数、响应内容与严格 JSON 解析、超时及 usage 元数据的实际形状。最多一次直连调用；若失败，停止，不盲目重试或放宽解析器。
3. 直连可行才做**一次**真实 Gateway 彩排：复用 6F1 的隔离合成 PostgreSQL/认证/分析线程路径，确认当前代码已生效；同一 run 从认证请求到 `inspect_business_catalog` → `query_business_data` → 内部 Reviewer → `write_analysis_report` → owner artifact GET。记录 Reviewer 是否通过、实际调用次数、是否有报告、前端或 API 安全轨迹是否能显示状态。允许一次模型主链运行，不能为了“增加信心”连续重复模型请求。若已有演示容器/卷，先精确识别项目归属，避免清理、重命名或覆盖其他 Docker 资源；需要构建/重启仅限该隔离项目，完成后保留并报告状态。
4. 若模型拒绝、格式不符、token 参数不兼容、20 秒 Reviewer timeout、Lead 未调用 writer，或报告未发布，只记录**首个真实失败点**与最小可行修复方案；不要现场改代码或把失败包装成通过。成功也只说明这一个合成样例闭环，不代表任意报告数字正确、AS-07/08/09/10 整体验收或默认四容器生产 Compose 已验收。

## 证据与边界

只运行此探针所需的 health/模型/HTTP/持久 readback 检查；不跑全量 pytest、Playwright、Docker 数据库门禁或重复 6F1 彩排。绝不在报告、日志摘录或聊天输出中粘贴 API Key、原始 SQL、结果行、token、DSN 或报告正文；可用计数、哈希、稳定码、状态和端点响应码表达。明确区分“真实模型”与“合成数据”，记录命令及退出码、容器名/镜像版本、是否复用既有卷、未验证项。输出到忽略的 `.reviews/phase-06f3c-real-reviewer-probe.md`，不要提交；完成后给 GPT 精要结论并停审查，不启动后续阶段。
