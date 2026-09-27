# Phase 6F3F13：固定本机验收栈前端刷新

## 初始结果（Fix 01 前）

2026-09-27 15:57 UTC 的只读前置检查触发提示词停线条件：固定 project `insightflow-acceptance-local` 存在，但 5 个容器全部已停止，Compose 状态为 `exited(5)`。Gateway 以 exit 137 退出，故真实 Nginx→Frontend/Gateway 服务路径不可用。未构建、启动、替换或重建任何容器，也未发 HTTP/浏览器请求；本轮没有新 frontend image/container ID。

## 起点与回滚点

- Git 起点为 `9aa40ef`，tracked 工作树干净，仅本提示词未跟踪。固定 tag `upstream-v2.1.0-rc0` 仍解析到 `609bfde0ced76ff0a58c02ff5c741df768f44502`。
- Docker Engine `linux 29.1.2`，Compose `2.40.3-desktop.1`。project 名称为 `insightflow-acceptance-local`；Docker Compose 项目元数据列出的文件为：
  - `docker/docker-compose.yaml`
  - `docker/docker-compose.analytics-demo.yml`
  - `docker/docker-compose.analytics-demo-app.yml`
  - `.reviews/insightflow-acceptance-local.override.yaml`
- 项目列表未提供启动时的 `--env-file` 参数；本轮没有读取或展开 env 文件，也没有据此重构 Compose 启动命令。
- Nginx 容器端口映射仍配置为 `127.0.0.1:29384 -> 2026/tcp`。容器已停止，未验证该入口能响应。
- 旧 Frontend 回滚点：容器 `insightflow-acceptance-local-frontend-1`，container ID `19dc264850941ffe85e7ee2564e72182cb020b8a295e3e174fa2030f79eb4569`，image ID `sha256:52eaffb601a2e5de810b69532787021a054a4c9e929e4a58324e5ea5c9b59347`。该旧容器与镜像未改动。
- 回滚可行性：本轮没有替换 frontend，因而无需实际回滚；旧容器和旧 image ID 均保留。若后续获准刷新后验证失败，可据此恢复旧 frontend。该恢复动作本轮未执行。

| 服务 | 容器 ID | 状态 / 退出码 |
| --- | --- | --- |
| Frontend | `19dc264850941ffe85e7ee2564e72182cb020b8a295e3e174fa2030f79eb4569` | exited / 143 |
| Gateway | `dcfef835fcfc86a7cf09c4041a6bcf5043ed5626331da90c182bb82bd30bd997` | exited / 137 |
| Nginx | `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` | exited / 0 |
| PostgreSQL | `b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0` | exited / 0 |
| Redis | `932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e` | exited / 0 |

## 已执行的只读命令

以下列出的只读证据命令退出码均为 `0`；没有执行 Compose 生命周期、build、pull、HTTP、登录或模型命令。

- `docker info --format '{{.OSType}}|{{.ServerVersion}}'`：`linux|29.1.2`。
- `docker compose version --short`：`2.40.3-desktop.1`。
- `docker compose ls --all --format json`：目标 project 存在，状态 `exited(5)`；记录到以上 Compose 文件。
- `docker ps --all --filter label=com.docker.compose.project=insightflow-acceptance-local --format ...`：返回上述 5 个已退出容器。
- `docker inspect --format '{{.Name}}|{{.Id}}|{{.Image}}|{{.State.Status}}|{{.State.ExitCode}}' ...`：记录容器身份、旧 Frontend 镜像和退出码。
- `docker inspect --format '{{json .HostConfig.PortBindings}}' <nginx-container>`：`2026/tcp` 映射至 `127.0.0.1:29384`。

## 未执行与限制

