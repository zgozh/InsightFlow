# InsightFlow 历史本机试用与验收证据

> 当前标准安装、配置和工作台使用步骤见根目录[安装与运行指南](../Install.md)。本文件保留有日期的合成 PostgreSQL 演示配置和验收记录；这些历史运行不代表当前整体发布状态。

## 6D2：持久化 PostgreSQL 16 演示

本节的合成演示数据库是显式 opt-in 的 Compose overlay，与一次性数据库门禁分开管理。`make up` 仍只启动 Nginx、Frontend、Gateway、Redis 四个默认服务。演示栈使用独立 Compose project `insightflow-analytics-demo`、独立容器名和具名数据卷；数据库不发布宿主机端口，只允许同项目 Gateway 通过私有 Compose 网络访问。网页入口固定为 loopback `127.0.0.1:2027`。

### 一次性准备

从仓库根目录的 PowerShell 执行。先按本机设置完成 `make config`、`make setup`，并创建首次登录需要的 `config.yaml`、`.env` 和 `frontend/.env`。模型调用需要操作者自行配置 provider；下面的数据库演示全是合成数据。

创建本机 TLS 证书与 Git 忽略的演示变量文件。需要本机可用的 `openssl`：

```powershell
$null = New-Item -ItemType Directory -Force .analytics-demo
$demoHome = [System.IO.Path]::GetFullPath((Join-Path $PWD ".analytics-demo\app-home")).Replace("\", "/")
$null = New-Item -ItemType Directory -Force $demoHome
$configPath = [System.IO.Path]::GetFullPath((Join-Path $PWD "config.yaml")).Replace("\", "/")
$extensionsConfigPath = [System.IO.Path]::GetFullPath((Join-Path $PWD "extensions_config.json")).Replace("\", "/")
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$authBytes = New-Object byte[] 32
$internalBytes = New-Object byte[] 32
$random.GetBytes($authBytes)
$random.GetBytes($internalBytes)
$betterAuthSecret = [Convert]::ToBase64String($authBytes)
$internalAuthToken = [Convert]::ToBase64String($internalBytes)
$random.Dispose()
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes `
  -keyout .analytics-demo/server.key `
  -out .analytics-demo/server.crt `
  -subj "/CN=analytics-demo-postgresql" `
  -addext "subjectAltName=DNS:analytics-demo-postgresql"

$adminPassword = [guid]::NewGuid().ToString("N")
$readerPassword = [guid]::NewGuid().ToString("N")
$caPem = Get-Content -Raw .analytics-demo/server.crt
$readerCredential = @{
  engine = "postgresql"
  host = "analytics-demo-postgresql"
  port = 5432
  database = "analytics_test"
  username = "analytics_demo_reader"
  password = $readerPassword
  tls_mode = "verify_full"
  ca_pem = $caPem
} | ConvertTo-Json -Compress

@"
BIND_HOST=127.0.0.1
PORT=2027
DEER_FLOW_HOME=$demoHome
DEER_FLOW_CONFIG_PATH=$configPath
DEER_FLOW_EXTENSIONS_CONFIG_PATH=$extensionsConfigPath
BETTER_AUTH_SECRET=$betterAuthSecret
DEER_FLOW_INTERNAL_AUTH_TOKEN=$internalAuthToken
ANALYTICS_DEMO_ADMIN_PASSWORD=$adminPassword
ANALYTICS_DEMO_DB_PASSWORD=$readerPassword
ANALYTICS_DEMO_READER_CREDENTIAL=$readerCredential
"@ | Set-Content -Encoding ASCII .env.analytics-demo
```

`.analytics-demo/` 保存 TLS 文件和独立 Gateway 本地状态，`.env.analytics-demo` 保存仅供本机演示的随机密码与只读凭证 JSON；这些路径均已加入 `.gitignore`。Gateway 的 runtime home 由 `DEER_FLOW_HOME` 指向该 project 独有的绝对路径，不会复用其他既有应用栈的 SQLite 或认证状态。不要把凭证复制到数据源记录，那里只填 `env://ANALYTICS_DEMO_READER_CREDENTIAL`。

