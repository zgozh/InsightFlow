# Phase 6F3F5 Fix 01：恢复既有验收栈并复验已发布报告

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。先读 `.reviews/phase-06f3f5-login-readiness-and-existing-report-browser.md` 与上一份 6F3F5 提示词；不重做 6F3F4 的前端修复或已通过的定点测试。

## 已知事实与目标

固定 Compose project `insightflow-acceptance-local` 的只读 `ps --all` 显示：Frontend 为 Up；NGINX、PostgreSQL、Redis 为 Exited (0)，Gateway 为 Exited (137)，约五小时前退出。`/login` 无 HTTP 响应、Gateway readiness 无法运行。因此本轮浏览器流程尚未触及登录产品代码，更不能据此否定前端 `isFetching` 修复。`137` 本身不等于 OOM 结论。

本切片只恢复**同一组既有容器及数据卷**，然后执行一次已有报告的浏览器只读验收。不要新建管理员、报告、Agent run、模型调用或数据库；不要清卷、`down`、`up --force-recreate`、重建镜像、替换配置，且不要触碰旧 6F1 栈。若无法在这些边界内恢复，停线并报告精确原因。

## 执行顺序

1. 只读确认当前 HEAD、tracked 工作树和固定 project 的五个容器 ID、服务名、状态、挂载卷。记录 Gateway 的 `.State.OOMKilled`、退出时间及最近**脱敏**日志类别，不读/输出 `.env`、凭据、请求正文或自由异常文本。核对 Compose project 标签，避免误操作其它栈。
2. 若仍是上述已停止状态，按依赖顺序启动**已存在**的 PostgreSQL、Redis，再启动 Gateway，最后 NGINX；Frontend 已运行则不重启。使用精确 project/容器目标与非重建的 `start` 语义。任何服务起不来时只做一次有界、与该服务直接相关的状态/日志诊断；不要循环重启或扩展到代码修改。
3. 用有界健康检查确认五服务状态、Gateway `/health/ready` 与 NGINX `http://127.0.0.1:29384/login` 可达。若失败，停止浏览器步骤并给出服务/HTTP 状态、退出码、OOMKilled 事实及最可能的下一步；不推测 NGINX 是原先前端 loading bug 的根因。
4. 健康后继续上一份 6F3F5 提示词的浏览器诊断：先对 ignored helper 做最小拆分，分别记录 `login_page`、`email_field`、`password_field`、`submit_click`、`auth_response`、`reports_route` 的布尔/稳定状态。通过既有 DPAPI owner 与临时 profile 执行一次流程，严禁打印账号、密码、cookie、header、URL 参数、响应正文、密钥或 Playwright 异常自由文本。
5. 登录通过后在同一会话打开已有发布报告及 run `63cfc92a-97d9-446d-ad21-58d71ff97821` 的分析线程；核对 loading 消失、trace trigger/panel、Reviewer 拒绝/通过卡片、owner-checked artifact 下载事件与 HTTP 状态。只读，不查看报告正文；不把单例成功写成 AS-09/10 全项 PASS。

## 验证与停止条件

本切片是 V3 定点运行时集成验收，但只需：容器/健康状态、ignored helper 的 AST/语法检查、一次真实浏览器主流程与结果读回。6F3F4 的 Playwright 2/2、Prettier、ESLint、tsc 证据保持有效，不重复跑；不跑全量前后端套件。若真实浏览器暴露确定的**产品代码**缺陷，先记录最小复现与根因，再只修直接受影响文件、跑对应定点回归；不顺手改认证或分析架构。若是环境/脚本错误，只在本切片修最小 helper 问题，最多再尝试一次有明确变化的浏览器流程。

脱敏报告写入 `.reviews/phase-06f3f5-fix-01-stack-restore-and-browser-readback.md`，记录容器 ID 前后是否相同、卷是否保持、Gateway OOMKilled 事实、健康及浏览器 checkpoint、真实 trace/下载结果或精确阻断。若只恢复容器与改 ignored helper，无需空提交；若改 tracked 产品/文档代码，独立提交并保持工作树干净。完成后停在 GPT 复验，不自行启动下一阶段。
