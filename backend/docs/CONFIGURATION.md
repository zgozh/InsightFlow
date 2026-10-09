# InsightFlow 配置指南

运行配置以仓库根目录的 `config.yaml` 为主，MCP 服务与技能启用状态放在
`extensions_config.json`。从 `config.example.yaml` 和
`extensions_config.example.json` 复制生成；这两个运行文件应保持在 Git 忽略列表内。

## 配置路径与加载

`config.yaml` 依次从显式路径、`DEER_FLOW_CONFIG_PATH`、当前目录和仓库根目录解析。
`extensions_config.json` 使用对应的 `DEER_FLOW_EXTENSIONS_CONFIG_PATH`，并沿用相同
的显式路径优先规则。环境变量值可写成 `$OPENAI_API_KEY`；缺失变量解析为空字符串。
不要把真实密钥写入示例配置或提交到仓库。

Gateway 请求会通过 `get_app_config()` 读取应用配置。模型、工具、标题、摘要和记忆等
运行选项通常在下一次请求时生效；数据库、沙箱、插件、调度器、MCP 长任务和其他在
`STARTUP_ONLY_FIELDS` 中登记的基础设施字段需要重启 Gateway。Analytics 限额在启动时
解析并冻结。修改配置结构时要同步增加示例文件中的 `config_version`。

## 模型、工具与技能

- `models[]` 声明可供用户选择的模型；每项包含 `name`、`use`、模型标识、服务端
  密钥和能力字段。示例配置给出 OpenAI 兼容接口及 DeepSeek 接口用法。由可信扩展提供
  的模型类应使用其文档给出的导入路径。
- `tools[]` 和 `tool_groups[]` 决定 Lead Agent 可用的文件、命令、网页研究及 Analytics
  工具。当前内置网页路径为 DuckDuckGo 搜索和 Jina 抓取；抓取只取回网页正文，不提供
  浏览器控制或图片搜索。
- `skills.path` 指向 Gateway 主机上的技能目录，`skills.container_path` 是沙箱内对应
  的绝对路径。提交到仓库的公共技能位于 `skills/public/`；用户技能和凭证留在运行环境。
- `extensions_config.json` 管理 MCP server 配置和技能启用状态。`middlewares`、第三方
  Python 插件及模型导入路径可以执行代码，只能配置可信来源。运行时可变的 MCP 与技能
  字段由 Gateway API 原子写入扩展配置。

普通子代理通过内置 `task` 工具运行；`subagents` 可调节其模型、超时、工具和技能策略。
这不等于已删除的独立 Custom/Managed Agent 管理产品。定时任务固定使用 Lead Agent。

## 数据库、认证与调度

`database` 选择 Gateway 持久化后端。Analytics 需要 SQLite 或 PostgreSQL 等持久化数据库；
`database.backend: memory` 时不会运行 Analytics 迁移，Analytics API 返回 503。多 worker
部署应按示例配置 run ownership 与 Redis stream bridge，并确保实例时钟同步。

`run_events.backend` 默认是 `db`，复用 `database` 选择的应用数据库；按示例配置时写入
SQLite 应用库，并在 Gateway 重启后保留。`memory` 仅适合显式选择的临时/开发运行，进程
退出后 events/messages 丢失；切换到持久后端不会补回此前未持久化的事件。`db` 要求
`database.backend` 为 `sqlite` 或 `postgres`；若应用数据库仍为 `memory`，运行时会回退到
内存事件存储。单节点且希望独立文件存储时可显式选择 `jsonl`。

`auth` 管理本地登录与 OIDC 登录选项。PAT、账户偏好、thread/run 隔离及服务端授权由
Gateway 控制；客户端提供的身份字段不能覆盖认证上下文。

`scheduler.enabled` 控制定时任务后台服务。计划运行是非交互的，并使用标准 Gateway
Lead Agent 生命周期。队列超时、并发数和轮询间隔在 `scheduler` 中配置。
`mcp_tasks` 是可选的普通 MCP 长任务状态追踪器，不是 Agent 产品或子代理批次系统。

## 沙箱

### Local

Local sandbox 在 Gateway 主机进程中执行命令，仅适用于可信开发环境。它不是安全隔离
边界。其命令子进程只继承固定的精确环境变量白名单：`PATH`、`PATHEXT`、`COMSPEC`、
`SYSTEMROOT`、`WINDIR`（命令查找和 Windows 进程启动）；`HOME`、`USERPROFILE`、
`HOMEDRIVE`、`HOMEPATH`、`PWD`（用户目录与当前目录）；`TMP`、`TEMP`、`TMPDIR`（临时
文件）；`SHELL`、`VIRTUAL_ENV`（shell 与 Python 虚拟环境识别）；`LANG`、`LANGUAGE`、
`LC_ALL`、`LC_COLLATE`、`LC_CTYPE`、`LC_MESSAGES`、`LC_MONETARY`、`LC_NUMERIC`、
`LC_TIME`（本地化）；`TERM`、`COLORTERM`（终端行为）。Windows 名称匹配不区分大小写，
POSIX 名称匹配大小写精确。其他 Gateway 变量按名称默认全部排除；HTTP/HTTPS/ALL proxy
变量可能携带凭据，因此不继承。`NO_PROXY` 同样不继承：它会改变代理绕过路由，启动命令
不需要该设置。技能需要的凭据必须通过 `required-secrets` 和本次请求的 `context.secrets`
显式注入；注入值不会从同名的 Gateway 环境变量自动取得。

