# InsightFlow

InsightFlow 是受控的经营分析工作台，基于 DeerFlow v2.1.0-rc0 的 Agent 运行时构建。仓库保留上游 MIT 许可证与版权声明；许可条款见 [LICENSE](LICENSE)，上游项目见 [DeerFlow](https://github.com/bytedance/deer-flow)。

## 功能

- 对登记的数据源、指标、报告和审计历史提供受控分析。
- 基于会话的分析，支持流式响应、产物、普通子代理任务和定时运行。
- 精简的网页研究路径：DuckDuckGo 搜索与 Jina 抓取。
- 由运维人员配置 MCP 服务和技能；安装技能时执行 SkillScan 检查。
- 为 Agent 文件与命令工具提供 Local 和 AIO 沙箱模式。

工作台包含分析、聊天、数据源、指标、报告、历史和定时任务页面。产品面不包含已删除的 IM 桥接、Custom Agent 编辑器、项目/文档/回收站页面或交互式浏览器控制。

## 快速开始

Docker 本机试用需要 Docker Desktop/Compose、`make`、Python 3.12+ 和 `uv`。本地开发还需要 Node.js 22+ 与 pnpm 10.26.2+。

1. 在交互式终端运行配置向导，选择模型；仅当所选提供方需要时才输入 API key。本地 Ollama 不需要 key；Docker 中运行的 Gateway 连接宿主机 Ollama 时，需将 `base_url` 设为 `http://host.docker.internal:11434`：

   ~~~sh
   make setup
   ~~~

2. 启动 Docker 试用环境：

   ~~~sh
   make up
   ~~~

打开 http://localhost:2026，并在首次访问时通过 `/setup` 创建管理员账号。Nginx 发布端口默认只绑定本机回环地址。使用 `make down` 停止 Docker 服务；源码开发可先运行 `make install`，再使用 `make dev`。PowerShell 本机试用、模型配置和 Analytics 前置条件见[本机试用指南](docs/LOCAL_TRIAL.md)。

必填项、默认配置、经营分析凭据与高级选项的区别见[配置速览](docs/LOCAL_TRIAL.md#配置速览)。

持久化合成 PostgreSQL 16 演示是手动 opt-in 的 Compose overlay，启动方式见[本机试用指南](docs/LOCAL_TRIAL.md)；`make up` 不会启动它。

不要提交 config.yaml、extensions_config.json、.env 或模型凭证。配置说明见 [CONFIGURATION](backend/docs/CONFIGURATION.md)，部署说明见 [Install](Install.md)。

## 分析与 Agent 边界

平台内置 Analytics 查询工具经受控查询服务执行：数据源凭证保存在服务端 secret reference 中，查询计划先授权再执行，并保留审计历史。任意第三方 MCP 工具目前没有被强制接入这条策略链，可能提供独立的数据访问路径；统一约束所有 MCP 访问仍是发布阻塞。

Lead Agent 可将普通任务委派给内置子代理。定时运行使用 Lead Agent 和标准 Gateway run 生命周期。Local 沙箱命令以 Gateway 主机权限运行；AIO 使用独立沙箱服务。外部 AIO provisioner 仅作为配置的客户端端点；本仓库不包含或启动该服务。

MCP 服务、扩展、模型提供方和沙箱端点均应视为可信代码或服务。不要把 Gateway 直接暴露给不可信网络。

## 开发

~~~sh
# 全应用依赖检查
make check

# 后端
cd backend
make test
make lint

# 前端
cd frontend
pnpm check
pnpm test
pnpm test:e2e
~~~

后端默认测试套件离线运行；真实 Provider 测试需显式启用。参见[后端开发说明](backend/AGENTS.md)、[前端开发说明](frontend/AGENTS.md)和[验收场景](docs/acceptance/acceptance-scenarios.md)。

## 许可证与归属

本仓库基于 DeerFlow v2.1.0-rc0 派生，保留其 MIT 许可证和版权声明。InsightFlow 的专属修改在本仓库维护。详见 [LICENSE](LICENSE)。
