# Phase 6F3F14：真实「小惊喜」HTML 试用

## 结论

固定验收栈已从原容器恢复；真实 Chromium 使用现有本机测试账号登录成功，「创建一个小惊喜」按钮只填入了可编辑模板，未自动发送。将占位符替换为「星空」后，界面可选并确认精确模型 `deepseek-flash`。

随后只有一次 UI 提交尝试。临时浏览器夹具没有观察到 `/runs/stream` 请求（计数 0、放行 0），且浏览器在同步检查后关闭；限定范围的 Nginx 最近访问日志也未找到对应记录。这不足以证明提交未到 Gateway，也不足以证明形成了 run。没有可确认的 thread/run ID、模型响应、工具轨迹、HTML artifact 或预览；Provider 请求总数未知。本切片因此**未验收**，不重试、不删除任何会话或产物。

## Engine 与既有栈恢复

恢复时 Docker Desktop 可执行文件存在，Desktop 进程仍在，`docker info --format '{{.ServerVersion}}'` 返回 `29.1.2`；Engine 已可达，所以没有再次启动 Docker Desktop。项目中的五个 container ID、项目筛选标签和三个命名卷与 6F3F13 验收记录一致。五个容器均于 `2026-09-27T16:53:39Z` 至 `16:53:41Z` 之间退出，符合 Engine 停止时共同退出的时间特征；Gateway 为 exit 137、`OOMKilled=false`。该时间相关性不确定其历史 exit 137 根因。

固定端口 `29384` 启动前无监听者。Gateway `docker logs --tail 100` 返回 100 行，仅在进程内分类，未发现迁移、数据库损坏或启动失败信号，没有打印日志正文；该条命令的退出码未单独留存。`docker info --format '{{.ServerVersion}}'` 返回 `29.1.2`，该命令退出码也未单独留存。三个现有命名卷及挂载保持不变：

| 服务 | 原容器 ID | 镜像 ID | 恢复后状态 |
| --- | --- | --- | --- |
| PostgreSQL | `b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0` | `sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6` | healthy |
| Redis | `932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e` | `sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf` | healthy |
| Gateway | `dcfef835fcfc86a7cf09c4041a6bcf5043ed5626331da90c182bb82bd30bd997` | `sha256:a4a9dbd3207504d86bf108d53457c0a6f0af07b57afc6920f687f432c4052320` | healthy |
| Frontend | `2b275c7b6fd58ed0b7a7b19555b2020ed1007ab56f549f51c512f6b44f23cead` | `sha256:2802c7b1be7f1fdd7aba55c703a9441441b16608aee8f4dab53db40f2d5edbfb` | running |
| Nginx | `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` | `sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752` | running |

原卷仍为 `insightflow-acceptance-local_app-home`（挂载 `/app/backend/.deer-flow`）、`insightflow-acceptance-local_analytics-demo-data`（`/var/lib/postgresql/data`）及 `insightflow-acceptance-local_redis-data`（`/data`）。没有 Compose `up`、build、pull、down、卷删除、配置修改或重建容器。

相关只读核对：`docker ps -aq --filter label=com.docker.compose.project=insightflow-acceptance-local` 得到 5 个原 ID；`docker volume ls --filter label=com.docker.compose.project=insightflow-acceptance-local --format '{{.Name}}|{{.Driver}}'` 得到上述 3 个 local 卷。容器状态通过 `docker inspect <原 ID>` 的 JSON 在 PowerShell 进程内只投影 name/id/image/status/exit/OOM/health/时间与 named-volume name/destination；没有展开 env/config。`Get-NetTCPConnection -State Listen -LocalPort 29384` 返回 0 个监听者。一次仅用于展示的 Docker Go-template 只读查询因 Windows 参数引号解析失败，没有产生容器操作；之后改由 PowerShell 解析 `docker inspect` JSON 完成核对。

只启动原容器，依赖顺序与命令结果如下：

| 命令 | 退出码 | 读回 |
| --- | --- | --- |
| `docker start b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0` | `0` | PostgreSQL healthy |
| `docker start 932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e` | `0` | Redis healthy |
| `docker start dcfef835fcfc86a7cf09c4041a6bcf5043ed5626331da90c182bb82bd30bd997` | `0` | Gateway running/healthy |
| `docker start 2b275c7b6fd58ed0b7a7b19555b2020ed1007ab56f549f51c512f6b44f23cead` | `0` | Frontend running |
| `docker start bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` | `0` | Nginx running |

固定入口使用无正文 GET：`curl.exe --max-time 20 --silent --show-error --output NUL --write-out '%{http_code}|%{content_type}|%{size_download}' 'http://127.0.0.1:29384/'` exit `0`，HTTP `200`、`text/html; charset=utf-8`、69921 bytes；同参数对 `http://127.0.0.1:29384/health` exit `0`，HTTP `200`、`application/json`、50 bytes。`Invoke-WebRequest` 曾在 PowerShell 客户端内部抛 `NullReferenceException`，未取得状态；因此改用 `curl.exe`。一次只读 PowerShell 变量名与自动变量 `$HOME` 冲突导致首页元数据未捕获，随后用独立变量名完成同一无副作用 GET。未打印页面正文。

## 真实浏览器路径与断点

- `.reviews/insightflow-acceptance-local.admin.dpapi` 存在；只在当前用户进程内用 DPAPI 解封并传给 Chromium runner，未显示或落盘任何账号、口令、cookie 或模型密钥。真实 Chromium 经 `127.0.0.1:29384` 登录成功。
- 聊天欢迎页的小惊喜建议可见。点击后模板进入可编辑输入框；提示词包含 `[主题]`，此时 `/runs/stream` 计数为 `0`。将主题替换为「星空」后确认没有占位符。UI 中精确 `deepseek-flash` 选项存在，选择后重新打开 picker 也确认其为当前模型。
- 点击提交 `1` 次。临时夹具的路由回调计数为 `0`、放行为 `0`，没有 wire body、响应状态或 `Content-Location`，故没有 run/thread ID。它不能区分“点击未触发请求”“URL 未被路由监控匹配”或“异步请求未赶在同步检查前出现”。夹具提前结束；不把其 `model_in_wire_body=false` 当作模型字段缺失证据。
- `.reviews/phase-06f3f14-live.cjs` 与同目录 PowerShell wrapper 是本轮一次性忽略 helper，没有静态凭据；不要重新运行，因为唯一提交操作已消耗。它的 outcome 标签把“未观察到 stream”误写成“wire 缺模型”，本报告已按证据边界更正。
- 另只读扫描固定 Nginx 最近 5 分钟、至多 200 行日志：命令 exit `0`，筛选 `/runs/stream` 的匹配数 `0`。由于该有限访问日志结果本身不能证明完整记录了本次请求，仍将 Gateway 到达状态标为**未证实**；没有直接读原始日志。
- 这次试用没有可验证的真实 run、工具调用、HTML 路径、产物面板、sandbox iframe、内容或点击互动证据。`.reviews/phase-06f3f14-prompt.png` 与 `.reviews/phase-06f3f14-welcome.png` 是提交前 UI 截图；没有产物截图。唯一一次提交之后没有第二次提交或模型尝试。

下一轮如获授权，应先用已验证的认证 API/SDK runner 对 Gateway 做单次直接 run，提交时显式记录响应 `Content-Location`，再从同一 thread/run 的 messages API 只读提取工具名与虚拟 artifact 路径。该路径能验证模型→工具→产物，但不能替代本轮未证实的 UI submit 链；若继续验 UI，应另做有明确异步等待和请求/响应观测的单次切片，不复用本轮的即时计数判断，也不重发本次请求。
