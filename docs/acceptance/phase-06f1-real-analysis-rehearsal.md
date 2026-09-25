# Phase 6F1：受控经营分析真实链路彩排

日期：2026-09-26（Asia/Shanghai；run 创建时间为 `2026-09-25T16:13:12.248739+00:00`）

基线：`main` 起点 `1f2ecc4`，包含 6E2B2B 实现 `f48731c`；`upstream-v2.1.0-rc0` tag/tree 一致，起始工作树干净。
结论：隔离合成 PostgreSQL 上的一条 NGINX 登录、持久 analysis thread、真实 `deepseek-flash` 调用、受控查询、run-scoped 报告写入及同线程读取链路已实测；这只是 6F1 窄范围彩排，**不是 AS-01..AS-15 或 Phase 6 的整体验收**。待 GPT 独立复验。

## 隔离环境与门禁

- Docker Engine `29.1.2`、Compose `2.40.3` 可用。唯一操作的 Compose project 为 `insightflow-analytics-demo`；启动前其容器、卷、网络为空，`127.0.0.1:2027` 空闲。未操作其他 checkout/project，也未使用 `down -v` 或 prune。
- 仅使用被 `.gitignore` 忽略的 `.analytics-demo/`、`.env.analytics-demo` 和该 project 的容器/卷。未覆盖根 `config.yaml`；模型 key 只检查当前 `.env` 中 `DEEPSEEK_API_KEY` 是否存在，不读取或回显值。演示模型 ID 精确为 `deepseek-flash`，使用 `https://api.deepseek.com`，第三方 tracing 未启用。
- 固定上游 tag/tree 未改。Compose 静态渲染退出码 **0**：

  ```powershell
  docker compose -p insightflow-analytics-demo --env-file .env --env-file .env.analytics-demo -f docker/docker-compose.yaml -f docker/docker-compose.analytics-demo.yml -f docker/docker-compose.analytics-demo-app.yml config --quiet
  ```

