# Phase 2B2 受控数据源执行闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 2B1 的非执行授权值接入真实 PostgreSQL 16/MySQL 8.4，形成带 EXPLAIN 成本门禁、短期单次 plan、只读事务、超时与结果配额的执行闭环。

**Architecture:** domain 定义不可变执行值，application 编排三次授权复验和单次 plan 状态机，infrastructure 独占凭证、SQLAlchemy Async Core、数据库方言和结果规范化。真实数据库行为由隔离 Docker 栈证明；API、Agent 与持久化仍留给后续阶段。

**Tech Stack:** Python 3.12、SQLAlchemy Async Core 2.0、asyncpg 0.31、asyncmy 0.2、PostgreSQL 16、MySQL 8.4、pytest、Docker Compose、Ruff、uv。

**Spec:** `docs/architecture/phase-02b2-governed-datasource-execution.md`

## Global Constraints

- 起点为 `07e5d952d4c14173941336ce70d2ca3d4af4741e`；除架构状态行、本文和配套 prompt 外工作树必须干净。
- 固定 tag `upstream-v2.1.0-rc0` 继续指向 commit `609bfde0ced76ff0a58c02ff5c741df768f44502`、tree `2473c22e163a3879490848a7995eb2b7be7f6f50`。
- 使用一个最终提交：`feat: add governed datasource execution`。各任务保留 RED/GREEN 证据，不创建中间提交。
- 新增或修改的注释、docstring、架构说明与复杂测试说明使用中文；标识符、协议字段和稳定错误码保持英文。
- domain 仅依赖标准库；application 不得导入 SQLAlchemy、asyncpg、asyncmy、FastAPI、Gateway 或 Harness。
- SQLAlchemy、asyncpg、asyncmy 只能从 `app.analytics.infrastructure` 导入。
- HIGH 风险不可执行；任何 catalog、凭证、EXPLAIN、授权或数据库异常均默认拒绝。
- 不增加 API、Agent Tool、MCP、前端、ORM、业务 migration、Redis、消息队列或审批流程。
- 所有正常 uv 命令使用官方索引和 `--locked`；只有受控加依赖步骤允许先更新 lock。
- Docker 集成栈只绑定 `127.0.0.1`，不使用开发/生产数据，不并入默认 compose。

## File map

Create production:

- `backend/app/analytics/domain/execution.py` — limits、cost、receipt、result、稳定决定。
- `backend/app/analytics/application/execution_ports.py` — gateway/store/clock/token 端口和内部 plan 值。
- `backend/app/analytics/application/execution.py` — create/execute 两个 use case。
- `backend/app/analytics/infrastructure/execution_plan_store.py` — 有容量的异步单次内存 store。
- `backend/app/analytics/infrastructure/datasource_secrets.py` — `env://` resolver、私有 credential、TLS context。
- `backend/app/analytics/infrastructure/result_normalizer.py` — 严格 cell/row JSON 规范化与配额。
- `backend/app/analytics/infrastructure/database_runtime.py` — SQLAlchemy gateway、共享连接清理和方言分派。
- `backend/app/analytics/infrastructure/postgresql_runtime.py` — PostgreSQL EXPLAIN/execute。
- `backend/app/analytics/infrastructure/mysql_runtime.py` — MySQL EXPLAIN/execute与大小写模式门禁。

Create tests/support:

- `backend/tests/test_query_execution_domain.py`
- `backend/tests/test_query_execution_use_cases.py`
- `backend/tests/test_execution_plan_store.py`
- `backend/tests/test_datasource_secrets.py`
- `backend/tests/test_result_normalizer.py`
- `backend/tests/test_database_runtime.py`
- `backend/tests/test_analytics_postgresql_integration.py`
- `backend/tests/test_analytics_mysql_integration.py`
- `docker/docker-compose.analytics-test.yml`
- `scripts/test_analytics_databases.py`

Modify:

- `backend/pyproject.toml`、`backend/uv.lock`
- analytics 三层 `__init__.py`
- `backend/app/analytics/AGENTS.md`
- `backend/tests/test_analytics_boundaries.py`
- 必要时 `backend/tests/test_compose_default_bind_host.py`
- `docs/PROGRESS.md`
- 已批准 architecture、本文和 prompt。

