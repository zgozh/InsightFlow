# Phase 6F3F4 Fix 01：验证并修复分析路由的 metadata refetch 加载循环

> 执行者：现有 `gpt-6-luna`（max）。从暂停记录 `.reviews/phase-06f3f4-pause-handoff.md` 和当前 `docs/prompts/phase-06f3f4-analysis-metadata-query-lifecycle.md` 续接；不重做模型、报告、数据库与前几轮浏览器证据。

## 已有证据与单一假设

同一已发布分析线程的 `metadata.analysis_mode` 为严格布尔 true；真实浏览器内两次同源 LangGraph SDK metadata GET 均完成且为 HTTP 200，但路由持续显示 loading。源码中 `ExistingAnalysisThread` 在 `metadata.isLoading || metadata.isFetching` 时返回 loading，而其子 `ChatPage` 一旦挂载又使用同一 `useThreadMetadata` 查询（默认 `staleTime=0`），可能使子组件挂载触发 refetch、父组件因 `isFetching` 卸载子组件，形成循环。**这是待验证假设，不是授权先改代码。**Gateway 的 run admission 仍是权威安全门，普通线程 marker=false 绝不能被前端强行进入分析模式。

## 一个连贯实施与验收切片

验证级别 V2（共享路由/查询状态）+ 一次真实浏览器定点复核；不跑全量 E2E/Rstest/构建以求安心。新代码注释和测试场景中文优先。

1. 在现有 `frontend/tests/e2e/analysis-entry-activation.spec.ts` 用已有 `mockLangGraphAPI` 构造**已存在且 metadata.analysis_mode=true** 的线程，直接打开 `/workspace/analysis/{id}`，断言 loading 会结束且 `[data-testid="analytics-trace-trigger"]` 出现。让该线程 metadata 的第二次 GET 可观察，以证明是子组件挂载/同 key 重新取数造成父路由被 `isFetching` 反复遮挡；不要靠 sleep 制造 RED。先运行这一条，记录真实 RED；若不能复现，停下改用暂停记录中的最小 query-state 布尔探针，不凭假设修改产品代码。
2. 若 RED 与假设一致，仅修 `frontend/src/app/workspace/analysis/[thread_id]/page.tsx` 的路由初始加载判断：有可用已验证 metadata 时，后台 refetch 不应卸载 ChatPage；同时保持 `metadata` 缺失、查询错误、marker 非严格 true 的既有 fail-closed 状态。不要移除 marker 检查、改变 Gateway admission、加重试/全局缓存或新状态源。把已有普通聊天 ID 拒绝用例与新合法线程用例一起跑 GREEN。
3. 若还需确认，比较 SDK metadata GET 次数在修复前后是否不再持续循环；计数只记整数和固定状态，不输出 URL、ID、请求/响应正文、SQL、token、凭据。直接改动文件做 TypeScript/ESLint/Prettier 定点检查；不机械重跑全前端测试。生产镜像无源码挂载时只 build/recreate 既有 project 的 Frontend，保留 Gateway/数据库/卷。
4. 对同一已发布 run **只再做一次**真实浏览器只读复核：应离开 loading，出现 trace trigger/panel 与 Reviewer 拒绝/通过状态，且报告 artifact 的 owner-checked Web 入口/下载事件可达；不读取正文，不创建新 run、报告或用户。若仍失败，报告具体新断点并停止，不展开又一轮盲试。
5. 按实际证据更新 AS-09/10 与 PROGRESS 的事实边界；单例通过不等于场景全项 PASS。实现+直接测试一个提交，文档可同提交；若假设未证实且无代码修复，只写 ignored 报告、不造空提交。报告 `.reviews/phase-06f3f4-fix-01-metadata-refetch-loop.md` 列 RED/GREEN、精确改动、浏览器结果、未验证项和固定栈状态。工作树干净，停在 GPT 复验。
