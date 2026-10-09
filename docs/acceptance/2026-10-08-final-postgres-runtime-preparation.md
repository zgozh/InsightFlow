# 最终 PostgreSQL 运行验收准备

日期：2026-10-08。结果是准备完成，不是 AS03/AS12 或最终应用验收通过。本任务没有构建、启动新 Gateway/Frontend/Nginx、调用模型，也没有操作 29384、29385 或已停 MySQL；另两位实现者正在修改的前后端源码未读取。

## 已准备并实际验证

在既有隔离 PostgreSQL fixture `evidence-pg-live-20261008-c0efb9fd03-postgres-1`（loopback `29386`）中，已有两个用途隔离的数据库与角色：business `analytics_fixture_20261008` / `analytics_cq_20261008_reader` 只读，application `iflow_runtime_app_20261008` / 同名 owner role 可创建应用表。它们是同一独立 PG fixture 服务中的不同数据库和角色，不是两个独立 PostgreSQL 集群。app 密码只在 `.reviews/final-postgres-runtime-20261008/app-role-password.dpapi`；admin 与 business reader 凭据沿用既有 DPAPI 文件。没有新建明文密码文件。

business fixture 的真实连接已按 `verify_full`、CA 与 `127.0.0.1` IP SAN 验证；server `SHOW ssl=on`，三个连接角色的 `pg_stat_ssl.ssl=true`。Business reader 可读取 3 行，`SELECT` 成功且 `INSERT/UPDATE/DELETE` 被拒绝。Application owner 可连接、有 `CREATE` 权限、尚无用户表。原 synthetic evidence 数据、主快照 digest 与 migration revision 在 TLS 前后保持一致。详细独立记录见[PG fixture TLS 记录](2026-10-08-postgres-fixture-tls.md)。

stable DatasourceSecret DTO 的 TLS 合同只接受 `tls_mode=disable|verify_full` 与 `ca_pem`；loopback 可用 disable，非 loopback 的 Docker DNS 业务源配置为 `verify_full` 并带本 fixture 公共 CA。生产接口与默认策略没有修改。证书私钥只存在目标数据卷且权限 `0600`；public cert SAN 同时包含 Docker alias `postgres`、实际 container name、`127.0.0.1`。

配置准备来自 `.analytics-demo/config.yaml`：其中 1 个 model、API key 是环境变量引用且引用存在于本地 `.env`；本任务没有测试模型连通性。staged runtime config 使用 `database.backend=postgres`、`postgres_url=$DEER_FLOW_PG_APP_URL`、`run_events.backend=db`、Analytics enabled，未增加显式 `checkpointer` override。稳定配置支持应用 PostgreSQL 路径，但新空 app DB 上的迁移、history/checkpoint/event/artifact 持久化仍需启动最终构建后实测。

## 独立运行栈预检

准备文件在 `.reviews/final-postgres-runtime-20261008/`。独立 Compose project 为 `iflow-final-pg-20261008`；Gateway、Frontend、Redis、Nginx 都需要显式 `sha256:...` image ID，`pull_policy: never`，没有 `build`。Gateway 使用独立 Home、staged config 与扩展 config；Nginx 是唯一 host published service，绑定 `127.0.0.1:29388`；Redis 是 required service；Gateway 只通过 external fixture 网络使用 `postgres:5432`，没有把容器地址误设为宿主机 `127.0.0.1:29386`。

当前静态预检状态为 `safe`，输出保存在 `runtime-preflight-summary.json`。它通过 `docker compose config --format json` 检查四个服务、immutable image IDs、无 build/pull、loopback-only port、isolated mounts、Redis required、PG fixture 网络，以及 business credential 的 `host=postgres`、`tls_mode=verify_full` 与 CA 存在。解析后的 Compose JSON 和敏感 env 只在进程内处理，摘要仅写 allowlisted 安全字段。最终栈 container 尚未创建，29388 当前无监听者。

本次静态检查使用当时本机已存在的镜像 IDs，仅用于验证配置形状；它们不代表后端阶段冻结后的最终构建。最终 Gate 必须传入主会话冻结构建所得 Gateway/Frontend IDs，并使用如下预检入口：

```powershell
& '.reviews\final-postgres-runtime-20261008\runtime_preflight.ps1' `
  -RedisImageId '<local sha256 image ID>' `
  -NginxImageId '<local sha256 image ID>' `
  -GatewayImageId '<frozen Gateway sha256 image ID>' `
  -FrontendImageId '<frozen Frontend sha256 image ID>'
```

此入口只准备隔离配置、从 DPAPI 临时解密参数并运行 Compose 静态 config 检查，不启动容器。后续统一验收运行时使用同一独立 manifest 和 process-only credential staging；本次没有执行部署命令。

## 最终主正向探针

待阶段构建冻结后按[独立主正向 probe](../../.reviews/final-postgres-runtime-20261008/final-runtime-probe.md)执行：用合成管理员 A 创建 datasource、登记真实 schema 与受限 policy/metric、授权合成普通用户 B；B 发起经营分析，验证真实角色链、evidence/report/artifact、列表/预览/下载、SSE Live 与持久 GET events 的 `(run_id, seq)` 一致性及刷新回填。Probe 依据现有 `monthly_metrics` fixture 的实际列与只读权限编写；没有 `currency` 列，因此是否选用收入案例及最终用户文案留待实际 case 决定，不标注货币单位。

其他未验 Gate 包括慢查询 timeout/cancel/failure（优先离线 HTTP model fixture）、定时分析复用、app PostgreSQL 恢复后的 history/checkpoint/events/evidence/artifact 和未完成 run 状态，以及 checkpoint resume 来源 run server provenance。上述均没有在本次准备中宣称通过或修复。

## 本次实际检查

- 仅对本任务脚本运行 Python `py_compile` 与 PowerShell AST 语法检查。
- 真实 PG 直接连接检查：server TLS、verify_full CA/hostname、readonly 权限、app owner 连接与 app DB 空表状态。
- TLS 前后只读证据对比：revision、总行数、synthetic run 行数、snapshot 长度与 digest。
- Compose 静态 config 检查通过；没有执行 `up`、build、pull、model call 或最终产品 probe。
- 回退脚本仅做了语法检查，未执行。若需要回退，只使用 `.reviews/final-postgres-runtime-20261008/fixture_tls_rollback.ps1`；它只针对已核验的目标 container/volume、清除本任务 TLS override 与生成的证书，不触碰数据库记录或其他服务。
