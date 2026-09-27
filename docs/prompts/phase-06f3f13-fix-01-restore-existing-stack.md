# Phase 6F3F13 Fix 01：无损恢复固定栈，再判断前端局部刷新

起点为 `1484a85`，先核对 HEAD、工作树（预期仅本提示词未跟踪）及 `docs/acceptance/phase-06f3f13-local-frontend-refresh.md`。主会话接受其停线结论，并授权恢复**现有** `insightflow-acceptance-local` 容器；这不是重建整栈或重置数据。用户要求持续推进，若条件安全，最终仍需让 `http://127.0.0.1:29384/` 呈现 6F3F12 最新前端。

## 安全恢复

1. 只读核对五个既有容器 ID、Compose project 标签、镜像 ID、端口、命名卷及退出时间；查看 Gateway 的 `OOMKilled`/退出状态与有限的尾部日志，报告稳定错误类型，不输出密钥、SQL、token、凭据或用户数据。若现有 ID 与验收报告不符、卷缺失、端口被别的进程占用，或日志显示数据损坏/迁移风险，停止并报告，不执行生命周期命令。
2. 若无上述风险，直接启动**原有容器**，优先 PostgreSQL、Redis，健康后 Gateway、Frontend、Nginx；使用 `docker start`/等价只启动现有容器的方式，不 `compose up`、不建新容器、不拉镜像、不删卷。每阶段核对健康/状态；Gateway 若仍 exit 137 或启动失败，停止此切片并给出最短诊断，不循环重启。
3. 旧栈恢复后，确认 Nginx 的旧首页与 Gateway health 能从固定入口响应，并保持原有数据。随后只读查明现有 Compose 文件加 override 的准确调用方式以及是否需要未记录的 env-file；先用 `docker compose config --quiet` 与渲染服务列表/容器配置摘要（不输出秘密）证明不会改动其他服务或卷。**若无法证明同一 project 的 frontend-only 更新安全，先停在“旧栈已恢复，前端仍旧版”并报告，不猜测命令。**
4. 只有第 3 步证明安全后，基于当前 `9aa40ef` 的前端源码只构建/替换 frontend 服务；保留旧 frontend 镜像 ID 作为回滚点。不得全栈 `up --build`、`down`、`pull`、改数据库/Gateway/Redis/Nginx 配置或清理卷。失败时把 frontend 恢复到原镜像/容器，并如实记录。
5. 经 Nginx 做最小浏览器冒烟：`/` 的 GitHub 仓库外链、`/workspace` CTA、新 SVG favicon、桌面/375px 黑洞画面；仅在有可安全复用的普通登录态时查看“小惊喜”预填，不创建或删除账号、不调用模型。容器状态和 Gateway health 最终仍需正常。若前端未更新，不得称新 UI 已上线。

## 证据与交接

本次是环境恢复与局部部署，V3 只验证服务状态和上述入口，不重复前端单测、后端全套、数据库集成或真实模型链。把根因判断、实际命令与退出码、原/新容器及镜像 ID、卷保持情况、入口截图/响应、可回滚方式及未验证项追加到 `docs/acceptance/phase-06f3f13-local-frontend-refresh.md`，同步 `docs/PROGRESS.md`。将本提示词与记录作为一个独立纯文档提交，检查 diff/工作树/固定 tag/lockfile；不 push。完成后停在 GPT 复验，不开始其他阶段。
