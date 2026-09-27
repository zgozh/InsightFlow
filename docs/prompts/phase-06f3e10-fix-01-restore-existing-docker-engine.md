# Phase 6F3E10 Fix 01：恢复既有验收栈后续接 Reviewer 定因

> 执行者：现有 `gpt-6-luna`（max）。先读本文件及 `docs/prompts/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`，再读 `.reviews/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`。不重做已完成的离线核查。

## 起点和范围

上轮唯一阻断是 `docker ps` 无法连接 `npipe:////./pipe/dockerDesktopLinuxEngine`；代码/测试未改，模型请求 0 次，HEAD `63fcc8b`。本切片先恢复 Windows Docker Desktop Linux engine 与既有 `insightflow-acceptance-local`。这是环境接线修复，不改仓库配置、凭据、Dockerfile、Compose、lockfile 或其它项目资源；V0/V1 只读状态核查足够，不跑测试。

1. 只读确认当前 Docker context、`docker version`、Docker Desktop 进程与本机安装路径；不要把环境变量或凭据值打印到报告。若只是错误 context，切回现有 Desktop Linux context；记录原 context 与改变，不改全局其它设置。
2. 若 Docker Desktop 未运行且找到可信本机安装路径，可按 Windows 工具规则以隐藏窗口启动一次，等待引擎就绪；不要循环重启/重装/升级 Docker，不要下载镜像。若需要用户交互、管理员授权或安装，则停止并给用户明确的手动动作。
3. 引擎可连接后，只读列出 `com.docker.compose.project=insightflow-acceptance-local` 的容器、健康与网络/卷。仅当**原有且可明确辨认的 5 个容器仍在**、只是停机时，允许按其确切容器名启动它们；不得 `compose up/build/recreate/down`，不得新建或删除容器/卷/网络。若容器缺失、项目标签不符或状态异常，停止报告，不另建平行验收栈，也不动旧 6F1 项目。
4. 五容器就绪时，用已验证的最小健康请求确认 Gateway 可用。然后继续原 6F3E10 提示词第 2–6 步：安全分类、定点验证、最多一次诊断 run、证据驱动修复及最多一次修复验收 run。此前模型预算未使用，不需扣除。若恢复环境失败，仅写脱敏短报告停下；无需提交空变更。

## 报告

将环境恢复证据追加到 `.reviews/phase-06f3e10-reviewer-invalid-response-diagnosis-and-fix.md`；最终仍按原提示词提交实现报告。禁止输出 Reviewer 正文/SQL/结果行/token/凭据。若必须用户操作，清楚说明“下一步用户该点哪里或启动什么”，不要把环境阻断伪称为产品缺陷。
