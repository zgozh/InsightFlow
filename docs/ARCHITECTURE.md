# InsightFlow 架构概览

InsightFlow 是基于 DeerFlow v2.1.0-rc0 Agent 运行时构建的受控经营分析工作台。上游归属、
许可证和保留范围见仓库 [README](../README.md) 与 [LICENSE](../LICENSE)。

## 服务拓扑

本地 `make dev` 启动三个面向应用的服务；默认 Docker Compose（prod/dev）启动四个容器。Nginx 是对外的统一入口。

| 服务 | 容器端口 | 职责 |
| --- | ---: | --- |
| Nginx | 2026 | 反向代理；转发 API 并提供前端 |
| Gateway | 8001 | FastAPI、LangGraph 兼容接口、Agent 运行时和 Analytics API |
| Frontend | 3000 | Next.js 工作台 |
| Redis | 6379 | Docker Compose 内部 Redis Streams bridge，不发布宿主机端口 |

Nginx 将 `/api/langgraph/*` 映射到 Gateway 的运行时接口，将其他 `/api/*` 请求转发到
Gateway，其余请求交给前端。两个默认 Compose 文件的服务集合是 `nginx`、`frontend`、
`gateway` 和 `redis`；Redis 是必需的默认服务，不是可选 profile。Compose 只将 Nginx
入口绑定到 loopback；Gateway 与 Redis 端口不直接发布到宿主机。

应用数据库默认是 SQLite，数据库文件为 `.deer-flow/data/deerflow.db`（相对 Gateway
工作目录），默认部署持久化在仓库 `backend/.deer-flow` 下。运维人员可通过配置选择外部
PostgreSQL 作为应用数据库，但默认 Compose 不启动 PostgreSQL。业务 PostgreSQL/MySQL 是
单独登记的外部数据源；AIO sandbox 通过显式 DooD overlay 启用。

## 后端分层与运行

- `backend/packages/harness/deerflow/` 提供 Agent、middleware、模型、工具、技能、MCP、
  持久化和 sandbox 抽象，导入前缀为 `deerflow.*`。
- `backend/app/` 提供 Gateway 与 InsightFlow Analytics 服务，导入前缀为 `app.*`。
- App 可以依赖 Harness；Harness 不得依赖 App。Python 扩展通过独立的
  `deerflow-extension-api` 合约贡献受信任组件。

Gateway 通过 RunManager、`run_agent()` 和 StreamBridge 驱动 Lead Agent。middleware 负责
线程数据、上传、沙箱、摘要、标题、计划任务和澄清等生命周期。普通子代理由 `task`
工具委派；定时任务调用相同的 Gateway run 生命周期。平台内置 Analytics Agent 工具只经由
受控查询和报告服务工作。任意第三方 MCP 工具没有被强制接入这条策略链，可能自行访问
数据源；AS-14 仍是发布阻塞，不能把“管理员不会配置危险 MCP”当作通用安全保证。

Sandbox 有 Local 和 AIO 两种配置。Local 在 Gateway 主机执行命令，仅面向可信开发环境；
AIO 将命令放进独立容器。AIO 外部 provisioner 只保留 Gateway 客户端配置，其服务端由
部署方另行提供，本仓库不包含或启动该服务。

## 前端产品面

Next.js 工作台包含登录与设置、分析、聊天、数据源、指标、报告、历史和定时任务页面，
并支持线程产物预览。聊天通过 LangGraph SDK 接收增量事件，状态由线程 hooks 维护。
工作台没有独立的 Custom/Managed Agent 管理、IM 连接、项目/文档/回收站或浏览器控制页面。

## 配置和安全边界

根目录 `config.yaml` 管理模型、工具、沙箱和后台服务；`extensions_config.json` 管理
MCP server 与技能启用状态。二者由示例模板生成，实际文件被 Git 忽略。第三方 Python
扩展和 MCP 服务以 Gateway 权限运行，必须来自受信任来源。

Analytics 查询使用管理员登记的数据源和 opaque secret reference；服务端先授权并生成
一次性计划，再执行受限查询和记录审计。客户端不能覆盖身份或提升查询限额。Gateway
与 sandbox 的权限、网络策略应按部署边界配置。

## 版本

发布版本在 `backend/pyproject.toml` 与 `frontend/package.json` 中保持一致。
`scripts/verify_versions.sh` 校验这两个版本源。项目已移除 Helm chart，不再维护第三个
chart 版本源。

模块级运行细节见 [backend/AGENTS.md](../backend/AGENTS.md)、
[backend/docs/ARCHITECTURE.md](../backend/docs/ARCHITECTURE.md) 和
[frontend/AGENTS.md](../frontend/AGENTS.md)。
