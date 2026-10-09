# Query 风险门禁补充验收（2026-10-09）

仅补测前次证据缺口；此前 11 类 HTTP 安全矩阵未重跑。使用现有 PostgreSQL 只读 fixture `127.0.0.1:29386`，未启动或修改容器，未调用模型。

| 门禁 | 实际证据 |
| --- | --- |
| 已存在但 B 无权访问的数据源不可枚举 | 用户数据源列表不包含该合成数据源；对其发起 plan 得 HTTP `200` / `datasource_unavailable`，与既有随机不存在数据源的 HTTP `200` / `datasource_unavailable` 相同。合成数据源已停用。证据：`.reviews/final-postgres-runtime-20261008/security-probes/query-risk-remaining-evidence.json`。 |
| HIGH 敏感列拒绝 | 复用已验收的 PostgreSQL fixture 证据：授权阶段返回 `sensitive_column`，没有创建 plan。证据：`docs/acceptance/2026-10-08-controlled-query-live.md`。本轮未重跑 HIGH。 |
| MEDIUM 实际结果裁剪 | 当前 `config.yaml` 为 5000 ms / 1000 行 / 1,048,576 bytes；`delivery.py` 对 MEDIUM 将三项减半，实际预算为 2500 ms / 500 行 / 524,288 bytes。API plan/execute 审计风险为 MEDIUM：行数用例返回 `plan_created` 后 `result_limit_reached`，恰为 500 行、6031 bytes；字节用例返回 `plan_created` 后 `result_limit_reached`，为 2 行、400042 bytes。两个结果均为截断状态。证据：同上 JSON；配置来源 `backend/app/analytics/config.py` 与 `config.yaml`，风险裁剪来源 `backend/app/analytics/application/delivery.py`。本轮实际 API 查询验证了行数和字节裁剪；2500 ms 预算由当前配置及裁剪实现直接确认，未人为制造慢查询触发该 MEDIUM 时限。 |
| PostgreSQL 真正 statement timeout 与清理 | 直接调用 `PostgreSQLRuntime`，在现有只读 PostgreSQL fixture 上以 300 ms server statement timeout 执行合成预授权语句；HTTP/SQL parser 路径拒绝 `pg_sleep`，故此项是 adapter 层证据，不代表 API plan/execute 超时链路已验证。实际得到 SQLSTATE `57014`、稳定码 `execution_timeout`，耗时 391 ms；超时后匹配的活动 backend 为 0，原连接不可复用、事务已关闭，新连接 `SELECT 1` 成功。cancellation grace 为 500 ms。证据：`.reviews/final-postgres-runtime-20261008/security-probes/postgresql-statement-timeout-evidence.json`，执行器：同目录 `postgresql_statement_timeout_probe.py`。 |

未覆盖边界：真实 PostgreSQL 超时没有经过 HTTP plan/execute，因为 SQL parser 在执行前拒绝 `pg_sleep`；MEDIUM 的 2500 ms 超时没有由 API 慢查询触发。其余本次指定门禁均有对应证据。探针只保存稳定状态码、预算、计数及连接清理结果；合成数据源已停用。
