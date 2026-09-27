# Phase 6F3F3：分析路由未挂载轨迹的根因闭环

> 执行者：现有 `gpt-6-luna`（max）。实施依据为本文件和 `.reviews/phase-06f3f2-existing-run-browser-trace-and-report.md`；从 `de0c198` 继续，不重做之前两次浏览器流程，不发模型/Gateway 新 run。按 `systematic-debugging` 先证实根因再修。

## 已知断点与确定的代码条件

同一已发布 run 的报告卡片点击成功、URL 命中 `/workspace/analysis/{thread_id}`、该线程 metadata GET 为 200，但 `analytics-trace-trigger` 未挂载。只读代码核对表明 `frontend/src/app/workspace/analysis/[thread_id]/page.tsx::ExistingAnalysisThread` 只有在 `metadata.data.metadata?.analysis_mode === true` 时才返回 `<ChatPage mode="analysis" />`；而 `chat-page.tsx` 在 analysis mode 下无条件渲染 `<AnalyticsTracePanel>`，该组件无条件渲染 `analytics-trace-trigger`。因此“HTTP 200”尚不足以证明 marker 为 true，也未排除路由状态/客户端异常或旧前端镜像。不能把按钮缺席直接归因于 trace 投影算法。

## 一个诊断/修复切片

验证级别：先 V1 只读精确分支诊断；若确认为前端路由/共享线程 marker 问题，则按受影响面 V2（安全准入/持久化改动才升 V3 定点集成）。不用全量测试、全量 Playwright、构建或新模型请求作为例行收尾。

1. 只用既有 DPAPI owner 会话和同一 thread，在进程内读取该次 `GET /threads/{id}` 的固定结构；仅输出 `status`、`metadata_is_object`、`analysis_mode_is_true` 三项与字段类型枚举，不输出整个 metadata 或线程 ID。若 marker 不是严格布尔 true，沿服务端线程创建/持久化/读取路径追溯为何 6F3E10 当时 `analysis_mode=true` 却当前不满足；**不得**通过去掉前端 guard、默认标为 analysis 或把普通线程升级来掩盖问题。
2. 若 marker 严格为 true，做**一次**聚焦浏览器观察（不是完整报告流程）：直接打开同一分析线程，只记录固定 route-state 分支（loading/unavailable/missing/wrong/none）、分析页外壳是否挂载、按钮是否挂载，以及客户端 pageerror 是否发生的固定类别/计数；浏览器网络只收该 thread metadata 的 HTTP 状态和 marker 布尔，不记录响应正文、控制台自由文本、截图、HTML、SQL、行、报告正文或凭据。检查当前 Frontend 容器是否加载了包含 analysis guard/trace testid 的构建；若镜像与已提交源码不符，只重建/替换现有 project 的 Frontend 服务，不碰 Gateway/数据库/卷，然后用同一 focused 浏览器步骤确认。
3. 仅在证据确定根因后改最小生产路径：marker 持久化丢失则修服务端源头并保护“普通线程不可升级”；路由查询错误则修前端查询/状态；旧镜像则只修部署状态。为已确认的产品缺陷补一条直接回归。按修改面跑定点测试、类型/格式检查；修复后最多一次同 run 的只读浏览器复核轨迹按钮、Reviewer 拒绝/通过及报告入口。不要发第三条分析 run 或重复完整浏览器套件。
4. 若此次仍只能观察到“按钮缺席”而没有 marker、route state 或异常类别，停止并报告具体无法取得哪一项证据；不猜测修复，不扩展范围。新证据改变 AS-09/10 结论时才更新验收文档与 PROGRESS，纯文档按 V0 diff 检查。

交付脱敏报告 `.reviews/phase-06f3f3-analysis-route-before-trace-root-cause.md`，含根因链、实际检查、修复/未修复原因与尚未验收项。生产修复用独立提交；只改文档则文档提交；只改 ignored helper 无须空提交。保留固定验收栈/DPAPI，工作树干净，停在 GPT 复验。
