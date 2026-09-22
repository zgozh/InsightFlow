# Phase 2C2 Authenticated Analytics Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 2A–2C1 的安全查询内核通过现有 Gateway 认证交付为管理员控制面、用户 plan/execute 与审计 API。

**Architecture:** `app.analytics` 自己解析 `AppConfig` 的 extra 配置块并构造应用服务；Gateway 只注入共享 engine/session、认证主体并映射 HTTP。所有查询继续经过 policy、semantic authorization、持久化 plan store 和审计门禁，客户端永远不能提交 principal、授权对象或执行限额。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy async、SQLGlot（沿用）、pytest、Ruff。

**Spec:** `docs/architecture/phase-02c2-authenticated-analytics-delivery.md`

## Global Constraints

- 起点必须是规格提交 `d42c69ff068e357488f216ff5010c325575de89b`。
- 固定 tag `upstream-v2.1.0-rc0` 的 commit/tree 不得变化。
- 中文优先；机器字段、API path、错误码与标识符保持英文。
- 不新增依赖、容器、数据库、Redis、队列、后台线程、Agent Tool、MCP 或前端。
- Harness 不得 import `app.*`；domain/application 不得 import FastAPI/SQLAlchemy/Harness。
- 生产 Python 新增/修改不超过 18 个。
- 仅创建一个最终实现提交；TDD 证据写入忽略的 `.reviews/phase-02c2-implementation-report.md`。
- 所有 `uv` 命令使用 `--locked`，必要时设置 `UV_DEFAULT_INDEX=https://pypi.org/simple`。

---

## File Structure

### Create

- `backend/app/analytics/config.py` — App-owned strict config 与 `ExecutionLimits` 构造。
- `backend/app/analytics/application/management.py` — owner-scoped 管理用例。
- `backend/app/analytics/application/delivery.py` — raw SQL plan/execute 交付编排与拒绝审计。
- `backend/app/analytics/composition.py` — 只接收已注入 engine/session/config 的 composition root。
- `backend/app/analytics/api/__init__.py` — API 窄出口。
- `backend/app/analytics/api/models.py` — strict request/response DTO 与脱敏序列化。
- `backend/app/analytics/api/router.py` — `/api/analytics` 路由和稳定错误映射。
- `backend/tests/test_analytics_config.py`
- `backend/tests/test_analytics_management.py`
- `backend/tests/test_analytics_delivery.py`
- `backend/tests/test_analytics_composition.py`
- `backend/tests/test_analytics_api.py`

### Modify

- `backend/app/analytics/domain/audit.py`
- `backend/app/analytics/domain/__init__.py`
- `backend/app/analytics/application/persistence_ports.py`
- `backend/app/analytics/application/__init__.py`
- `backend/app/analytics/infrastructure/persistence/audit_log.py`
- `backend/app/analytics/infrastructure/persistence/__init__.py`
- `backend/app/analytics/infrastructure/__init__.py`
- `backend/app/analytics/AGENTS.md`
- `backend/app/gateway/app.py`
- `backend/app/gateway/AGENTS.md`
- `backend/tests/test_analytics_sql_audit_log.py`
- `backend/tests/test_analytics_boundaries.py`
- `backend/tests/test_config_version.py`
- `config.example.yaml`
- `backend/docs/CONFIGURATION.md`
- `backend/docs/API.md`
- `README.md`
- `docs/PROGRESS.md`
- 本计划与对应 prompt（原样提交）。

不得修改 `backend/pyproject.toml`、`backend/uv.lock`、frontend、Docker、现有 Analytics 迁移或 2A/2B 安全实现。确需其他文件时停止报告。

---

### Task 1: App-owned config 与审计读取契约

**Files:** config、domain audit、persistence ports、相关 `__init__`、config tests、audit domain tests。

**Interfaces:**

- `AnalyticsConfig.from_app_config(config: object) -> AnalyticsConfig`
- `AnalyticsConfig.execution_limits() -> ExecutionLimits`
- `QueryAuditRecord`：审计表安全字段的不可变读模型。
- `QueryAuditLog.list_for_principal(*, principal_id, limit, before_started_at, before_id) -> tuple[QueryAuditRecord, ...]`

- [ ] 写 config RED：默认值、extra forbid、bool-as-int、float cost、交叉行数约束、领域边界复用。
- [ ] 写 audit record RED：aware time、稳定枚举/measurement、不得出现敏感字段。
- [ ] 实现最小 config 与 domain/port；不得让 domain import Pydantic。
- [ ] 运行 Task 1 focused tests 并记录 RED/GREEN。

### Task 2: 审计 keyset 读取与管理用例

**Files:** `audit_log.py`、`management.py`、persistence exports、对应 tests。

**Interfaces:**

- `AnalyticsAdministration` 提供 spec §5.1 的 async 方法；ID issuer 作为可注入 callable。
- 审计按 `(started_at DESC, id DESC)`，游标两个字段必须同时提供或同时省略。

- [ ] 写 audit repository RED：exact principal、确定排序、同时间 ID 次序、limit 1..100、损坏行整体失败。
- [ ] 写 management RED：owner 隔离、服务端 ID、schema/policy 先验证 owned datasource、metric exact owner。
- [ ] 扩展现有 `SqlQueryAuditLog`，不新增第二套 ORM/model。
- [ ] 实现管理用例，只组合已有 repository 端口，不 import HTTP/SQLAlchemy。
- [ ] 验证 owner 不自动获得 query policy。