---

### Task 1: 执行领域契约

**Files:** `domain/execution.py`、domain exports、`test_query_execution_domain.py`。

**Produces:** `ExecutionLimits`、`QueryCostEstimate`、`QueryPlanReceipt`、`QueryExecutionResult`、plan/execution decision codes and values。

- [ ] 先写 RED，覆盖 frozen/slotted、普通 int（拒绝 bool）、Decimal 有限正值、timeout/TTL/列数/字节数硬边界、tuple-only rows、row width 等于 columns、无 SQL/secret 字段。

代表性断言：

```python
def test_execution_limits_reject_boolean_integer():
    with pytest.raises(ValueError):
        _limits(statement_timeout_ms=True)


def test_plan_receipt_has_no_sql_or_secret():
    names = {field.name for field in fields(QueryPlanReceipt)}
    assert names == {"plan_id", "expires_at", "estimate"}


def test_result_preserves_duplicate_columns():
    result = QueryExecutionResult(
        columns=("id", "id"), rows=((1, 2),),
        row_count=1, byte_count=17, truncated=False,
    )
    assert result.columns == ("id", "id")
```

- [ ] 运行 RED：

```powershell
uv run --locked pytest tests/test_query_execution_domain.py -q
```

- [ ] 按 spec §4 实现最小标准库契约并导出；错误码不得携带自由文本。

- [ ] 运行 GREEN 与边界检查：

```powershell
uv run --locked pytest tests/test_query_execution_domain.py tests/test_query_authorization_domain.py -q
uv run --locked ruff check app/analytics/domain tests/test_query_execution_domain.py
```

---

### Task 2: 应用端口与三次授权编排

**Files:** `application/execution_ports.py`、`application/execution.py`、application exports、`test_query_execution_use_cases.py`。

**Consumes:** `DatasourceCatalog`、`AuthorizePreparedQuery`、Task 1 values。

**Produces:** `DatasourceQueryGateway`、`ExecutionPlanStore`、`Clock`、`PlanTokenIssuer`、`CreateQueryExecutionPlan`、`ExecuteQueryPlan`。

- [ ] 用 fakes 写 RED，逐项固定：输入身份一致、EXPLAIN 前授权、EXPLAIN 后授权、执行前授权、datasource 精确相等、cost 门禁、claim 必须先于外部 I/O、失败后不恢复 plan。

核心 fake 记录调用顺序，至少断言：

```python
assert events == [
    "datasource:first", "authorize:first", "explain",
    "datasource:second", "authorize:second", "store:put",
]
```

并发或过期不可在 use case 中自行 `get/delete`；只能调用 store 的原子 `claim()`。

- [ ] 运行 RED，实现 spec §5—7 的 exact signatures 和稳定决策；当前授权必须与原
  `AuthorizedQuerySpec` 使用 dataclass 精确相等，禁止只比较 version。

- [ ] GREEN：

```powershell
uv run --locked pytest tests/test_query_execution_use_cases.py tests/test_authorize_prepared_query.py -q
```

---

### Task 3: 安全 token 与单次内存 plan store

**Files:** `infrastructure/execution_plan_store.py`、infrastructure exports、`test_execution_plan_store.py`。

**Produces:** `SecurePlanTokenIssuer`、`SystemClock`、`InMemoryExecutionPlanStore(max_entries)`。

- [ ] 写 RED：store 只收到 token SHA-256；put collision/capacity；惰性清理；到期边界；principal mismatch；100 个并发 claim 恰好一个成功；成功 claim、错 principal 的有效 token 和过期 token 都消费记录；外部统一不可用。

```python
results = await asyncio.gather(*(store.claim(token_digest=digest, principal_id="u1") for _ in range(100)))
assert sum(result is not None for result in results) == 1
```

- [ ] 以单个 `asyncio.Lock` 覆盖 purge/check/pop 临界区；禁止后台线程和 wall-clock naive datetime。

- [ ] GREEN：

```powershell
uv run --locked pytest tests/test_execution_plan_store.py tests/test_query_execution_use_cases.py -q
```

---

### Task 4: `env://` 凭证与 TLS 边界

