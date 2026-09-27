# Phase 6F3F13：固定本机验收栈前端刷新

从 `9aa40ef` 的已复验首页代码继续。用户希望直接在本机浏览器看到新像素黑洞、GitHub 入口和聊天“小惊喜”示例；当前 6F3F12/Fix 01 只做了源码与 Playwright 定点验证，**尚未部署到固定的 `insightflow-acceptance-local` 栈**。本切片只刷新现有前端运行产物并做真实 Nginx 入口检查，不改应用功能。

## 操作边界

1. 先读 `docs/LOCAL_TRIAL.md` 和既有 `.reviews/` 中与固定验收栈直接相关的最新记录，核对 Docker 运行状态、Compose project、实际 compose 文件/参数、公开入口和当前 frontend 容器/镜像 ID。只读采集回滚所需旧 frontend image ID 与容器 ID；不要输出 `.env`、`config.yaml` 或密钥内容。如果固定栈不是预期的 project、其他服务不健康或需先动数据库/Gateway，则停下报告，不擅自升级范围。
2. 如现有构建流程能安全只更新 frontend，则在相同 Compose project 中只构建/替换 frontend 服务，保留原 Nginx、Gateway、Redis、应用数据库、业务数据库与所有卷。不得运行 `down`、`down --volumes`、`pull`、全栈 `up --build`，不得新建并行验收栈。记录新旧 frontend 容器/镜像 ID；若更新失败，按第 1 步记录恢复旧 frontend，报告真实状态。
3. 经真实 `http://127.0.0.1:29384/`（若固定栈入口已变，以第 1 步核对值为准）确认：`/` 可访问；新红橙 SVG favicon 可获取且页面优先采用它；页头 `GitHub 仓库` 安全外链指向 `https://github.com/zgozh/InsightFlow`；Hero CTA 仍指向 `/workspace`；桌面与 375px 手机视口均能看见文字与黑洞且不重叠。若已有安全可复用的普通用户本地会话，再额外确认欢迎页“小惊喜”只预填可编辑文本；不要创建/删除账号、重置数据或发起新的模型调用来完成本切片。
4. 检查 Nginx/Gateway/frontend 容器仍为预期运行状态，仅针对本次更新的 HTTP/浏览器路径做定点冒烟。若浏览器显示旧 favicon，区分缓存与服务端产物，给用户明确刷新方法；不要因此重建其他容器。别把没有执行的真实 Agent→沙箱→HTML artifact 链说成已验收。

## 验证、证据和交接

这是本机部署/入口变更，验证等级 V3 但范围只限前端服务更新与对应入口。无需重跑 6F3F12 已通过的全量/定点单测，更不跑后端全套、PostgreSQL/MySQL 门禁或真实模型；只有产物构建和部署后冒烟是新证据。把时间、旧/新 frontend ID、命令退出码、入口结果、是否做了登录态欢迎示例检查、回滚可行性和未验证项写到 `docs/acceptance/phase-06f3f13-local-frontend-refresh.md`，同步 `docs/PROGRESS.md`，与本提示词一起提交一个纯文档记录。提交前后工作树检查，固定 tag/tree 与 lockfiles 不变；不要 push，停在 GPT 复验。