需要 Docker Compose V2；双 `--env-file` 用法已用 v2.40.3 验证，后一个文件覆盖前一个文件中的同名变量。Compose shell 环境变量优先级高于 env 文件；每次启动或停止前都从本地文件重载专用标量变量，避免 PowerShell profile 中的同名值改写独立 home 或 loopback 端口。只读凭证 JSON **不要**经 `ConvertFrom-StringData` 赋给 `$env:ANALYTICS_DEMO_READER_CREDENTIAL`：它含有 JSON 转义的 PEM 换行，PowerShell 会将 `\n` 解成实际换行，破坏 JSON。让 Compose 通过 `--env-file` 原样读取该单行值；若当前启动 shell 已有同名覆盖，只清除该进程中的覆盖，不改其他环境：

```powershell
$demoEnvironment = Get-Content -Raw .env.analytics-demo | ConvertFrom-StringData
$env:DEER_FLOW_HOME = $demoEnvironment["DEER_FLOW_HOME"]
$env:DEER_FLOW_CONFIG_PATH = $demoEnvironment["DEER_FLOW_CONFIG_PATH"]
$env:DEER_FLOW_EXTENSIONS_CONFIG_PATH = $demoEnvironment["DEER_FLOW_EXTENSIONS_CONFIG_PATH"]
$env:BETTER_AUTH_SECRET = $demoEnvironment["BETTER_AUTH_SECRET"]
$env:DEER_FLOW_INTERNAL_AUTH_TOKEN = $demoEnvironment["DEER_FLOW_INTERNAL_AUTH_TOKEN"]
$env:BIND_HOST = $demoEnvironment["BIND_HOST"]
$env:PORT = $demoEnvironment["PORT"]
$env:ANALYTICS_DEMO_ADMIN_PASSWORD = $demoEnvironment["ANALYTICS_DEMO_ADMIN_PASSWORD"]
$env:ANALYTICS_DEMO_DB_PASSWORD = $demoEnvironment["ANALYTICS_DEMO_DB_PASSWORD"]
Remove-Item Env:ANALYTICS_DEMO_READER_CREDENTIAL -ErrorAction SilentlyContinue
```

### 启动与停止

```powershell
# 先执行上面的专用环境变量重载块。
docker compose -p insightflow-analytics-demo `
  --env-file .env --env-file .env.analytics-demo `
  -f docker/docker-compose.yaml `
  -f docker/docker-compose.analytics-demo.yml `
  -f docker/docker-compose.analytics-demo-app.yml `
  up -d --build --wait
```

等待 Gateway 健康后访问 <http://127.0.0.1:2027>，在 `/setup` 创建此演示 project 的管理员。PG 初始化时创建固定数据库 `analytics_test`、仅有 `demo.orders` 授权列 SELECT 权限的 `analytics_demo_reader`，并写入 10 条合成订单。Reader 没有业务 schema 外的读取权限、写入/建表权限或 TEMP 权限。初始化只在新数据卷首次启动时执行。

停止时使用完全相同的 `-p`、`--env-file` 和 `-f` 参数，并仅执行 `down`：

```powershell
# 新开终端时，先执行上面的专用环境变量重载块。
docker compose -p insightflow-analytics-demo `
  --env-file .env --env-file .env.analytics-demo `
  -f docker/docker-compose.yaml `
  -f docker/docker-compose.analytics-demo.yml `
  -f docker/docker-compose.analytics-demo-app.yml `
  down --timeout 20
```

`down` 会停止此 project 的容器并移除它的网络，保留 `insightflow-analytics-demo_analytics-demo-data` 数据卷；再次运行启动命令可继续使用。不要使用 `make down` 管理这个 project，也不要对它执行 `down -v`。默认栈和其他既有容器、卷（实际名称见后续资源记录）不属于此演示 project。

### 管理员注册

用刚创建的管理员登录。可在 `/workspace/datasources` 新建 PostgreSQL 数据源，名称任意、默认 schema 为 `demo`，`secret_ref` 填 `env://ANALYTICS_DEMO_READER_CREDENTIAL`。schema 快照中登记 `demo.orders` 的列：`order_id integer`、`order_date date`、`region text`、`product text`、`status text`、`amount numeric(12,2)`、`customer_email text (PII)`、`internal_note text (SENSITIVE)`。另有未注册的 `demo.internal_margin` 表用于负例。

