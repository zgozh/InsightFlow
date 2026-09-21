# Phase 2B1 实施提示词：语义查询授权核心

你是 InsightFlow Phase 2B1 实施工程师。严格执行已批准的 spec 和 plan，不重新设计，不开始数据库执行链。

## 起点

- repo：`D:\develop\workspace\InsightFlow`
- branch：`main`
- HEAD 必须是：`f2d35d337b9c9f6abb96918fec0e0ee996402713`
- parent：`8a11d0ea46ffda459a1da69f2924d7b9259fc8ba`
- 固定 tag commit/tree：
  - `609bfde0ced76ff0a58c02ff5c741df768f44502`
  - `2473c22e163a3879490848a7995eb2b7be7f6f50`

开工时只允许以下三个 GPT 架构师文件为 untracked：

```text
docs/architecture/phase-02b1-semantic-authorization-core.md
docs/superpowers/plans/2026-09-21-phase-02b1-semantic-authorization-core.md
docs/prompts/phase-02b1-semantic-authorization-core.md
```

三者只读，最终原样提交。存在其他未提交路径立即停止。

## 必读

1. `AGENTS.md`
2. `backend/AGENTS.md`
3. `backend/app/analytics/AGENTS.md`
4. `docs/architecture/phase-02a-sql-policy-core.md`
5. `docs/architecture/phase-02b1-semantic-authorization-core.md`
6. `docs/superpowers/plans/2026-09-21-phase-02b1-semantic-authorization-core.md`
7. `.reviews/phase-02a-implementation-report.md` 的 Fix 01 部分

Spec 是行为权威，plan 是唯一施工清单。逐项 TDD 执行。

## 唯一目标

把真实的 Phase 2A `PreparedQuery`、不可变 SchemaSnapshot 和 principal policy 转成确定性语义授权结果：

- 防伪造：先重新执行 Phase 2A 并要求 `PreparedQuery` 完整相等；
- SQLGlot schema qualification；
- 表、列、函数全部 default-deny；
- 解析 alias、JOIN、CTE、非相关子查询到物理表列；
- 相关子查询 fail closed；
- PII/sensitive、跨 schema、笛卡尔连接为 HIGH；
- HIGH 在 V1 默认拒绝并返回 `APPROVAL_REQUIRED`；
- 输出 `AuthorizedQuerySpec`，但它仍无 plan ID 和执行权。

特别要求：Phase 2A 允许但不在有效 policy 函数白名单中的 `nextval`、`setval`、`GET_LOCK`、advisory-lock 和未知 UDF 必须拒绝。危险函数 denylist 不是授权机制。

## 允许修改/新增

```text
backend/app/analytics/domain/schema.py
backend/app/analytics/domain/access_policy.py
backend/app/analytics/domain/authorization.py
backend/app/analytics/domain/__init__.py
backend/app/analytics/application/authorization.py
backend/app/analytics/application/__init__.py
backend/app/analytics/infrastructure/semantic_authorizer.py
backend/app/analytics/infrastructure/__init__.py
backend/app/analytics/AGENTS.md
backend/tests/test_query_authorization_domain.py
backend/tests/test_authorize_prepared_query.py
backend/tests/test_semantic_authorizer.py
backend/tests/test_analytics_boundaries.py
docs/PROGRESS.md
docs/architecture/phase-02b1-semantic-authorization-core.md  # 只读
docs/superpowers/plans/2026-09-21-phase-02b1-semantic-authorization-core.md  # 只读
docs/prompts/phase-02b1-semantic-authorization-core.md  # 只读
```

本地可写 `.reviews/phase-02b1-implementation-report.md`，保持 ignored。

## 禁止

