# Analytics Domain Guide

`app.analytics` owns InsightFlow's business-analysis domain. It may import the generic `deerflow.*` Harness only from future composition/agent adapters; Harness must never import this package.

## Layer rules

- `domain/`: standard library only; immutable business contracts and deterministic policies.
- `application/`: use cases and ports; may import `domain/`, never delivery/runtime frameworks.
- `infrastructure/`: real adapters. `sql_policy.py` and `semantic_authorizer.py` are the only modules allowed to import `sqlglot`; the rest arrives with MySQL/PostgreSQL/repository work in Phase 2B2/2C.
- `agent/`: added with real tools and immutable Agent definitions in Phase 3.
- `api/`: added with real FastAPI routes in Phase 2C; routes call application use cases.

SQLGlot is a lenient parser, not a security validator. Successful parsing is never approval: the adapter allowlists the statement root, scans the whole AST for forbidden nodes, then serializes and re-parses before returning anything. Keep the pinned `sqlglot==30.18.0` exact — AST shape is security-relevant behaviour.

Normalized and prepared SQL accepts no SQL comments or optimizer hints, no session/property assignment (`SELECT @x := id`), and no unbound parameters (`?`, `:name`, `@name`, PostgreSQL `$n`). If a later phase supports parameterized execution it must first add an explicit immutable binding contract to the domain and then relax this rule deliberately — never widen the current policy in place.

`PreparedQuery` is syntax-approved and row-bounded, and is deliberately **not** executable authority. It is not a permission grant and not a query-plan token.

## Semantic authorization (Phase 2B1)

`SqlglotSemanticAuthorizer` never trusts a `PreparedQuery` because of its Python type: it re-runs Phase 2A with the same engine and row limit and requires exact equality, so a hand-built value cannot bypass syntax policy.

Authorization is default-deny. Every physical relation and every column must appear in both the schema snapshot and the effective principal policy; every SQL function — including `COUNT`, `SUM`, `CAST` and anonymous calls — must be explicitly allowlisted. `nextval`, `setval`, `GET_LOCK`, advisory locks and unknown UDFs are therefore denied; the Phase 2A dangerous-function denylist is only defense in depth and never an authorization mechanism. CTE and non-correlated subquery sources resolve through to physical tables; correlated subqueries fail closed rather than being guessed.

`PreparedQuery.relations` is a Phase 2A syntax artifact and is never used as a permission input — permissions come only from the qualified physical lineage.

`AuthorizedQuerySpec` records the reconciled lineage and the schema/policy versions, and is deliberately **not** executable authority: it has no plan ID, connection, credential or execute method. A HIGH result (sensitive/PII column, cross-schema relation, Cartesian join, aggregate-only column under an aggregate) is always **denied** with `APPROVAL_REQUIRED`; V1 has no path that turns HIGH into an approval.

Phase 2B2 owns secret resolution, database adapters, `EXPLAIN` cost checks, short-lived server-side plan IDs, read-only transactions, timeout/row/byte caps and result sanitization. It must recheck the schema and policy versions before issuing a plan ID, because a `PreparedQuery` or `AuthorizedQuerySpec` can go stale. Never hand either value to a database.

Never store or pass a raw datasource password/DSN in domain objects. Domain objects carry only an opaque `secret_ref`; credential resolution belongs to infrastructure. Every new dependency direction must remain covered by `tests/test_analytics_boundaries.py`.

## 标识符语义

物理对象的 catalog/schema/relation/column 一律按真实元数据名称精确匹配：AST 先经 SQLGlot 的方言标识符规范化，再与 `SchemaSnapshot` 的真实名称比对，绝不用全局 `casefold()` 模拟方言规则。

- PostgreSQL：未加引号的 `orders` / `Orders` / `ORDERS` 折叠为小写；`"Orders"` 只匹配真实名称为 `Orders` 的对象；不存在精确对象时必须拒绝。
- MySQL：当前没有 `lower_case_table_names` 证据，只有元数据与查询大小写完全一致才放行，无法确认的大小写不一致安全拒绝（宁可误拒绝，不可误授权）。

`PrincipalAccessPolicy` 的 relation/column 规则也必须精确对应真实对象，大小写不同的规则不能授权另一个对象。只有 SQL 函数 allowlist 保持大小写不敏感。`AuthorizedQuerySpec.relations` / `.columns` 记录 `SchemaSnapshot` 的真实名称。

Phase 2B2 的 MySQL schema adapter 必须先读取或显式配置该服务器的 `lower_case_table_names` 语义，再决定是否扩展 `SchemaSnapshot` 契约；在此之前不得引入连接、驱动或服务器探测。

## 受控执行（Phase 2B2）

