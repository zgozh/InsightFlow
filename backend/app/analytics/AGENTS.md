# Analytics Domain Guide

`app.analytics` owns InsightFlow's business-analysis domain. It may import the generic `deerflow.*` Harness only from future composition/agent adapters; Harness must never import this package.

## Layer rules

- `domain/`: standard library only; immutable business contracts and deterministic policies.
- `application/`: use cases and ports; may import `domain/`, never delivery/runtime frameworks.
- `infrastructure/`: real adapters. `sql_policy.py` and `semantic_authorizer.py` are the only modules allowed to import `sqlglot`; `datasource_secrets.py` / `database_runtime.py` / `mysql_runtime.py` / `postgresql_runtime.py` own credentials and drivers; `persistence/` may import SQLAlchemy and Alembic. Infrastructure never imports Harness (`deerflow.*`), `app.gateway`, FastAPI or LangChain.
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

## 持久化控制面（Phase 2C1）

Analytics 拥有**自己的** SQLAlchemy `MetaData`（`AnalyticsBase`）与**自己的** Alembic 链，绝不注册进 Harness 的 `Base.metadata`：Harness 不得反向 import App，而依赖 import 副作用把 App 模型塞进 Host 的 `create_all()`，会让空库、autogenerate 与独立测试的表集合发生漂移。代价是 Host 的迁移过滤器必须显式排除固定前缀 `analytics_`（`migrations/_env_filters.py::APP_OWNED_TABLE_PREFIXES`，是常量而不是又一个运行时注册表）。两条链互不认识：

- 版本表分离：Analytics 用 `analytics_alembic_version`，Harness 用 `alembic_version`；
- Analytics 链**只** `upgrade head`，绝不 `create_all + stamp head`；未知 revision、空版本表、多版本行、有 `analytics_*` 表却无版本表一律拒绝启动（`bootstrap_analytics_schema`），绝不自动重 stamp；
- PostgreSQL 用 Analytics 专用的固定 advisory lock（与 Harness 的 key 不同），SQLite 用每 engine 的 `asyncio.Lock` 加 30 秒 `busy_timeout`。注意 SQLite 的 `transactional_ddl` 为 `False`：Alembic 不会自己开启或提交迁移事务，**版本表写入必须由调用方提交**，否则会建出表却没有任何 revision 记录；
- 迁移通过调用方注入的连接执行（`config.attributes["connection"]`）；生产 bootstrap 绝不由 DSN 另建 engine，否则 search path、事务与锁都会落到另一条会话上。

权限仍然默认拒绝：owner 只决定管理归属，**owner 本身不获得查询权限**；`get_accessible()` 要求存在与 principal 精确匹配的 policy 行且数据源为 `active`，`None` 从不表示跨用户查询。schema/policy 的 `replace` 必须携带 `expected_version`：完全相等幂等、内容不同但版本相同拒绝、当前版本不等于 expected 拒绝；metric 是 exact-owner scope 且版本只能前进。

plan 的持久化是**明确的短期执行状态例外**：`analytics_execution_plans` 保存 Phase 2A 重新序列化后的 canonical SQL 与 opaque `secret_ref`，payload 上限 1 MiB、TTL 上限 300 秒，`claim()` 时立即删除。原始 token 永不落库（只存 SHA-256），摘要也永不写日志；不得把这段 SQL 复制进日志、异常、receipt 或审计。

`SqlExecutionPlanStore.claim()` 只用**一条** `DELETE ... RETURNING`：先删除，再在 adapter 内校验 principal、过期与 payload。错 principal、过期、已领取、损坏与未知 payload 版本都已经被消费并统一返回 `PLAN_UNAVAILABLE`，失败后绝不恢复 token。禁止 SELECT-then-DELETE、dict 替代与 `asyncio.Lock`。

审计是**门禁**而不是尽力而为的日志：

```text
plan:    audit:start -> datasource -> authorize -> explain -> datasource -> authorize -> store:put -> audit:finish
execute: store:claim -> audit:start -> datasource -> authorize -> gateway:execute -> audit:finish
```

