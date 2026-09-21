# Phase 2B2 架构：受控数据源执行闭环

状态：架构规格已由用户批准，可以按配套实施计划施工。

基线：Phase 2B1 Fix 01，`780286c803e7549f2ba294dca2501d25fc7ba021`。

## 1. 目标与范围

Phase 2B2 把 Phase 2A/2B1 的“语法安全、语义授权”结果接到真实 PostgreSQL 与 MySQL，但不会把
`PreparedQuery` 或 `AuthorizedQuerySpec` 直接当成数据库执行权限。

本阶段一次交付完整闭环：

1. 重新验证当前授权；
2. 在只读、限时连接中执行 `EXPLAIN`；
3. 检查估算行数、引擎成本与计划体积；
4. 签发短期、单次、服务端保存的 `plan_id`；
5. 原子领取 plan 后再次验证授权；
6. 在新的只读事务中流式执行原 SQL；
7. 限制时间、行数和规范化 JSON 字节数；
8. 返回无驱动对象、无凭证、可稳定序列化的结果；
9. 无论成功、拒绝、超时还是取消，都回滚并释放连接。

本阶段不增加 API、Agent Tool、MCP、前端、ORM 模型、业务数据迁移或 analytics 持久化实现。Phase 2C
负责数据源/策略/plan 的持久化和 HTTP 交付，Phase 3 才把能力暴露给 Agent。

## 2. 不可妥协的安全属性

- 数据库只接收通过 Phase 2A 且通过当前 Phase 2B1 授权的 SQL。
- 创建 plan 前、`EXPLAIN` 后、正式执行前均重新运行完整语义授权，并要求新的
  `AuthorizedQuerySpec` 与原值精确相等。
- HIGH 风险仍然不可执行；Phase 2B2 不引入人工批准捷径。
- plan 是服务器端能力，不是客户端自报声明；plan token 不携带 SQL、权限或凭证。
- plan 绑定 principal、datasource、query hash、schema version、policy version 和执行限制，默认 60 秒过期，
  且只能原子领取一次。
- plan 被领取后，即使数据库暂时失败也不会恢复，避免重放和重复成本。
- 原始 DSN、密码、数据库异常文本、原始 EXPLAIN JSON 和任意驱动对象不得进入 domain、日志、plan receipt
  或查询结果。
- 数据库级只读与超时是第二层防线，不能替代 Phase 2A/2B1。
- 任何无法解释的数据库行为、计划结构、结果类型或 MySQL 标识符模式都默认拒绝。

## 3. 依赖方向

```text
domain
  ├── ExecutionLimits / QueryCostEstimate
  ├── QueryPlanReceipt / QueryExecutionResult
  └── 稳定执行决策码
        ▲
application
  ├── DatasourceQueryGateway port
  ├── ExecutionPlanStore port
  ├── PlanTokenIssuer / Clock ports
  ├── CreateQueryExecutionPlan
  └── ExecuteQueryPlan
        ▲
infrastructure
  ├── SQLAlchemyDatasourceQueryGateway
  │     ├── PostgreSQL + asyncpg
  │     └── MySQL 8.4 + asyncmy
  ├── EnvironmentDatasourceSecretResolver
  ├── InMemoryExecutionPlanStore
  └── SystemClock / SecurePlanTokenIssuer
```

domain 继续只依赖标准库。application 不得导入 SQLAlchemy、asyncpg、asyncmy、FastAPI、Harness 或 Gateway。
所有数据库依赖只能出现在 `app.analytics.infrastructure`。

## 4. 领域契约

以下名称是设计约束；实施时可以为保持单一职责拆成多个小文件，但不能改变语义。

### 4.1 `ExecutionLimits`

不可变且带 slots，字段全部显式传入，不在执行代码中散落默认值：

```python
@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    connect_timeout_ms: int
    statement_timeout_ms: int
    cancellation_grace_ms: int
    max_estimated_rows: int
    max_engine_cost: Decimal
    max_explain_bytes: int
    max_result_columns: int
    max_result_rows: int
    max_result_bytes: int
    plan_ttl_seconds: int
```

约束：