为当前登录 principal 创建访问策略，关系设为 `demo.orders`；将 `order_id`、`order_date`、`region`、`product`、`status`、`amount` 和 `customer_email` 设为 ALLOW，函数白名单为 `and`、`cast`、`count`、`sum`。把 PII 列留在快照中并标成 PII；即使策略将它设为 ALLOW，HIGH 风险查询仍会被拒绝。`internal_note` 不加入访问策略。schema、策略和指标都通过 `/workspace/datasources`、`/workspace/metrics` 中的管理员面板保存。

在指标页登记以下度量：

| Key | 名称 | 公式 | 维度 |
| --- | --- | --- | --- |
| `january_paid_revenue` | 1 月已支付收入 | `sum(amount)` | `order_date`, `status` |
| `january_paid_revenue_by_region` | 1 月各地区已支付收入 | `sum(amount)` | `region`, `order_date`, `status` |
| `january_refund_order_ratio` | 1 月退款订单占比 | `count(refunded orders) / count(orders)` | `order_date`, `status` |

### 三个自然语言问题与复算结果

开启模型问答需要本机 `config.yaml` 中的 provider 配置和相应本地 key。下面列出期望问题、确定性公式和可复算 SQL；自然语言推理会由操作者选用的模型生成，SQL 与答案可以直接对照。

1. **“2026 年 1 月已支付订单收入总额是多少？”**

   公式：`SUM(amount)`，日期范围为 `2026-01-01 <= order_date < 2026-02-01`，且 `status = 'paid'`。期望收入 **540.00**。

   ```sql
   SELECT SUM(amount) AS revenue FROM demo.orders
   WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01'
     AND status = 'paid' LIMIT 1
   ```

2. **“1 月各地区的已支付收入分别是多少？”**

   公式：按 `region` 分组的 `SUM(amount)`，沿用 1 月与 `paid` 条件。期望结果：North **300.00**、South **150.00**、West **90.00**。

   ```sql
   SELECT region, SUM(amount) AS paid_revenue FROM demo.orders
   WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01'
     AND status = 'paid'
   GROUP BY region ORDER BY region LIMIT 10
   ```

3. **“1 月退款订单数和订单总数是多少，退款占比是多少？”**

   公式：`COUNT(refunded orders) / COUNT(orders)`。期望数量 **2 / 8**，占比 **25%**。

   ```sql
   SELECT COUNT(*) FILTER (WHERE status = 'refunded') AS refunded_orders,
          COUNT(*) AS total_orders FROM demo.orders
   WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01' LIMIT 1
   ```

### 负例与检查入口

通过受控查询工具分别尝试读取 `demo.internal_margin`、`demo.orders.internal_note`、PII 列 `customer_email`，以及 `INSERT`、`UPDATE`、`CREATE TABLE` 和两个以分号连接的查询。预期稳定拒绝码依次包括 `unknown_relation`、`column_not_allowed`、`sensitive_column`、`unsupported_statement` 和 `multiple_statements`；每次应返回空列/行、零行数且无 evidence。直接以数据库 reader 连接时，对 `public.orders`、`demo.internal_margin`、PII 列、写操作、建表和 TEMP 的尝试由 PostgreSQL 权限拒绝。

可在 `/workspace/history` 查看审计，在 `/workspace/reports` 查看已保存报告；query tool 的成功输出带有可复核的 `evidence`（query hash、plan digest、result digest 和 evidence id）。聊天附件从所属 thread 的 artifact 入口打开。PostgreSQL 门禁在 service/tool 层直接验证 evidence、audit 与真实数据库行为；单独的 API/HTTP 回归验证 FastAPI 路由契约，但两者都不调用模型。本次没有验证模型生成 SQL、端到端 Agent run、Reviewer 或报告生成链路。

`scripts/test_analytics_databases.py --engine postgresql` 是另一条一次性 PostgreSQL 16 门禁：只用隔离 project、tmpfs 数据目录和 loopback 测试端口，结束时只对该 project 执行不带 `--volumes` 的 `down`。它不启动上述持久 demo overlay，也不复用它的数据卷。

## Phase 6D2 门禁记录（2026-09-25）

