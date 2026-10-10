# 安装与运行 InsightFlow

默认推荐使用 Docker Compose。GNU Make 提供便捷命令，但不是部署必需品；没有 Make 时，可在仓库根目录直接运行 `scripts/deploy.sh`。Windows 用户需要 Git for Windows 的 Git Bash 来运行该 Bash 脚本。

## 环境要求

- 默认 Docker 部署：Docker Desktop（Windows/macOS）或 Docker Engine（Linux），以及 Docker Compose V2；`docker compose up --wait` 需要当前 Compose 版本支持。
- 直接运行部署脚本：Bash，以及 Python 3 或 OpenSSL，用于首次生成并保存认证密钥。Windows 可使用 Git Bash。
- Make 命令：GNU Make、Python 3.12+ 和 `uv`。运行本机前端还需要 Node.js 22+ 和 pnpm 10.26.2+。

有 Make 时可运行 `make check` 查看工具要求，`make doctor` 检查应用配置和本机运行条件。仓库脚本不会替你安装系统依赖。

## 配置模型和本地文件

首次配置模型可运行 `make setup`。交互向导会在根目录 `config.yaml` 写入所选模型，并按 provider 要求把 API key 写入 Git 忽略的根目录 `.env`。向导不会提供凭据。

### 配置文件各自负责什么

| 位置 | 用途 | 何时需要 |
| --- | --- | --- |
| 根目录 `config.yaml` | 应用设置与模型条目。可由 `make config` 从模板生成。 | 需要调用 Agent 时配置模型；Gateway 和工作台本身可在没有模型时启动。 |
| 根目录 `.env` | 模型 provider 密钥及 Compose 使用的环境变量；`.env.example` 只提供占位示例。 | 配置模型凭据或覆盖部署默认值时。 |
| 根目录 `extensions_config.json` | 可选的 MCP 服务与技能配置，由 Gateway 管理。 | 需要接入这些扩展能力时；普通聊天不要求填写。 |
| 管理员登记的数据源 | 经营分析使用独立的外部 PostgreSQL/MySQL 数据源，连接凭据由服务端 `secret_ref` 引用。 | 使用经营分析时；不要把业务数据库凭据放进 `config.yaml` 或前端环境文件。 |
| Docker Compose | 启动 Nginx、Frontend、Gateway 与 Redis；根目录 `.env` 可设置入口 `BIND_HOST` 和 `PORT`。 | 使用 Docker 部署或覆盖默认入口时。 |

手工配置可运行 `make config` 生成配置模板，再在 `config.yaml` 的 `models:` 下配置所需模型条目，并把对应的 provider key 写入 `.env`。该命令不会覆盖已有文件，也不会替你选模型或生成凭据。Gateway 和工作台可以在没有模型配置时启动，但 Agent 无法调用模型。

Windows PowerShell 可在首次初始化时直接运行配置脚本和模型向导：

```powershell
python scripts/configure.py
Push-Location backend
uv run python ..\scripts\setup_wizard.py
Pop-Location
```

本机源码开发可在 PowerShell 中逐项安装依赖：

```powershell
Set-Location backend
uv sync --locked
Set-Location ..\frontend
python ..\scripts\pnpm.py install
Set-Location ..
uv tool install pre-commit
pre-commit install --overwrite
```

若只部署 Docker，可按下一节在 Git Bash 中复制模板并手动填写模型配置；无需在宿主机安装 `uv` 或 Node.js。

## Docker 生产部署

### Windows 与 Git Bash：不使用 Make

先启动 Docker Desktop，并在 Git Bash 中进入仓库根目录。检查 Docker Compose 与密钥生成工具可用：

```sh
docker compose version
python --version
```

部署脚本会依次尝试 `python3`、`python` 和 `openssl` 生成密钥；在 Git Bash 中至少需要其中一种。若没有 Python，可改用 `openssl version` 检查 OpenSSL。Compose 版本需支持 `docker compose up --wait`。

复制 Docker Compose 所需的环境文件和配置模板：

以下命令只用于首次部署且目标文件尚不存在时。若本地文件已存在，不要覆盖；保留文件并按需编辑。

```sh
cp .env.example .env
cp frontend/.env.example frontend/.env
cp config.example.yaml config.yaml
cp extensions_config.example.json extensions_config.json
```

编辑 `config.yaml`，配置所需模型条目；编辑根目录 `.env`，填写模型对应的 provider key。数据源密码稍后由管理员在服务端通过 `secret_ref` 配置，不要写进 `config.yaml` 或前端环境文件。

启动默认生产栈：

```sh
bash scripts/deploy.sh
```

首次启动会构建镜像、启动默认的四个容器，并等待 Gateway readiness 检查通过。脚本会把认证密钥保存在 `backend/.deer-flow`，后续启动会复用。浏览器打开 <http://localhost:2026>，在 `/setup` 创建首位管理员，然后从 `/login` 登录。

常用脚本命令：

| 命令 | 行为 |
| --- | --- |
| `bash scripts/deploy.sh` | 构建镜像并启动默认四容器，等待 Gateway 就绪 |
| `bash scripts/deploy.sh build` | 只构建镜像 |
| `bash scripts/deploy.sh start` | 使用已构建镜像启动服务 |
| `bash scripts/deploy.sh down` | 停止并移除容器与网络，保留应用目录和 Docker 数据卷 |

