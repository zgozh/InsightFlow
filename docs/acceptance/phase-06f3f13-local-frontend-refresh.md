# Phase 6F3F13：固定本机验收栈前端刷新

## 结果

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
- 本切片唯一阻塞是既有验收栈当前停止。需由用户/主会话先决定是否恢复固定栈（尤其 Gateway exit 137 的处置）；本报告未将未运行的服务描述为健康，也未宣称部署或入口验收通过。