- 没有构建或替换 Frontend；旧镜像和容器保留，可供后续审批后的回滚/刷新流程使用。
- 由于 Nginx、Frontend、Gateway、PostgreSQL、Redis 均已退出，未验证首页、favicon、GitHub 外链、`/workspace` CTA、375px 视口或登录态欢迎示例。也未判断是否存在可复用普通用户会话。
- 未重启其他服务，未触碰数据库/Gateway 数据、命名卷、账号或密钥；未读取 `.env`、`config.yaml` 或凭据内容。
- 首轮预检的唯一阻塞是既有验收栈停止；Fix 01 后续获准恢复，过程和验收范围记录于下文。本段仅记录首轮当时状态，不代表当前容器状态。

## Fix 01：无损恢复与 Frontend-only 刷新

### 结论

授权恢复后，原五个容器均以原 container ID 启动成功；Gateway 首次恢复即 `running/healthy`，此前 exit 137 的历史原因仍未知。只替换了 Frontend 容器：新镜像通过当前 checkout 构建，固定 Nginx 入口仍在 `127.0.0.1:29384` 返回页面，GitHub 仓库入口、`/workspace` CTA 与 SVG favicon 均通过真实 Chromium 检查；桌面和窄屏黑洞均未遮挡文案。其他四个容器及三个命名卷保持原 ID/名称。

### 启动前安全核对

- HEAD 为 `1484a85`，tracked 工作树干净；除本 Fix 01 提示词外无其他未跟踪改动。原五个 container ID、Compose project/service 标签、image ID 与前一报告一致。
- Gateway 原状态为 `exited/137`、`OOMKilled=false`。对它执行 `docker logs --tail 100`（退出码 `0`）后，只在内存中分类稳定异常类型；未发现异常类型、启动失败、终止、迁移或数据损坏标记。该有限日志不能证明 exit 137 的历史根因。
- 固定项目已有命名卷为 `insightflow-acceptance-local_app-home`、`insightflow-acceptance-local_analytics-demo-data`、`insightflow-acceptance-local_redis-data`；挂载分别对应 Gateway home、PostgreSQL data、Redis data。恢复和部署期间未删除或重建卷。启动前 `127.0.0.1:29384` 没有其他监听者。
- 容器 Compose 标签给出的配置文件、working directory 与 env-file 名称足以重放项目的 Compose 参数；没有读取或回显 env/config 内容。精确参数下 `docker compose config --quiet` 退出码 `0`，渲染出五个目标服务与上述三个卷。
- 当前渲染配置的 Nginx host port 为 `2027`，与既有 Nginx 容器实际绑定的 `127.0.0.1:29384` 不同；frontend/gateway/nginx 的 Compose config hash 也与既有容器不同。为避免触及这类漂移，先确认 Frontend 无端口、卷或依赖，渲染出的 Frontend 运行环境键在内存中与旧容器一致，再运行 `docker compose --dry-run up -d --no-deps --build frontend`：退出码 `0`，计划只提及 `frontend`。实际更新使用 `--no-deps --no-build --pull never frontend`，没有重配或重建其他服务/卷。未将其他服务的 hash 差异解释为已解决。
- `git diff --quiet 9aa40ef HEAD -- frontend` 与 `git merge-base --is-ancestor 9aa40ef HEAD` 均 exit `0`：本次镜像构建所用 Frontend 源码与 Fix 01 目标提交一致。

以下 `docker compose` 操作使用同一组、从目标容器 Compose 标签读回的参数（没有展开文件内容）：`--project-name insightflow-acceptance-local --project-directory D:\develop\workspace\InsightFlow\docker --env-file D:\develop\workspace\InsightFlow\.env --env-file D:\develop\workspace\InsightFlow\.env.analytics-demo -f D:\develop\workspace\InsightFlow\docker\docker-compose.yaml -f D:\develop\workspace\InsightFlow\docker\docker-compose.analytics-demo.yml -f D:\develop\workspace\InsightFlow\docker\docker-compose.analytics-demo-app.yml -f D:\develop\workspace\InsightFlow\.reviews\insightflow-acceptance-local.override.yaml`。

