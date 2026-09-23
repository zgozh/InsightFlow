# 前端源码边界

本指南描述 InsightFlow 前端的活动代码边界。新增功能遵循仓库级
`AGENTS.md` 的中文优先、i18n 和测试约定。

### Data Flow

1. 聊天页面通过 `core/threads/hooks.ts` 提交用户消息并启动 Gateway run。
2. LangGraph SDK 消费 SSE；`core/api/stream-mode.ts` 在请求前校验
   Gateway 支持的模式，`core/threads/stream-state.ts` 合并非消息状态。
3. 线程 hooks 更新消息、产物、普通子代理进度和运行状态，Workspace 组件订阅
   并渲染。
4. `useThreadHistory` 从 Gateway 分页读取持久化消息，再按服务器提供的
   `deerflow_seq` 与身份锚点合并检查点和当前流。不要用时间戳重新排序，也不要
   丢弃已显示的消息。

流重连遇到 replay gap 时，`core/api/api-client.ts` 清理旧游标，重新读取持久状态，
再从保留尾部继续订阅。gap 不代表 run 已结束，不能因此取消后端 run。

## 聊天与子任务

- `src/app/workspace/chats/[thread_id]/page.tsx` 负责普通聊天页的提交、导航和编辑后
  重跑；分析页复用同一聊天状态与 providers。
- `src/components/workspace/messages/message-list.tsx` 负责消息列表、人机输入卡片和
  子任务卡片。页面只把卡片答复转换为普通用户消息。
- `core/tasks/` 聚合 `task_started`、`task_running` 和终态工具结果中的子代理进度。
  实时步骤与历史回填按 message index 去重，累计 token 用量只能前进，重播事件不能重复
  累加。
- 定时任务页面固定调用 Lead Agent，不查询 Agent catalog，也不发送任意
  `assistant_id`。用户未显式编辑频率时保留已有间隔。
- 主聊天与 Side Chat 可以共享模型选项 UI，但保留各自的选择回调和模式/推理强度状态。

## 产物和面板

`ThreadState.artifacts` 是 run 产物的事实来源；Artifact provider 只保存线程范围内的
面板状态和刷新缓存。正式产物在 run 完成后刷新，未完成的 `write_file` 预览保持为临时
消息状态。编辑只允许针对已加载的 UTF-8 文本产物；保存时校验 SHA-256 版本，冲突不能
覆盖 Agent 新输出。

CSV/TSV 预览通过 worker 解析，限制输入大小、行列数和处理时间。不要把解析工作移回
主线程。聊天右侧面板由 ChatBox 统一布局，Artifact 与 Side Chat 共用同一可调整面板组。

## API 与静态模式

`core/api/fetcher.ts` 统一 Gateway REST 请求、cookie 和 CSRF 行为；
`core/api/api-client.ts` 提供 LangGraph SDK 客户端。静态模式的只读 fallback 位于
`core/api/static-response.ts`，仅为仍在使用的路由提供明确 fixture。写请求和未知路由
必须失败，不能为已删除的 Agent、子代理或 IM API 返回伪造成功。

新功能应在对应的 `core/` 域内封装 schema、API 和 hooks；页面不要散落原始 fetch。

## Analytics 数据边界

`core/analytics/` 是前端访问受控 Analytics API 的唯一入口。所有请求经
`core/api/fetcher`，每个响应使用严格 Zod schema 校验。查询键、日志、错误文案和 trace
投影不得包含 SQL、凭证、DSN、计划令牌、结果行或异常原文。

Analytics trace 只展示审核通过的工具名和字段，是 LangGraph 消息的纯投影，不创建第二套
run 状态。前端管理员判断仅控制界面显示，Gateway 的授权仍是最终边界。

## 国际化与公共页面

InsightFlow 新增的用户可见文案以中文为主，并同时提供 `zh-CN` 与 `en-US` 词条。
稳定错误码、机器日志字段保持英文。不要在 JSX 中通过条件表达式内联两种语言。

根路由布局保持静态：`src/app/layout.tsx` 不读取 cookie，也不引入聊天专用 KaTeX、
Streamdown 样式。登录与工作台布局负责认证后的 locale provider。富文本样式只加载到
确实渲染对应内容的页面。

## 测试

- 纯逻辑放在 node Rstest 项目；真实 DOM、React effect 和组件交互使用
  `*.dom.test.tsx`。
- 路由与流交互放在 Playwright E2E；请求 mock 必须符合 Gateway 当前 schema。
- 修改核心 UI 后运行 `pnpm format:write`、`pnpm check`、相关 Rstest、E2E 与
  `pnpm build`。