`plan_id` 是服务端能力令牌，不是客户端自报的权限声明。它不携带 SQL、权限或凭证；`ExecutionPlanStore` 只保存 `secrets.token_urlsafe(32)` 的 SHA-256 摘要，原始 token 只在创建时返回一次。不存在、过期、已领取与 principal 不匹配对外统一返回 `PLAN_UNAVAILABLE`，避免枚举。

完整语义授权会被重跑三次：创建 plan 前、`EXPLAIN` 之后、正式执行之前；每次都必须得到 allowed 且新的 `AuthorizedQuerySpec` 与原值 dataclass 精确相等（只比 version 不够，schema/policy 内容可能在版本号未变时漂移）。`AuthorizedQuerySpec` 与 `PreparedQuery` 依然不可执行——只有被 store 原子 `claim()` 的 plan 能到数据库，且 claim 必须发生在所有外部 I/O 之前，失败后不恢复 token。HIGH 永远不执行。

凭证只存在于 infrastructure 私有对象内，绝不进入 repr、日志、异常、domain 或 receipt；plan token、DSN、用户名、密码、原始 SQL 与原始 EXPLAIN JSON 都不记录。数据库错误一律映射为稳定决定码，驱动异常文本不外泄。

每次 EXPLAIN/execute 使用 `NullPool` 与 `echo=False` 的短生命周期 engine，并在 finally 中 `dispose()`；超时或取消后连接必须销毁，绝不复用。EXPLAIN 禁止 `ANALYZE`，执行 SQL 只能精确取自 `authorized.prepared.sql`。结果逐行消费（禁止 `fetchall()`），未知类型不得调用 `repr()`/`str()`。`UNSUPPORTED_RESULT_TYPE` 同时覆盖不受支持的结果值类型、无法安全承载的结果元数据与结果形状；`RESULT_LIMIT_REACHED` 只用于携带截断结果的正常执行决定。

超时语义必须按方言分别表述，不得笼统写成"服务端终止查询"：

- **PostgreSQL 16**：只读事务内设置本地 `statement_timeout`，服务端超时负责中止查询；`asyncio.timeout(statement_timeout_ms + cancellation_grace_ms)` 限制客户端总耗时；超时或取消后销毁连接，不得复用。
- **MySQL 8.4 + asyncmy**：当前连接仍然设置 `MAX_EXECUTION_TIME`。缓冲 `exec_driver_sql` 读取会得到 MySQL errno 3024，因此可以证明服务端限制确实已武装，`EXPLAIN` 走的正是这条缓冲路径。生产查询使用 `connection.stream()` 服务端游标，而实测（MySQL 8.4.11 与 8.0.46 表现一致）`MAX_EXECUTION_TIME` **不会抢占该流式路径**：它的实际终止边界是客户端 `asyncio.timeout(statement_timeout_ms + cancellation_grace_ms)`，随后必须使连接失效并销毁。真实数据库验收已证明客户端超时返回后 `information_schema.processlist` 中残留活动查询为零。服务端限制在该路径上保留为纵深防御——**不得把尚未发生的服务端抢占写成保证，也不得由此泛化成"取消所有服务端超时"**。
- MySQL 额外读取 `@@lower_case_table_names`，只有 `0` 放行，`1`/`2`/缺失返回 `UNSUPPORTED_IDENTIFIER_MODE`。

真实数据库门禁（Docker 必须已启动，PostgreSQL 16 + MySQL 8.4 只绑定 `127.0.0.1`）：

```powershell
python scripts/test_analytics_databases.py --engine postgresql
python scripts/test_analytics_databases.py --engine mysql
python scripts/test_analytics_databases.py --engine all
```

`InMemoryExecutionPlanStore` 只在单进程内有效，不跨重启、不支持多 worker。Phase 2C 在把 plan/execute 暴露给 API 或 Agent 之前，必须提供基于应用持久化数据库的原子 claim 实现并补充多 worker 竞争测试；端口与领域契约不得依赖 dict 或 `asyncio.Lock`。

## 语言规范

本模块新增或修改的注释、docstring、架构说明与复杂测试场景说明使用中文（见仓库级 `AGENTS.md`）。
变量名、函数名、测试函数名、错误码、SQL 关键字与 SQLGlot API 名保持英文；不给显而易见的代码加逐行
翻译式注释；不批量翻译未触及的上游文件。

## Commands

Every `uv` command uses `--locked` so a user-level mirror index cannot rewrite `uv.lock`; the only exception is the intentional `uv lock --upgrade-package <name>`, which must be followed by the coordinate-drift check in the phase plan.

```bash
PYTHONPATH=. uv run --locked pytest tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_boundaries.py
```
