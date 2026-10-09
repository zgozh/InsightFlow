# 原演示入口最终升级准备记录

状态：原入口 Apply 已调用一次；下方独立只读 post-checks 通过。原 Apply 执行调用在 30 秒等待后没有回传其 JSON/exit status；事后进程检查未发现仍在运行的 rollout 脚本。没有再次 Apply，也没有声称脚本自身返回特定成功码。五容器当前均为 `running`，原入口仍为 `127.0.0.1:29384`。未执行模型任务。执行入口为 [`rollout.ps1`](../../.reviews/final-postgres-runtime-20261008/original-entry-rollout/rollout.ps1)，默认参数仅预检；显式 `-Apply` 才会备份 app-home 并更新服务。

## 原项目身份与镜像

Compose project 为 `insightflow-acceptance-local`，working directory 为 `D:\develop\workspace\InsightFlow\docker`。容器标签的 Compose 文件顺序为：

1. `docker/docker-compose.yaml`
2. `docker/docker-compose.analytics-demo.yml`
3. `docker/docker-compose.analytics-demo-app.yml`
4. `.reviews/insightflow-acceptance-local.override.yaml`

Nginx 配置的发布绑定仍是 `127.0.0.1:29384 -> 2026/tcp`。当前停止态资源：

| 服务 | 原容器 ID | 原 image ID / 引用 |
|---|---|---|
| Gateway | `0e79879e8ce0ab1c16c6c8dd6b106588d288b396e489146f0770ec7c046d0181` | `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716` / `iflow-6f3e2-b9c45a-gateway:latest` |
| Frontend | `86e254edcfa835caca53581446f669c66a52f56f6c3009184453aec2534b0b6b` | `sha256:a45a6dd1a8213a42d5406d3f5f04dfe7042addf11dca0255c8645cc0ae47bce2` / `insightflow-analytics-demo-frontend:latest` |
| Nginx | `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` | `sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752` / `nginx:alpine` |
| Analytics PostgreSQL | `b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0` | `sha256:a3b7f434b2dc57ce85a67e171163eb8ab1a1ebcb39d27484661f26b1dfbe30d6` / `postgres:16` |
| Redis | `932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e` | `sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf` / `redis:7-alpine` |

当前 Compose 源文件从 `.env.analytics-demo` 渲染出的 Nginx host port 是 `2027`，与现场原容器的 `29384` 不同；此外源码存在已知 drift。Apply 不执行全栈 Compose up，也不重建 Nginx：只启动原 PG/Redis 容器，再以 `--no-deps` 更新 Gateway/Frontend，最后启动原 Nginx 容器。前后守卫核对五个项目容器集合、未更新服务的容器/image ID、目标镜像 ID、原 mounts、volumes 与 `29384` 入口绑定。

这次只切换 Gateway 与 Frontend。目标 image ID 已在本机按完整 ID 核对：Gateway `sha256:1109d361bc2aa8c8bac4b842ed84fa8bee10f89390df6c6ad0f4da57276e10eb`（`insightflow-feedback-gateway:server-computation-20261009`），Frontend `sha256:365f55389e29117a5d81cb6afa8a87ef22e411a94c41c995b25a3cc9a5b3c066`（`insightflow-release-frontend:catalog-ui-20261009`）。原 Gateway、Frontend 回滚 tag 仍映射到表中的旧 image ID；脚本会在 preflight 和 Apply 前再核对 tag→ID。

## 原数据与配置

Gateway 实际仍挂载原 `app-home` volume `insightflow-acceptance-local_app-home` 到 `/app/backend/.deer-flow`。其余持久卷为 `insightflow-acceptance-local_analytics-demo-data`（PostgreSQL 业务数据）与 `insightflow-acceptance-local_redis-data`。脚本核对卷名、Compose project label 与挂载目标，不调用 `down -v`，不重建卷。

