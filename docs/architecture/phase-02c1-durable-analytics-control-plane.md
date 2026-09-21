# Phase 2C1 架构：持久化 Analytics 控制面

状态：方案已批准，等待用户审阅本文后进入实施计划。

## 1. 目标与边界

Phase 2C1 把 Phase 2B2 仅存在于进程内的安全查询闭环，升级为可跨 Gateway
进程和重启共享的持久化控制面。它交付：

- `DatasourceDefinition`、`SchemaSnapshot`、`PrincipalAccessPolicy` 和
  `MetricDefinition` 的持久化仓库；
- 基于应用数据库的短期、单次、原子 `ExecutionPlanStore`；
- 不保存原始 SQL 与结果行的查询审计账本；
- Analytics 自有的前向迁移链，以及 SQLite/PostgreSQL 仓库验证；
- 在真实业务数据库 I/O 前强制写入审计开始记录的应用层门禁。

本阶段不增加 FastAPI 路由、Gateway 装配、配置项、Agent Tool、MCP、前端页面、
Redis、消息队列或新容器。Phase 2C2 才负责认证 HTTP 交付与应用装配，Phase 3
才向 Agent 暴露工具。

2C1 不得放宽 Phase 2A、2B1、2B2 已建立的默认拒绝规则。

## 2. 架构决策

采用“同一应用数据库、独立 bounded-context 元数据与迁移链”：

```text
Gateway composition（Phase 2C2）
        │ 注入 AsyncEngine / async_sessionmaker
        ▼
app.analytics.application ports / use cases
        ▲
        │ 实现端口
app.analytics.infrastructure.persistence
        ├── AnalyticsBase / analytics_* tables
        ├── repositories / versioned codecs
        ├── SqlExecutionPlanStore
        └── analytics Alembic chain
        │
        └── 复用 DeerFlow 应用数据库连接，不新增数据库或容器
```

Analytics ORM 不继承 `deerflow.persistence.base.Base`，也不注册到 Harness 的
`Base.metadata`。原因是：

1. `app.analytics` 是 App 拥有的业务域，Harness 不得反向 import App；
2. 依赖 import 副作用把 App 模型塞进 Harness `create_all()`，会让空库、Alembic
   autogenerate 与独立测试的表集合发生漂移；
3. 独立 metadata 与迁移链使表所有权、回滚和边界测试清晰，同时仍复用同一个物理
   SQLite/PostgreSQL 应用数据库，不增加部署复杂度。

Analytics 迁移链使用独立版本表 `analytics_alembic_version`，所有业务表统一使用
`analytics_` 前缀。Harness Alembic 的对象过滤器必须明确排除该版本表和
`analytics_` 前缀，避免主迁移 autogenerate 生成错误的 `drop_table`；Analytics
Alembic 也只能管理自己的 metadata。两条迁移链不得互相 import 对方的业务模型。

## 3. 依赖与运行边界

- `domain/` 继续只依赖标准库；本阶段新增审计值对象也遵守此规则。
- `application/` 只依赖 domain 和 Protocol，不得 import FastAPI、SQLAlchemy、
  Gateway 或 `deerflow.*`。
- `infrastructure/` 可以 import SQLAlchemy/Alembic，但不得 import `app.gateway`、
  FastAPI、LangChain 或 Harness。
- Phase 2C2 的 composition root 可以从 Harness 获取已经初始化的 `AsyncEngine` 与
  `async_sessionmaker`，并将它们作为构造参数注入 Analytics；反向依赖禁止。
- `database.backend=memory` 不提供持久化 Analytics 能力。2C1 不偷偷回退到内存
  store；2C2 遇到这种配置必须不挂载能力或稳定返回 503。
- SQLite 仅支持单 Gateway worker 的本地开发；多 worker 继续由现有全局门禁要求
  PostgreSQL。

## 4. 数据模型

所有主键、外键值和 principal/owner 标识使用现有字符串身份契约，不在仓库层猜测
租户。时间统一保存时区感知 UTC。JSON 字段只存经过显式 codec 验证的有界 JSON，
禁止 pickle、任意对象序列化和通用 `repr()`。

### 4.1 `analytics_datasources`

| 字段 | 约束 |
| --- | --- |
| `id` | 主键，服务端生成的 UUID 字符串 |
| `owner_id` | 非空；管理归属，不隐含查询权限 |
| `name` | 非空；`(owner_id, name)` 唯一 |
| `engine` | `mysql` / `postgresql` check constraint |
| `secret_ref` | 非空 opaque reference；不得保存真实 DSN/密码 |
| `default_schema` | 可空 |
| `status` | `active` / `disabled` / `unhealthy` check constraint |
| `created_at`, `updated_at` | UTC |

