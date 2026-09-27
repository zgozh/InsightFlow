# Phase 6F3F5：前端更新后的登录就绪与既有报告浏览器验收

> 执行者：现有 `gpt-6-luna`（max）。从已复验的路由修复 `92b70a8` 继续；先读 `.reviews/phase-06f3f4-fix-01-metadata-refetch-loop.md`。该修复的定点 2/2 Playwright、Prettier/ESLint/tsc 证据有效，不重跑。

## 目标与边界

唯一一次修复后浏览器尝试在合并的 `login` 阶段报通用 `Error`，没有到分析页；这既不是路由修复失败的证据，也不能说明登录产品代码有错。只复用固定验收栈和已发布 run `63cfc92a-97d9-446d-ad21-58d71ff97821`。不发模型/Gateway 新 run，不重建 Frontend/Gateway 或数据库，不轮换凭据，不创建用户/报告。

验证为 V1 环境/验收脚本诊断 + 一条 V3 定点浏览器主流程；不跑全量前后端套件。先只读确认原 project 的 5 容器状态、Frontend/Nginx 的 `/login` 经现有入口返回正常页面状态、Gateway health 可用；如果 Frontend 刚更新尚未就绪，做一次有界健康等待再进入浏览器，不靠重复启动 Playwright 碰运气。容器若异常，报告具体服务/状态，不擅自重建其它资源。

在 Git 忽略的 `.reviews/phase-06f3f2-browser.py` 中仅拆分登录诊断：记录固定 checkpoint `login_page`、`email_field`、`password_field`、`submit_click`、`auth_response`、`reports_route` 各自是否完成，以及同源认证 API 的固定 HTTP 状态；不得记录 email/password、cookie/header、URL 参数、响应正文或 Playwright 异常自由文本。先 Python/PowerShell AST 检查，再用现有 DPAPI owner 和临时 profile 执行**一次**浏览器流程。

若登录通过，直接在同一会话打开已有报告与分析线程，核对修复后的页面退出 loading、trace trigger/panel、Reviewer 拒绝与通过卡片，并尝试 owner-checked artifact 下载事件/HTTP 状态；不读取报告正文。若登录失败，根据精确 checkpoint 区分站点未就绪、脚本选择器/等待条件、认证 API 状态或产品缺陷；能以现有代码/状态证明的 helper 问题可在同一切片最小修复并只再试一次，不能盲试。若需重置管理员、访问私有凭据或权限扩张，停下说明用户需执行的动作。

若证实产品代码缺陷，先给出最小复现与根因，再改直接受影响文件并跑对应定点回归；不要顺手改分析路由或认证架构。只在新证据改变结论时更新 `docs/acceptance/phase-06d-contract-reconciliation.md` 与 `docs/PROGRESS.md`，不把 AS-09/10 单例升为整项 PASS。脱敏报告 `.reviews/phase-06f3f5-login-readiness-and-existing-report-browser.md` 应列健康/登录 checkpoint、真实轨迹与下载结果或精确阻断。若只改 ignored helper/报告，不做空提交；若改产品或文档，独立提交并保持工作树干净。完成后停在 GPT 复验。