### Task 3: raw SQL 交付编排

**Files:** `application/delivery.py`、application exports、delivery tests。

**Interfaces:**

- `PlanAnalyticsQuery.execute(*, principal_id: str, datasource_id: str, raw_sql: str)`。
- `ExecuteAnalyticsQuery.execute(*, principal_id: str, plan_id: str)`。
- 返回已有稳定 decision 值或一个窄的 delivery decision；不得返回 raw SQL/authorized object。

- [ ] 写完整事件序列 RED：accessible datasource -> policy -> authorization -> plan。
- [ ] 写 policy/authorization 拒绝审计 RED；start 失败返回 `AUDIT_UNAVAILABLE` 且不进入后续阶段。
- [ ] 写 repository/policy/authorizer 未知异常默认拒绝且异常文本不传播。
- [ ] 实现编排；只将服务器产生的 authorized + 固定 limits 交给 2C1 plan use case。
- [ ] 写 execute 仅转发 principal + token 的测试。
- [ ] 断言 raw SQL 只以 SHA-256 query_hash 进入审计。

### Task 4: Composition 与生命周期

**Files:** `composition.py`、infrastructure exports、Gateway `app.py`、composition tests。

**Interfaces:**

- `AnalyticsServices` frozen/slotted bundle，仅公开 admin/delivery/catalog/audit read 所需服务。
- `build_analytics_services(*, config, engine, session_factory, backend) -> AnalyticsServices | None`。
- Gateway 在共享 engine 初始化后调用；API dependency 从 `app.state.analytics_services` 取值或 503。

- [ ] 写 RED：disabled/memory 返回 None 且不迁移；SQL backend 复用精确 engine/session。
- [ ] 写 RED：enabled SQL 下配置、engine/session、迁移失败阻止启动。
- [ ] 构造 environment secret resolver、MySQL/PostgreSQL runtimes、SQL gateway、durable store 与 use cases。
- [ ] 在 Gateway lifespan 挂载且 shutdown 清引用，不 dispose 共享 engine。
- [ ] 增加 boundary AST 测试：Harness 无 App import；application 无 framework；infrastructure 无 Gateway/Harness/FastAPI。

### Task 5: Strict API DTO 与认证路由

**Files:** `api/*`、API tests、Gateway router 注册。

- [ ] 写 router RED：未认证 401、非管理员 403、PAT 无 admin、services 缺失 503。
- [ ] 写伪造字段 RED：principal/owner/limits/prepared/authorized/version/credential 全部 422。
- [ ] 写 raw SQL 与 plan token 脱敏 RED：验证错误、日志、异常响应不得包含原值。
- [ ] 写用户 datasource response RED：不含 owner/secret_ref；admin response 也绝不含 resolved credential。
- [ ] 写管理 CRUD/replace/retire 的 404/409/422 稳定映射测试。
- [ ] 写 query plan/execute 正常拒绝为 200 + stable code，成功 token 只出现于 plan response。
- [ ] 写 user/admin audit exact-principal 与 keyset tests。
- [ ] 实现 `models.py` 与 `router.py`；router 只能调用 `AnalyticsServices` 应用入口。
- [ ] 在 `create_app()` 注册 router，不新增公共 auth/CSRF 例外。

### Task 6: 配置样例、文档与进度账本

**Files:** config example、config version test、README、backend API/CONFIGURATION、两个 AGENTS、PROGRESS。

- [ ] 将 `config_version` 从 45 提升到 46，并写完整中文 `analytics:` 示例。
- [ ] 文档说明 env secret JSON、管理顺序、plan 两步调用、memory/disabled 503、重启边界。
- [ ] API 文档不得提供客户端 principal/limits 示例；不得粘贴真实 SQL/密码。
- [ ] 更新模块 guides 的 composition、API 和安全不变量。
- [ ] `docs/PROGRESS.md` 记录 2C1 `eda8878 + 0fc32bd` 已验收；Phase 2 仍 `In progress`，next gate 为 `Phase 2C2 GPT 复验`。

### Task 7: 最终门禁与单提交

- [ ] 运行 focused suite：本阶段 5 个新测试、现有 audit/plan/use-case/boundary/auth/config-version/guidance tests。
- [ ] 运行 `ruff check` / `ruff format --check`，范围只覆盖改动的 Analytics/Gateway/tests。
- [ ] 若未改 2B2 database runtime，不运行 Docker；若改动了则停止说明越界，不应继续。
- [ ] 运行 `git diff --check`、敏感字符串/禁止 import AST 检查、changed-file 精确核对。
- [ ] 证明 `pyproject.toml`、`uv.lock`、frontend、docker、固定 tag/tree 零变化。
- [ ] 只创建提交 `feat: deliver authenticated analytics api`。
- [ ] 完成后工作树干净，Phase 3 未启动。

## Acceptance Checklist

- [ ] 客户端只能提交 `{datasource_id, sql}` 或 `{plan_id}`。
- [ ] principal、owner、limits 与 authorization 全部服务端派生。
- [ ] 管理员不因 owner 身份自动获得查询权限。
- [ ] disabled/memory 稳定 503，无内存持久化伪装。
- [ ] policy/auth/plan/execute 审计与业务数据库门禁完整。
- [ ] raw SQL/token/credential 不进入日志、审计或错误。
- [ ] 审计读取 exact-principal 且无跨租户 wildcard。
- [ ] 无新依赖/容器/Agent/UI，生产 Python 文件预算合规。