`owner_id` 只决定管理归属。即使是 owner，也必须存在与其 principal 精确匹配的
`PrincipalAccessPolicy` 才能查询，禁止隐式 owner 放行。

V1 不硬删除数据源。删除语义是改为 `disabled`，从而保留审计引用并立即让
`DatasourceCatalog.get_accessible()` 默认拒绝。

### 4.2 `analytics_schema_snapshots`

每个 datasource 只保存一个 current snapshot：

| 字段 | 约束 |
| --- | --- |
| `datasource_id` | 主键；逻辑引用 datasource |
| `engine` | 与 datasource 精确一致 |
| `version` | 非空、不可变版本标识 |
| `default_schema` | 非空 |
| `relations_json` | 有界、显式编码的 relation/column/sensitivity 数组 |
| `updated_at` | UTC |

替换 snapshot 时必须携带调用方刚读取的 `expected_version`（首次创建为 `None`），并在
同一事务中锁定、读取和比较旧值：

- 新对象与旧对象完全相等：幂等成功；
- 内容不同但 `version` 相同：拒绝，防止同版本静默漂移；
- 当前版本不等于 `expected_version`：稳定冲突，不写入；
- 内容不同、当前版本等于 `expected_version` 且新版本不同：原子替换。

版本生成由后续管理用例负责；仓库不得自行修改调用方传入的 domain value。

### 4.3 `analytics_access_policies`

主键为 `(datasource_id, principal_id)`，保存：

- `version`；
- `relations_json`：relation、column 与 `ColumnAccess`；
- `allowed_functions_json`；
- `updated_at`。

同样要求 `expected_version`，并执行“完全相等幂等；内容变化但版本相同拒绝；当前
版本不等于 expected 时稳定冲突”的规则。缺少 policy、空 policy、损坏 policy 或
principal 不精确匹配均为默认拒绝。禁止通配 principal。

### 4.4 `analytics_metrics`

主键为 `(owner_id, key)`，字段对应当前 `MetricDefinition`：`name`、`description`、
`expression`、`dimensions_json`、`version`、`status`、时间戳。

V1 的 metric 是 exact-owner scoped：`MetricCatalog.list_accessible()` 与
`get_accessible()` 只返回 `owner_id == principal_id` 的记录，不引入组织、租户、共享
目录或新的 RBAC 模型。Metric expression 在本阶段只是业务定义文本，绝不进入 SQL
执行器。

### 4.5 `analytics_execution_plans`

| 字段 | 约束 |
| --- | --- |
| `token_digest` | SHA-256 小写十六进制主键；绝不保存原始 token |
| `principal_id` | 非空、精确匹配 |
| `datasource_id` | 非空、用于索引和清理 |
| `payload_version` | 初始固定为 `1` |
| `payload_json` | `StoredExecutionPlan` 的有界、显式、版本化编码 |
| `issued_at`, `expires_at` | UTC；`expires_at > issued_at` |

索引至少覆盖 `expires_at` 和 `(principal_id, expires_at)`。

为了让另一个 worker 在签发者退出后仍能执行，payload 必须包含重建
`StoredExecutionPlan` 所需的完整 immutable snapshot，包括 canonical prepared SQL、
datasource definition、authorization、cost 和 limits。这里保存的是 Phase 2A 重新序列化
后的 canonical SQL，不是用户原始 SQL；它最多存活 300 秒，并在 claim 时立即删除。
这是一项明确的短期执行状态例外，不得把 SQL 复制进日志、异常、receipt 或 query
audit。payload 中只有 `secret_ref`，绝不包含解析后的用户名、密码或 DSN。

单个 payload 的 UTF-8 编码上限为 1 MiB，超过即拒绝签发。未知 `payload_version`、
字段缺失、非法 enum、非有限 Decimal、naive datetime 或 domain invariant 失败均
fail closed。

### 4.6 `analytics_query_audits`

审计表只保存安全元数据：

- `id`：UUID 字符串；
- `principal_id`、可空 `datasource_id`；
- `phase`：`policy` / `authorization` / `plan` / `execute`；
- `status`：`started` / `completed`；
- `query_hash`：可空 SHA-256；对解析前拒绝可由交付用例计算请求摘要；
- 可空 `risk`、`decision_code`（`started` 记录可以尚无最终决定）；
- 可空 `schema_version`、`policy_version`；
- 可空 `estimated_rows`、canonical decimal `engine_cost`、`plan_digest`；
- 可空 `row_count`、`byte_count`、`truncated`、`latency_ms`；
- `started_at`、可空 `finished_at`。

