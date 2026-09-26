# AGENTS.md

本文件是 InsightFlow 前端开发指南；同目录的 `CLAUDE.md` 通过
`@AGENTS.md` 引入本文件。开始修改前还需阅读目标目录最近的 `AGENTS.md`。

## 产品与技术栈

前端是 Next.js 16、React 19、TypeScript 5.8、Tailwind CSS 4 和 pnpm 10.26.2
构建的受控经营分析工作台，需要 Node.js 22 或更新版本。LangGraph SDK 负责线程运行
与流式响应，TanStack Query 管理服务端状态。

工作台页面包括分析、聊天、数据源、指标、报告、历史和定时任务。独立的
Custom/Managed Agent、IM 连接、项目/文档/回收站、浏览器控制、博客、showcase 和文档页
均已从产品面移除。普通 `task` 子代理进度仍属于聊天运行时。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `pnpm dev` | 启动开发服务器 |
| `pnpm build` | 构建生产版本 |
| `pnpm check` | 运行 lint 和 TypeScript 检查 |
| `pnpm format` / `pnpm format:write` | 检查 / 应用格式 |
| `pnpm test` | 运行 Rstest 单元及 DOM 项目 |
| `pnpm test:e2e` | 运行 Playwright E2E |
| `pnpm start` | 启动生产构建 |

单元测试位于 `tests/unit/`。纯逻辑使用 node 项目；只有真实 DOM、React effect 或组件
交互需要 `*.dom.test.tsx`。Playwright 测试位于 `tests/e2e/`，通常通过
`page.route()` 拦截 Gateway 请求；fixtures 必须与当前 API schema 一致。

开发服务器默认使用 Webpack。只有诊断本地 bundler 问题时才设置
`DEER_FLOW_DEV_BUNDLER=turbo`。宿主机 pnpm 命令经 `scripts/pnpm.py` 运行，以遵循仓库
锁定的 pnpm 版本。

## 源码布局

- `src/app/`：首页、登录/初始化/认证回调、工作台路由、产物查看器和同源 API handlers。
- `src/app/workspace/`：`analysis/**`、`chats/**`、`datasources`、`metrics`、
  `reports`、`history`、`scheduled-tasks`。
- `src/core/threads/`：线程创建、历史、stream、元数据与运行生命周期 hooks。
- `src/core/analytics/`：严格响应 schema、API、query hooks 和安全 trace 投影。
- `src/core/api/`：Gateway fetcher、LangGraph client、stream mode 检查和静态模式 fallback。
- `src/core/tasks/`：普通 `task` 工具子代理的实时进度和历史步骤。
- `src/core/i18n/`：中文与英文词典；InsightFlow 新增的用户文案必须同时提供两种语言。
- `src/components/workspace/`：聊天、Analytics、设置、定时任务和产物界面。
  `ui/`、`ai-elements/` 是生成组件，不要手工修改。

## 运行时边界

标准开发和 Docker 环境经 Nginx 访问 Gateway。默认保留空的
`NEXT_PUBLIC_BACKEND_BASE_URL` 和 `NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph`。
仅当显式分离前后端本地开发时才直接配置 Gateway URL。

线程 hooks 负责提交和 stream 状态。支持的 stream mode 以
`src/core/api/stream-mode.ts` 为准；不支持的模式必须在发 HTTP 请求前拒绝。SSE replay
gap 后应重新载入持久状态并继续订阅；gap 不是运行结束，也不能取消仍在执行的 run。

定时任务固定运行 Lead Agent。页面不得查询已删除的 Agent catalog 或发送任意
`assistant_id`。用户没有主动修改时间间隔时，保存和复制操作都应保留原频率。

静态模式只可为仍被保留的只读 Gateway 路由提供 fixtures。写请求和未知路由应在本地失败；
不能为已删除的 Agent、子代理或 IM API 添加伪造成功响应。

## Analytics 数据边界

`src/core/analytics/` 是前端访问受控 Analytics API 的唯一入口。请求统一使用
`@/core/api/fetcher`，响应必须通过严格 Zod schema。SQL、凭证、DSN、计划令牌、结果行和
异常原文不能进入 query key、trace 或面向用户的错误消息。前端管理员判断只控制界面，
Gateway 授权仍是最终边界。

分析页复用常规聊天 providers 和线程 stream。Analytics trace 只安全投影审核通过的工具名
与字段，不创建第二份运行状态，也不渲染原始工具 payload。

报告 Reviewer 轨迹只从当前 `write_analysis_report` 的后端安全 ToolMessage 回执派生：只有完整的
`published` / `existing` 回执能显示复核通过和固定报告产物；拒绝只显示有限 reason code 的本地化文案，
复核不可用/超限分别显示失败/受限。evidence 预检、发布冲突、未知码或损坏回执不得推断 Reviewer
结论；普通聊天历史中的 `publish_analysis_report` 与 `task` 映射继续保留。这只是现有消息的纯投影，
不是第二状态源，也不代表 AS-09 已整体验收。

## 国际化与样式

InsightFlow 新增的前端文案以中文为主，并进入现有 i18n 体系，同时提供 `zh-CN` 与
`en-US`。不要在 JSX 中内联语言分支；稳定错误码和机器日志字段保持英文。

根布局保持静态：`src/app/layout.tsx` 不读取 cookies，也不导入聊天专用 KaTeX /
Streamdown 样式。认证 locale provider 由登录和工作台布局负责。富文本 CSS 只加载在实际
渲染对应内容的页面。

当前 pnpm workspace override 用于约束保留的 Nextra/MathJax 依赖链中的
`@xmldom/xmldom`。只有依赖链不再解析易受影响版本后才能移除 override；调整该项时先
运行生产构建。

## 提交前检查

1. 遵循目标目录最近的 `AGENTS.md`。
2. 按根目录比例工程策略选择 V0–V3；可观察行为、重要契约或确认的回归需要持久保护时，补充或更新
   `tests/unit/`、`tests/e2e/` 测试，不为机械改名或已有覆盖重复加测试。
3. 先对受影响文件做格式与定点检查。共享类型/接口/配置按 V2 检查受影响模块；启动、路由、依赖、构建
   行为或里程碑集成按 V3 运行相应的 `pnpm check`、`pnpm build`、E2E。纯文档变更按 V0 回读与检查 diff；
   不把 `pnpm format:write`、全量检查和生产构建当作每次提交的固定仪式。适用的显式 CI 门禁仍须满足。
4. 路由、命令或模块边界变化时同步更新本文件。