- 基线为 `main` 上 6D1 提交 `0025a63b1440e81d2d3e47445e7ea41064cd93ca`。此次改动只增加测试、一次性门禁隔离、合成数据初始化和 opt-in 演示配置/文档；没有改 Analytics 生产运行时代码或 lockfiles。
- Harness 命令 `uv run --locked pytest tests/test_analytics_database_harness.py -q`（`backend/`）：退出码 **0**，**11 passed**，4.33s。
- 真实 PG16 命令 `python scripts/test_analytics_databases.py --engine postgresql`：退出码 **0**。临时 PostgreSQL **16.15** 健康，端口仅映射 `127.0.0.1:55432`；Analytics PostgreSQL 集成与持久化测试 **43 passed**，13.65s。查询经注册服务和 Agent tool 执行，不启动模型或 HTTP Agent run。期望值为 540.00、地区收入 North/South/West 为 300.00/150.00/90.00、退款订单与总单数为 2/8；重复查询校验 query hash、plan digest、result digest 与 evidence id。成功 audit 记录与 evidence 的 query hash、plan digest、决定码和行数相核对。未授权关系/列、PII、DML、DDL、多语句拒绝；SQLAlchemy 执行事件 marker 与 `pg_stat_statements` 均没有记录被拒绝 SQL，拒绝审计不含 SQL、token、凭证或结果值。Reader 的真实 PostgreSQL grants 另外拒绝业务白名单之外的 schema/table/column、写入、建表与 TEMP。
- 门禁启动前 project 的容器/卷/网络为空且端口空闲；runner 只对 `insightflow-analytics-test` 执行不带 `--volumes`、`--remove-orphans` 的 `down`。结束后容器、卷、网络仍为空，55432 释放。此门禁没有启动持久演示 Compose。
- 演示 Compose 用临时占位变量执行 `docker compose config --format json --no-env-resolution` 静态渲染，退出码 **0**；未解析仓库 `.env` 内容或启动 demo 容器。检查确认 PG 没有宿主机端口，Gateway 与 DB 共用隔离网络，Web ingress 为 `127.0.0.1:2027`，Gateway runtime home 为仓库 `.analytics-demo/app-home` 独立绝对路径。Docker Compose 为 v2.40.3。
- Ruff 命令（`backend/`）：`uv run --locked ruff check tests/test_analytics_database_harness.py tests/test_analytics_postgresql_integration.py ../scripts/test_analytics_databases.py` 与 `uv run --locked ruff format --check tests/test_analytics_database_harness.py tests/test_analytics_postgresql_integration.py ../scripts/test_analytics_databases.py` 均退出码 **0**。`uv lock --check` 退出码 **0**，解析 213 个包；`git diff --check` 退出码 **0**。`backend/uv.lock` 和 `frontend/pnpm-lock.yaml` 与基线一致，未修改。
- 本地模型凭据未读取，未调用模型 API；没有运行全量 14k 后端或 Playwright。已运行的真实路径边界是 app service/tool 与 PostgreSQL，不代表 HTTP Agent、自然语言 SQL 生成、Reviewer 或报告生成全链路通过。第三方 MCP 的 AS-14 发布阻塞仍在，不能据本次样例宣称整体发布就绪。

本指南描述 Windows PowerShell + Docker Desktop 的本机路径。容器能启动、页面能打开，不代表模型调用或业务数据分析已经端到端验证。

## Phase 6F1：真实分析链路彩排

2026-09-26 在独立 `insightflow-analytics-demo` project 上完成一次合成数据真实分析彩排。曾发现 PowerShell 演示步骤会解码凭据 JSON 中的 PEM 换行，且 shell 环境覆盖会优先于 Compose `--env-file`；现按上文“启动与停止”步骤只清除当前进程的 reader credential 覆盖，并让 Compose 原样读取单行 JSON，证书仍以 `verify_full` 校验。真实模型 run、持久线程身份、PostgreSQL evidence、报告写入/读取和拒绝结果详见[Phase 6F1 验收记录](acceptance/phase-06f1-real-analysis-rehearsal.md)。该 opt-in 演示不表示默认四服务 AS-15、AS-14 或 Phase 6 已验收；project 与合成数据库卷保留供操作者复验。

## 当前安装入口

当前安装、模型配置、默认服务启动和工作台使用步骤统一见根目录[安装与运行指南](../Install.md)。以下各节保留带日期的合成 PostgreSQL 演示配置及历史验收结果，不能作为当前整体发布状态的证明。

## 本机实测记录（2026-09-24）

