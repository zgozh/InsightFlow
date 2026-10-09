# 安装与运行 InsightFlow

默认容器部署是本地使用的最短路径。仓库根目录的命令可在 Windows PowerShell、macOS 和 Linux 执行；Windows 需要 Docker Desktop、Python、`uv`，以及仓库支持的 GNU Make/Git Bash 工具链。

> **当前状态（2026-10-09）：** 功能与部署验收按批准范围通过，29384 原入口的首页、health/ready 与匿名拒绝独立后验收通过。详细实例、备份与交付边界见[最终交付状态](docs/acceptance/2026-10-09-final-delivery.md)。Root 最终源码/暂存审查及 commit/push 尚待完成；远程 CI 未运行。

## 环境要求

- Docker Desktop 和 Docker Compose V2：运行默认容器栈。
- GNU Make、Python 3.12+ 和 `uv`：生成配置、安装依赖和启动本机服务。
- Node.js 22+ 和 pnpm 10.26.2+：本机前端开发。

运行 `make check` 查看本机缺少的工具。完成配置后可运行 `make doctor` 检查应用配置和本机运行条件。仓库脚本不会替你安装系统依赖。

## 配置模型和本地文件

首次配置可在交互式终端运行 `make setup`。向导会在 Git 忽略的根目录 `config.yaml` 写入模型条目；如果所选 provider 需要 API key，向导会将你提供的 key 写入根目录 `.env`。向导不会提供凭据。若 `config.yaml` 已存在，向导会先询问是否重配。

手工配置时运行 `make config`。它会复制示例配置、扩展设置和环境变量模板，不会覆盖已有配置；然后在 `config.yaml` 的 `models:` 下启用模型，并将 provider 所需的 key 放入 `.env`。Agent 调用需要有效的模型条目和该 provider 要求的凭据；Gateway 与工作台可以在未配置模型时启动，但不能执行模型请求。

Windows PowerShell 不使用 Make 时，可直接运行同一配置脚本：

~~~powershell
python scripts/configure.py
Push-Location backend
uv run python ..\scripts\setup_wizard.py
Pop-Location
~~~

本机开发安装依赖时，`make install` 会安装后端、前端和 pre-commit 工具。若需在 PowerShell 中逐条执行：

~~~powershell
Set-Location backend
uv sync --locked
Set-Location ..\frontend
python ..\scripts\pnpm.py install
Set-Location ..
uv tool install pre-commit
pre-commit install --overwrite
~~~

## 启动服务

### Docker 生产部署

在仓库根目录运行：

~~~sh
make up
~~~

默认 Compose 启动 Nginx、Frontend、Gateway 和 Redis，并等待健康检查。Redis 是必需服务，只在 Compose 网络内可用。浏览器打开 <http://localhost:2026>；默认只有 Nginx 入口发布到宿主机，并绑定 `127.0.0.1`。首次访问时在 `/setup` 创建管理员，再从 `/login` 登录。运行 `make down` 停止并移除容器和网络；命名数据卷会保留。

### 本机开发与本机优化运行

首次安装依赖后，在仓库根目录运行：

~~~sh
make install
make dev
~~~

这会启动本机 Gateway、Frontend 和 Nginx，开发模式支持代码重载，入口为 <http://localhost:2026>。本机优化模式使用 `make start`，默认会构建前端；设置 `SKIP_FRONTEND_BUILD=1 make start` 时会复用现有产物，且要求 `frontend/.next/BUILD_ID` 已存在。`make stop` 停止本机进程。

### Docker 开发环境

使用 `make docker-start` 和 `make docker-stop` 运行、停止 Docker 开发 Compose 配置。查看开发栈日志使用 `make docker-logs`。Docker 开发配置与生产部署使用不同的 Compose 文件。

若 Docker 使用期间 `make doctor` 报告宿主机缺少 Nginx，该检查针对本机 `make dev` / `make start`；Docker Compose 内已有 Nginx。启动失败时先确认 Docker Desktop 正在运行、`2026` 端口可用，并且所需配置文件与环境变量存在。`make up` 未能就绪时会显示 Compose 状态和近期 Gateway 日志。

