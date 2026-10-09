# Phase 6F3F20：唯一欢迎卡片真实流程与发布门槛

日期：2026-10-07。状态：单次真实用户流程已执行，成功产物预览已证实；交互变化未证实，不能判整条链通过。不重发模型或重复该示例。前端部署成功，主会话已独立目视部署双尺寸截图并核对容器/health/favicon，接受部署首页；能力证据与剩余门槛已交付，整体 Phase6/发布仍 In progress。未提交、未 push。

## 固定栈恢复与主机拒绝记录

Docker Desktop 安装存在，以 `Start-Process -WindowStyle Hidden` 一次启动；55秒有界引擎检查内返回 EngineReady 29.1.2。只读核对固定 project 原五容器、三个卷与 Nginx `127.0.0.1:29384`；Gateway 历史 exit137/OOM=false 的原因仍未知，不据此修复或重建数据库。

实施者仅 `docker start` 原 PostgreSQL、Redis 成功，随后均 healthy。启动原 Gateway/Frontend/Nginx 的组合命令在 CreateProcess 前被自动审批拒绝：`blocked by policy`，无更具体原因；未执行，不绕过。用户随后手动启动这三容器；实施者只读确认五服务 running，Gateway/PG/Redis healthy，`/health` HTTP200，才继续已授权步骤。

当时可供用户手动恢复的最小命令仅为已核实名称：`docker start insightflow-acceptance-local-gateway-1 insightflow-acceptance-local-frontend-1 insightflow-acceptance-local-nginx-1`。用户已完成恢复，无需重复执行。

## Frontend-only 部署

忽略目录 helper `.reviews/phase-06f3f21-deploy.ps1` 使用既有 Compose project-directory、两个 env-file、三个 Compose 文件与原 override；参数与 [6F3F13历史记录](phase-06f3f13-local-frontend-refresh.md)相同。不读取/回显凭据或私密配置值。`config --quiet`、Frontend ports/volumes/env 边界比较、`--dry-run up -d --no-deps --no-build --pull never frontend` 均通过。首次 PowerShell ConvertFrom-Json 遇 `NO_PROXY`/`no_proxy` 大小写重复键，改用 Python 进程内解析比较后通过；这是 helper 解析修复，无生产配置变更。

旧 Frontend image `sha256:7ec6ef1502830d6fd61a620a1a95af9c7b65d112a9782c9a6d7772a39d3f3426` 保留为 `insightflow-acceptance-local-frontend:rollback-6f3f21`。仅 `build --quiet frontend` 与 `up -d --no-deps --no-build --pull never frontend` 退出码0，新容器 `1e2c37bbcd3992a4d8955c13c1e81e04892d075c42028f12cd063baa7a253e97`，新 image `sha256:18f137c24a8d55f15fde1de30d1bd9f0d367cb6f27b3ed04aa52f2a5bcb07430`。

另外四个 ID 未变：

| 服务 | 当前 ID / 状态 |
| --- | --- |
| Gateway | `24319da1dc42ba43fe1b001dfe6e0200e0667e09f0802de68da7025ab1fa5d3d`，running/healthy |
| Nginx | `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d`，running |
| PostgreSQL | `b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0`，running/healthy |
| Redis | `932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e`，running/healthy |

原卷 `insightflow-acceptance-local_app-home`、`insightflow-acceptance-local_analytics-demo-data`、`insightflow-acceptance-local_redis-data` 保持不变。未 full-stack up/down、重配其他服务或重建卷。

真实 Chromium 1280×720、375×812 经 `29384` 获取 `/` HTTP200，无横向溢出，favicon HTTP200且解码32×32；`/health` HTTP200。部署完整页截图：

- `D:/develop/workspace/InsightFlow/.reviews/phase-06f3f21-deployed-desktop.png`
- `D:/develop/workspace/InsightFlow/.reviews/phase-06f3f21-deployed-mobile.png`

## 唯一真实欢迎卡片流程

只读 Gateway 配置布尔核对：精确 `deepseek-flash` 存在、`write_file` 存在。首次 docker exec 在 `/app` 无包路径，改为 `/app/backend` 后检查成功，不改配置。既有 DPAPI 账号只在用户进程内解封并经 stdin 交给 headless Chromium，没有打印或落盘账号/密码/cookie/key。

从旧安全 runner 派生忽略目录 `.reviews/phase-06f3f20-live.cjs/.ps1`，在点击前注册请求和响应监听，先异步等待响应再读计数，随后有界等待 stream 与 run 终态；使用排他创建的 attempt marker 禁止第二次提交。不保存聊天/产物截图，不输出消息、模型正文或 HTML。

| 边界 | 真实结果 |
| --- | --- |
| 登录、欢迎卡片 | 登录成功，“创建一个小惊喜”可见；点击只填可编辑模板，发送前stream计数0。 |
| 主题与模型 | 将 `[主题]` / `[theme]` 替换为“星空”；精确 `deepseek-flash` UI 选择确认，wire body 模型匹配。 |
| 显式提交 | submit_attempts=1，stream_requests=1，stream_forwarded=1；没有重发run。 |
| stream / run | HTTP200、stream结束、run status=success。thread=`01973633-304e-45f9-99d1-317e086d706a`；run=`542fe919-892f-4cf0-93a9-bd7eef3e2760`。 |
| Content-Location | `/api/threads/01973633-304e-45f9-99d1-317e086d706a/runs/542fe919-892f-4cf0-93a9-bd7eef3e2760`。 |
| 同run工具 / 产物 | messages GET200、6 rows。首次 collector 将包装层 `content` 全跳过，工具计数为空；只读修正对象包装投影与 tool_call_id 关联后确认 `write_file` / `present_files` 调用各1、结果各1。state GET200，HTML artifact 为 `/mnt/user-data/outputs/starry-night.html`。 |
| 正常预览入口 | artifact-trigger→HTML条目→iframe可见；sandbox=`allow-scripts allow-forms`，星空主题可见，外部请求0。 |
| 一次交互 | 发现1个按钮，点击完成；300ms后按钮文本/class/style/ariaPressed及body文本比较没有变化。仅证明“未观测到所检查状态变化”，不证明所有交互无效。 |

最早未闭合的验收边界是**点击后的可观察交互变化**；run、工具调用、持久产物与真实预览已有证据。该单次模型产物结果不据此判定平台产品缺陷；不读HTML、不额外点击、不重新发送模型。一次UI/Gateway run不等于只调用一次底层LLM API，本轮未统计底层供应商请求次数。普通 run 执行期间 Frontend-only build 完成后刷新前端；Gateway未重启，run完成/预览仍成功，但不能把此流程外推为所有重连/恢复保证。

## 交付与剩余门槛

本轮无生产后端改动。新增/同步 `docs/current-capabilities.md`、两份 README、PROGRESS和6F3F21状态；生成脚本 Ruff check/format通过，重生成资产 SHA256完全相同；文档本地链接及 `git diff --check`通过。未重复有效前端checks，未跑全套或新数据库门禁。Frontend实际image build已成功。

最多五项风险排序、已有/缺失证据、是否阻断简历演示与可直接使用的简历描述统一见[当前能力证据](../current-capabilities.md#最多五项剩余门槛按风险)。下一切片切换到其他优先级门槛，不再为这个小惊喜示例无限试验。