- 所有整数必须是普通正整数，拒绝 `bool`；
- `max_engine_cost` 必须是有限正 `Decimal`；
- `max_result_rows <= PreparedQuery.row_limit <= MAX_QUERY_ROWS`；
- `connect_timeout_ms` 范围为 100—30,000，`statement_timeout_ms` 为 100—60,000，
  `cancellation_grace_ms` 为 50—5,000；
- `max_result_columns` 范围为 1—256，`max_result_bytes` 最大 16 MiB，`max_explain_bytes` 最大 4 MiB；
- `plan_ttl_seconds` 范围为 5—300；Phase 2C 推荐配置为 60 秒，但领域层不提供隐式默认值；
- TTL 只表达能力有效期，不表达数据库 statement timeout；
- 应用装配层在 Phase 2C 提供配置值，本阶段测试全部显式构造。

### 4.2 `QueryCostEstimate`

字段：engine、estimated rows、engine cost、plan digest。不得保存原始计划。

- `engine_cost` 只在同一数据库引擎内比较，PostgreSQL 与 MySQL 的 cost 不具有横向可比性；
- `plan_digest` 是规范化计划 JSON 的 SHA-256，用于审计关联，不是授权输入；
- 缺少必要字段、非有限数值、负值、计划超出字节上限均返回拒绝，而不是填零。

### 4.3 `QueryPlanReceipt`

只返回：`plan_id`、`expires_at`、`estimate`。不返回 SQL、`AuthorizedQuerySpec`、凭证或数据源连接信息。

`plan_id` 是敏感能力令牌：

- 生产实现固定使用 `secrets.token_urlsafe(32)`；测试通过 `PlanTokenIssuer` 注入确定性 token；
- 日志中只能出现其 SHA-256 摘要的短前缀；
- `ExecutionPlanStore` 只保存 token 摘要，不保存原 token。

### 4.4 `QueryExecutionResult`

```text
columns: tuple[str, ...]
rows: tuple[tuple[JsonScalar, ...], ...]
row_count: int
byte_count: int
truncated: bool
```

使用列数组与行数组，而不是按列名构造 dict；SQL 结果允许重复列名，dict 会静默覆盖数据。

允许的 `JsonScalar`：`None`、`bool`、`int`、有限 `float`、`str`。数据库返回的 Decimal、日期时间和 UUID
必须先按第 11 节规范化为字符串。不得把驱动值原样穿透。

### 4.5 稳定决策码

至少覆盖：

- `PLAN_CREATED`；
- `PLAN_UNAVAILABLE`：不存在、过期、已领取、principal 不匹配统一使用此码，防止枚举；
- `AUTHORIZATION_STALE`；
- `DATASOURCE_UNAVAILABLE`；
- `SECRET_UNAVAILABLE`；
- `EXPLAIN_REJECTED`；
- `COST_LIMIT_EXCEEDED`；
- `UNSUPPORTED_IDENTIFIER_MODE`；
- `EXECUTION_TIMEOUT`；
- `RESULT_LIMIT_REACHED`；
- `UNSUPPORTED_RESULT_TYPE`；
- `DATABASE_UNAVAILABLE`；
- `EXECUTED`。

面向调用方的决定不得携带原始异常文本。内部异常可用 `raise ... from error` 保留调试链，但日志过滤必须经过
脱敏边界。

## 5. 应用端口

### 5.1 `DatasourceQueryGateway`

```python
class DatasourceQueryGateway(Protocol):
    async def explain(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryCostEstimate: ...

    async def execute(
        self,
        *,
        datasource: DatasourceDefinition,
        authorized: AuthorizedQuerySpec,
        limits: ExecutionLimits,
    ) -> QueryExecutionResult: ...
```

凭证解析完全封装在 gateway 的 infrastructure 实现中。application 只看 `secret_ref`，不会接触密码或 DSN。

### 5.2 `ExecutionPlanStore`

store 保存内部 `StoredExecutionPlan`：token digest、principal、不可变 datasource 快照、授权值、成本、limits、
签发/过期时间。

端口必须支持：

- `put()`：拒绝摘要冲突和容量溢出；
- `claim()`：在同一临界区内验证摘要、principal、过期时间并删除；
- `purge_expired()`：容量判断前清理过期项。