## 设置经营分析工作流

1. 首次访问 `/setup` 时创建首位管理员，然后登录。
2. 管理员登记业务数据源并发布 schema snapshot，配置数据源访问策略；连接凭据只由服务端引用，例如将 `secret_ref` 设为 `env://ANALYTICS_DS`，并把凭据保存在 Git 忽略的根目录 `.env`。
3. 登记指标定义、负责人和口径，再将指标授权给相应主体。指标可见性与数据源查询策略是两项独立授权。
4. 普通用户可在 `/workspace/analysis/new` 手动填写经营问题。数据源与指标页面也提供将文字带入新建分析草稿的快捷入口；草稿可编辑，只有用户显式提交后才运行。预填修复的 4 项定点测试和浏览器探针均已通过，见[修复验收记录](docs/acceptance/2026-10-09-prefilled-analysis-draft-fix.md)。
5. 运行阶段显示允许公开的摘要。完成查询、evidence 校验和报告复核后，报告才会出现在 `/workspace/reports`；用户可下载报告，并在 `/workspace/history` 查看审计记录。
6. 可在 `/workspace/scheduled-tasks` 创建定时任务。后台自动调度还需在 `config.yaml` 中启用 `scheduler.enabled`。

## 数据库与凭据

Gateway 应用数据库默认使用 SQLite，位于 `backend/.deer-flow`，默认 Docker 部署会持久化该目录。运维人员也可以显式配置外部 PostgreSQL 作为应用数据库。业务 PostgreSQL/MySQL 是单独登记的外部数据源，不由默认 Compose 启动。为业务库使用只读账号，并通过服务端 `secret_ref` 引用凭据；不要把密码写入数据源记录、浏览器请求或受版本控制的文件。TLS 参数见[后端配置指南](backend/docs/CONFIGURATION.md)。

不要提交 `config.yaml`、`extensions_config.json`、`.env`、前端环境文件、数据库凭据或管理员密码。只配置可信任的模型 provider、MCP 服务、扩展和沙箱端点。Local sandbox 使用 Gateway 进程的主机权限；默认 Compose 入口只绑定本机回环地址。

可选的 LangSmith、Langfuse 或 Monocle tracing SDK 可能在 Gateway 结构化输出投影之外采集 prompt 和工具输入/输出。启用时应只发送到可信目标，并单独管理访问权限和保留期限。

## 常见空状态和错误

- 数据源列表为空：尚未登记数据源，或当前主体无权查看。
- 指标列表为空：没有 active 指标归属当前主体或明确授权给当前主体。指标授权不会自动授予数据源访问权。
- 报告列表为空：还没有 run 完成 evidence 校验和发布复核。审计历史也只显示当前主体可见的记录。
- `401`：通常需要先在 `/setup` 创建管理员，或重新登录。
- `403`：已登录主体缺少相应权限；检查数据源策略、指标授权和资源 owner。
- `404`：检查路由和资源 ID。owner 隔离资源不属于当前账号时也可能返回 `404`，请确认登录账号、线程和资源 ID。
- Agent 不能调用模型：确认 `config.yaml` 启用了 `models[]`，并且 `.env` 中有对应 provider 要求的 key。
- 业务查询连不上数据库：检查 Gateway 容器可达的数据库地址、`secret_ref`、只读账号、schema snapshot、访问策略和 TLS。应用数据库配置不会代替业务数据源配置。

当前功能和验收范围见[当前能力说明](docs/current-capabilities.md)，交付门禁见[最终交付状态](docs/acceptance/2026-10-09-final-delivery.md)，架构见[InsightFlow 架构概览](docs/architecture/insightflow-overview.md)。`docs/LOCAL_TRIAL.md` 保留带日期的合成 PostgreSQL 演示与历史验收证据，不是标准安装指南。
