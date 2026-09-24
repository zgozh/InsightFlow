# InsightFlow 本机试用指南

本指南描述 Windows PowerShell + Docker Desktop 的本机路径。容器能启动、页面能打开，不代表模型调用或业务数据分析已经端到端验证。

## 最短试用步骤

在仓库根目录打开 PowerShell。Docker Desktop、Docker Compose、`make`、Python 3.12+ 和 `uv` 必须可用。使用 MSYS GNU Make 时仓库会选择 MSYS 自带的 POSIX shell 与 `/usr/bin/bash`；Node.js 22+ 和仓库锁定的 pnpm 10.26.2 是本地开发、运行 `make check` 的依赖，Docker 构建则在镜像内安装前端依赖。

1. 在交互式终端运行 `make setup`，选择模型提供方和模型；仅当所选提供方需要时才输入 API key。本地 Ollama 不需要 key。若 Gateway 运行在 Docker、Ollama 运行在宿主机，向导生成后需编辑 Git 忽略的 `config.yaml`，把该模型的 `base_url` 从 `http://localhost:11434` 改为 `http://host.docker.internal:11434`。向导把模型定义写入根目录 `config.yaml`，把所需的 key 写入 Git 忽略的 `.env`。如果此前运行过 `make config`，配置已存在时向导会询问是否重配；确认后继续。非交互终端运行 `make setup` 会安全退出，不会改写配置。

   也可以运行 `make config` 生成模板，再手动编辑 `config.yaml` 的 `models` 项；需要凭据的提供方还要在 `.env` 设置对应变量，例如 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`。只有 `.env` 中有 key 还不够：`config.yaml` 必须有模型条目并引用该变量。像本地 Ollama 这样的无 key 提供方不需要配置 key；容器访问宿主机上的 Ollama 时还需使用 `host.docker.internal` 地址。`make config` 在 `config.yaml` 已存在时会中止，不会覆盖它。

2. 运行 `make doctor` 检查配置。未配置模型时会报告 `models configured` 失败；Windows Docker 路径没有宿主机 Nginx 时，`nginx` 项也会失败，这不妨碍 Docker Compose 内的 Nginx 启动。不要把这两项误读为容器启动健康检查。

3. 构建并启动 Docker 服务：

   ```powershell
   make up
   ```

   等待脚本报告 `DeerFlow is running!`，然后打开 <http://localhost:2026>。默认仅绑定 `127.0.0.1`。

4. 首次访问会进入 `/setup`。在页面创建管理员账号后登录。管理员邮箱和密码由使用者自行设定；不要把它们写进仓库或交给测试脚本。

5. 结束试用时运行 `make down`。它停止并移除该 Compose 项目的容器和网络，不带 `--volumes`；不要自行追加 `-v`，以免删除本机持久数据。`make up` 可以重新启动。

## 配置文件与能力边界

| 文件                     | 用途                                                                  |
| ------------------------ | --------------------------------------------------------------------- |
| `config.yaml`            | 必须有至少一个模型条目；沙箱、工具、Analytics 等 Gateway 配置也在这里 |
| `.env`                   | 模型 key、可选 Jina key、数据库 secret JSON 等运行时环境变量          |
| `extensions_config.json` | MCP 服务和技能启用状态；本机模板生成会创建空配置                      |
| `frontend/.env`          | 前端本机开发配置；Docker 试用一般沿用 Compose 的服务地址              |

上述文件均为 Git 忽略文件。不要提交真实 key、密码、数据库连接材料或管理员凭证。Jina key 是可选项；未配置时仍可使用 `web_fetch`，但可能受到上游匿名请求限额影响。AIO external provisioner 只是 Gateway 调用的外部兼容端点，本仓库不包含或启动其服务端。

聊天依赖有效的 `config.yaml -> models[]`、提供方要求的凭据（如有）以及管理员账号。本次无模型凭据冷启动验证没有发起模型请求，因此模型对话仍需使用者配置后实测。

Analytics 的应用控制面默认使用本机持久 SQLite。要分析业务数据，还需准备一份小型、非敏感的 PostgreSQL 或 MySQL 数据集，并为 Gateway 提供只读账号。管理员在“数据源”登记连接（`secret_ref` 使用 `env://ANALYTICS_DS`），发布与真实表列一致的 schema snapshot，为明确的用户 principal 配置访问 policy，并在“指标”登记指标和维度。凭证 JSON 由 `.env` 中的 `ANALYTICS_DS` 提供，字段为 `engine`、`host`、`port`、`database`、`username`、`password`；TLS 选项见[配置指南](../backend/docs/CONFIGURATION.md)。关闭 TLS 仅允许连接 loopback；容器访问宿主机时不要把 `host.docker.internal` 当作 loopback。

推荐的最小演示数据：一个 `demo` schema、一张包含日期、状态、金额和产品标识的合成订单表、50–200 行合成数据，以及只能读取所需 schema/table/column 的数据库账号。不放入真实个人信息。建议从 1 vCPU、1 GiB 内存和 1 GiB 持久磁盘起步；这是小型样例库的资源预算建议，尚未做容量基准。默认 Compose 不新增业务数据库服务。

`scripts/test_analytics_databases.py --engine all` 使用独立临时 PostgreSQL/MySQL 实例验证驱动、迁移和受控查询；脚本结束会删除临时容器和网络。它们不是可供人工试用的持久数据源。

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
- 启动前确认冲突的四个已停止容器来自另一 checkout（Compose project `docker`，目录为 `D:\develop\workspace\deer-flow\docker`）。仅临时改名以保留容器和卷；本次 `make down` 退出码 0 后，四个容器均恢复原名和原 ID，没有清除卷。
- 当前根配置的 `models` 列表为空，因此模型对话未验证。没有通过持久业务数据库、只读账号、schema snapshot 和用户 policy 完成 Analytics 查询；**经营分析未端到端验证**。按指南填写模型与业务数据源配置后，再由使用者进行人工试用。
- 静态演示未提供可复现的 Agent→沙箱 HTML 写入→artifact 登记→浏览器预览全链路证据；现有 artifact 预览 E2E 使用模拟写入与响应。保留四个可编辑欢迎示例，不增加第五个网页示例。
- `D:\develop\workspace\InsightFlow-6A-baseline-20260924` 仍需保留；它不属于已登记 worktree，可能包含未跟踪文件。不得递归删除或移动，如需清理应先由使用者检查并另行授权。