`claim()` 对不存在、过期、已领取和 principal 不匹配返回同一不可用结果。不得先 `get` 再 `delete`。

### 5.3 时间与 token

`Clock` 和 `PlanTokenIssuer` 是小端口，便于确定性测试 TTL、竞争与摘要；生产实现分别使用 timezone-aware UTC
和 `secrets`。禁止通过 monkeypatch 全局时间测试 plan 生命周期。

## 6. 创建执行 plan

`CreateQueryExecutionPlan.execute(principal_id, datasource_id, authorized, limits)`：

1. 验证输入 principal/datasource 与 `authorized` 一致，limits 与 prepared row limit 一致；
2. 通过 `DatasourceCatalog.get_accessible()` 获取 ACTIVE 数据源；
3. 调用现有 `AuthorizePreparedQuery.execute()`，对同一 `PreparedQuery` 进行完整当前授权；
4. 只接受 allowed 且新的 `AuthorizedQuerySpec == authorized`；否则返回 `AUTHORIZATION_STALE`；
5. 调用 gateway `explain()`；
6. 拒绝超出 estimated rows、engine cost 或 explain bytes 的计划；
7. EXPLAIN 完成后再次执行步骤 2—4，并要求 `DatasourceDefinition` 也与 EXPLAIN 前精确相等；
8. 生成随机 token，只把 SHA-256 摘要与内部 plan 写入 store；
9. 返回 `QueryPlanReceipt`。

任何 catalog、secret、数据库、解析或存储失败都不得降级为 plan。EXPLAIN 与第二次授权之间发生的变化必须使签发
失败。

## 7. 执行 plan

`ExecuteQueryPlan.execute(principal_id, plan_id)`：

1. 对 plan token 计算摘要，通过 store 原子 `claim()`；
2. 不可用统一返回 `PLAN_UNAVAILABLE`；
3. 重新加载 ACTIVE 数据源，要求当前定义与 plan 内 datasource 快照精确一致；
4. 再次调用 `AuthorizePreparedQuery`，要求当前授权值与 plan 内授权值精确一致；
5. 调用 gateway `execute()`；
6. 返回稳定执行决定和 `QueryExecutionResult`。

claim 必须发生在所有外部 I/O 之前。这样同一 token 的并发请求只有一个能进入数据库；后续授权或数据库失败不会
恢复 token。

## 8. 凭证边界

V1 提供 `EnvironmentDatasourceSecretResolver`，只接受 `env://VARIABLE_NAME`：

- 环境变量名必须匹配严格的大写标识符规则；
- 环境变量内容为受限 JSON：engine、host、port、database、username、password、`tls_mode`，以及可选
  `ca_pem`；
- JSON 不允许额外字段、空白标识、引擎不一致或 URL/DSN 字符串；
- `tls_mode` 只接受 `disable` 或 `verify_full`：`disable` 只允许 loopback 主机；`verify_full` 使用系统信任根，
  可叠加内存中的 `ca_pem`，必须校验证书链和主机名；不接受任意 CA 文件路径；
- 使用 SQLAlchemy `URL.create()` 构造连接信息，禁止字符串拼接；
- credential 类型放在 infrastructure 私有模块，并使用隐藏 repr；
- 错误和日志只能包含 datasource id 与稳定错误码，不能包含 secret ref 的值、环境变量内容、用户名或地址。

本阶段不支持任意文件路径、Vault、云 Secret Manager 或 API 提交明文密码。后续 resolver 通过同一内部接口扩展。

## 9. 连接策略

- 使用 SQLAlchemy Async Core，不使用 ORM、Session 或模型映射；
- 每次 EXPLAIN/execute 创建短生命周期 `AsyncEngine`，配置 `NullPool`、`echo=False`，完成后始终
  `await engine.dispose()`；
- 不跨数据源或调用复用连接，避免租户凭证、默认 schema、timeout 和 session 变量串线；
- SQL 文本只能来自 `authorized.prepared.sql`，不得接受额外片段、排序字段或用户拼接参数；
- Phase 2A 尚未支持绑定参数，因此 gateway 不接受 params；
- 建连受 `connect_timeout_ms` 限制；SQL 的 Python 总时限固定为
  `statement_timeout_ms + cancellation_grace_ms`，rollback/close 最多使用 `cancellation_grace_ms`，不能无限等待；
