# Phase 6E2B2A：受控分析专用报告写入（后端，仍不启用运行）

你是 InsightFlow 实施 Agent（`gpt-6-luna`，max），GPT 只负责方案与复验。先读全局/根/涉及模块 `AGENTS.md`、`.reviews/phase-06e2b2-safe-report-artifact-feasibility.md`、`docs/prompts/phase-06e2b1-analysis-tool-allowlist.md`。从本提示词提交后的干净 main 开始；若不符先报告。上游固定 tag/tree、依赖与 lockfile 不动。不要读取或输出真实 `.env`、`config.yaml`、`os.environ` 或业务行值。本片只补**后端专用 Markdown 报告工具**；不得解除 `analysis_mode_unavailable`、改前端停用页或宣称 Phase 6/AS-14 完成。

## 已批准的设计边界

`publish_analysis_report` 现有工具只登记索引，不能证明文件存在；通用 `write_file`/bash/AIO shell 不能给受控分析。复用现有 `PublishAnalysisReport` 用例、线程所有者保护的 artifact GET、`resolve_outputs_confined_path` 和 Markdown 预览合同，**不要**复用仅用于编辑已存在文件的 PUT。用户已接受 AS-13 边界：任意模型正文/artifact 内容不保证绝无敏感文本；但平台派生的审计和外发/持久化事件投影不得把原始 SQL、token、凭据或结果行当作结构化字段外泄。

1. 新增仅供 analysis 构图使用的 `write_analysis_report(title, markdown, evidence_ids, runtime)`。模型 schema 只有这三个字段，不能接受 principal/thread/run/path/filename/URL/credential。由 Gateway 在已认证、持久化标记的 analysis run 中注入一次性、单用途写入能力；该能力闭包绑定可信 principal/thread/run 与存储根目录，客户端 `context/configurable` 同名字段必须被过滤。工具入口再次校验受信身份/标记与能力绑定，不以模型或传入配置自报授权。普通聊天工具表保持原样，不能获得新 writer。
2. 路径由服务端确定，为该用户、线程和运行下唯一的 `/mnt/user-data/outputs/analysis-report-{run_id}.md`；`run_id` 必须先作严格安全标识校验。只写 UTF-8 Markdown，拒绝 NUL 和超限正文（可沿用现有文本 artifact 的 2 MiB 上限），不接收模型指定路径或 HTML 文件类型。使用现有 outputs confinement 再作实际路径/符号链接检查；不得写到 Gateway 任意路径。使用 create-only 语义：同 run/同正文完成后重试可复用，异正文绝不覆盖。并发重试至少不得覆盖或返回错误成功；若现有存储抽象无法安全实现，停止并报告具体接缝。
3. 文件成功写入后才调用现有 `PublishAnalysisReport` 登记索引。文件与 DB 无共同事务：索引失败时返回稳定失败、不得发成功回执；允许留下该线程中的未索引孤儿文件，后续同正文重试可复用并重试索引。不要引入队列、表、迁移或通用文件事务框架，也不要删除可能被并发重试使用的文件。报告发布成功/既有相同记录时，结果只包含安全的状态、报告 ID、服务端路径与 evidence ID，不返回 Markdown 正文或内部身份字段。旧 `publish_analysis_report` 合同不变。
4. 在 6E2B1 的**固定来源正向白名单**中仅为 analysis 增加此 writer，精确来源验证后模型绑定与最终 ToolNode/dispatch 同一集合；普通聊天不能拿到它，也不能恢复通用文件、MCP、bash、task 或动态插件。只有此工具的成功结果可进入报告 artifact 回执；不扩大 `present_files` 或任意 outputs 的可信范围。
5. 新工具的 `markdown` 参数会进入模型内部 tool call；内部消息保持完整，但 SSE、RunJournal、历史 events/messages/checkpoint seed 的外发/持久化副本不得把该大段正文再复制为结构化工具参数。沿用 6E3A 投影接缝，按**精确工具身份**在副本中遮盖 `markdown`，保留安全元数据；增量 chunk、无名/模糊块仍按既有保守策略处理，不使普通流中止。不要把这一条误写成“artifact 正文已自动脱敏”：正文仍是用户/模型文本，仅受线程权限保护。

## 最小充分证据

按安全敏感 V3 做有价值的合成哨兵回归：真实工具 schema 不含身份/路径；伪造 context 不能取得能力；普通聊天无 writer，analysis 图精确为 catalog/query/writer，伪造其他 tool_call 在执行层拒绝；合法 Markdown 写到唯一受限路径并能经现有 owner-check GET 读取，跨线程/符号链接/超限/NUL/HTML 路径拒绝；同正文重试、异正文冲突、索引失败与恢复的结果准确；只有发布成功有报告回执；外发 SSE/journal/历史不含 Markdown/SQL 哨兵而内部模型消息保持原样。测试使用合成用户、文本和临时存储，不能断言或展开真实进程环境。只跑直接受影响的 backend 测试、Ruff 与 diff 检查；不机械跑 14k 全套、Docker、Playwright、真实模型或数据库。只有发现具体跨边界问题才扩大。

若身份注入、outputs confinement、索引失败语义、执行图或事件投影有任何一项无法证实，保留分析运行拒绝，不提交宣称成功的半成品，报告精确缺口。成功则独立一个提交，更新直接相关 `AGENTS.md` 与 `docs/PROGRESS.md` 为“本切片待 GPT 复验、分析仍未启用”，工作树干净；报告 commit/parent、文件范围、真实门禁及未验证项。停在 GPT 复验，不启动前端或后续阶段。