| 项目                 | 结果                                                                                                                                                                                                                              |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 运行环境             | Windows PowerShell、MSYS GNU Make 4.4.1、Docker Desktop Engine 29.1.2、Compose v2.40.3、Python 3.12.4、uv 0.11.28、Node.js 24.14.0、pnpm 10.26.2                                                                                  |
| Python 包索引        | 本机锁文件检查和同步通过；运行时临时设置 `$env:UV_DEFAULT_INDEX='https://pypi.org/simple'` 以避开默认索引解析失败，没有修改锁文件                                                                                                 |
| 配置生成路径         | PowerShell 调用 Make 的模板生成、MSYS shell 脚本路由及 GBK 代码页输出回归通过；`backend/tests/test_configure.py` 和 `backend/tests/test_doctor.py` 共 44 项通过                                                                   |
| 冷启动               | `make up` 退出码 0；Gateway 和 Redis 的 Docker healthcheck 通过，Nginx `/health` 返回 `healthy`，首页、`/setup`、`/login` 返回 200；未登录访问 `/workspace/chats` 返回 307 并转到 `/setup`                                        |
| 首次认证状态         | `/api/v1/auth/setup-status` 返回 `needs_setup: true`；本地 `.better-auth-secret` 与 `.internal-auth-token` 已生成，仅确认文件存在，没有读取其内容                                                                                 |
| 停机与持久卷         | `make down` 退出码 0；试用容器和网络已移除，`deer-flow_redis-data` 卷保留，创建时间未改变                                                                                                                                         |
| Analytics 数据库门禁 | PostgreSQL 16.15（`postgres:16`）、MySQL 8.4.11（`mysql:8.4`）：82 passed，2 个 MySQL timeout/只读用例的 `MySQLResult._finish_unbuffered_query` 未 await warning；两个临时服务均 healthy，脚本自动 teardown，未留下测试容器或网络 |
| 未完成的人工验收     | 未提供真实模型 key，未执行模型对话；未登记持久业务数据源，未执行业务 Analytics 查询；管理员账号由试用者创建                                                                                                                       |

本机 `make check` 因宿主机没有 Nginx 返回 1；`make doctor` 会显示宿主机 Nginx 和未配置模型两项失败以及 Local sandbox 提示。Docker 试用的服务路径已通过独立 Compose 冷启动和 HTTP 检查。

本机此前有一组已停止、名称与本项目冲突的旧容器。验证期间将它们临时改名以保留原容器和数据卷，测试结束后已恢复原名与原 ID。若同一环境再次运行 `make up` 遇到 `container name ... is already in use`，先确认对应的是哪一组旧容器，再按需改名或通过其原 Compose 项目清理；不要用 `docker volume prune` 或 `make down -v`。

## Phase 6C 复核补记（2026-09-24）

- 再次运行 `make up` 退出码 0；Compose 等待 Nginx、Frontend、Gateway、Redis 就绪后报告运行成功。HTTP 检查中 `/health`、首页、`/setup`、`/login` 均为 200；未登录访问 `/workspace/chats` 返回 307 并转到 `/setup`；`/api/v1/auth/setup-status` 返回 `needs_setup: true`。没有创建管理员账号，也没有发起模型请求。
- 启动前确认冲突的四个已停止容器来自另一份既有 checkout（Compose project `docker`，机器路径 `D:\develop\workspace\deer-flow\docker`）。仅临时改名以保留容器和卷；本次 `make down` 退出码 0 后，四个容器均恢复原名和原 ID，没有清除卷。
- 当前根配置的 `models` 列表为空，因此模型对话未验证。没有通过持久业务数据库、只读账号、schema snapshot 和用户 policy 完成 Analytics 查询；**经营分析未端到端验证**。按指南填写模型与业务数据源配置后，再由使用者进行人工试用。
- 静态演示未提供可复现的 Agent→沙箱 HTML 写入→artifact 登记→浏览器预览全链路证据；现有 artifact 预览 E2E 使用模拟写入与响应。保留四个可编辑欢迎示例，不增加第五个网页示例。
- `D:\develop\workspace\InsightFlow-6A-baseline-20260924` 仍需保留；它不属于已登记 worktree，可能包含未跟踪文件。不得递归删除或移动，如需清理应先由使用者检查并另行授权。

## Phase 6D1 契约复核补记（2026-09-24）