**Files:** `infrastructure/datasource_secrets.py`、`test_datasource_secrets.py`。

**Produces:** 私有 `ResolvedDatasourceCredential` 和 `EnvironmentDatasourceSecretResolver`；不得从 infrastructure 导出 credential 类型。

- [ ] 写 RED：只接受 `env://[A-Z][A-Z0-9_]*`；JSON exact keys；engine/port/标识验证；隐藏 repr；禁止 DSN；loopback 才可 disable TLS；`verify_full` 使用系统 roots 与可选 `ca_pem`、开启 hostname verification；异常不包含 env 内容。

```python
assert "password" not in repr(credential)
assert "secret-value" not in str(caught.value)
```

- [ ] 实现时使用 `json.loads` 后 exact-key 校验和 `ssl.create_default_context(cadata=...)`；不得读取用户提供的 CA 路径。

- [ ] GREEN：

```powershell
uv run --locked pytest tests/test_datasource_secrets.py -q
```

---

### Task 5: 确定性结果规范化

**Files:** `infrastructure/result_normalizer.py`、`test_result_normalizer.py`。

**Produces:** 内部 `normalize_cell()` 与 async row accumulator；只返回 domain `QueryExecutionResult`。

- [ ] 写 RED 覆盖重复列名、Unicode、Decimal、date/time/datetime/UUID、有限 float、NaN/Infinity、bytes/memoryview、恶意对象（`__repr__`/`__str__` 调用即抛错）、列上限、首行超限、正好等于上限、下一行超限。

- [ ] 字节算法固定为 UTF-8、`ensure_ascii=False`、`separators=(",", ":")` 的 columns+完整 rows canonical JSON；测试写死期望字节数，禁止用同一个生产 helper 计算 expected。

- [ ] 对未知对象直接返回稳定拒绝，绝不格式化该对象；实现必须逐行 async 迭代，禁止 `fetchall()`。

- [ ] GREEN：

```powershell
uv run --locked pytest tests/test_result_normalizer.py -q
```

---

### Task 6: 受控依赖与 SQLAlchemy gateway 骨架

**Files:** `backend/pyproject.toml`、`backend/uv.lock`、`database_runtime.py`、`test_database_runtime.py`、boundary tests。

**Produces:** `SQLAlchemyDatasourceQueryGateway`，按 engine 委派 PostgreSQL/MySQL runtime；每次调用 `NullPool` + dispose。

- [ ] 先保存 lock 坐标清单到忽略的 `.reviews/phase-02b2-lock-before.txt`，再只添加：

```toml
"sqlalchemy[asyncio]>=2.0.49,<2.1",
"asyncpg>=0.31,<0.32",
"asyncmy>=0.2.14,<0.3",
```

运行一次受控锁更新，然后立即比较坐标，若出现三项以外的无关升级/降级则停止报告：

```powershell
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv lock
uv sync --check --locked
```

- [ ] 用 fake engine/runtime 写 RED：不支持 engine、secret failure、connect timeout、runtime error 都映射稳定码；engine 创建参数包含 `NullPool`/`echo=False`；每条路径 dispose；不得记录 URL。

- [ ] 扩展 boundary test：SQLAlchemy/asyncpg/asyncmy 只允许 infrastructure，domain/application 源码字符串扫描也不得出现这些 import。

- [ ] GREEN：

```powershell
uv run --locked pytest tests/test_database_runtime.py tests/test_analytics_boundaries.py -q
```

---

### Task 7: PostgreSQL runtime 与真实集成

**Files:** `postgresql_runtime.py`、PostgreSQL integration test、Docker compose、测试脚本的 PostgreSQL 部分。

**Produces:** PostgreSQL 16 的 JSON EXPLAIN 和流式 execute。

- [ ] 先用可观测 fake connection 写单元 RED，固定命令顺序：begin → read only → local timeout → EXPLAIN/SELECT → rollback；禁止 ANALYZE；cost/rows 非有限、缺失、plan 超字节拒绝。

- [ ] 实现 validated integer timeout 的可信控制语句；业务 SQL只能原样取自 `authorized.prepared.sql`。

