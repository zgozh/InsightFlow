# 直连查询 API 安全验收（2026-10-09）

本次只读/受控执行探针针对 `127.0.0.1:29388`，复用既有 B 用户、管理员会话和 revenue fixture；未改生产代码、策略或部署，也未触发模型。探针结果保存在 `.reviews/final-postgres-runtime-20261008/security-probes/query-api-security-evidence.json`，仅记录状态、稳定码、计数和不可逆摘要，不保存请求 SQL、凭据、原始 plan token 或查询结果。

验证命令：`node --check .reviews/final-postgres-runtime-20261008/security-probes/query_api_security_probe.cjs` 通过；随后运行 `.reviews/final-postgres-runtime-20261008/security-probes/run_query_api_security_probe.ps1`，退出码 `0`。PowerShell runner 保留 UTF-8 BOM。

真实 API 结果：匿名 `GET /datasources` 为 `401`；匿名 plan `POST` 为 `403`，在认证前由 CSRF 防护拒绝；B 用户访问管理员 datasource 路由为 `403`。不存在的 datasource 返回 HTTP `200` / `datasource_unavailable`。探针发现没有已存在且对 B 不可见的数据源，因此未构造该拒绝场景，也未创建新数据源。

11 种拒绝形状均返回 HTTP `200`、仅含稳定 `code` 且没有创建 plan：未授权关系 `unknown_relation`；禁止的 `description` 与 `customer_email` 列 `column_not_allowed`；DDL/DML `unsupported_statement`；事务控制及多语句 `multiple_statements`；行注释/块注释 `comment_not_allowed`；全角分隔符 `parse_error`；Unicode 行分隔符注释 `comment_not_allowed`。拒绝响应未回显 SQL 或凭据。

合法 MEDIUM 查询的 plan 返回 `plan_created`，响应字段闭合且未回显 SQL；管理员 A 对 B 的一次性 plan 执行返回 `plan_unavailable`，随后 B 对同一 token 也得到 `plan_unavailable`。现有 plan store 实现先删除 token 再校验 principal，源码明确将错 principal 探测也消费 token，以统一错误码防止枚举。使用第二个独立 plan，B 执行返回 `executed`，结果为 3 行，字段仅为 `period`、`revenue`、`users`，fixture 中三个月金额与预期一致；同一 token 重放返回 `plan_unavailable`。因此错 principal 尝试会消耗该一次性 token，这是已观察到的当前语义。

B 的审计读取返回 HTTP `200`，36 条记录均属于 B，字段集合闭合且不含 SQL、plan token 或结果载荷；本次 MEDIUM plan/execute 对应审计共 4 条。执行结果 JSON 的字段集合也闭合。

边界：本次验证覆盖一个 MEDIUM plan/execute 正例，没有验证 MEDIUM 预算裁剪；当前 SQL 风险分类没有触发 HIGH 输入，因此 HIGH 拒绝未做 live 验证；未触发真实 statement timeout。相关 delivery 与 PostgreSQL adapter 测试未在本切片重跑，不将其记为本次通过证据。
