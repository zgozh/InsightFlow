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

## 安全数据分析 Agent 工作流（Phase 3）

`app.analytics.agent` 是 App-owned Agent bridge。Harness 只通过配置化 tool loader 动态加载它，
Harness 自身不 import App，也没有 Analytics 专用开关。

- `runtime.py` 只保存 Gateway 在 composition 成功后绑定的**不可变** `AnalyticsServices`，shutdown 清除。
  重复绑定**不同**对象是配置错误（`analytics_agent_already_bound`），绝不静默替换；它不创建
  engine/session/repository，也不 dispose 共享资源。
- principal 只来自 Gateway `inject_authenticated_user_context` 写入的 `runtime.context["user_id"]`。
  刻意**不**回退到 ambient ContextVar 或 `DEFAULT_USER_ID`：后者是未认证桶，把它当 principal 会让
  未认证路径落到一个字面量为 `default` 的账号上。取不到就是稳定的 `analytics_unavailable`。
- `inspect_business_catalog` 无身份参数，只返回 datasource 的 `id/name/engine/default_schema/status`
  与 metric 的 `key/name/description/dimensions/version/status`；不含 owner、`secret_ref`、policy 或内部版本。
- `query_business_data` 的参数**只有** `datasource_id` 与 `sql`，并在一次调用内完成 plan → execute：
  plan token 只活在函数局部变量里，绝不进入 ToolMessage、checkpoint、run event、日志、异常或 evidence。
  execute 失败不重新 plan、不自动重试；取消照常传播。
- 成功执行返回确定性 evidence：`evidence_id` 是安全元数据 canonical JSON 的 SHA-256，`result_digest`
  是 canonical columns+rows 的 SHA-256。字段白名单固定，不含 SQL、token/digest、secret、DSN、异常文本或 PII。
  结果仍受 Phase 2 的列/行/字节上限约束。
- Gateway 只在认证 analysis run 准入后发行绑定 principal/thread/run 的短生命周期 collector，并只通过
  worker 的 `ToolRuntime.context` 传给固定查询与报告工具。`query_business_data` 只有在 plan→execute 得到
  成功决定、构造规范 evidence 与有界结果后才登记快照；拒绝、异常、取消不登记。每 run 最多保存 20 项、
  合计 16 MiB；快照仅含规范 evidence、列与有界 JSON 行，不含 raw SQL、plan token 或凭证。
- `write_analysis_report` 在文件与索引写入前要求 evidence ID 非空、无重复并全部命中同一 collector 的成功
  记录；未知、伪造、跨 owner/thread/run 或缺少 collector 均稳定拒绝。collector 是 run-local 内存对象，不是
  进程级索引、checkpoint state、run event、对外回执或持久化 evidence 库。普通聊天不获此 collector，原有
  受控查询返回行为保持不变，但不能据此获得受控报告资格。

Lead-only 与 subagent 隔离：DeerFlow 会把父级 tool group 原样继承给 subagent，因此
`config.example.yaml` 用 operator-owned、**加法式**的 `subagents.agents.general-purpose.disallowed_tools`
与 `subagents.agents.bash.disallowed_tools` 拒绝 `inspect_business_catalog` / `query_business_data` /
`publish_analysis_report`。它只能追加拒绝项，永远不能解除内置拒绝项，客户端与 run context 都无法覆盖。

`agent/` 模块不得 import SQLGlot、SQLAlchemy、驱动、secret resolver 或 repository；它只调用
`AnalyticsServices` 应用入口，Phase 4 的 UI 与 Phase 3 的 Agent 因此共用同一条 Phase 2 安全闭环。

## 分析报告索引与产品工作台（Phase 4）

报告索引是 Phase 3 artifact 的**补口**：`analytics_analysis_reports` 只登记
`principal_id / thread_id / run_id / artifact_path / title / status / evidence_ids / created_at`，
**不保存** artifact 内容、原始 SQL、结果行、prompt、token 或凭证。字段白名单由
`tests/test_analytics_report_domain.py` 的字段集合断言钉住；表结构本身也没有这些列。

- 迁移是纯前向的 `0002_analytics_analysis_reports`：Analytics 自有链照旧只 `upgrade head`，
  Harness 链与 `alembic_version` 完全不受影响。该表**没有**指向 Harness 表的跨链外键：报告索引
  必须比会话活得更久。
