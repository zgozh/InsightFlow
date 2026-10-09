# InsightFlow 任务中断点

最新最终收尾：功能组合验收通过，AS11服务器确定性计算后的唯一自动任务也成功；Windows残差定点修正及共享proxy参数复验通过。原29384已一次升级、52文件全apphome备份保留、独立首页/health/ready200与匿名401通过，原PG/Redis/Nginx和卷未变；29388也保留。Root已接受最终源码与306文件暂存审查；本状态记录截于发布提交前，commit/push状态以Git记录为准，远程CI结果以Actions为准（本记录形成时尚未运行）。原Apply退出码未取回不能冒称exit0，禁止重放Apply。所有private IDs/claim保存在忽略目录，不能删claim盲重发。准确最新状态以[PROGRESS.md](PROGRESS.md)顶部为准。下方此前恢复/暂停事实均为历史。

历史恢复检查（2026-10-09早期，后续进展见本页顶部及 [PROGRESS.md](PROGRESS.md)）：当时任务处于继续执行状态，完整发布尚未验收。29388既有四服务和PG fixture已按用户新授权恢复；当时真实正例已唯一执行，首次查询成功但最终run error，后续有policy_denied/attempt_limit/numeric_validation_failed。claim已存在，禁止删除重发。私有context与安全终态摘要保存在runtime-probes；当时下一步是只读诊断已有运行，再定点修复。文档须中文默认、仅中英文、清理过时内容；全部验收后commit/push。勿重复构建、初次Apply或删除保留数据。以下为历史暂停记录，不覆盖当前事实。

保存时间：2026-10-08 00:52（Asia/Shanghai）。该暂停记录已被用户随后明确提出的“继续任务”撤销，任务恢复执行。以下保留暂停时事实，当前进展以 [PROGRESS.md](PROGRESS.md) 顶部为准：指标授权前后端与隔离真实验收已闭合，29384原入口已恢复；正在推进固定内部角色与可验证报告接线。

工作区：`D:\develop\workspace\InsightFlow`，分支 `main`，HEAD `a678d54`。本轮大量修改尚未提交、未 push，必须保留所有已修改/新增文件，不能 reset、clean 或覆盖。实施默认 `gpt-6-luna` / max，主会话规划和独立审查；提示词先落盘。停止时没有发现匹配本次指标测试的 Python/uv/pytest/ruff 进程；既有应用服务未主动停止。

## 最近的用户问题与结论

普通账号看到数据源、指标、报告、审计为空。空状态本身是设计范围，但普通账号应能分析获授权资源：管理员登记治理资源并授权，普通用户执行受控查询、发布报告和查看自己的审计。

- 数据源空：未登记或缺精确 principal policy；不能仅凭提示确定是哪一种，未修改真实账号权限。
- 指标空：已确认功能缺口，原 SqlMetricRepository 仅按创建者读取，没有共享授权路径；已开始补齐显式 grant。
- 报告/审计空：当前账号尚无发布报告/受控查询记录，不能通过共享指标开放他人的报告或审计。

## 当前切片：指标显式授权（中断，未验收、未部署）

实施者 `/root/metric_grants_backend_luna` 已中断。冻结契约在 [后端实施提示词](prompts/2026-10-08-metric-grants-backend.md)。实施者的初步说明在 [切片验收文档](acceptance/2026-10-08-metric-grants-backend.md)，该文档还没有最终检查结果，不能当作验收通过。

已经实际落盘：

- MetricRepository 增加 exact-owner 管理读、授权列表、grant/revoke；普通目录按 ACTIVE + owner 或精确 grant 读取，跨 owner 同 key 对当前用户发生歧义时隐藏，不随意选取。
- AnalyticsAdministration 管理读取和授予/撤销先检查 exact-owner；grant 与数据源 policy 独立。
- `analytics_metric_grants` 表及 additive `0004_metric_grants.py`（接0003）；授权只引用 Analytics 的指标表，不引用 Harness 身份表。
- 管理 HTTP：GET `/metrics/{metric_key}/grants`；PUT/DELETE `/metrics/{metric_key}/grants/{principal_id}`，统一置于现有 analytics/admin 前缀及管理员门禁，当前 owner 从认证上下文取得。
- 直接相关 repository / management / API / migrations 回归测试；未做前端接线。

涉及 `backend/app/analytics/{application/persistence_ports.py,application/management.py,infrastructure/persistence/catalogs.py,infrastructure/persistence/models.py,api/models.py,api/router.py}`、0004 migration、相关 backend tests 和 Analytics AGENTS。部分文件同时承载此前耐久 evidence 未提交修改，独立审查要区分切片。