- 不得修改依赖或 `backend/uv.lock`。
- 不得新增 asyncpg、MySQL driver、SQLAlchemy 依赖或其他包。
- 不得增加 secret resolver、DSN、数据库连接、连接池、EXPLAIN、执行、plan ID、timeout、row/byte cap。
- 不得增加 ORM、migration、API、Agent、Tool、MCP、UI、Docker 或配置。
- 不得修改 Harness、Gateway、Phase 2A 历史 plan/prompt、README、LICENSE、`CLAUDE.md`。
- 不得把 SQLGlot import 放进 domain/application。
- 不得信任 `PreparedQuery` 的 Python 类型本身；必须重跑 Phase 2A 并完整比较。
- 不得把 `PreparedQuery.relations` 当成权限依据；权限依据只能来自 qualification 后的物理 lineage。
- 不得默许 SQL 函数；policy 未列出的全部拒绝。
- 不得允许 HIGH；未来人工批准流程必须另行设计。
- 不得猜测相关子查询 lineage。
- 不得开始 2B2。

## 环境说明

用户机器有 Docker，但 2B1 是纯离线语义授权，不使用 Docker。Docker PostgreSQL/MySQL 留给 2B2 的真实集成验收。

所有 uv 命令使用：

```powershell
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv run --locked ...
```

## 施工纪律

严格按 plan 四个 Task：

1. domain tests RED → schema/policy/authorization contracts GREEN；
2. application tests RED → catalogs/use case GREEN；
3. semantic corpus RED → SQLGlot authorizer GREEN；
4. docs、门禁、单提交、review report。

RED 必须发生在对应 production code 前，记录命令、非零 exit 和真实失败。不能用故意写坏 import 或 lint failure 充当行为 RED。

若 SQLGlot 30.18.0 的实际 AST 与 spec 假设不同：先用最小 AST inspection 证明，记录到 report；只能做满足既定安全行为的最小偏差，不能放宽 default-deny。

## 最终门禁

从 `backend/`：

```powershell
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv sync --check --locked
uv lock --check
uv run --locked pytest tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_boundaries.py
uv run --locked ruff format --check app/analytics tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_boundaries.py
make lint
```

从 repo root：

```powershell
git diff --check
git diff --name-only f2d35d3..HEAD
git diff -- backend/uv.lock
git status --short --branch
git rev-parse 'upstream-v2.1.0-rc0^{commit}'
git rev-parse 'upstream-v2.1.0-rc0^{tree}'
```

focused/guidance/lint/lock 必须全部通过。完整 native-Windows suite 沿用已证明的 baseline，写 `NOT RUN`，不得写 PASS。

## 提交

只创建一个提交：

```text
feat: add semantic query authorization core
```

提交后工作树干净；`.reviews/` 和 `text.md` 不提交。写完 `.reviews/phase-02b1-implementation-report.md` 后停止，不得开始 2B2。

## 最终回复

```text
PHASE 2B1 RESULT: PASS | FAIL

Commit:
- <full hash or NONE>
- Parent: f2d35d337b9c9f6abb96918fec0e0ee996402713

Changed paths:
- <path — purpose>

TDD:
- Domain RED: <command / exit / failure>
- Application RED: <command / exit / failure>
- Semantic RED: <command / exit / failure>
- GREEN: <commands / exits / totals>

Authorization matrix:
- PreparedQuery forgery rejected: PASS | FAIL
- Relations/columns default-deny: PASS | FAIL
- Functions default-deny: PASS | FAIL
- Alias/JOIN/CTE/subquery lineage: PASS | FAIL
- Correlated query rejected: PASS | FAIL
- PII/cross-schema/Cartesian denied HIGH: PASS | FAIL
- AuthorizedQuerySpec execution authority: NO

Boundary:
- Dependency/uv.lock changed: NO | YES
- Database/EXPLAIN/plan ID/API/Agent/Docker added: NO | YES
- SQLGlot outside infrastructure: NO | YES
- Harness/Gateway changed: NO | YES
- Baseline tag/tree changed: NO | YES
- Phase 2B2 started: NO | YES

Deviations:
- None | <exact evidence-backed deviation>

Review artifact:
- .reviews/phase-02b1-implementation-report.md
```

只报告真实执行结果。