- `artifact_path` 必须是 `/mnt/user-data/outputs/` 下的规范化相对目标（拒绝绝对路径、反斜杠、
  空段、`.`、`..`、目录本身、控制字符与超长值）。打开它仍然要经过
  `/api/threads/{thread_id}/artifacts/{path}` 的 thread ownership 检查——报告索引**不是**公共 URL，
  也不签发任何 URL。
- `evidence_ids` 只接受 1..20 个 64 位小写 SHA-256，且不重复。没有 evidence 的"分析报告"正是
  Phase 3 要禁止的无依据数字，因此领域层直接拒绝空列表。
- 发布幂等键是 `(principal_id, thread_id, run_id, artifact_path)`，**全部由服务端从受信 runtime
  派生**（`agent/runtime.py::trusted_principal` 与 `trusted_thread_run`）。`publish` 返回稳定结果码：
  `published`（新建）/ `existing`（逐字重试）/ `report_conflict`（同键不同内容，绝不静默覆盖）。
  并发重试由唯一约束兜底，最多留下一行。
- `publish_analysis_report` 是 Lead-only 工具：模型可见参数只有 `title` / `artifact_path` /
  `evidence_ids`，工具结果也**不**回显 principal/thread/run。它在 `present_files` 成功之后才应被
  调用，且只登记索引——不读、不复制、不上传 artifact。
- `GET /api/analytics/reports`（principal-scoped）与 `GET /api/analytics/admin/reports?principal_id=`
  （显式 admin 端点）都只返回索引元数据；游标成对出现，keyset 语义与审计读取一致。
- 读取侧对损坏行整体失败：状态、evidence JSON、路径或标题被绕过领域层改写时，整页返回稳定错误，
  绝不返回"部分正确"的证据。

`agent/reports.py` 与 `agent/tools.py` 一样，不得直接 import 文件系统、sandbox、SQLAlchemy 或驱动。
旧 `publish_analysis_report` 只登记索引，合同不变。`write_analysis_report` 是仅供 Gateway
composition 使用的窄适配器：模型 schema 只有标题、Markdown 正文和 evidence ID；它必须从受信
runtime 同时取得身份与 Gateway 签发的本 run writer 能力，先通过领域预检，再由能力写入固定
`analysis-report-{run_id}.md`，最后才调用同一个 `AnalyticsServices.publish_report` 用例。
文件与索引没有共同事务；索引失败时返回稳定失败、不发成功 artifact 回执，允许同正文重试复用孤儿文件。
正文仍是受线程所有者保护的 artifact，不代表自动脱敏；消息、事件与历史副本必须由 Harness 精确
工具投影遮盖 `markdown`，不得把正文搬入索引或回执。工具正向白名单和 Gateway 的
`analysis_mode_unavailable` 门禁由各自模块约定，writer 合成测试不代表分析入口已启用。

**报告 Reviewer 门禁（Phase 6F3B1）**：writer 完成身份、领域与 run-owned evidence 校验后，必须先使用
Gateway 发行的同 run Reviewer capability，再写 artifact 或登记索引。Capability 仅从成功查询 collector
解析快照、标题、草稿和 evidence ID；不从模型消息、checkpoint 或模型自报字段重建。Lead assembly
把服务端最终选定的未绑定 base model 交给该能力；Reviewer 直接调用该模型，不绑定工具/结构化工具、不经过
Lead ToolNode、task 或 MCP。Reviewer 输入总量按 UTF-8 字节限制为 64 KiB，输出请求限 256 token、返回体
限 2 KiB，调用限时 20 秒；无法提供受限输出参数、超限、超时、取消、模型错误或封闭 JSON 不合法均不能写入。
每 run 最多两次不同内容复核，同一 title+markdown+evidence 的已通过重试复用仅含摘要码的决定；并发调用受
run-local 锁与现有 create-only artifact writer 双重约束。拒绝仅向 Lead 返回有限稳定 `reason_code`。
LLM pass 只是流程门，不是数学证明；本语义不替代 AS-07/08/09/10 验收，也不声称第三方 provider 自有遥测
不会导出内容。Reviewer 的 LangChain invocation 明确清空继承回调/标签/metadata，避免普通 RunJournal
接收其原始输入与输出；不要改成 `RunnableBinding` 包装模型调用，因为 LangChain 会重新合并 ambient callbacks。

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