禁止字段：原始/规范化 SQL、plan token 或 token digest、secret ref、DSN、用户名、
密码、驱动异常文本、原始 EXPLAIN JSON、查询结果 columns/rows、PII 值。

`started` 长期未完成表示 worker 崩溃或结果更新失败，是有价值的证据，不得由读取
接口伪装成成功。审计记录不做本阶段自动删除；保留策略留给部署验收阶段配置。

## 5. 持久化端口

继续复用现有只读端口：

- `DatasourceCatalog`
- `MetricCatalog`
- `SchemaCatalog`
- `AccessPolicyCatalog`
- `ExecutionPlanStore`

新增彼此职责分离的应用端口，不把 SQLAlchemy session 暴露给 application：

```python
class DatasourceAdminRepository(Protocol):
    async def get_owned(self, *, owner_id: str, datasource_id: str) -> DatasourceDefinition | None: ...
    async def list_owned(self, *, owner_id: str) -> tuple[DatasourceDefinition, ...]: ...
    async def save(self, datasource: DatasourceDefinition) -> None: ...

class SchemaSnapshotRepository(SchemaCatalog, Protocol):
    async def replace(self, snapshot: SchemaSnapshot, *, expected_version: str | None) -> None: ...

class AccessPolicyRepository(AccessPolicyCatalog, Protocol):
    async def replace(self, policy: PrincipalAccessPolicy, *, expected_version: str | None) -> None: ...
    async def remove(self, *, datasource_id: str, principal_id: str) -> None: ...

class MetricRepository(MetricCatalog, Protocol):
    async def save(self, metric: MetricDefinition) -> None: ...
    async def retire(self, *, owner_id: str, metric_key: str) -> None: ...

class QueryAuditLog(Protocol):
    async def start(self, entry: QueryAuditStart) -> None: ...
    async def finish(self, completion: QueryAuditCompletion) -> None: ...
```

实际命名可以在实施计划中做小幅调整，但必须保持端口隔离、keyword-only identity 和
不可变输入；不得出现一个返回任意 dict 的“万能 repository”。仓库异常只能携带稳定
reason，不得携带数据库异常文本或序列化 payload。

## 6. 原子 plan store

`SqlExecutionPlanStore` 实现既有 `ExecutionPlanStore`，构造参数接收
`async_sessionmaker`、`max_entries` 和 payload codec，不依赖全局 engine、dict 或
`asyncio.Lock`。

### 6.1 `put()`

一个事务内完成：

1. 获得 plan-store 容量锁；PostgreSQL 使用固定的 transaction-scoped advisory
   lock，SQLite 显式使用 `BEGIN IMMEDIATE` 的数据库级写串行化；
2. 删除 `expires_at <= plan.issued_at` 的过期记录；
3. 检查 digest 冲突；
4. 统计当前记录，达到 `max_entries` 时抛出稳定
   `ExecutionPlanStoreError("capacity_exceeded")`；
5. 插入 versioned payload 并提交。

容量锁只保护短事务，不包围任何业务数据库网络 I/O。

### 6.2 `claim()`

使用单条数据库原子语句按 `token_digest` 删除并返回记录。先删除，再在 adapter 内
验证 principal、expiry 与 payload；因此：

- 两个独立 Gateway worker 竞争同一 token 时，最多一个得到 plan；
- 错 principal、过期 token、损坏 payload 与未知版本都已被消费并返回 `None`；
- 不存在、过期、已领取、身份不匹配和损坏，对上层统一表现为
  `PLAN_UNAVAILABLE`；
- 失败后绝不恢复 token，避免重放和重复成本。

不得先 SELECT 再 DELETE，不得用进程锁模拟数据库原子性，不得在日志中输出 digest。

### 6.3 `purge_expired()`

执行有界的数据库 DELETE，不启动后台线程。Phase 2C2 在正常签发路径调用清理；部署
阶段可再决定是否增加定时清理，但不能成为 2C1 的新服务。

## 7. 审计门禁

新增稳定执行决定码 `AUDIT_UNAVAILABLE`。审计不是 best-effort 日志，而是访问业务
数据库前的安全门禁：

### 创建 plan

