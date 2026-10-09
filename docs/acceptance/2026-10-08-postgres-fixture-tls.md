# PostgreSQL fixture TLS 准备与验收记录

日期：2026-10-08。此记录只覆盖本任务的 PostgreSQL fixture TLS 准备与直接连接探针，不代表 Gateway 容器路径或最终产品运行验收。生产 DatasourceSecret DTO 与 TLS 策略未改动。

## 目标与保全边界

只操作 Compose project `evidence-pg-live-20261008-c0efb9fd03` 的 `evidence-pg-live-20261008-c0efb9fd03-postgres-1`，镜像 `postgres:16`，container ID `5fdcfedc8678252bd0d368cf047dd4243b3ee7d4f1288d0d5099fa68bbed3ec4`，数据卷 `evidence-pg-live-20261008-c0efb9fd03-data`，网络 `evidence-pg-live-20261008-c0efb9fd03-net`。网络只连此 fixture；容器 DNS aliases 包含 `postgres` 与实际 container name，宿主端口仅 `127.0.0.1:29386`。

Docker Desktop 原先未运行；按已授权的单次恢复启动后，Engine 在 21 秒内就绪。Desktop 自动恢复了原先停止的 29384/29385 应用容器；本任务没有对它们发出 start/stop，也未操作已停的 MySQL。目标 PG fixture 当时是 Exited，随后只启动了上述 exact container。现在它保持运行，`pg_isready` 显示 accepting connections；没有重启数据库容器。

启动 TLS 前保存的只读摘要在 `.reviews/final-postgres-runtime-20261008/fixture-before-tls.json`。当时 `SHOW ssl=off`、配置来源 `default`、参数上下文 `sighup`，`pg_file_settings` 没有 SSL 项，数据卷中没有 `server.crt` 或 `server.key`，也没有其他 PostgreSQL client session。现有 evidence 数据库迁移版本为 `0004_metric_grants`，证据表共 22 行：主合成 run 1 行、容量 run 20 行、冲突 run 1 行；主快照 34 bytes，digest 为 `06fe37e857e7efb27709fb13c640848e908c8da67dfb82af8c842cfb68479c9`。

## TLS 配置与验证

PostgreSQL 16 容器内已有 OpenSSL 3.5.7。新自签名 server/CA 证书只在该 fixture 数据卷内生成，没有安装依赖或新建服务。私钥在 `/var/lib/postgresql/data/server.key`，owner `postgres:postgres`、权限 `0600`；公开证书 `server.crt` 权限 `0644`。有效期为 `2026-10-08 15:13:11 UTC` 至 `2027-10-08 15:13:11 UTC`。SAN 含 `DNS:postgres`、`DNS:evidence-pg-live-20261008-c0efb9fd03-postgres-1` 和 `IP:127.0.0.1`。仅公开 CA 副本保存在被 Git 忽略的 `.reviews/`，私钥未复制到主机，也未输出。

稳定 secret DTO 的 TLS 字段是 `tls_mode` 与 `ca_pem`，合法模式为 `disable` 或 `verify_full`；`disable` 只允许 loopback/localhost，非 loopback 默认 `verify_full`。没有 `ssl_mode` 或通用 `ssl` 覆盖字段。因此，business 参数使用 `tls_mode=verify_full` 并携带这份 CA；没有放宽生产限制或伪装连接 host。

变更前已确认 `ssl` 的 PostgreSQL context 是 `sighup`。仅执行 `ALTER SYSTEM SET ssl = 'on'` 与 `pg_reload_conf()`，reload 成功，无需重启；现在 `SHOW ssl=on`，配置来源为数据卷的 `postgresql.auto.conf` 第 3 行。配置回退记录和受身份/卷/会话检查保护的回退脚本见 `.reviews/final-postgres-runtime-20261008/TLS-回退说明.md` 与 `fixture_tls_rollback.ps1`；回退尚未执行。

实际 TLS 探针使用 Python 默认安全验证上下文，加载 CA、要求证书链校验并开启 hostname 校验，host 为 `127.0.0.1`。结果保存在 `.reviews/final-postgres-runtime-20261008/fixture-tls-probe.json`：

- admin、business readonly 与 app owner 三条连接的 `pg_stat_ssl.ssl` 都为 `true`，server `SHOW ssl=on`。
- `analytics_cq_20261008_reader` 可读取 `analytics_fixture_20261008.public.monthly_metrics` 的 3 行，`SELECT=true`、`INSERT/UPDATE/DELETE=false`；没有 `currency` 列。
- `iflow_runtime_app_20261008` owner 可连接并有数据库 `CREATE` 权限；尚无用户表。
- TLS 后的独立 loopback 明文基线在 `.reviews/final-postgres-runtime-20261008/fixture-after-tls.json`：版本、证据行数、主快照长度/digest 与 synthetic run 行数均和 TLS 前一致；其他 client session 为零。

证书公开元数据与 key 权限摘要在 `tls-cert-public-metadata.txt`；整个证书内容只有公开证书，不含私钥。TLS 的 PostgreSQL 16 配置和 reload 行为按官方文档核对：[SSL/TCP](https://www.postgresql.org/docs/16/ssl-tcp.html)、[`pg_ctl` reload](https://www.postgresql.org/docs/16/app-pg-ctl.html)、[`pg_stat_ssl`](https://www.postgresql.org/docs/16/monitoring-stats.html)。

## 未覆盖的运行 Gate

本切片没有启动 Gateway、Frontend、Nginx，没有构建镜像或调用模型。Docker DNS `postgres` alias 与对应 SAN 已从容器网络/证书中核对；Gateway 经该网络实际连接的端到端 `verify_full` 验证留到统一构建后的最终 Gate。业务数据没有 currency 列的事实保留，最终 case 的文案及是否使用当前数值 oracle 尚待最终实际 case 决定。