- 默认 Compose 与持久化边界已按当前配置/代码核对：生产与 Docker 开发默认是 `nginx`、`frontend`、`gateway`、`redis` 四服务；Redis 是必需容器。Gateway 应用库默认是 `backend/.deer-flow/data/deerflow.db` SQLite 并挂载持久目录。可选应用 PostgreSQL 和业务 PostgreSQL/MySQL 由运维提供，均不由默认 Compose 启动。该项为静态配置/代码核对，不是本补记重新启动 Docker 的记录。
- 后端聚焦命令首次尝试：`uv run --locked pytest tests/test_auth_middleware.py tests/test_analytics_api.py tests/test_analytics_delivery.py tests/test_semantic_authorizer.py tests/test_sql_policy.py tests/test_result_normalizer.py tests/test_analytics_agent_tools.py tests/test_analytics_agent_reports.py tests/test_business_analysis_skill.py tests/test_compose_default_bind_host.py tests/test_compose_default_workers.py tests/test_gateway_services.py tests/test_scheduled_task_queue.py tests/test_subagent_executor.py -q`，退出码 **1**。pytest 未启动；UV 依赖解析使用的 `https://pypi.tuna.tsinghua.edu.cn/simple` 返回 403，报 `sqlglot==30.18.0` 无法解析。该次没有测试失败 ID。
- 后端同一聚焦命令重试：PowerShell 进程先设 `$env:UV_DEFAULT_INDEX = 'https://pypi.org/simple'`，随后运行上述 `uv run --locked pytest ... -q`，退出码 **0**，**817 passed，0 failed，0 skipped，2 warnings，14 个测试文件**，43.82s。两个弃用 warning 分别为 Starlette TestClient 与 `httpx` 的兼容提示、单请求 `cookies=` 行为提示；不是测试失败。没有运行数据库容器门禁。
- 前端聚焦命令 `pnpm rstest run unit/core/analytics/trace.test.ts unit/components/analytics/analytics-trace-panel.dom.test.tsx`，退出码 **0**，**2 files / 28 passed / 0 failed / 0 skipped**，5.14s。
- 矩阵静态检查通过（PowerShell here-string 管道到 `python -`，以 UTF-8 读取 11 份变更文档，校验尾随空白/末尾换行、AS ID 顺序、三种状态值以及矩阵所引用文件和测试标识存在）：退出码 **0**，**15 行，所有引用可定位；状态计数为 2 项自动测试已证实 / 10 项仅设计或未真实验收 / 3 项与实现矛盾**。AS-13 的 HIGH/PII 拒绝与审计子行为有自动测试，但整项还要求跨工具响应、Gateway events、receipt、artifact 和报告投影扫描，故按整体契约归为未验收。第一次校验器因 PowerShell→Python 命令管道传输源码时的编码，把脚本内中文状态标签转成乱码，退出码 **1**；矩阵文件本身 UTF-8 正常、标签无乱码。将标签改用 Python `\u` Unicode 转义的修正版退出码 **0**，全部行与引用校验通过。这是检查脚本输入编码问题，不是矩阵内容失败；没有遗漏的 AS ID。
- `git diff --check` 退出码 **0**、无空白错误输出。提交前仓库核对为根目录 `D:\develop\workspace\InsightFlow`、`main` 分支、HEAD `bb6af491ee389460b52a9f84627a68388ea7de35`、固定 tag tree `2473c22e163a3879490848a7995eb2b7be7f6f50`；`git ls-files` 为 **2251**（两份新增文档尚未计入已跟踪数，提交后预计 2253）。`backend/uv.lock` 和 `frontend/pnpm-lock.yaml` SHA-256 与起点一致，未修改；此处未移动固定 tag。
- 这批命令不需要也没有读取 `.env`，未发起模型请求、未创建数据库容器。本机历史数据库门禁仍只记录 PG 16.15 / MySQL 8.4.11 共 82 passed；原记录没有退出码，因此不将其表述为本切片新运行或完整业务分析验收。旧离线全量后端的 13 个失败仍按 Phase 5 记录保留，未在本切片重跑，也未标为通过。
- 行为证据和端到端残差按 AS-01..AS-15 逐条记录于[契约矩阵](acceptance/phase-06d-contract-reconciliation.md)；AS-14 第三方 MCP 绕过路径仍是发布阻塞，但不阻止 6D2 对平台自有受控查询路径做独立验证。
