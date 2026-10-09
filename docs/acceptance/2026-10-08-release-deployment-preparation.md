# 2026-10-08 可审阅部署准备验收

本切片为指标授权与耐久证据更新准备了固定栈的镜像回滚标记、SQLite 一致备份和人工更新/回滚脚本。没有启动、停止或重建任何容器；没有恢复数据库、改账号、执行业务 SQL 或调用模型。

## 安全快照

固定项目 `insightflow-acceptance-local` 的 5 个容器均为 stopped。原容器 ID 前缀为 frontend `01fa48766c33`、gateway `24319da1dc42`、nginx `bd9c15d61f79`、analytics-demo-postgresql `b48581dee6ee`、redis `932ac78d8adb`。Gateway 的 `app-home` 卷没有任何运行中的挂载者；隔离项目 Gateway 使用独立 bind 路径。

安全检查器在内存中渲染 Compose JSON，只输出镜像 ID、声明环境匹配布尔值、端口与卷核对结果。Frontend 的 2 项、Gateway 的 13 项声明环境与旧容器一致；三个持久卷分别是 `insightflow-acceptance-local_app-home`、`insightflow-acceptance-local_redis-data` 和 `insightflow-acceptance-local_analytics-demo-data`，渲染名与旧容器挂载名相符。原 Nginx 与固定配置均绑定 `127.0.0.1:29384`。

当前调用环境的 `PORT=2027` 曾使初次 Compose 渲染检查落到 2027。检查器和人工脚本现显式将本次 Compose 子进程的 `PORT` 固定为 `29384`、`BIND_HOST` 固定为 `127.0.0.1`，复验后的渲染和旧容器绑定一致；不会修改 `.env` 文件。

## 回滚标记与数据库备份

已为原旧镜像增加独立 tag：

- Frontend `insightflow-acceptance-local-frontend:rollback-metric-grants-20261008` → `sha256:dd2045e3c8d5afc261290ec19e51b4f1d67d2b9a4f8234d4fd785641c0988dc1`
- Gateway `insightflow-acceptance-local-gateway:rollback-metric-grants-20261008` → `sha256:a2077298dd68b27c453808c64afab42569b3c6e66c165b4a0cc897e23ffd1c60`

既有品牌回滚 tag 未覆盖。Gateway 配置使用 SQLite 默认文件 `/app/backend/.deer-flow/data/deerflow.db`。在旧 Gateway 已停止且确认没有运行写入者后，从该停止容器复制主数据库和存在的 WAL/SHM 到忽略目录 `.reviews/release-deploy-20261008/sqlite-backup-20261008/`。仅核对 SQLite 文件头，没有读取数据库行；主文件格式检查通过，WAL 与 SHM 均已复制。

旧 Gateway 不兼容后续 Analytics Alembic revision，所以回滚必须先暂停 app writers，再恢复这组三个 SQLite 文件，之后才能启动旧 Gateway/Frontend。该快照之后写入的 SQLite 记录会被恢复操作丢弃。回滚脚本的 Apply 需要显式 `-AcknowledgePostBackupDataLoss`。

## 人工脚本

- `safe_manifest.py`：只读核对固定项目、配置边界、卷、端口和 SQLite 默认配置，不输出配置值或容器环境。
- `prepare_snapshot.py`：为原镜像创建独立 tag，并从停止的 Gateway 复制 SQLite 主文件和存在的 sidecar。
- `update-fixed-stack.ps1`：默认只做 plan；显式 `-Apply` 后校验 fixed project/service 标签，并用原 Redis、业务 PostgreSQL、Nginx 的精确容器 ID 启动，不让 Compose 替换它们。只用 `up -d --no-deps --no-build --pull never gateway frontend` 更新应用；Gateway 健康后才启动原 Nginx。入口检查在最多 30 秒内重试 Nginx 转发的 `/health` 与首页，均为 HTTP 200 后才继续检查另外三个容器 ID、loopback 端口和三卷。
- `rollback-fixed-stack.ps1`：默认 dry-run；显式 `-Apply -AcknowledgePostBackupDataLoss` 才暂停 writers、恢复 SQLite 主文件/WAL/SHM，用精确 ID 启动原 Redis、业务 PostgreSQL、Nginx，并只用 Compose 替换 Gateway/Frontend；Gateway 健康后才启动原 Nginx。

人工更新命令：

```powershell
& .reviews/release-deploy-20261008/update-fixed-stack.ps1 -Apply
```

回滚命令（会丢弃备份之后新增的 SQLite 记录）：