- [ ] 新建 compose 中的 PostgreSQL 16、schema/fixture、只读业务用户，端口显式 loopback；不得使用管理员账号执行被测查询。

- [ ] 写 integration RED/GREEN：正常 SELECT、JSON plan、直接注入写 SQL 被只读事务拒绝、`pg_sleep` 超时、取消后 `pg_stat_activity` 无残留、流式截断、所有路径 rollback、错误脱敏。

```powershell
python scripts/test_analytics_databases.py --engine postgresql
```

脚本失败时输出 compose status 和有限尾部日志，并始终执行 compose down。

---

### Task 8: MySQL runtime 与真实集成

**Files:** `mysql_runtime.py`、MySQL integration test、Docker compose、测试脚本 MySQL 部分。

**Produces:** MySQL 8.4 JSON v1 EXPLAIN、`lower_case_table_names=0` 门禁和流式 execute。

- [ ] fake RED 固定：先读取 `@@lower_case_table_names`；非 0/缺失拒绝；设置 session `MAX_EXECUTION_TIME`；开始 READ ONLY；只接受 JSON v1 顶层 cost；递归 row fields 必须有限非负并求和；rollback/close。

- [ ] Compose 固定 MySQL 8.4 Linux、`lower_case_table_names=0`、健康检查、测试 schema 和非管理员只读账号。

- [ ] integration RED/GREEN：正常 SELECT、JSON plan、大小写错误对象不执行、直接写被只读事务拒绝、`SLEEP` 超时、取消后 processlist 无残留、流式配额、凭证错误脱敏。

```powershell
python scripts/test_analytics_databases.py --engine mysql
python scripts/test_analytics_databases.py --engine all
```

---

### Task 9: 文档、完整门禁与单提交

- [ ] 更新 analytics `AGENTS.md`：plan 非外部权限、三次授权、单次领取、凭证/结果边界、数据库版本、Docker 命令、2C 多 worker 接力。

- [ ] 更新 `docs/PROGRESS.md`：Phase 2 仍为 In progress；证据加入 2B2，next gate 为 `Phase 2B2 GPT 复验`，不得宣告整个 Phase 2 完成。

- [ ] 运行单元/回归门禁：

```powershell
cd backend
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv sync --check --locked
uv lock --check
uv run --locked pytest tests/test_query_execution_domain.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py tests/test_datasource_secrets.py tests/test_result_normalizer.py tests/test_database_runtime.py tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_query_execution_domain.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py tests/test_datasource_secrets.py tests/test_result_normalizer.py tests/test_database_runtime.py tests/test_analytics_postgresql_integration.py tests/test_analytics_mysql_integration.py tests/test_analytics_boundaries.py
uv run --locked ruff format --check app/analytics tests/test_query_execution_domain.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py tests/test_datasource_secrets.py tests/test_result_normalizer.py tests/test_database_runtime.py tests/test_analytics_postgresql_integration.py tests/test_analytics_mysql_integration.py
```

- [ ] 从 repo root 运行真实 Docker 门禁：

```powershell
python scripts/test_analytics_databases.py --engine all
```

- [ ] 检查文件预算、diff、固定 tag/tree、依赖坐标；`.reviews/` 和测试凭证不得提交。

- [ ] 一次提交全部允许文件：

```text
feat: add governed datasource execution
```

- [ ] 在忽略文件 `.reviews/phase-02b2-implementation-report.md` 记录每个 RED/GREEN、Docker 镜像/健康状态、超时/取消证据、依赖坐标变化、测试计数、commit/parent、文件预算与全部偏差。停止，不启动 2C。

## Plan self-review

- spec §1—18 均映射到具体任务和验证命令。
- application 不接触 credential，domain 不接触数据库库；真实 SQL 只来自授权值。
- 三次授权、两次 datasource snapshot 比较、EXPLAIN 门禁、单次 claim 和执行前复验均有测试。
- PostgreSQL/MySQL 的只读、timeout、取消和 EXPLAIN 由真实 Docker 验证，不以 mock 冒充。
- plan store 的单进程限制显式保留给 2C，在本阶段没有 API 可绕过该边界。
- 没有 API、Agent、UI、ORM、migration、Redis 或额外数据库方言。