最后已报告验证：首轮定点 pytest **123 passed / 3 failed / 1 warning**。失败初步定位：API 用例误期望管理员自己的 ACTIVE 指标不可见；空库 bootstrap 尚断言0003；0001→0002 报告迁移基线表集合误包含0004。实施者称正在修这三项，暂停前没有回报复验结果，因此仍记为未闭合。Ruff lint 与 git diff --check 已报告通过；format --check 指出 management/catalogs/migration-test 三文件需格式化，未收到最终通过结果。主会话还没有独立审查生产 diff，不能宣称修复完成。

恢复后先读实际 diff 和失败断言状态，再派 Luna 完成最小修补与定点复验；若只是格式调整，不重复已有效测试。后端冻结并经主会话审查后，再写前端提示词并接管理员授权面板/严格 schema/API/hooks/i18n，补普通账号授权后的使用路径。不要自动授予当前真实账号权限、填充伪审计、改演示业务数据或直接运行0004到旧部署库。

## 此前已保留的有效证据

- 黑洞粒子首页、真实 EHT favicon/署名、InsightFlow 品牌与五语言 README/主要文档完成，固定入口29384 Frontend 已部署；完整截图、检查与回滚信息见 [首页报告](acceptance/phase-06f3f21-immersive-black-hole-landing.md) 和 [品牌报告](acceptance/2026-10-07-insightflow-product-documentation.md)。LICENSE 必要版权声明和机器包/配置名保留。
- AS-01 认证隔离、AS-15 默认四服务/readiness 已接受；AS-14 按批准边界接受。完整15场景仍有12项未全部闭合，不能按场景数量换算工作百分比。
- MEDIUM 查询预算收紧代码与定点证据已接受，真实双数据库 AS-06 仍待完成，见 [预算报告](acceptance/2026-10-07-as06-medium-budget.md)。
- 耐久查询证据 foundation 已实现并独立复核，最近证据 DTO/codec/边界定点 **59 passed**，Ruff/format/diff 已通过。零行成功、失败带证据、坏摘要、高风险/阻断证据拒绝已修。见 [foundation 报告](acceptance/2026-10-07-durable-query-evidence-foundation.md) 与 [复核提示词](prompts/2026-10-08-evidence-review-fixes.md)。尚未接 Gateway/query tool/artifact；不能声称重启恢复链完整。

## 最终边界与后续顺序

用户选择 **AS-01～AS-15 完整发布验收**，目标仍继续。2026-10-08 最新范围裁决为 PostgreSQL（AS-03）必验，MySQL 作为 AS-02 可选适配；既有 MySQL adapter/usecase 与双库真实记录保留，不再要求追加 MySQL 自然语言模型、HTTP 或事件验收。参考 [总计划](superpowers/plans/2026-10-07-full-release-acceptance.md)、[本次范围记录](acceptance/2026-10-08-postgres-only-acceptance.md)、[差距盘点](acceptance/2026-10-07-full-release-gap-audit.md)、[架构决策0005](decisions/0005-controlled-analysis-evidence-and-roles.md)。

恢复顺序：指标授权后端闭合和前端接线 → Gateway 耐久 evidence / 固定结果 artifact bridge → App-owned 受限 SQL Analyst / Data Analyst / Reviewer / ReportWriter 调用与确定性数字口径核验 → 安全结构化阶段事件/SSE/回放 → PostgreSQL 必验真实分析与风险/超时/截断（AS-03）；MySQL 保留可选 adapter/usecase 与既有双库证据，不追加自然语言模型/HTTP/事件验收 → 定时分析及 PostgreSQL 应用库重启恢复 → 全部场景最终裁决。角色接线当前冻结待主会话审查，阶段事件与其余未完成场景仍须按完整发布计划验收。

保持 analysis 最终可见三工具 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`，不以补角色为由开放 task/MCP/bash。普通聊天已有子 Agent、工具与其他能力继续保留。角色必须是有界真实调用，不以提示词标签冒充 Agent；MetricService 是服务。AS-13 保证只限批准的结构化投影，不扩成任意自由文本无敏感内容保证。

## 运行环境与暂停后恢复注意

- 固定演示 project `insightflow-acceptance-local`，入口 `http://127.0.0.1:29384`，五容器/三卷。29384 与根 PORT 存在漂移，不能 full-stack up 导致换端口；不删除已有容器和卷，Frontend 曾单独更新并保存回滚 tag。
- 独立 AS-01/15 栈 `as01-as15-1bf6932f3abd`，入口29385、默认四服务、SQLite；忽略目录 `.reviews/as01-as15-1bf6932f3abd/` 保存 compose/overlay/probe/DPAPI fixture。恢复时先检查实际状态，不假设暂停时服务仍 running。
- 既往 Gateway/Frontend/Nginx 自动启动曾被主机审批以 blocked by policy 拒绝，用户手动启动。不得绕过拒绝，也不能把用户以前手动启动的回复当成现在服务状态；仅必要时说明真实阻塞。
- 凭据/模型配置只在进程内读取，禁止输出 DPAPI 内容、DSN/token、SQL/结果行或模型原始消息。不要重跑已经有效的 welcome surprise run，也不发无必要模型请求。
