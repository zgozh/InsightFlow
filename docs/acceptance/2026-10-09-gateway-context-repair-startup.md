# Gateway 构建上下文修复与 PostgreSQL 启动验收

## 结果

已在 `iflow-final-pg-20261008` 新项目中启动 Gateway、Frontend、Nginx 与 Redis。Gateway 和 Redis 为 healthy，Frontend 与 Nginx 为 running。新 Gateway 使用镜像 `insightflow-release-gateway:pg-final-20261009`，镜像 ID 为 `sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63`，`WORKDIR` 为 `/app`。Nginx 仅发布 `127.0.0.1:29388`。

## 上下文修复与镜像

冻结构建上下文缺少 20 个生产 Python 文件，全部位于 `backend/packages/harness/deerflow/sandbox/`。修复前覆盖审计统计 `app` 136 个、`packages` 456 个生产 `.py` 文件；修复后缺失文件为 0、内容 hash 差异为 0。只复制恢复这 20 个文件，没有复制测试、缓存、配置或密钥，也没有改生产源码、锁文件或正式 Dockerfile。

ignored Dockerfile 从已核准基础镜像 `sha256:703a15480954b4a52979fd1b2f35bfea39e1958bba4deb85728890e645958656` 派生，只执行 sandbox `COPY` 并将 `WORKDIR` 设为 `/app`，修正继承命令 `cd backend` 与工作目录不匹配的问题。使用本地缓存构建，没有运行包管理器、APT 或测试。最终镜像 ID 与运行中的 Gateway 镜像一致；镜像内离线导入检查通过。

构建证据：

- `.reviews/release-stage-build-20261008/gateway-build-20261009/production-python-coverage-after-20261009.json`
- `.reviews/release-stage-build-20261008/gateway-build-20261009/gateway-context-repair-build-20261009.log`
- `.reviews/release-stage-build-20261008/gateway-build-20261009/context-repair-image-probe-20261009.json`

## 有界恢复与运行读回

`-ResumePartial -PreviousGatewayImageId 703a15480954b4a52979fd1b2f35bfea39e1958bba4deb85728890e645958656` 预检通过，随后 Apply 返回 `started / health / ready`，exit 0。launcher 只恢复已存在的新项目；Gateway 与 Frontend 按一致 token 配置重建，Nginx 启动，Redis 容器与数据卷保持原样。端口 guard 通过 Nginx `HostConfig.PortBindings` 验证 loopback 绑定，并确认宿主机没有未知 listener。

运行中容器与镜像：

| 服务 | 容器 ID | 镜像 ID | 状态 |
| --- | --- | --- | --- |
| Gateway | `42bbe18d4d02700d9427fbcf1ceaf62eddfdffde220109176fe038e7fc78b960` | `sha256:c7fe6b3b50e02b99c427ac0240687c48db82475e698c0617e36c2c964ad39e63` | healthy |
| Frontend | `a81ff51433672de7fedc2a62cf8304c83fc1cd4884553b8e2f1c88845860f0ce` | `sha256:fae029bdcec4b8a82fc11d864e6ae9fc4c99892c2a62bac334583ddd61fd759c` | running |
| Nginx | `7558d230dfca40c08b8beddd1b421f9960eebbb116ca5620d3e56670e4081112` | `sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752` | running |
| Redis | `1c2c66daa6767818c66cbdf14f122ce430f212ddf62da682e8d2f12203d83fee` | `sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf` | healthy |

部署与只读读回证据位于 `.reviews/final-postgres-runtime-20261008/startup-probes/`：

- `resume-partial-preflight-20261009.json`、`resume-partial-apply-20261009.json`
- `final-container-readback-20261009.json`
- `gateway-readiness-20261009.json`、`gateway-http-acceptance-20261009.json`
- `gateway-pg-acceptance-20261009.json`

## PostgreSQL 与 HTTP 门禁

Gateway 内部 `/health/ready` 返回 HTTP 200，`database=ok` 且 `checkpointer=ok`。应用数据库只读 catalog 检查发现 9/9 个应用表；唯一 Alembic revision 与镜像源码 head 相同；4/4 个 LangGraph checkpointer 表存在，`checkpoint_migrations` 有 10 行。

同一 Gateway 容器使用既有 `ANALYTICS_CQ_PG_READONLY_CREDENTIAL` 经生产 `EnvironmentDatasourceSecretResolver` 建立业务 PostgreSQL 连接。`verify_full`、主机名校验、证书必需、服务端 SSL 与当前连接 SSL 均通过；只执行 `SELECT`，确认 `public.monthly_metrics` 可读且有 3 行。

经 loopback Nginx 的 `/` 和 `/health` 均返回 HTTP 200；`/health` 响应为 `{"status":"healthy","service":"deer-flow-gateway"}`。未认证 `/api/*` 探测返回 401，符合既有认证边界，没有弱化认证或改动 API 路由。

## 保留边界

已授权退役清单中的 10 个测试容器按前一阶段指令移除；postcheck 确认 4 个卷、2 个网络保留。此次启动只操作 `iflow-final-pg-20261008` 的有界 partial 状态，没有触碰 29384 演示项目、其他项目、PG fixture 数据、MySQL 数据、正式 Dockerfile、生产源码或锁文件。未调用模型、未执行 seed。

退役证据：`.reviews/final-postgres-runtime-20261008/startup-probes/retirement-delete-20261009.json` 与 `retirement-postcheck-20261009.json`。