- 超时或取消后显式 invalidate/close 连接，状态未知的连接不得复用。

## 10. EXPLAIN 与执行的数据库差异

### 10.1 PostgreSQL 16

EXPLAIN：

- 开启事务；
- `SET TRANSACTION READ ONLY`；
- `SET LOCAL statement_timeout = <整数毫秒>`；
- 执行 `EXPLAIN (FORMAT JSON) <approved SQL>`，明确禁止 `ANALYZE`；
- 解析顶层 `Plan -> Total Cost` 与 `Plan Rows`；
- 规范化 JSON、检查字节数并计算摘要；
- rollback。

执行：同样先建立只读事务并设置本地 timeout，再通过 SQLAlchemy 异步流式结果读取。无论成功或失败都
rollback。

PostgreSQL 官方说明只读事务会禁止主要写命令，但它不是“绝不写磁盘”的底层沙箱，因此仍必须保留 SQL AST
allowlist 和数据库最小权限账号。

### 10.2 MySQL 8.4

连接后首先读取 `@@lower_case_table_names`：

- 只支持值 `0`；
- 值 `1`、`2` 或无法读取时返回 `UNSUPPORTED_IDENTIFIER_MODE`；
- 本阶段不扩展 `SchemaSnapshot`，也不猜测 Windows/macOS 文件系统语义。

EXPLAIN：

- 设置当前连接的 `MAX_EXECUTION_TIME`（对下面这条 EXPLAIN 缓冲读取生效；流式执行路径的语义见 §10.3）；
- `START TRANSACTION READ ONLY`；
- 执行 `EXPLAIN FORMAT=JSON <approved SQL>`，禁止 `EXPLAIN ANALYZE`；
- 兼容并明确测试 MySQL 8.4 默认 JSON v1；
- 从顶层 `query_block.cost_info.query_cost` 读取 cost；递归收集访问节点的
  `rows_examined_per_scan` / `rows_produced_per_join` 并求和作为保守工作行数，任一出现的值必须是有限非负数；
- 任一必需成本字段缺失或非有限时拒绝；
- rollback 并关闭连接，因此无需恢复 session 变量。

执行使用同样的 session timeout 与只读事务。MySQL 只读事务仍允许临时表变更，但 Phase 2A 只允许单条 SELECT，
并禁止赋值和危险语法，因此不能依靠该例外构造写入。

### 10.3 超时语义（按方言分别成立）

客户端 SQL 总时限固定为 `statement_timeout_ms + cancellation_grace_ms`，后者为服务器返回取消结果和清理留下
明确余量。测试必须证明超时返回后查询没有继续占用活动连接。**但"由服务端终止查询"这一点只在 PostgreSQL 上成立**，
因此不得笼统表述为"双层超时都由服务端负责"：

- **PostgreSQL 16**：只读事务内的本地 `statement_timeout` 由服务端执行并中止查询；`asyncio.timeout()` 只是
  客户端总时限。超时或取消后销毁连接，绝不复用。
- **MySQL 8.4 + asyncmy 0.2.15**：连接仍然设置 `MAX_EXECUTION_TIME`，缓冲 `exec_driver_sql` 读取会得到 MySQL
  errno 3024，因而可以证明服务端限制确实已武装——`EXPLAIN` 走的正是这条缓冲路径，继续受服务端限制保护。
  **实测 MySQL 8.4.11 与 8.0.46 表现一致：`MAX_EXECUTION_TIME` 不会抢占 `connection.stream()` 打开的服务端
  游标。** 该流式路径的实际终止边界是 Gateway 外层的
  `asyncio.timeout(statement_timeout_ms + cancellation_grace_ms)`，随后必须使连接失效并销毁。真实数据库验收
  已证明客户端超时返回后 `information_schema.processlist` 中残留活动查询为零。

