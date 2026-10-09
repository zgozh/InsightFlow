# Gateway 运行时复用与 PostgreSQL 启动验收

## 构建结果

复用本机 `iflow-6f3e2-b9c45a-gateway:latest` 中的 `/app/backend/.venv`、Node、npm、uv 和系统运行时。构建前后该基础 tag 均解析为 `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716`。新 tag 构建前不存在。

派生 Dockerfile 位于 `.reviews/release-stage-build-20261008/gateway-build-20261009/gateway-reuse-runtime.Dockerfile`，输入使用已冻结的 Backend-only context。Dockerfile 先删除 `/app/backend` 下除 `.venv` 外的旧源码项，再复制冻结源码；没有修改正式 Dockerfile、源码、`pyproject.toml`、`uv.lock` 或根 `.dockerignore`。

实际构建命令：

```powershell
docker build --pull=false --progress=plain --file .reviews/release-stage-build-20261008/gateway-build-20261009/gateway-reuse-runtime.Dockerfile --tag insightflow-release-gateway:pg-20261009 .reviews/release-stage-build-20261008/gateway-build-20261009/context
```

初次构建退出码为 `0`，完整日志保存在 `.reviews/release-stage-build-20261008/gateway-build-20261009/gateway-reuse-runtime.log`。发现继承的 CMD 会从 `/app` 执行 `cd backend`，因此在派生 Dockerfile 末尾恢复 `WORKDIR /app` 后，仅做了一次缓存配置层构建；源码复制与锁定同步层均为缓存命中，没有取包。修正构建日志为 `.reviews/release-stage-build-20261008/gateway-build-20261009/gateway-reuse-runtime-workdir-fix.log`。最终 tag 的不可变镜像 ID 为 `sha256:703a15480954b4a52979fd1b2f35bfea39e1958bba4deb85728890e645958656`，`Config.WorkingDir=/app`、继承 CMD 未变；此前临时 ID `sha256:eed9b69ce4174479952040f3e27be213bc54d5d91d6d7faf3de40060451517e6` 已被该最终 ID 替代。

镜像内只执行一次锁定同步：

```text
uv --no-config sync --locked --default-index https://pypi.org/simple --extra redis --extra postgres
```

同步没有运行 apt、npm 或 Node 安装步骤。新增的 PostgreSQL 依赖为 `langgraph-checkpoint-postgres 3.1.1`、`psycopg 3.3.3`、`psycopg-binary 3.3.3`、`psycopg-pool 3.3.0`。

## 离线镜像核对

对新镜像以 `--pull=never --network none --read-only` 执行了一次导入与摘要核对，退出码为 `0`。`PostgresSaver`、`asyncpg`、`psycopg`、`psycopg_pool`、`redis` 和 `langgraph` 均可导入；版本为 `asyncpg 0.31.0`、`langgraph 1.2.9`、`langgraph-checkpoint-postgres 3.1.1`、`psycopg 3.3.3`、`psycopg-binary 3.3.3`、`psycopg-pool 3.3.0`、`redis 7.4.0`。Node `v22.23.3`、npm `10.9.9`、uv `0.11.1` 及 `lark-cli` 路径仍在镜像中。

镜像内摘要与冻结 context 一致：

| 文件 | SHA-256 |
| --- | --- |
| `uv.lock` | `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912` |
| `app/gateway/services.py` | `553feedda37ee4b388fb909ce3e017018d206882326e7990acbd82ddeafff000` |
| `packages/harness/deerflow/runtime/runs/worker.py` | `ea1fbd93f1000e930bcdd499ece665df6cc14275acfbae42dab2f8a6d5f5152b` |
| `app/analytics/agent/stages.py` | `d05132946a2fd8299b96dcb45dbf2556eab9b820140ba062887f30025db7c160` |
| `app/analytics/agent/roles.py` | `f04e30e8b3bb2dd3c26a7e76f72e69fc743feac475ae74ebf73d991b95cdce57` |

曾有一次过宽的探针额外尝试导入 `RedisSaver`，镜像没有单独的 Redis checkpointer 模块。项目锁定的 `redis` extra 提供的是 Redis Streams client；本次验收据此核对 `redis` 导入，不安装额外 checkpoint 包，也不改变锁文件。

## 已授权容器清理与保留复验

清理前只读 inventory 记录了 30 个已退出容器，见 `.reviews/final-postgres-runtime-20261008/startup-probes/container-inventory-20261009.json`。按授权仅对以下 10 个完整 ID 执行普通 `docker rm`；没有使用 `-v`、`-f`、`compose down` 或 `prune`。命令退出码为 0，容器数从 30 降到 20，回执在 `.reviews/final-postgres-runtime-20261008/startup-probes/retirement-delete-20261009.json`。