默认入口只绑定本机 `127.0.0.1:2026`。默认部署运行 Nginx、Frontend、Gateway 和 Redis；Redis 仅在 Compose 网络内服务 Streams bridge。不要把 Gateway 或 Redis 端口发布到公网。

### 使用 Make 的 Docker 部署

```sh
make setup
make up
```

`make setup` 交互配置模型；如果已手工准备好配置，也可直接运行 `make up`。`make up` 会等待 Gateway 健康检查通过。打开 <http://localhost:2026>，在 `/setup` 创建管理员。停止并移除容器和网络、保留持久数据：

```sh
make down
```

### 本机开发与 Docker 开发

本机源码开发需要安装后端与前端依赖：

```sh
make install
make dev
```

`make dev` 启动本机 Gateway、Frontend 和 Nginx 三个进程，支持代码重载，入口为 <http://localhost:2026>。`make stop` 停止这些本机进程。

`make start` 运行本机优化模式并默认构建前端。只有 `frontend/.next/BUILD_ID` 已存在时，才使用 `SKIP_FRONTEND_BUILD=1 make start` 复用已有构建；`make stop` 停止服务。Docker 开发环境使用另一份 Compose 配置，命令为 `make docker-start`、`make docker-stop` 和 `make docker-logs`。

可选的本机 PostgreSQL 分析演示栈在默认四个容器之外增加一个业务 PostgreSQL 容器，合计五个容器。仓库的演示环境示例将入口设为 `2027`；它不是默认生产栈入口，实际端口以该演示环境文件为准。配置和启动方式见[本机 PostgreSQL 试用记录](docs/LOCAL_TRIAL.md)。默认入口仍是 `http://localhost:2026`。

## 首次使用与分析授权

1. 首次访问 `/setup` 时创建首位管理员，然后登录。
2. 管理员登记外部业务数据源并发布 schema snapshot。使用只读数据库账号，通过服务端 `secret_ref` 引用连接凭据，例如 `env://ANALYTICS_DS`；凭据保存在根目录 `.env`。
3. 配置数据源访问策略，再登记指标定义、负责人和口径，并单独把指标授权给相应用户。指标授权不会自动授予数据源访问权限。
4. 用户在 `/workspace/analysis/new` 输入经营问题后提交分析。数据源和指标目录也可预填一个可编辑草稿；只有显式提交才会运行。
5. 查询、证据核验和报告复核成功后，报告出现在 `/workspace/reports`。所有者可以下载报告，并在 `/workspace/history` 查看可见的审计记录。
6. 可在 `/workspace/scheduled-tasks` 创建定时任务。后台调度还需要在 `config.yaml` 中启用 `scheduler.enabled`。

## 数据库、凭据与安全边界

Gateway 的应用数据库默认使用 SQLite，文件位于 `backend/.deer-flow/data/deerflow.db`，Docker 部署会持久化该目录。运维人员也可显式配置外部 PostgreSQL 作为应用数据库。业务 PostgreSQL/MySQL 是管理员单独登记的外部分析数据源；默认 Compose 不会启动它们。

不要提交 `config.yaml`、`extensions_config.json`、`.env`、前端环境文件、数据库凭据或管理员密码。只配置可信任的模型 provider、MCP 服务、扩展和沙箱端点。Local sandbox 使用 Gateway 进程的主机权限。

可选的 LangSmith、Langfuse 或 Monocle tracing SDK 可能在平台结构化输出之外采集 prompt、工具输入/输出或模型回复。启用前应确认目标可信，并单独管理访问权限和数据保留期限。TLS 配置见[后端配置指南](backend/docs/CONFIGURATION.md)。

## 常见问题

- Docker 启动失败：确认 Docker Desktop 正在运行、Compose 支持 `up --wait`，并检查 `2026` 端口及 `.env`、`frontend/.env`、`config.yaml` 是否存在。
- 启动未通过 readiness：部署脚本会显示 Compose 容器状态和最近的 Gateway 日志；先检查这些信息和模型配置。
- `make doctor` 报告宿主机缺少 Nginx：该检查针对本机 `make dev` 或 `make start`；Docker Compose 自带 Nginx。
- Agent 无法调用模型：确认 `config.yaml` 的 `models` 下已配置所需模型条目，并且根目录 `.env` 有该 provider 所需的 key。
- 数据源或指标列表为空：请管理员检查数据源登记、schema snapshot、访问策略和指标授权。
- 报告列表为空：只有完成证据核验和报告复核的运行会发布报告。
- `401`：先在 `/setup` 创建管理员，或重新登录。`403` 表示当前账号缺少所需权限；`404` 也可能表示资源属于其他账号。
- 业务数据库连接失败：检查 Gateway 可访问的地址、`secret_ref`、只读账号、schema snapshot、访问策略和 TLS。应用数据库连接配置不会代替业务数据源配置。

当前功能与验收范围见[当前能力说明](docs/current-capabilities.md)，最终交付证据见[最终交付状态](docs/acceptance/2026-10-09-final-delivery.md)，完整合同见[发布验收场景](docs/acceptance/acceptance-scenarios.md)。
