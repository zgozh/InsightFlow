# 指标前端：独立审查后的三处夹具补正

主会话已中断旧frontend实施者并冻结源，然后独立读取panel/core/API与失败测试。当前没有发现生产grant dispatch缺陷，不重写panel。由新的 `gpt-6-luna` / max 完成这个极小切片；禁止继续背景阅读/扩大测试/部署/改后端/新增功能。旧前端实现已落盘，所有既有品牌/黑洞和本轮grant修改保留。

## 已定位根因与最小修补

1. `tests/unit/components/analytics/metric-grant-panel.dom.test.tsx` mock整个 analytics/api只导出三个函数，漏 `AnalyticsRequestError`。真实 analytics-catalog-views 的 `analyticsErrorStatus()` 首先 instanceof该类；漏mock会直接抛错。补出该真实错误类（使用项目支持的partial actual mock，或与已有API夹具一致的最小Error类替身），保留三API spies，不修改生产错误判断。
2. 同文件“blocks duplicate submissions in the same turn”在同步act点击后立即断言 mockedGrant call count，但实际useMutation调用API异步调度。panel的submissionLock已在handler同步设定并禁按钮。**先 await waitFor(mockedGrant被调用一次)，再resolve deferred promise**；保留两次同一turn提交/禁重提交断言。若实际仍无法调用则报告具体stack再修，不能直接删除用例或放宽生产锁。
3. `analytics-admin-panels.dom.test.tsx` 在关闭revenue、打开margin后 `screen.getByText('margin')` 同时命中表格和对话框。使用 `within(screen.getByTestId('metric-grant-panel')).getByText('margin')` 精确断言新面板，保留旧输入清空证明。
4. 修这两文件import顺序与Prettier。前端production已经tsc/Prettier/diff通过，只有测试改动不重跑tsc或96项既有有效证据。运行新panel三个用例（整个该文件）与admin-panel切换指标这一用例；Rstest如无testName filter只跑这两个相关文件即可，不重跑core/API/其他页面。
5. 将 `docs/acceptance/2026-10-08-metric-grants-frontend.md` 验证占位补为真实命令/结果：前轮96/99、3夹具补正后定点结果、既有TS/格式/diff证据和仅测试ESLint修正。确认已通过的检查需要找到旧实施者实际日志/报告，找不到精确命令则标明其报告证据，不伪造命令。限制仍未部署/未改真实账号。

只拥有上述两个tests与这一验收文档。生产源禁止修改（除非已证明真实缺陷且先回报主会话），不改hooks/core/AGENTS/current-capabilities/总PROGRESS/INTERRUPTION。完成实际定点检查与两文件ESLint/Prettier/diff即冻结；给准确结果，不再研究下一阶段。
