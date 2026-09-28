# Phase 6F3F14：登录后「小惊喜」真实产物试用

从已验收的 `a81e43a` 和保留的固定本机栈继续。用户想确认聊天首页保留的「创建一个小惊喜」不仅能显示，还能像主流 Agent 一样生成可预览的交互式 HTML。本切片只做一条真实产品路径的试用；不要把此结果外推为全局验收。

## 前置与边界

1. 恢复断点时 Docker Desktop Linux Engine 的 named pipe 不存在。先验证 Docker Desktop 是否已安装；若其可执行文件存在且 Engine 未启动，可**仅启动 Docker Desktop 本身一次**（Windows `Start-Process` 必须带 `-WindowStyle Hidden`），有界等待 Engine 就绪；需交互登录/提权、可执行文件找不到或单次启动仍失败时停下并明确告诉用户需要手动开启 Docker Desktop，不循环重试。随后核对 `insightflow-acceptance-local` 原五容器 ID 与三个原卷。若它们只是随 Engine 停止而退出，可参照 `docs/acceptance/phase-06f3f13-local-frontend-refresh.md` 仅按依赖顺序 `docker start` **现有** PostgreSQL、Redis、Gateway、Frontend、Nginx，逐步确认 health；ID/卷漂移或 Gateway 不健康即停。复用原 frontend/Gateway/数据库/Redis/Nginx 与卷，不重建、删卷或修改 env/config，不执行 Compose `up`。
2. 用现有可安全复用的本机测试账号和登录方式，绝不打印、提交或记录口令/API key/cookie。没有可用账号或模型凭证时停止报告，直接告诉主会话缺哪一类输入；不要为本切片创建管理员、重置用户或猜测密钥。模型必须是现有 OpenAI-compatible 配置里的 **`deepseek-flash`**，不能写成其他模型或依赖旧的隐含默认值。
3. 真实 Chromium 经 Nginx 登录并到聊天欢迎页，确认「创建一个小惊喜」可见、点击只把中/英文对应模板填入可编辑输入框、未自动发送；将 `[主题]` 人工替换成具体安全主题（如「星空」）并确认无占位符后，至多**提交一次用户消息**。不要为获取绿色结果反复发起同一模型任务；若失败，抓取安全的稳定状态/错误码和必要的 run、thread、工具名，不输出模型原文、token、凭据、SQL 或用户隐私。
4. 若 run 成功，核对真实 Agent 工具轨迹中是否有沙箱文件生成/展示动作，取得 HTML artifact 的线程绑定路径；通过当前登录用户可访问的现有产物/预览入口打开它，验证 HTML 页面有预期的可见内容和至少一个简单点击互动，且不依赖外网资源。记录 UI 截图（忽略目录）、run/thread ID、产物路径的**非敏感摘要或虚拟路径**及 HTTP/DOM 证据。只查这一条路径，不跑普遍性的安全渗透或模型评测。
5. 如模型回答文本但没有生成产物、工具不可用、预览失败或运行超时，明确区分哪一段断链；停止在事实结论并向主会话提出最小修复点，**不要本轮自行扩成架构改造或重试多次**。不把欢迎示例、模拟 Playwright 或普通聊天 6F3F11 当成真实 HTML 链证据。若运行产生试用会话/产物，保留它供用户查看，不删除既有数据。

## 验证与交付

V3 仅针对已部署产品的这一条登录→填充→单次提交→真实 Agent→沙箱→HTML artifact→预览链；不跑全量前后端、数据库集成、前端 build、其它 E2E 或无关模型。若只做到了预填而没有真实产物，也如实记录阶段性结果。把命令/浏览器步骤、模型名、计数、每个边界的事实证据、剩余问题与是否需要用户操作写入 `docs/acceptance/phase-06f3f14-real-surprise-artifact-trial.md`，同步 `docs/PROGRESS.md`；提示词和记录一个纯文档提交，提交后工作树检查，不 push，停在 GPT 复验。