```powershell
& .reviews/release-deploy-20261008/rollback-fixed-stack.ps1 -Apply -AcknowledgePostBackupDataLoss
```

## 验证与发布状态

已实际运行 `safe_manifest.py`、`prepare_snapshot.py`、更新脚本默认 plan、回滚脚本默认 dry-run，以及回滚 Compose `config --quiet` 校验。Python 与 PowerShell 语法检查通过。默认 plan/dry-run 均未启动容器。固定栈保持 stopped；隔离栈保持原健康状态。

源码与 tests 冻结后，Frontend 镜像构建通过，`insightflow-analytics-demo-frontend:latest` ID 为 `sha256:a45a6dd1a8213a42d5406d3f5f04dfe7042addf11dca0255c8645cc0ae47bce2`。首次 Gateway 构建在 Dockerfile 的 `uv sync --locked --extra redis` 因锁文件漂移失败；主会话修复并冻结锁文件后，Gateway 单独构建通过，`iflow-6f3e2-b9c45a-gateway:latest` ID 为 `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716`。旧 Gateway rollback tag 仍指向原 ID `sha256:a2077298dd68b27c453808c64afab42569b3c6e66c165b4a0cc897e23ffd1c60`。

两镜像构建后，更新脚本默认 plan 实际报告 `frontend:True,gateway:True`，并确认 fixed port、safe config、三卷和回滚 tag。固定项目仍有 0 个运行容器，隔离项目仍有 4 个运行容器。未执行 `-Apply`，真实 `/health` 请求、部署、业务数据验收和用户账号流程均未进行；可由操作者运行上面的人工更新命令。

## 手动 Apply 后的误报与只读状态补记

随后操作者运行了一次 `update-fixed-stack.ps1 -Apply`。脚本报告在 `replace_gateway_frontend` 阶段失败，但只读检查显示 Gateway 与 Frontend 已实际由预期新镜像启动，Gateway healthy；Redis 与业务 PostgreSQL healthy；原 Nginx 容器仍为 exited。当前读取到的精确状态为：Gateway 容器 `0e79879e8ce0ab1c16c6c8dd6b106588d288b396e489146f0770ec7c046d0181`、镜像 `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716`；Frontend 容器 `86e254edcfa835caca53581446f669c66a52f56f6c3009184453aec2534b0b6b`、镜像 `sha256:a45a6dd1a8213a42d5406d3f5f04dfe7042addf11dca0255c8645cc0ae47bce2`；Nginx 原容器 `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` 保持 `127.0.0.1:29384` 映射且在该次快照时为 exited。Redis 与业务 PostgreSQL 的原容器 ID 未变。主会话已指导操作者仅手动启动原 Nginx；本切片没有执行启动，也不应再次运行 first-deploy Apply。

该误报机制已用无副作用 Python 合成命令复现：当前 PowerShell 为 `5.1.26100.8875`，在 `$ErrorActionPreference='Stop'` 和原有 `*> $null` 重定向下，写 ASCII stderr 后退出 0 会抛出错误，虽然 `$LASTEXITCODE=0`；退出 7 的命令也会抛出且 catch 中 `$LASTEXITCODE=-1`。两个 Compose 调用函数现只在原生调用期间临时将偏好设为 `Continue`，随后恢复原值并按捕获到的 `$LASTEXITCODE` 判定。相同合成检查确认 stderr/exit 0 返回 0，stderr/exit 7 保留 7 并可判失败，且原偏好恢复。结合 Compose 操作后容器已换成预期镜像且 Gateway healthy 的只读状态，这与该 PowerShell 误报机制一致；未用真实 Compose 操作复现。

`safe_manifest.py` 现仅接受标准 Windows drive path 或精确 `/run/desktop/mnt/host/<drive>/...` 前缀；映射后要求真实路径解析到当前 workspace 内且文件存在，并且只从 Gateway 的 `/app/backend/config.yaml` mount 检查配置。合成路径检查确认 Docker Desktop 与 native workspace 路径通过、未知前缀与 workspace 外路径拒绝。只读清单因此识别出当前配置仍为 SQLite 默认路径，没有把 Docker Desktop mount 表示误报成配置缺失。

此补记的局部验证通过：两个 PowerShell 文件语法解析、`safe_manifest.py` AST、stderr 的 exit 0/7 合成检查、路径前缀与 workspace 边界检查、safe manifest 只读检查。没有执行改变容器状态的命令、Apply/rollback、真实 HTTP 请求、数据库恢复或应用测试；Nginx 的真实 `/health` 与首页验证留给操作者完成 Nginx 手动启动后进行。
