# Phase 2C2 架构：认证 Analytics 交付与 Gateway 装配

状态：已批准，等待实施。

## 1. 目标与边界

Phase 2C2 把 2A–2C1 的安全查询内核装配进现有 Gateway，形成可通过 HTTP 使用的闭环：

```text
认证主体
  -> 管理员配置 datasource / schema / policy / metric
  -> 用户提交 datasource_id + raw SQL
  -> policy -> authorization -> EXPLAIN -> durable plan
  -> 用户提交一次性 plan_id
  -> 原子 claim -> 再授权 -> 受控执行 -> 脱敏结果
  -> principal-scoped audit 查询
```

本阶段不增加 Agent Tool、MCP、前端、自动 Schema 探测、SQL 自动生成、指标表达式展开、
定时任务、Redis、队列、新数据库或新容器。Phase 3 才向 Agent 暴露应用用例，Phase 4 才建设 UI。

## 2. 方案选择

采用“App 自有配置解析 + App 自有 composition root + 窄 FastAPI router”：

- 复用 Gateway 已初始化的应用 `AsyncEngine` 与 `async_sessionmaker`，不建第二个控制面数据库。
- `analytics:` 是 `AppConfig(extra="allow")` 的 App 扩展块，由 `app.analytics` 严格校验；
  Harness 不得 import `app.analytics`，也不新增业务域配置类型。
- Gateway 只负责认证、管理员门禁、生命周期挂载和 HTTP 映射；业务编排留在 application。
- 路由始终注册；disabled 或 `database.backend=memory` 时稳定返回 503，不提供内存降级。

拒绝把 Analytics 类型塞进 Harness、在 router 内直连数据库，以及让客户端提交
`PreparedQuery` / `AuthorizedQuerySpec` 的方案。

## 3. 配置契约

`config.example.yaml` 增加顶层 `analytics:`，App 侧模型使用 `extra="forbid"`，启动时冻结，修改需重启：

```yaml
analytics:
  enabled: true
  query_max_rows: 1000
  connect_timeout_ms: 3000
  statement_timeout_ms: 5000
  cancellation_grace_ms: 500
  max_estimated_rows: 100000
  max_engine_cost: "100000"
  max_explain_bytes: 1048576
  max_result_columns: 128
  max_result_rows: 1000
  max_result_bytes: 1048576
  plan_ttl_seconds: 60
  audit_page_size: 50
```

- `query_max_rows` 与 `max_result_rows` 不得超过 10,000，后者不得高于前者。
- timeout、bytes、columns、TTL、成本直接构造成 `ExecutionLimits`，不能复制边界逻辑。
- `max_engine_cost` 从十进制字符串解析为 `Decimal`，禁止 float。
- API 不接受任何限额覆盖。
- disabled/memory 时不运行 Analytics 迁移，所有 Analytics API 稳定 503。

## 4. 生命周期与依赖

在 `langgraph_runtime` 完成应用数据库初始化后、Gateway ready 前：

1. 解析 Analytics 配置；
2. disabled/memory 时令 `app.state.analytics_services = None` 并继续启动；
3. SQL backend 从 Harness 获取现有 engine/session factory，并作为参数传给 App composition；
4. 执行 `bootstrap_analytics_schema`；
5. 构造 repositories、policy、authorizer、database gateway、durable plan store、audit 与应用服务；
6. 原子设置 `app.state.analytics_services`。

enabled 且使用 SQL backend 时，配置错误、engine/session 缺失或迁移失败必须阻止启动。
shutdown 只清理 state 引用，共享 engine 仍由 Harness 释放。

```text
app.gateway -> app.analytics.api / composition
composition -> application + infrastructure
api -> application/domain
infrastructure -> application/domain
deerflow.* -X-> app.analytics
```

## 5. 应用服务

### 5.1 `AnalyticsAdministration`

只接受服务端给出的 `owner_id`：

- list/get/create/update datasource；ID 由服务端生成；不物理删除，以 `disabled` 停用；
- get/replace schema snapshot，replace 必须带 `expected_version`；
- get/replace/remove exact-principal policy，replace 必须带 `expected_version`；
- list/get/save/retire owner-scoped metric，版本只能前进。

schema/policy 操作必须先确认 datasource 属于当前管理员。管理员身份只提供管理权，不自动获得查询权。

### 5.2 `PlanAnalyticsQuery`

唯一 raw SQL 入口只接收认证 `principal_id`、客户端 `datasource_id` 和短生命周期 `raw_sql`：

1. exact principal 获取可访问 datasource；
2. 以 datasource engine 和服务端 `query_max_rows` 运行 Phase 2A；
3. policy 拒绝时写 `policy` start/completion 审计并返回稳定码；
4. policy 通过后运行 Phase 2B1；
5. authorization 拒绝时写 `authorization` start/completion 审计并返回稳定码；
6. 只把服务端产生的 `AuthorizedQuerySpec` 与固定 `ExecutionLimits` 交给
   `CreateQueryExecutionPlan`；后者继续承担 plan 审计与业务库 I/O 门禁。

raw SQL 不得进入日志、异常、审计或响应；只有 Phase 2A 产生的 SHA-256 `query_hash` 可进审计。
审计 start 失败统一 `AUDIT_UNAVAILABLE`，不能继续后续业务数据库步骤。

### 5.3 `ExecuteAnalyticsQuery`

