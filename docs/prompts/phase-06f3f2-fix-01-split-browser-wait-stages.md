# Phase 6F3F2 Fix 01：拆分既有浏览器等待点并完成一次定向复核

> 执行者：现有 `gpt-6-luna`（max）。先读 `.reviews/phase-06f3f2-existing-run-browser-trace-and-report.md` 与本文件；不重做报告登录/列表证据，不发模型请求。

上轮唯一浏览器流程在 `.reviews/phase-06f3f2-browser.py` 的合并 `analysis_thread` 阶段 `TimeoutError`。该阶段含 click、URL、轨迹触发器和步骤等待，现有日志不能判定是哪一环；此前登录、报告列表、卡片均已实测通过。按比例原则只修改被 Git 忽略的 browser helper：将这个合并阶段拆成固定安全 checkpoint（点击完成、实际路由是否命中、线程页受控元数据请求 HTTP 状态、trace trigger 是否挂载、panel step 是否出现），每个等待点失败即输出固定布尔/状态码和失败阶段；不输出 URL 中的线程 ID、页面正文、DOM HTML、工具参数、SQL、报告正文、凭据或异常文本。不要改产品代码或增加永久测试来修一个尚未确诊的 helper 超时。

验证 helper 的 Python/PowerShell 语法后，复用同一 DPAPI admin、原 5 容器和同一已发布 run `63cfc92a-97d9-446d-ad21-58d71ff97821`，**只再运行一次**登录→卡片→线程轨迹→artifact 入口的浏览器流程，不发新 Gateway/model run、不重建容器。若能完整通过，记录 Reviewer 拒绝/通过卡片、摘要 evidence 与 owner-checked artifact 下载事件/状态，不读取正文。若仍失败，按精确 checkpoint 区分产品行为和 helper 假设；确定的产品缺陷可在同一切片做最小修复与定点回归，但不能靠第三次浏览器尝试或整套 E2E 碰运气。若不能定因，立即停止并交付可操作的阻断报告。

只在新证据改变结论时更新 `docs/acceptance/phase-06d-contract-reconciliation.md`、`docs/PROGRESS.md`；文档按 V0 检查 diff，不运行无关测试。报告追加到 `.reviews/phase-06f3f2-existing-run-browser-trace-and-report.md`。若只改 ignored helper/报告，不创建空提交；保留固定栈和 DPAPI，工作树干净，停在 GPT 复验。
