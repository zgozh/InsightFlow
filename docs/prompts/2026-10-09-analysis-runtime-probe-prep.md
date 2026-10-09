# PostgreSQL 真实分析验收探针准备

gpt-6-luna/max。生产源码已冻结并独立审查，另一实施者正构建 Gateway 并启动新 iflow-final-pg-20261008 / 127.0.0.1:29388。你只拥有 `.reviews/final-postgres-runtime-20261008/runtime-probes/` 新探针文件和 `docs/acceptance/2026-10-09-analysis-runtime-probe-preparation.md`。不写 launcher、config、Compose、生产源码或其他记录，避免与启动切片重叠；不启动容器、不触发实际 API mutation 或模型，待主会话统一审查后再执行。

复用已有同机真实 auth/metric-grants/API/browser fixtures 脚本模式，rg 找对应文件，不读取输出已有账号密码。仅读 AS验收场景、API路由与服务的直接契约；不重做角色链/源码盘点。任务是把下一切片可执行探针准备好，不产长泛化计划。

准备脚本和最小运行说明：
- 只绑定新项目29388，身份 guard 必须验证新 Gateway/Frontend image IDs，不允许错操作29384/29385。新合成 admin A/普通 B，账号密码 DPAPI CurrentUser 存储，不能明文落盘或对话打印。admin角色仅赋予新合成fixture用户，方法沿用已有真实fixture，不修改真实账号。此切片先写脚本，不执行seed。
- 合成业务PG analytics_fixture_20261008.public.monthly_metrics 仅三行 period/revenue/users/description/customer_email。登记 datasource 使用服务端 env://ANALYTICS_CQ_PG_READONLY_CREDENTIAL（TLS verify_full）；模型/访问策略只允许 period/revenue/users，禁止description/customer_email。登记并启用 revenue 指标、显式授予 B 数据源/指标访问权限，保留 adminA/B403/anon401 对照。API schemas 以实际源码为准。
- 下一执行切片只计划一次 B 的真实模型 positive run：context选择已有deepseek-flash，可信分析模式，问题请求逐月 revenue 和合计，不制造 currency 单位。预期合计3901.25，月份原值1200.50/1800.00/900.75。必须检查实际工具执行、独立角色顺序、不可变 query artifact、报告索引/预览/download 以及平台结构化字段安全。不要仅run success就判链路通过。
- SSE custom analysis_stage 按(run_id, metadata.seq) 去重；和 GET durable events 完整匹配包括 workflow 终态。分页用 record.seq。事件meta字段闭合，不输出SQL/结果/凭据/自由正文。正例报告正文可以在内存按合成 oracle 核对，但日志仅safe布尔/hash/count/稳定code。
- 浏览器普通B应看到已授权 datasource/metric，执行后看到报告/本人审计；普通B无admin控制、刷新阶段历史存在。可复用现有 Playwright harness，不另搭框架。
- 为后续 AS04/05、AS11/12 留明确调用入口，不在此切片扩展实现全部失败矩阵/调度/恢复脚本。正例脚本应失败时停止并记录具体safe gate，不自动盲目重发付费model run。

V0/V1准备检查：脚本语法编译/AST、schema字段和对应调用readback即可，不打未启动API、不跑应用suite、不调用model。冻结actual files、用法、直接检查，并明确哪些准备与真实验收尚未执行。