HTTP/Agent 共用的薄入口，只接受认证 `principal_id` 与一次性 `plan_id`，调用 `ExecuteQueryPlan`。
不得接受 datasource、SQL、limits、schema/policy version 或 credential。

### 5.4 审计读取

新增不可变 `QueryAuditRecord` 与只读端口，按 `(started_at DESC, id DESC)` keyset 分页：

- 普通用户只能读当前 principal；
- 管理员必须给出非空、精确 `principal_id`，禁止 `None`/`*` 表示全租户；
- 默认 50、最大 100，游标为 `before_started_at + before_id`；
- 只返回审计表已有安全元数据，不增加 SQL、token/digest、secret、异常、EXPLAIN 原文或结果值。

## 6. HTTP 契约

统一前缀 `/api/analytics`。

用户接口：

| Method | Path | 作用 |
| --- | --- | --- |
| GET | `/datasources` | 当前 principal 可访问数据源，不含 `secret_ref`/owner |
| GET | `/metrics` | 当前 principal 自有指标 |
| POST | `/query-plans` | `{datasource_id, sql}`，返回稳定决定及成功时的一次性 plan |
| POST | `/query-executions` | `{plan_id}`，返回稳定决定与有界结果 |
| GET | `/audits` | 当前 principal 的审计分页 |

管理员接口：

| Method | Path | 作用 |
| --- | --- | --- |
| GET/POST | `/admin/datasources` | 列表、创建 owned datasource |
| GET/PUT | `/admin/datasources/{id}` | 读取、更新 owned datasource |
| GET/PUT | `/admin/datasources/{id}/schema` | 读取/replace snapshot |
| GET/PUT/DELETE | `/admin/datasources/{id}/policies/{principal_id}` | exact-principal policy |
| GET/POST | `/admin/metrics` | owner-scoped 指标列表、创建 |
| GET/PUT/DELETE | `/admin/metrics/{key}` | 读取、升级、retire |
| GET | `/admin/audits` | 必填精确 `principal_id` 的审计分页 |

所有接口使用现有 Gateway 认证。管理员接口必须在使用业务 body 前执行 `require_admin_user`；PAT
沿用现有规则，不获得管理员能力。

客户端模型 `extra="forbid"`，不得提交 `principal_id`、`owner_id`、prepared/authorized、limits、
server version 或 credential。raw SQL 与 plan token 使用隐藏表示，验证错误不得回显原值。

HTTP 映射：401/403 沿用认证；disabled/memory/未装配为 503；不存在与 owner 不匹配统一 404；
版本冲突为 409；脱敏输入错误为 422；正常 policy/authorization/plan/execute 拒绝为 200 + 稳定
`code`；未知 repository/driver 异常不得泄漏文本。

## 7. 安全不变量

1. principal/owner 只来自认证上下文，客户端同名字段必须拒绝。
2. 普通用户响应不含 `secret_ref`，任何响应不含解析后的 credential。
3. raw SQL 不写日志、审计、错误、receipt 或结果。
4. plan token 只在创建成功时返回一次，执行沿用持久化原子 claim。
5. HTTP 层不能直接调用 database gateway，必须走应用用例。
6. owner 不等于查询权限；管理员查询也必须有 exact policy。
7. HIGH 仍是 `APPROVAL_REQUIRED`，不增加人工批准 API。
8. memory backend 不得使用 `InMemoryExecutionPlanStore` 对外服务。
9. 不记录 token/digest、SQL、secret_ref、DSN、账号密码、结果单元格或原始 EXPLAIN。
10. 不增加跨租户列表；管理员审计也必须指定 exact principal。

## 8. 测试与验收

- 配置默认值、unknown field、Decimal、交叉限额与 disabled/memory；
- composition 复用共享 engine/session，迁移失败阻止启动；
- admin 门禁早于 repository，owner 越权统一 404；
- 客户端伪造 principal/owner/limits/prepared/authorized/version 被 422；
- 用户 datasource 响应不含 `secret_ref`；
- policy/authorization 拒绝审计，audit start 失败不进入后续步骤；
- plan/execute API 只调应用服务，一次性 token 与稳定映射成立；
- raw SQL/token 不进入日志、错误、审计和非授权响应；
- audit keyset 分页稳定、exact-principal、最大 100，损坏行 fail closed；
- SQLite 通过 Gateway lifespan 完成迁移与管理→plan→execute（业务 gateway 可替身）；
- Harness/Analytics boundary、guidance registry、Ruff 继续通过。

既有 PostgreSQL/MySQL runtime 已由 2B2/2C1 实测；若本阶段触及其生产路径，才重跑一次
`scripts/test_analytics_databases.py --engine all`，否则不重复拉起 Docker。

## 9. 体量预算

集中使用 `config.py`、`composition.py`、application 的 delivery/management、现有 audit persistence、
`api/{models,router}.py` 与 Gateway 精准挂载。新增/修改生产 Python 文件硬上限 18 个；不为每个
endpoint 建 controller/service/factory。需要新依赖、容器或超过预算时停止报告。

## 10. Phase 3 接力

2C2 通过后，Phase 3 才创建 Analytics Agent Tool。Agent 必须复用 `PlanAnalyticsQuery`、
`ExecuteAnalyticsQuery` 与目录用例，不能重写 policy、读取 credential、直连数据库或绕过审计。