- 审计 start 失败返回 `AUDIT_UNAVAILABLE`，并且不发起任何后续业务数据库调用；
- plan 的 finish 失败必须 `revoke` 已插入的 plan 且绝不返回 token；
- execute 的 finish 失败不返回查询结果，记录停留在 `started`——已经发生的外部查询无法用分布式事务回滚，`started` 就是"执行结果未知"的保守证据；
- 取消继续传播 `CancelledError`，只在有界 shield 中尽力写终态；
- 审计表结构本身不含 SQL、token/digest、secret ref、DSN、用户名/口令、驱动异常文本、原始 EXPLAIN 与结果值字段；`QueryAuditStart` / `QueryAuditCompletion` 也在领域边界拒绝这些内容进入。

PostgreSQL 门禁额外跑 `tests/test_analytics_persistence_postgresql.py`：每个测试在独立临时 schema 中运行，schema 生命周期由初始化超级用户完成，**被测连接仍是普通用户 `analytics_tester`**；它证明真实 `DELETE ... RETURNING` 竞争、advisory lock 容量上限与 `FOR UPDATE` 替换冲突。

## 认证交付与 Gateway 装配（Phase 2C2）

`app.analytics` 自己解析 `AppConfig` 的 `analytics:` extra 块（`config.py`，`extra=forbid`）并由
`composition.build_analytics_services` 装配；Gateway 只负责认证、管理员门禁、生命周期挂载与 HTTP 映射。

- composition **只接收**已经建立的共享 `AsyncEngine` / `async_sessionmaker`，不建第二个控制面数据库；
  `enabled=false` 或 `database.backend=memory` 返回 `None` 并且**不**运行迁移，所有 `/api/analytics`
  稳定 503 —— memory backend 绝不退化成 `InMemoryExecutionPlanStore`；
- 配置错误、engine/session 缺失、迁移失败都阻止启动：半可用的查询 API 比不可用更危险；
- 限额只来自服务端配置，客户端没有任何覆盖入口。

`PlanAnalyticsQuery` 是系统里**唯一**接受原始 SQL 的入口：

```text
可访问 datasource -> Phase 2A policy -> Phase 2B1 authorization -> CreateQueryExecutionPlan
```

- 只接受认证 `principal_id`、客户端 `datasource_id` 与短生命周期 `raw_sql`；授权值来自服务端重跑，
  限额来自配置，两者都不接受客户端输入；
- policy/authorization 拒绝会写对应阶段的审计；审计 start/finish 失败统一 `AUDIT_UNAVAILABLE` 并停止后续步骤；
- raw SQL 只以 Phase 2A 的 SHA-256 `query_hash` 进入审计，绝不进入日志、异常或响应。

`ExecuteAnalyticsQuery` 只转发认证主体与一次性 `plan_id`。

HTTP 契约（`/api/analytics`）的安全约束：

- principal/owner 只来自 `app.gateway.deps.get_current_user`；请求体里的同名/授权/限额/版本/凭证字段
  在 DTO 层（`extra="forbid"`）就被 422 拒绝；
- 管理员路由把 `require_admin_user` 作为路由依赖，先于请求体使用与任何 repository 调用；PAT 永不获得管理员能力；
- `install_request_error_handler` 把该前缀下的 422 折叠成 `{"code": "invalid_analytics_request"}`：
  FastAPI 默认会把 Pydantic 的 `input` 原样回显，而 `sql` / `plan_id` 正藏在里面；
- 普通用户 datasource 响应不含 `owner_id` / `secret_ref`；任何响应都不含解析后的凭证；
- owner 不匹配与不存在统一 404（不泄露"存在但不是你的"），版本冲突 409，存储/驱动失败 503 且不带文本；
- 审计读取只有 exact-principal：管理员也必须给出精确 `principal_id`，`*` 不是通配符。

行数上限：`max_result_rows` 是**全局服务器上限，不是每条查询必须达到的下限**。`PlanAnalyticsQuery`
在拿到服务端生成的 `AuthorizedQuerySpec` 后派生本次计划的 `ExecutionLimits`，只把该字段向下收紧到
`min(配置上限, authorized.prepared.row_limit)`，其余字段固定来自启动配置。这是服务端派生而不是客户端
override：上限只可能变小，`CreateQueryExecutionPlan` 里 `limits.max_result_rows <= prepared.row_limit`
的校验继续作为纵深防御，plan payload 保存收紧后的 limits，execute 不会重新放宽。

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