服务端 `MAX_EXECUTION_TIME` 在流式路径上保留为纵深防御。**不得把尚未发生的服务端抢占写成保证，也不得把
MySQL 的这一差异泛化成"取消所有服务端超时"。** 客户端总时限、连接失效、事务回滚与残留查询检查都不得削弱。
V1 不引入独立连接上的 `KILL QUERY` 看门狗；若未来需要由服务端强制终止流式查询，那是一个需要另行批准的新设计。

## 11. 结果规范化和配额

逐行处理，禁止先 `fetchall()`：

1. 从 result metadata 取得列名，保留顺序和重复名称；超过 `max_result_columns` 时在读取首行前拒绝；
2. 每个 cell 只接受下列转换：
   - `None` / `bool` / `int`：原值；
   - 有限 `float`：原值，NaN/Infinity 拒绝；
   - `str`：原值；
   - `Decimal`：规范十进制字符串，不转 float；
   - `date` / `time` / `datetime`：ISO 8601 字符串；无时区 datetime 必须按数据库值原样标识，不擅自假设 UTC；
   - `UUID`：标准字符串；
   - bytes、memoryview、驱动私有类型及其他对象：`UNSUPPORTED_RESULT_TYPE`。
3. 用固定 JSON 规则（UTF-8、`ensure_ascii=False`、紧凑分隔符）计算列头和完整行的字节数；
4. 下一完整行会超过行数或字节上限时停止，不返回半行或半个 cell，设置 `truncated=True`；
5. 若第一行本身超限，返回零行且 `truncated=True`；
6. 绝不调用未知值的 `repr()`、`str()` 或自定义序列化钩子。

`PreparedQuery.row_limit` 是 SQL 层上限，`max_result_rows` 是传输层独立上限，两者都必须执行。

## 12. 进程内 plan store 的明确边界

`InMemoryExecutionPlanStore`：

- 使用 `asyncio.Lock` 保护 put/claim/purge；
- 有显式 `max_entries`，先清理过期项，仍满则拒绝签发；
- 不启动后台清理线程；
- 不保证进程重启后保留，也不支持多 worker 共享。

这不是最终生产持久化方案。本阶段尚未暴露 API，因此该限制可接受；Phase 2C 在对外开放 plan 前必须提供基于应用
持久化数据库的原子 claim 实现，并运行多 worker 竞争测试。端口和领域契约不得依赖 dict 或 asyncio.Lock。

## 13. 依赖与锁文件

当前 SQLAlchemy 2.0.49 与 asyncpg 0.31.0 只通过上游依赖进入 lock。Phase 2B2 的 app 会直接 import 它们，必须在
`backend/pyproject.toml` 声明直接依赖：

- `sqlalchemy[asyncio]>=2.0.49,<2.1`；
- `asyncpg>=0.31,<0.32`；
- `asyncmy>=0.2.14,<0.3`。

`asyncmy` 0.2.14 提供 CPython 3.12 Windows 与 Linux wheel；SQLAlchemy 2.0 官方包含 asyncmy asyncio dialect。

只允许为新增直接依赖更新 `backend/uv.lock`。实施报告必须比较修改前后的顶层坐标，证明没有无关升级或降级；所有
后续 uv 命令继续使用 `--locked`。

## 14. Docker 集成环境

新增专用测试 compose，不并入默认生产栈：

- PostgreSQL 16；
- MySQL 8.4；
- 仅绑定 `127.0.0.1`；
- 固定测试数据库、非管理员测试用户和只读业务用户；
- 健康检查；
- 临时 volume 或 tmpfs，不复用开发数据；
- 不写入真实 secret 文件。

集成测试只在显式命令或 pytest integration marker 下运行。脚本负责启动、等待健康、注入测试用 env secret、运行测试、
输出失败日志并关闭栈；不得把 Docker 可用性变成普通单元测试的前提。

## 15. 测试与验收矩阵

### 15.1 纯单元测试