### AIO

AIO sandbox 在独立容器中运行 Agent 命令。设置 `sandbox.use` 为
`deerflow.community.aio_sandbox:AioSandboxProvider`，并按
`config.example.yaml` 中的 Option 2 配置 Docker socket、镜像和资源限制。容器网络策略
需要受支持的 Docker Engine；外部网络访问应按业务需要限制。容器环境只由显式配置的
`sandbox.environment` 构造；值写成 `$NAME` 时会从 Gateway 环境解析。该配置是运维主动
授权将指定值传入 AIO 容器，平台无法阻止运维主动映射 Analytics 数据源凭据；除非这种
暴露确有意图且已单独控制，不要配置此类映射。

仓库也保留 AIO 外部 provisioner 的客户端配置。配置 `provisioner_url` 表示 Gateway
连接使用方单独部署的兼容服务；本仓库不包含、不启动也不提供该服务端。服务端的部署、
隔离、网络策略和 API key 管理由服务运营者负责。通过不可信网络连接时使用 HTTPS，不能
通过公网明文 HTTP 发送 API key。共享线程目录只有在两端确实挂载同一用户/线程目录时
才能声明 `thread_data_mounts: true`；否则保留文件同步。

## Analytics governed query

`analytics:` 配置认证后的受控查询 API 和报告索引。字段由
`app.analytics.config.AnalyticsConfig` 严格解析，未知字段或不合规类型会阻止 Gateway
启动；限额在启动时冻结。Datasource 保存不透明的 `secret_ref`，例如
`env://ANALYTICS_DS`，实际数据库凭证从受限环境变量解析。

| 字段 | 默认值 | 作用 |
| --- | ---: | --- |
| `enabled` | `true` | 关闭时 Analytics 路由返回 503 |
| `query_max_rows` | 1000 | SQL 计划可授权的最大行数 |
| `connect_timeout_ms` | 3000 | 数据源连接超时 |
| `statement_timeout_ms` | 5000 | 单条语句超时 |
| `cancellation_grace_ms` | 500 | 取消查询后等待连接清理的时间 |
| `max_estimated_rows` | 100000 | 查询计划估算行数上限 |
| `max_engine_cost` | `"100000"` | EXPLAIN 成本上限；使用十进制字符串或整数 |
| `max_explain_bytes` | 1048576 | 计划文档字节上限 |
| `max_result_columns` | 128 | 返回列数上限 |
| `max_result_rows` | 1000 | 结果行数上限，不得高于 `query_max_rows` |
| `max_result_bytes` | 1048576 | 结果大小上限 |
| `plan_ttl_seconds` | 60 | 一次性查询计划有效期 |
| `audit_page_size` | 50 | 审计与报告索引的默认分页大小；服务端上限为 100 |

LOW 风险查询沿用启动配置；服务端把 `max_result_rows` 与授权 SQL 行数取较小值，因此查询
自身的 `LIMIT 10` 不会被默认值拒绝。MEDIUM 风险以语义授权结果为准，将全局
`statement_timeout_ms`、`max_result_rows` 和 `max_result_bytes` 分别减半（向下取整，并保持
领域下界），再将行数预算与授权 SQL 行数取较小值。若某项全局预算已到合法下界、无法严格
收紧，服务端写入 PLAN 阶段拒绝审计并以 `cost_limit_exceeded` 返回，不签发计划；审计不可用时
返回 `audit_unavailable`。客户端不能提交或提高这些限制。

凭证引用所指向的 JSON 环境变量包含 `engine`、`host`、`port`、`database`、
`username`、`password)，并可包含 `tls_mode` 或 `ca_pem)。关闭 TLS 仅允许连接
loopback 主机。Agent 的 `inspect_business_catalog` 和 `query_business_data` 使用受控数据源服务，
查询不能绕开授权计划直接连接登记数据源。Gateway analysis composition 提供的
`write_analysis_report` 需要本 run 的成功查询证据与 writer capability，才能写入固定报告 artifact
并登记索引。现有 `publish_analysis_report` 仍只登记已存在 artifact 的索引，不负责写文件或连接数据源。

## 排查与权威来源

- 配置字段及注释以仓库根目录的 `config.example.yaml` 为准。
- Gateway reload 边界以
  `backend/packages/harness/deerflow/config/reload_boundary.py` 和
  `tests/test_reload_boundary.py` 为准。
- Analytics 字段以 `backend/app/analytics/config.py` 为准。
- 容器拓扑与端口以根目录 `AGENTS.md` 和 `docker/` 下的 Compose 配置为准。