`CreateQueryExecutionPlan` 在第一次真实 `EXPLAIN` 前写入 `phase=plan`、
`status=started`。写入失败立即返回 `AUDIT_UNAVAILABLE`，不得连接业务数据库。
所有正常拒绝、成本拒绝和成功签发都尝试 finish；finish 失败时不得返回可执行 plan：
若 token 已插入，必须消费/删除该 token，再返回 `AUDIT_UNAVAILABLE`。

### 执行 plan

`ExecuteQueryPlan` 仍必须先原子 claim，随后、在 datasource lookup/authorization recheck
和真实 execute 之前写入 `phase=execute`、`status=started`。审计 start 失败时 token
保持已消费并返回 `AUDIT_UNAVAILABLE`，不得访问业务数据库。

执行结束后尝试 finish：

- finish 成功：返回原有稳定决定；
- finish 失败：记录仍停留在 `started`，不得把查询结果返回给调用者，返回
  `AUDIT_UNAVAILABLE`；
- 已经发生的外部查询无法通过分布式事务回滚，因此 `started` 记录就是“执行结果未知”
  的保守证据，不得删除或伪装成成功。

取消必须继续传播 `asyncio.CancelledError`，但在 finally/bounded shield 中尽力把审计
标记为对应稳定失败；清理不能无限阻塞取消。本阶段不引入 outbox、消息队列或分布式
事务。

Phase 2A policy 与 2B1 authorization 的纯计算/目录拒绝由 2C2 的交付编排用例补写
审计；2C1 只保证任何会触碰真实业务数据库的 plan/execute 路径先有审计记录。

## 8. Codec 与数据损坏策略

为 schema、policy、metric dimensions 和 execution plan 编写显式、版本化 codec：

- 固定字段名、固定排序和 UTF-8 紧凑 JSON；
- enum 只接受当前合法 value；
- tuple 在 JSON 中编码为 list，解码后恢复 tuple；
- `Decimal` 使用 canonical 字符串，禁止 float；
- datetime 使用带时区 ISO 8601，解码后统一 UTC；
- 未知字段、缺失字段、重复 relation/column、非有限数字和超限 payload 全部拒绝；
- 解码必须重新构造 domain dataclass，让既有 `__post_init__` 不变量再次执行；
- 错误消息只包含稳定错误类别和记录 ID 的安全替代值，不包含 payload。

禁止 `pickle`、`dataclasses.asdict()` 后不校验直接落库、Pydantic 任意 extras、动态
class import 或“遇到未知类型就 str()”。

## 9. 迁移与启动语义

迁移目录位于 `backend/app/analytics/infrastructure/migrations/`，首个 revision 创建
全部六张表及索引，revision ID 使用独立命名空间，例如
`0001_analytics_control_plane`。

迁移规则：

- 使用独立 `analytics_alembic_version`；
- 不编辑 Harness 历史 revision；
- 只 forward，不在启动时自动重建或重 stamp 未知 revision；
- PostgreSQL 使用与 Harness 不同的固定 advisory lock；
- SQLite 使用 30 秒 busy timeout，并保证同进程并发 bootstrap 串行；
- unknown revision、空版本表但已有 analytics 表、多版本行或迁移失败均拒绝启动；
- 首次空库直接 `upgrade head`，不使用 `create_all + stamp head` 快捷路径；
- 支持应用数据库的自定义 PostgreSQL schema，沿用注入 engine 已设置的 search path；
- downgrade 只用于开发/测试验证，生产回滚仍以应用备份和向前修复为主。

Phase 2C1 只提供 bootstrap 函数和仓库工厂；不修改 Gateway lifespan。2C2 在 Harness
应用数据库初始化成功后调用 Analytics bootstrap，再构造 repositories/use cases；任一
Analytics 迁移失败都必须让 Gateway 启动失败，不能暴露半可用查询 API。

## 10. 一致性与并发规则

- 所有读端口都使用请求传入的精确 principal/owner 条件，不允许 `None` 表示跨用户。
- datasource、schema、policy 写入在事务内校验归属和版本；不得 check-then-write 后
  脱离事务提交。
- 对同一 schema/policy 的并发替换必须产生一个明确成功者或幂等成功，不允许静默
  lost update。
- catalog 返回确定性顺序：datasource 按 `(name, id)`，metric 按 `(key, version)`；
  domain tuple 内部顺序保持 codec 规范化顺序。
- repository 不缓存权限或 schema；后续如需缓存必须另行设计失效协议。
- 不使用数据库外键连接业务数据源；这里只连接 InsightFlow 自己的应用数据库。