- `ExecutionLimits` 的类型、范围、不变量；
- cost、receipt、result 的冻结性和序列化约束；
- 创建 plan 前后的两次授权精确相等；
- datasource、schema、policy、query hash 或 limits 漂移均不签发；
- token 熵接口、只存摘要、TTL 边界；
- 不存在/过期/重放/越权统一 `PLAN_UNAVAILABLE`；
- 100 个并发 claim 恰好一个成功；
- store 容量与惰性过期清理；
- claim 后授权失败或 DB 失败也不能重放；
- 计划成本缺失、NaN、Infinity、负数和超限默认拒绝；
- 结果中重复列名、Decimal、日期、UUID、Unicode 的确定性规范化；
- bytes、未知对象、非有限 float 拒绝且不触发其 `__repr__` / `__str__`；
- 第一行超字节上限、正好等于上限、下一行越界的完整行行为；
- 所有异常决定无 DSN、密码、SQL 或驱动消息。

### 15.2 PostgreSQL 真实集成

- JSON EXPLAIN 的 cost/rows 解析与计划摘要；
- 只读事务正常 SELECT；
- 绕过上层、直接向 adapter 注入写 SQL 时由数据库只读事务拒绝；
- `statement_timeout` 和 Python timeout；
- 取消后无持续活跃查询；
- 流式行数/字节截断；
- 每条路径最终 rollback；
- 凭证错误只返回稳定码。

### 15.3 MySQL 真实集成

- `@@lower_case_table_names = 0` 门禁；
- JSON v1 EXPLAIN 的 cost/rows 解析；
- `START TRANSACTION READ ONLY` 正常 SELECT；
- 绕过上层直接写入时由数据库拒绝；
- `MAX_EXECUTION_TIME` 已在缓冲路径上被证明武装（errno 3024），且流式路径按 §10.3 的客户端超时语义终止；
- 取消后连接销毁且无持续查询；
- 流式行数/字节截断；
- 大小写错误对象不执行。

### 15.4 回归与边界

- Phase 2A 与 2B1 全部测试继续通过；
- SQLGlot 仍只出现在 infrastructure；
- SQLAlchemy/asyncpg/asyncmy 不得进入 domain/application；
- `PreparedQuery` / `AuthorizedQuerySpec` 仍无 plan_id/execute；
- plan receipt 无 SQL/secret；
- Harness/Gateway/frontend 不被修改；
- 固定 upstream tag/tree 不变。

## 16. 体量预算

Phase 2B2 允许：

- 不超过约 15 个 production 文件；
- 不超过约 10 个单元/集成测试文件；
- 一个专用 compose 文件和一个测试编排脚本；
- 一份架构、一份计划、一份提示词和一份本地评审报告。

禁止为了“通用数据库平台”增加插件注册中心、ORM 仓储、查询缓存、Redis、消息队列、审批 UI、审计平台或任意 SQL
方言。只支持 PostgreSQL 16 与 MySQL 8.4 的已验证能力。

## 17. Phase 2C 接力条件

Phase 2B2 通过后，2C 才可以：

- 持久化 DatasourceDefinition、SchemaSnapshot、PrincipalAccessPolicy；
- 用应用数据库实现多 worker 原子 PlanStore；
- 添加 API DTO、身份绑定、稳定错误映射；
- 增加配置项和管理员数据源管理；
- 把 plan/execute 暴露给 Phase 3 Agent Tool。

2C 不得放宽 Phase 2A/2B1/2B2 的任何默认拒绝规则。

## 18. 官方依据

- PostgreSQL `SET TRANSACTION READ ONLY`：<https://www.postgresql.org/docs/current/sql-set-transaction.html>
- PostgreSQL `statement_timeout`：<https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-STATEMENT-TIMEOUT>
- PostgreSQL `EXPLAIN`：<https://www.postgresql.org/docs/current/sql-explain.html>
- MySQL 8.4 transactions：<https://dev.mysql.com/doc/refman/8.4/en/commit.html>
- MySQL 8.4 EXPLAIN：<https://dev.mysql.com/doc/refman/8.4/en/explain.html>
- MySQL optimizer execution timeout：<https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html#optimizer-hints-execution-time>
- SQLAlchemy asyncio：<https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>
- SQLAlchemy asyncmy dialect：<https://docs.sqlalchemy.org/en/20/dialects/mysql.html#asyncmy>
- asyncmy 0.2.14：<https://pypi.org/project/asyncmy/0.2.14/>