- 隔离栈首次启动使用同一 `-p`、双 `--env-file` 与三个 `-f` 参数执行 `up -d --build --wait`，退出码 **0**。最终包含 Nginx、Frontend、Gateway、Redis 与专用 PostgreSQL 16 五个健康容器；只有 Nginx 发布 `127.0.0.1:2027`，Gateway/Redis/PostgreSQL 均无宿主机端口。PG 是合成业务数据源，不是应用持久化数据库。
- 发现 6D2 文档中的 PowerShell 步骤会把 JSON 内转义的 PEM 换行解码成真实换行，且 shell 覆盖优先于 Compose env-file。只修正了 Git 忽略的演示凭据 payload，使 `ca_pem` 是合法 PEM 字符串，并仅从当前启动进程清除 `ANALYTICS_DEMO_READER_CREDENTIAL` 覆盖，由指定 env-file 原样提供 JSON；保留 `verify_full` 与证书校验。经应用实际 `EnvironmentDatasourceSecretResolver` 得到 `resolved=true`、TLS context 可用。之后只重建目标 Gateway：

  ```powershell
  docker compose -p insightflow-analytics-demo --env-file .env --env-file .env.analytics-demo -f docker/docker-compose.yaml -f docker/docker-compose.analytics-demo.yml -f docker/docker-compose.analytics-demo-app.yml up -d --no-deps --force-recreate --wait gateway
  ```

  退出码 **0**，resolver 复核成功；未改安全逻辑或 TLS 模式。对应的最小操作说明更正见[本机试用指南](../LOCAL_TRIAL.md#启动与停止)。

## 真实请求与运行证据

通过 Chromium/Playwright 驱动的浏览器会话从 `http://127.0.0.1:2027` 进入 NGINX：根页、`/setup` 返回 200；未登录 Analytics/线程 API 返回 401；隔离演示管理员首次设置成功（201）并登录。页面为中文 locale，用户在 `/workspace/analysis/new` 提交一个对合成订单可确定性复算的问题。未用 fake model、直接文件写入或绕过 Gateway 的 Agent run。

本次有 1 次模型调用前 fail-closed 的预检 run：因演示配置缺少两个精确 allowlisted tool entry 而失败，没有 LLM/tool/audit 事件。只在忽略的演示 `config.yaml` 中补齐 `inspect_business_catalog` 与 `query_business_data` 的本地工具声明后，另有 2 次带模型的 run 尝试；未记录模型 API 请求总数：

1. 第一次带模型的 run 尝试 `7b0ff6a7-0175-402e-a048-8621e595046b` 有模型与工具事件，但凭据解析仍失败，审计出现 `secret_unavailable`（3 条）与 `unknown_relation`（1 条），没有报告。根因为演示 CA JSON 序列化及 env 优先级覆盖，已按上节保留 TLS 的方式修复；没有放宽查询或失败关闭边界。
2. 第二次且最后一次带模型的 run 尝试成功。持久线程 UUID：`8f675187-c9f6-430b-acae-fe09f9153e69`；run UUID：`2295b2fa-1d9e-46ca-a462-662abbd91579`；运行状态 `success`。匿名化请求身份链如下：

   | 请求/记录 | 结果 | 身份证据 |
   | --- | --- | --- |
   | `POST /api/threads`，`kind=analysis` | 200 | Gateway 持久化线程 `8f675187-c9f6-430b-acae-fe09f9153e69`，`analysis_mode=true` |
   | `POST /api/langgraph/threads`，同 `kind` 与 UUID | 200 | SDK 的 create 请求对应同一条 Gateway 持久记录 |
   | `POST /api/langgraph/threads/8f675187-c9f6-430b-acae-fe09f9153e69/runs/stream` | 200 | thread-scoped stream 使用同一 UUID |
   | `GET /api/threads/8f675187-c9f6-430b-acae-fe09f9153e69` | 200 | 返回的服务端 thread ID 相同且 `analysis_mode=true` |

   run 事件共 **14** 条，类型包括 `run.start`、`llm.human.input`、`llm.ai.response`、`llm.tool.result`、`run.end`、`workspace_changes`、`run.delivery`；工具事件包含且仅观察到固定分析链所需的 `inspect_business_catalog`、`query_business_data`、`write_analysis_report`。线程 token usage 查询为 200，`by_model` 精确为 `deepseek-flash`，token 数为正，`total_runs=1`。

## 查询、审计和报告

- 同一隔离 PostgreSQL 的 API 定点控制查询返回 200、单行、48 bytes，复算结果与 fixture 预期 **540.00** 一致，未在此文记录 SQL、凭据、查询 token 或结果行。该控制查询不是额外模型调用。
- Agent run 的 audit 时间窗内观察到 `function_not_allowed` 1 条，随后 `plan_created` 1 条与 `executed` 1 条；执行记录 `row_count=1`、`byte_count=56` 并含 query hash。报告的合成金额与 540.00 预期相符，报告引用的 evidence ID 与成功执行 evidence 对应。审计表不含 run ID，因此这里仅按运行时间窗及顺序关联，不声称数据库审计 schema 提供了直接 run 外键。
- 同一管理员的报告列表返回 200；索引记录 `published`，report ID `e1afbac9-58e7-443b-a0d6-f4035136c3ce`，关联上述 run，artifact 为 `/mnt/user-data/outputs/analysis-report-2295b2fa-1d9e-46ca-a462-662abbd91579.md`，引用 evidence ID `4b3cfe5ab0e2b1b96ce837269f957b37d25696652b389412fa05381281557f21`。通过同线程 Gateway artifact GET，所有者读取返回 200。artifact 正文只为核对本次合成数值/evidence 关联而读取；**没有扫描或声称任意自由文本、模型回复或 artifact 正文不存在敏感内容**。
- 对另一线程 UUID 请求同一 artifact 得到 404，证明此次跨线程拒绝；这不是不同真实用户之间的完整跨主体测试。
- 管理员 API 对 PII 列 `customer_email` 的计划请求返回稳定拒绝码 `sensitive_column`，未生成 plan ID。另一次 Agent 候选函数请求以 `function_not_allowed` 被拒绝后，模型沿授权路径成功规划并执行。这里不据有限拒绝样例声称完成 AS-04/05 全部负例矩阵。

## 相关文档及未覆盖项

- 6D2 文档只更正了演示 JSON/env-file 的序列化与优先级操作步骤，未更改默认 Compose、生产配置、resolver、安全逻辑、TLS 校验或凭据值；详情见[本机试用指南](../LOCAL_TRIAL.md#启动与停止)。
- AS-01 仅新增隔离管理员登录与单一线程所有者读取证据；完整多主体 thread/run/artifact 隔离未验证。AS-03 新增 PostgreSQL + 真实模型窄链证据，但不等于所有 PostgreSQL 行为契约完成。AS-10 证明本次 run-scoped 报告发布/读取，不具备 Reviewer 复核或普遍数字/evidence 校验；AS-14 仍为发布阻塞，因为普通聊天 operator MCP 不受平台 Query Policy 约束，且更广的 fail-closed/热更新等契约仍需独立验收。AS-13 不因本次 live run 升级：没有审查全部结构化输出/历史/可选 tracing 导出的机密边界；自由文本和 artifact 正文明确不在无敏感信息保证内。
- 本轮只用了 PostgreSQL 隔离 overlay；未运行 MySQL 模型分析、默认四服务 AS-15 全链、应用 PostgreSQL 重启恢复、计划分析、Reviewer 工作流、第三方 tracing、全量后端/Playwright/build，也未启动 5C。尚未进行演示栈清理；按 6F1 默认策略保留 `insightflow-analytics-demo` 容器与合成 PostgreSQL 卷供操作者复验。未保留私有凭据或自由文本日志到仓库。

本证据记录本身不构成发布签字。下一门为 GPT 对本切片与相关待复验实现的独立复验。
