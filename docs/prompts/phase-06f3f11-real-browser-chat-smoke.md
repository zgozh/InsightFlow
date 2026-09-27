# Phase 6F3F11：真实浏览器普通聊天最小闭环

> 执行者：现有 `gpt-6-luna`（max）实施子 Agent。6F3F10 的诊断报告已通过 GPT 复验：旧失败来自 ignored runner 的 `recursion_limit=10`，正常 Gateway 默认配置下一次 API chat run 已成功。此轮只验证用户实际操作路径，不重新诊断该旧错误。

## 目标

固定验收栈 `insightflow-acceptance-local` 上，从真实 Chromium 登录 → 进入普通聊天 → 通过 UI 发送一条简短合成问题 → 收到可见的完成回复 → 刷新后仍能看到同一会话消息。模型名精确为 `deepseek-flash`。这条证据与既有 API 成功、run-event DB 重启持久证据互补，不扩写为所有模型或分析场景通过。

## 边界与步骤

- 先只读确认五服务健康、入口 `/login` 可达；复用现有 DPAPI owner 和临时 profile。不得打印账号、密码、cookie、header、请求正文、模型回复、URL 参数或原始异常自由文本。
- 使用前端当前真实聊天输入控件和模型选择；若 UI 显示的模型不是 `deepseek-flash`，按现有操作选择它并只记录稳定模型名。不要通过直接 Gateway API 替代本轮的 UI 发送动作。请求不包含 `recursion_limit` override，也不人为提高全局预算。
- 只发**一次**无需工具的短合成消息，给出有界完成等待。结构化记录：发送动作是否触发、目标 thread/run 是否生成、run status 是否 `success`、回复在 UI 是否非空可见、是否出现错误提示、持久 run messages/events 的安全计数。刷新同一会话页面后确认用户消息和 AI 回复仍可见；不要保存正文或屏幕截图。
- 如一开始登录/页面无法到达，先按服务健康与 UI checkpoint 定位，不盲目重试模型。若已发送而失败，只用该 run 的稳定错误类型/阶段及受影响代码判因；明确产品缺陷时可做最小修复和直接回归，代码改变后最多再发一次合成消息。不要重建 Gateway/DB/Redis/NGINX 或清卷；仅前端代码确实改动时才更新 frontend 镜像。

验证级别 V3 的**单条主流程**；不跑全量后端、前端、Playwright 套件或另一个分析 run。既有 6F3F5/6F3F6 浏览器报告/轨迹与 6F3F9 DB 事件持久证据仍有效。若只是 ignored helper 与读回，无需空提交；若产生真实产品改动，做直接相关测试、diff review 和独立提交。必要时最小更新 `docs/PROGRESS.md`，只写这条普通浏览器聊天是否通过，不宣称整个 Phase 6/AS-09 完成。

脱敏报告放 `.reviews/phase-06f3f11-real-browser-chat-smoke.md`，记录前置健康、UI checkpoint、run 终态、刷新后可见性、失败分类（若有）、命令/退出码、固定容器/卷是否保持。完成后停在 GPT 复验，不自动启动下一阶段。