### 执行与验证证据

| 操作 | 结果 |
| --- | --- |
| `docker start` 原 PostgreSQL container `b48581dee6ee6cc4a1a7f58576777c96167bf77bb625d15226621d595c6c55b0` | exit `0`；healthy |
| `docker start` 原 Redis container `932ac78d8adb0748879821c736b23f20c3f80fcdea2868a441256a9341dc4c2e` | exit `0`；healthy |
| `docker start` 原 Gateway container `dcfef835fcfc86a7cf09c4041a6bcf5043ed5626331da90c182bb82bd30bd997` | exit `0`；首次恢复后 healthy，`OOMKilled=false` |
| `docker start 19dc264850941ffe85e7ee2564e72182cb020b8a295e3e174fa2030f79eb4569` (Frontend), `docker start bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` (Nginx) | 两条命令均 exit `0`；Frontend 与 Nginx running |
| 首次固定入口 `Invoke-WebRequest http://127.0.0.1:29384/`、`Invoke-WebRequest http://127.0.0.1:29384/health` | 分别 HTTP `200`，HTML / JSON |
| `docker image tag sha256:52eaffb601a2e5de810b69532787021a054a4c9e929e4a58324e5ea5c9b59347 insightflow-acceptance-local-frontend:rollback-52eaffb6` | exit `0`；旧镜像保持为回滚 tag |
| 上述 Compose 参数 + `config --quiet`; `--dry-run up -d --no-deps --build frontend` | 分别 exit `0`; dry-run 只列出 `frontend` |
| 上述 Compose 参数 + `build --quiet frontend` | exit `0`；只构建 Frontend |
| 上述 Compose 参数 + `up -d --no-deps --no-build --pull never frontend` | exit `0`；只重建 Frontend。新容器 `2b275c7b6fd58ed0b7a7b19555b2020ed1007ab56f549f51c512f6b44f23cead`，新镜像 `sha256:2802c7b1be7f1fdd7aba55c703a9441441b16608aee8f4dab53db40f2d5edbfb` |
| 更新后固定入口 `GET /`、`GET /health` | 分别 HTTP `200`，HTML / JSON；Gateway 再读回为 `running/healthy` |
| Node inline Playwright / Chromium `1280×720` 与 `375×812` | command exit `0`；`/` 均 HTTP `200`；外链文本为 “GitHub repository”，目标 `https://github.com/zgozh/InsightFlow`；CTA 可见且目标 `/workspace`；`/favicon.svg` HTTP `200`、`image/svg+xml`、815 bytes |

目视截图保存在忽略目录 `.reviews/phase-06f3f13-fix-01-desktop.png` 与 `.reviews/phase-06f3f13-fix-01-mobile.png`：桌面黑洞位于文案右侧，移动端位于文案下方，均无标题/正文重叠。最终仍是原 Gateway、Nginx、PostgreSQL、Redis container ID；三个卷名称不变。新 Frontend container/image ID 已记录，旧 Frontend image 另有 rollback tag。没有登录、创建/删除账号、访问聊天、发起模型请求或触碰分析数据。

### 范围与回滚

本轮未修复 Gateway exit 137 的历史原因，也未重启/重配 Gateway、Nginx、PostgreSQL、Redis；有效证据仅覆盖恢复后健康、Frontend-only 部署与公共首页。未检查认证后的“小惊喜”预填。当前 Compose 渲染中 Nginx 端口仍与正在运行的 Nginx 不同，故不要用未加服务限定的 Compose `up` 操作此固定栈。

若需回滚 Frontend，可将 tag `insightflow-acceptance-local-frontend:rollback-52eaffb6` 重新标回 `insightflow-analytics-demo-frontend:latest`，再以同一组 Compose/env-file 参数执行 `up -d --no-deps --no-build --pull never frontend`；该回滚未实际执行。未运行全量套件、模型或其他项目的 Docker 操作，未 push。
