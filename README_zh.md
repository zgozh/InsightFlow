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

需要 Docker Compose、Python 3.12+、Node.js 22+、uv 和 pnpm 10.26.2+。

1. 生成本地配置并安装依赖：

   ~~~sh
   make config
   make install
   ~~~

2. 编辑被 Git 忽略的 config.yaml，在 models 中至少配置一个模型。将 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 等凭证保存在环境变量中。
3. 启动开发环境：

   ~~~sh
   make dev
   ~~~

打开 http://localhost:2026。Nginx 发布端口默认只绑定本机回环地址。优化后的本地环境使用 make start；生产 Docker 环境使用 make up。分别使用 make stop 或 make down 停止。

不要提交 config.yaml、extensions_config.json、.env 或模型凭证。配置说明见 [CONFIGURATION](backend/docs/CONFIGURATION.md)，部署说明见 [Install](Install.md)。

## 分析与 Agent 边界

Analytics 查询经受控查询服务执行：数据源凭证保存在服务端 secret reference 中，查询计划先授权再执行，并保留审计历史。Agent 工具不能绕过该服务直接查询登记的数据源。

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