原 Gateway 的 `DEER_FLOW_CONFIG_PATH` 指向 `/app/backend/config.yaml`，其只读 host mount 是 `.analytics-demo/config.yaml`；该文件没有 `database` section，Gateway 环境也没有 `DATABASE_URL`。已从停止态原 Gateway image 源码确认实际解析顺序：`AppConfig.from_file()` 先读 YAML 并解析环境引用，再调用 `_apply_database_defaults()`，在 Pydantic 校验前对缺省 database section 补 `backend=sqlite` 与 `sqlite_dir=.deer-flow/data`。目标验收源码保留同一分支。因此原 app DB 实际路径为 `/app/backend/.deer-flow/data/deerflow.db`；`DatabaseConfig` 类字段单独构造时的 `memory` fallback 不代表 YAML 加载路径。

停止态原 app-home 的 `data` 目录只读文件元数据为：`deerflow.db` 3,055,616 B、`deerflow.db-wal` 4,132,392 B、`deerflow.db-shm` 32,768 B，共 3 个文件。未查询或输出任何数据库行。业务 PostgreSQL 数据 volume 与 app-home 是不同数据面，两个都保留。

Apply 在启动依赖前从原 Gateway 复制整个 `/app/backend/.deer-flow/.` 到忽略目录 `.reviews/final-postgres-runtime-20261008/original-entry-rollout/backups/20261009T133402Z-80ba4b6fd01b4db1a3bc83e77e814680/app-home`。备份共 52 个文件，包含 SQLite 主库、WAL、SHM 三件，也保留原认证密钥、用户与线程数据；未查询备份中的业务行。目标备份位于根 `.gitignore` 忽略路径下。失败时不自动删除此备份。

配置和认证材料保持原 host mounts：只读 `.analytics-demo/config.yaml`、只读 `.analytics-demo/extensions_config.json`、只读 `skills`；不复制 29388 的用户或配置。Nginx 配置与 PostgreSQL init SQL、TLS 文件也沿用原 mounts。

## 检查与剩余验收

部署前 AST 与默认 no-Apply 预检曾通过；Apply 后没有重跑预检或 Apply。现场通过一次只读检查确认：Gateway 为目标 image `sha256:1109d361bc2aa8c8bac4b842ed84fa8bee10f89390df6c6ad0f4da57276e10eb`、ID `a812849f8ed7cf1a5b1554c01a1ae347cbfc66c5b7cb495c6d49a6d505fdb1bb`，状态 `running/healthy`；Frontend 为目标 image `sha256:365f55389e29117a5d81cb6afa8a87ef22e411a94c41c995b25a3cc9a5b3c066`、ID `6426a2217974cdf428177adbe98961ef3d2906c4403cbb04d2a79e4fe6695bbb`，状态 `running`。原 Nginx、PG、Redis 的容器 ID 与 image ID 均未变，当前均 `running`；PG/Redis 为 `healthy`。app-home、analytics-demo-data、redis-data 三卷名称及 Compose project/volume labels 均与原身份一致。

原入口只读 HTTP 检查：`/` 返回 200，HTML 有 title 与 InsightFlow 标记；`/health`、`/health/ready` 返回 200；匿名 `GET /api/v1/auth/me` 返回 401。应用 SQLite 以 `mode=ro` 查询 Alembic metadata，仅读取并记录 revision `0024_project_documents`，未查询业务行。未更改原配置、认证、用户权限或持久卷；没有从 29388 复制数据。旧回滚 tag 与固定 override 在 `rollback-images.override.yaml`：Gateway `iflow-6f3e2-b9c45a-gateway:latest` → 原 image `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716`，Frontend `insightflow-analytics-demo-frontend:latest` → 原 image `sha256:a45a6dd1a8213a42d5406d3f5f04dfe7042addf11dca0255c8645cc0ae47bce2`。未执行回滚。

原入口过去曾有一次启动操作被 host 自动审批拒绝，用户手动恢复了现场。本轮遵循后续明确授权只执行一次 Apply；没有遇到新的审批拒绝，也没有绕过 host 权限。Apply 调用本身的退出状态未被执行器回传，因此本记录只陈述独立只读核实到的最终状态。

只读检查时，为从停止容器确认源码和 SQLite 文件元数据，临时副本留在 `%TEMP%\InsightFlow-29384-readonly-inspect`。删除该自建临时目录的命令被执行工具 policy 拒绝；未换通道尝试清理。此目录是本轮只读检查副本，不是 rollout 备份。