## 11. 测试与验收

### 11.1 纯单元测试

- 每个 codec 的 round-trip、unknown version、unknown field、损坏 enum、naive time、
  Decimal 和 1 MiB 上限；
- domain audit value 不变量与 `AUDIT_UNAVAILABLE`；
- boundary tests：domain/application 禁止依赖保持不变，infrastructure 仍不 import
  Gateway/Harness；
- 中文注释/docstring 规则和 guidance registry。

### 11.2 SQLite 仓库与迁移测试

- 从空库升级、重复升级、downgrade/upgrade round-trip；
- host migration filter 不触碰 `analytics_*` 和 `analytics_alembic_version`；
- datasource owner 与 policy principal 隔离；
- schema/policy 同版本漂移拒绝、完全相等幂等；
- metric exact-owner scope；
- plan put、容量、过期清理、错误 principal 消费、损坏 payload 消费；
- 两个独立 repository/session 的并发 claim 只返回一次；
- audit start/finish 和敏感字段缺席。

### 11.3 PostgreSQL 16 集成测试

复用现有 `docker/docker-compose.analytics-test.yml` 的 PostgreSQL 16 服务，在独立临时
schema 中运行，不新增 Compose service：

- Analytics migration head 可重复执行；
- 两个独立 engine/session factory 并发 claim，同一 token 恰好一个成功；
- capacity transaction 在独立连接竞争下不超额；
- schema/policy 并发 replace 无 lost update；
- 审计 start 失败时 fake business gateway 调用次数为零；
- 审计 finish 失败时结果不返回且审计保持 `started`。

普通离线测试不得依赖 Docker。真实 PostgreSQL 只通过显式 integration 命令运行。
Phase 2B2 已通过的 MySQL/PostgreSQL 业务数据源测试无需因本阶段重复全跑；只有执行
用例被审计门禁修改后，才重跑对应 focused regression，并在最终阶段跑一次双库门禁。

## 12. 安全验收清单

- [ ] 原始 plan token 不落库、不进日志、不进审计；
- [ ] audit 不含 SQL、secret ref、凭证、EXPLAIN JSON 或结果值；
- [ ] 持久 plan 只含 canonical SQL 和 opaque `secret_ref`，最长 300 秒并在 claim 时删除；
- [ ] 两个独立连接竞争 token 时最多一个进入执行路径；
- [ ] 错 principal 与过期/损坏 token 同样被消费且统一返回 `PLAN_UNAVAILABLE`；
- [ ] 审计 start 失败时真实业务数据库调用次数为零；
- [ ] 审计 finish 失败不返回查询结果或可执行 token；
- [ ] 缺失 datasource/schema/policy 与 repository 异常全部 fail closed；
- [ ] memory backend 不静默回退为对外可用的内存控制面；
- [ ] Host 与 Analytics 两条 Alembic 链互不管理对方表；
- [ ] 无新增容器、Redis、消息队列、后台清理线程或 Agent/API/UI 范围。

## 13. 文件与体量预算

推荐新增/修改范围：

- 生产 Python：12—18 个聚焦文件；
- migration：1 个 env/配置骨架 + 1 个首版 revision；
- tests：6—9 个聚焦文件；
- docs/plan/prompt：3 个文件；
- 不新增第三方运行时依赖；SQLAlchemy 和 Alembic 已存在。

若实现超过 22 个生产 Python 文件或出现第二个数据库/缓存服务，必须停止并报告，
不得以“企业级”为由扩展框架。`repositories.py` 可以按 catalog、plan、audit 三类职责
拆分，但不得为每张表机械创建 controller/service/factory 四层样板。

## 14. Phase 2C2 接力条件

2C1 复验通过后，2C2 才可以：

- 在 config 中加入经过边界校验的 Analytics 限额默认值；
- 在 Gateway lifespan 中 bootstrap 并装配持久化控制面；
- 增加管理员 datasource/schema/policy/metric 管理用例与 API；
- 增加只接收 raw SQL + datasource ID 的 authenticated plan/execute API；
- 从可信认证上下文绑定 principal，完成 policy/authorization 拒绝审计；
- 提供 query audit 只读 API，并为 Phase 3 Agent Tool 暴露应用用例。

2C2 不得让客户端提交 `principal_id`、`PreparedQuery`、`AuthorizedQuerySpec`、
`ExecutionLimits`、schema/policy version 或任何 credential，也不得绕过本阶段的持久化
plan store 与审计门禁。
