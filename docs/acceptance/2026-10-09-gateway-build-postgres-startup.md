# Gateway 构建与 PostgreSQL 启动切片记录

## Gateway 构建结果

2026-10-09 唯一一次 Gateway production image build 已启动并结束，退出码为 `1`。执行时段为 `2026-10-09T00:53:14+08:00` 至 `2026-10-09T00:53:32+08:00`。完整日志保存在 `.reviews/release-stage-build-20261008/gateway-build-20261009/gateway-build.log`。

```powershell
docker build --progress=plain --file backend/Dockerfile --tag insightflow-release-gateway:stage-20261009 --build-arg UV_EXTRAS=postgres --build-arg UV_INDEX_URL=https://pypi.org/simple .reviews/release-stage-build-20261008/gateway-build-20261009/context
```

失败发生在 Dockerfile 第 29 行 `apt-get update`：Debian bookworm、bookworm-updates 和 bookworm-security 的 InRelease 请求均返回 `502 Bad Gateway`（`151.101.30.132:80`），随后 apt 报无法获取 InRelease 和仓库未签名。构建没有到达 uv dependency sync 阶段。tag `insightflow-release-gateway:stage-20261009` 当前不存在，因此没有 Gateway image ID。构建命令已退出且没有活动 exec session。

Backend-only context 位于 `.reviews/release-stage-build-20261008/gateway-build-20261009/context`。其中包含冻结 Backend 输入和原样根 `.dockerignore`；暂存步骤排除了 `.env*`、真实配置、`.reviews`、`.deer-flow`、`.venv`、sandbox 和运行时数据。没有修改 Backend 源码、Dockerfile 或锁文件。

`backend/uv.lock` 当前与暂存副本 SHA-256 均为 `46f170b56fbc3703fffb4e8389274dd77488583e2d0804de760b705e89f6e912`，与本切片预期一致。

## 现有 Gateway 镜像依赖探针

最终用于决策、且保留完整安全摘要的探针覆盖旧 51c0 镜像和同项目 acceptance rollback 镜像；采用 `docker run --rm --pull=never --network none --read-only`，未传入环境变量或凭据。两个 image 的结果相同：

| 镜像 tag | Immutable image ID | asyncpg | psycopg | psycopg-pool | PostgresSaver / postgres checkpoint | redis | langgraph |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `iflow-6f3e2-b9c45a-gateway:latest` | `sha256:51c0cc1b4a9a48405f1329bbd25382989690bdf436494192e39e860cc3a35716` | `0.31.0` | 缺失 | 缺失 | 缺失 | `7.4.0` | `1.2.9` |
| `insightflow-acceptance-local-gateway:rollback-metric-grants-20261008` | `sha256:a2077298dd68b27c453808c64afab42569b3c6e66c165b4a0cc897e23ffd1c60` | `0.31.0` | 缺失 | 缺失 | 缺失 | `7.4.0` | `1.2.9` |

收到候选范围收窄指令前，另有一次按 gateway tag 过滤的批量探针已启动其他三张本地镜像；其 Python module 摘要未被保存，本记录不引用这些结果。之后没有继续扫描。

两镜像都含 `/app/backend/.venv`，并有 Node `22.23.3`、npm `10.9.9`、uv `0.11.1` 和 lark-cli `1.0.65`。镜像内 `backend/pyproject.toml` SHA-256 为 `5e304cedfeeee05a3b8959ef437269bf5549f0c17a48c0153697221d118116bb`，与当前工作树一致；镜像内 `backend/uv.lock` SHA-256 与当前 canonical hash 一致。

从现有 Dockerfile 布局看，派生镜像可以沿用 `/app/backend` 路径复制冻结源码，并通过排除 `.venv` 保留现有虚拟环境；但两张镜像都缺少 `psycopg`、`psycopg-pool` 和 `langgraph-checkpoint-postgres`，`PostgresSaver` 也无法导入。旧镜像里的 Gateway 业务源码不是冻结的新版本；派生镜像必须覆盖新冻结源码，不能直接把旧镜像当新版。只复制新源码不足以满足 PostgreSQL runtime；派生镜像仍需安装 postgres extra。此处只是可行性分析，没有修改正式 Dockerfile、生成派生镜像或检查 Docker 缓存。

## 启动边界

由于没有可用的新 Gateway image ID，本切片没有运行默认 runtime preflight、没有执行 `-Apply`，也没有启动 `iflow-final-pg-20261008`、应用数据库或模型。29384/29385 与 MySQL 未操作。既有静态预检摘要原件保持未改，副本保存在 `.reviews/final-postgres-runtime-20261008/runtime-preflight-summary-before-startup-20261009.json`，供后续审查。

因此，本切片尚未验证四服务健康、29388、PostgreSQL app migrations/checkpoint tables 或 business `verify_full` 连接；这些仍待主会话审查后确定后续构建方案并完成启动。