| 项目 | 删除的容器完整 ID | 清理前端口和数据挂载 |
| --- | --- | --- |
| `controlled-query-live-20261008` MySQL | `b89e394f76224c2af0ba88224354b6eee1eb63ed63bd542b21a540d21f20d3b1` | loopback `29387`；保留卷 `controlled-query-live-20261008_mysql_data` |
| `as01-as15-1bf6932f3abd` | Gateway `3a8639de4f895ccc9fad155822a7b26f338f61325ae7d23fe4c1b5017cb25406`；Frontend `92a623ba3f7d33f2fda9b87d5b52d2f2bf6b5e3f1993468da64008d412e1921c`；Nginx `b6ef444d369b6c80546382333c8cb63573c8733c413a0fe635d30050ab2e6cb7`；Redis `28e00c4a76d41c170de92f2a33a97228a3b16cfb524945ef91ba3f29672b6fe4` | Nginx loopback `29385`；保留 Redis 卷 `as01-as15-1bf6932f3abd-redis-data`、bind 数据和 network `as01-as15-1bf6932f3abd_deer-flow` |
| `insightflow-analytics-demo` | Gateway `ba1f52e3b0c81f56a767d607796430253ff3c8fc910bef668261c845df265f17`；Frontend `74cc5ba815e06487029d6dfb0f8d07ffe0cb3d3b53024d6903eaba694f35a898`；Nginx `9490a74b1fe2a7ea9e13ed7d908ca76aa7de582ae3644596451bc3973c80c3c4`；PostgreSQL `cd740a7da66b76637feb47f43c935a70f0a4b68e2d4ac0b730745255fa656c72`；Redis `62c14e9fe3cd3cff40f2329b69c0832f22b42623717a36fa3ab78d8ea62990fb` | Nginx loopback `2027`；保留 PostgreSQL 卷 `insightflow-analytics-demo_analytics-demo-data`、Redis 卷 `insightflow-analytics-demo_redis-data` 和 network `insightflow-analytics-demo_deer-flow` |

删除后只读复验确认：10 个目标 ID 均不在容器清单中；上述 4 个卷和 2 条网络仍存在；29384 的 `insightflow-acceptance-local` 五个容器仍在，Nginx `bd9c15d61f79f5701146f2ea806ebfa14d83c7df36ea89a46066018806f7d87d` 仍映射 `29384`；PG fixture `5fdcfedc8678252bd0d368cf047dd4243b3ee7d4f1288d0d5099fa68bbed3ec4` 仍在且未启动。主会话独立复验与本地只读结果一致。其余 `docker` 项目 13 个容器、`doc-qa` PostgreSQL 容器和卷均保留。旧 2027 Frontend 镜像 `sha256:bab7236dc5d75996397afe254692bf2a21b32f17bc5d8736a5b1390ed924acbe` 在清理前已不在本机；没有拉取或重建该镜像。

清理回读保存在 `.reviews/final-postgres-runtime-20261008/startup-probes/retirement-postcheck-20261009.json`。更早的 2027 network / volume / image 状态快照见 `retirement-resources-before-20261009.json`。

## 启动状态

获准清理的 10 个容器已移除，卷、网络、29384 演示栈和 PG fixture 均保留。PG fixture `5fdcfedc8678252bd0d368cf047dd4243b3ee7d4f1288d0d5099fa68bbed3ec4` 已单独启动；它没有 Docker `HEALTHCHECK`，因此以 `pg_isready`（exit 0）确认就绪。只读 TLS fixture probe 通过 `verify_full` 连接并确认业务只读权限及 3 行计数，记录在 `.reviews/final-postgres-runtime-20261008/startup-probes/pg-fixture-verify-full-20261009.json`。该探针通过 loopback `127.0.0.1:29386` 验证 fixture TLS，不代表 Gateway 容器内的业务连接已通过。

既有 launcher 的默认预检最初受 Docker 29.1.2 对不存在网络的错误文本影响，随后其固定网络 guard 仅增加对精确目标网络 `network iflow-final-pg-20261008-net not found` 的识别；PostgreSQL extra 离线导入探针的 shell 参数也修正了引号，使 Python 实际执行 import。最终默认预检结果为 `preflight_ok/ready_to_apply`，证据在 `.reviews/final-postgres-runtime-20261008/startup-probes/launcher-preflight-20261009.json`。

随后只对新项目 `iflow-final-pg-20261008` 执行一次 `-Apply`。Compose 创建了该项目网络、Redis 数据卷和四个容器；Redis 与 Frontend 运行，Gateway 退出码为 1，Nginx 保持 `created`。Gateway 的脱敏诊断为 `ModuleNotFoundError: deerflow.sandbox`，见 `.reviews/final-postgres-runtime-20261008/startup-probes/gateway-startup-diagnosis-20261009.json`。该模块在当前工作树中是已跟踪文件，但冻结 build context 缺少 `backend/packages/harness/deerflow/sandbox/`；context 中未发现 `.dockerignore` 规则排除该路径。当前阻塞属于构建上下文遗漏，需 Principal 审查是否刷新 context 后只做缓存源码层构建。

本次尚未证明 Gateway 启动健康、应用库迁移/checkpointer 表、29388 HTTP 健康检查或 Gateway 容器网络内的业务 `verify_full` 连接；Apply 创建的本项目容器、网络与卷均保留，未做回滚或删除。运行失败与后续修复仍待 Principal 审查。
