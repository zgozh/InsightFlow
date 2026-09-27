# Phase 6F3F4：分析线程 metadata 查询加载态的根因与最小修复

> 执行者：现有 `gpt-6-luna`（max）。先读 `.reviews/phase-06f3f3-analysis-route-before-trace-root-cause.md`、本文件及 `frontend/AGENTS.md`；从 `346f4b4` 继续。不要重跑历史模型 run、报告发布或全量 Playwright。

## 已证事实与假设边界

已发布线程在真实浏览器的 `GET /threads/{id}` 返回 200，body 中 `metadata.analysis_mode` 为严格布尔 true；分析 URL 正确，但 15 秒后仍是 `ExistingAnalysisThread` 的 loading 文案，`ChatPage`/trace trigger 未挂载，pageerror 为 0。当前源码中，该路由的 `useThreadMetadata` 返回值只要 `isLoading || isFetching` 就保持 loading；`ChatPage mode="analysis"` 一旦挂载会无条件输出 trace trigger。`getAPIClient()` 可能使用编译期 `NEXT_PUBLIC_LANGGRAPH_BASE_URL`，因此“任意同路径 GET 200”尚不能证明 SDK 查询正常完成或同源。不得猜测性移除 loading/marker guard。

## 一个连贯切片（不要再拆成多个空转的 Fix）

先 V1 定点诊断，若确认共享路由/配置缺陷再按 V2 定点修复。安全 marker/权限持久化发生变化才升 V3；全量 pytest/Rstest/Playwright、后端数据库和新模型请求均不是本切片默认门禁。

1. 只复用原 owner/线程、DPAPI 和固定 5 容器。先只读对比浏览器页面 origin 与**该路由实际 SDK 请求**的 origin、路径类别、请求启动/完成/失败计数及 HTTP 状态（只报 `same_origin`、固定类别、数字，不打印 URL、ID、header 或 body）；同时核对前端有效的 `NEXT_PUBLIC_STATIC_WEBSITE_ONLY` 与 `NEXT_PUBLIC_LANGGRAPH_BASE_URL` 是否使 SDK 指向当前 Nginx 入口。不要回显任意环境变量的原值或凭据。前次 helper 的 response callback 可能只证明“有一个同后缀 GET 200”，必须区分它与 SDK 查询。
2. 用**一次**聚焦浏览器观察明确查询生命周期：metadata 请求是未发出、反复 refetch、已完成但 UI 仍 `isFetching`，还是请求到了错误 origin/旧服务。可以在 Git 忽略 helper 中收集安全请求/响应计数；如仍不能区分，允许给现有路由增加临时、只输出固定布尔的诊断属性并只重建原 project 的 Frontend 服务一次，诊断完成后移除该属性或证明它属于有价值的永久状态契约。不得记录模型/报告正文、SQL、结果行、token、自由文本异常或整个 DOM。
3. 形成单一根因假设并核对同仓正常聊天路由的 metadata 查询模式。若是前端编译配置/旧镜像问题，修部署状态而非业务代码；若是 TanStack 查询/路由状态代码缺陷，修真正的失效/悬挂源头，保留“marker 非 true 不得进入分析聊天”的 fail-closed 语义。只为确认的可观察回归加一条有价值测试。若确为后端响应/持久化问题，沿实际 SDK 请求追源头，不在前端假装成功。
4. 按改动范围跑最小相关测试、类型/格式检查；然后最多一次同一已发布 run 的只读浏览器复核，目标是分析页面能结束 loading、出现 trace trigger 和 Reviewer 拒绝/通过卡片。若浏览器因客观环境阻断，报告已通过的较窄证据和未验证项，不宣称闭环。报告下载可在同一次复核里顺带检查；不要再新建分析 run、报告或用户。前端需加载改动时只替换 Frontend，不动 Gateway/数据库/卷。
5. 只有新证据改变事实边界时，才更正 `docs/acceptance/phase-06d-contract-reconciliation.md`、`docs/PROGRESS.md`；不把 AS-09/10 单例升级为整项 PASS。报告 `.reviews/phase-06f3f4-analysis-metadata-query-lifecycle.md`，列安全请求生命周期、根因、补丁或未修复理由、实际检查结果与资源状态。若有产品修复，独立提交；若仅环境/ignored helper 修复，不做空提交。工作树干净，停在 GPT 复验。
