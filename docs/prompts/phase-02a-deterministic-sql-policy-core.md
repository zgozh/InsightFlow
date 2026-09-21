# Phase 2A 实施提示词：确定性 SQL Policy Core

你是 InsightFlow Phase 2A 的实施工程师。严格执行已经批准的架构规格和施工计划，不重新设计总体架构，不扩展到 Phase 2B/2C。

## 已验收起点

- 工作目录：`D:\develop\workspace\InsightFlow`
- 当前分支：`main`
- 开工 HEAD 必须是：`53ed1f4fa8d36009a96615d708f833be7675f73c`
- HEAD message：`feat: establish analytics domain boundary`
- Phase 1 已通过 GPT 架构复验。
- 固定 tag：`upstream-v2.1.0-rc0`
- tag commit：`609bfde0ced76ff0a58c02ff5c741df768f44502`
- tag tree：`2473c22e163a3879490848a7995eb2b7be7f6f50`
- `backend/.venv` 已由 uv 建立；当前 226 个包可用，但 SQLGlot 尚未安装。

开工时工作树允许且只允许存在以下三个由 GPT 架构师预先创建的 untracked 文件：

```text
docs/architecture/phase-02a-sql-policy-core.md
docs/superpowers/plans/2026-09-21-phase-02a-deterministic-sql-policy-core.md
docs/prompts/phase-02a-deterministic-sql-policy-core.md
```

它们是只读施工依据，必须原样纳入最终提交，不得改写。若还有任何其他未提交路径，立即停止并报告。

## 开工前必须完整阅读

1. `AGENTS.md`
2. `backend/AGENTS.md`
3. `backend/app/analytics/AGENTS.md`
4. `docs/architecture/architecture-refactoring-report.md`，重点第 6、7、9、10 节
5. `docs/decisions/0001-insightflow-hard-fork.md`
6. `docs/architecture/phase-02a-sql-policy-core.md`
7. `docs/superpowers/plans/2026-09-21-phase-02a-deterministic-sql-policy-core.md`
8. `.reviews/phase-01-implementation-report.md`，重点 Windows 与 uv 两个环境风险

第 6 项是行为规格，第 7 项是唯一施工计划。逐项执行 checkbox，不得跳过真实 RED、lockfile 完整性检查或最终门禁。

## 本轮唯一目标

建立一个不连接数据库的确定性 SQL 语法安全核心：

- 冻结的 query policy 请求、决策、风险、原因码和 prepared-query 领域值；
- runtime-checkable 的同步 `QueryPolicy` application port；
- 只在 infrastructure 使用 SQLGlot 的 `SqlglotQueryPolicy`；
- 显式 MySQL/PostgreSQL 方言；
- 单语句与根节点白名单；
- 全 AST 写入/DDL/事务/导出/锁节点拒绝；
- projection wildcard 和危险函数拒绝；
- OFFSET 与非字面量/负 LIMIT 拒绝；
- 顶层 LIMIT 注入或收紧；
- 同方言序列化并重新解析；
- 物理 relation inventory、LOW/MEDIUM 分类和稳定 SHA-256；
- 完整安全语料、领域约束和依赖边界测试。

输出的 `PreparedQuery` 只是“语法已批准且结果行数有界”的不可执行值，不是权限批准，不是 query-plan token，也不能直接交给数据库。

## 依赖与环境纪律

只允许新增一个生产依赖：

```toml
"sqlglot==30.18.0",
```

要求：

- 加到 `backend/pyproject.toml` 根项目的直接 dependencies；
- 使用纯 Python 包，不添加 `[c]`、`[rs]` 或其他 extra；
- 不新增 `asyncpg`、MySQL driver、SQLAlchemy 包或任何其他依赖；
- 唯一允许不带 `--locked` 的 uv 命令是：`uv lock --upgrade-package sqlglot`；
- 所有 uv 命令前设置 `$env:UV_DEFAULT_INDEX='https://pypi.org/simple'`；
- 其他 uv 命令统一使用 `--locked`；
- 按 plan 中的 Python 脚本比较 lock 前后 coordinates，除根项目 metadata 与 `sqlglot 30.18.0` 外不得升级、降级或换 registry；
- 禁止手工拼改 `uv.lock` 来绕过解析器。

## 允许新增/修改

仅限：

```text
backend/app/analytics/AGENTS.md
backend/app/analytics/domain/__init__.py
backend/app/analytics/domain/query.py
backend/app/analytics/application/__init__.py
backend/app/analytics/application/query_policy.py
backend/app/analytics/infrastructure/__init__.py
backend/app/analytics/infrastructure/sql_policy.py
backend/tests/test_query_policy_domain.py
backend/tests/test_sql_policy.py
backend/tests/test_analytics_boundaries.py
backend/pyproject.toml
backend/uv.lock
docs/PROGRESS.md
docs/architecture/phase-02a-sql-policy-core.md       # 只读，原样提交
docs/superpowers/plans/2026-09-21-phase-02a-deterministic-sql-policy-core.md  # 只读，原样提交
docs/prompts/phase-02a-deterministic-sql-policy-core.md                      # 只读，原样提交
```

本地证据允许写入 `.reviews/phase-02a-implementation-report.md`，保持 ignored，不提交。

不得修改 `backend/tests/test_agent_guidance_check.py`：本轮没有新增 `AGENTS.md`，现有 analytics guide 已注册。

## 严禁事项

- 不得修改 `backend/packages/harness/**`、Gateway、router、runtime、middleware、subagent registry。
- 不得增加数据库 driver、连接池、连接、事务、SQL 执行或 `EXPLAIN`。
- 不得实现 schema/table/column/row/function/PII/tenant 权限；危险函数固定 denylist 只是第一层防御。
- 不得加入 secret resolver、DSN、host、username 或明文凭据。
- 不得加入 plan ID、query audit repository、ORM、migration、API、Agent、Tool、MCP、UI、Docker 或配置项。
- 不得将 SQLGlot import 放到 `domain/` 或 `application/`。
- 不得把 SQLGlot 解析成功当作安全批准；其 parser 是宽松 parser，不是 validator。
- 不得允许 `SELECT *` 或 `SELECT t.*`；只允许 `COUNT(*)`。
- 不得返回 parser 原始报错文本、堆栈或其他不稳定细节到 domain decision。
- 不得改名 `deerflow.*`，不得改 README、LICENSE 或 `CLAUDE.md`。
- 不得 amend Phase 1，不得移动固定 tag。
- 不得开始 Phase 2B 或 2C。

## TDD 与行为要求

按 plan 的四个 Task 顺序执行：

1. 领域测试 RED → 领域契约 GREEN。
2. application/boundary 测试 RED → port GREEN。
3. SQL 安全语料 RED → 精确依赖/lock → adapter GREEN。
4. 文档、全部门禁、边界核对、单提交、review report。

每个 RED 必须发生在相应 production code 出现之前，并记录原始命令、非零退出码和关键失败。禁止把 lint failure、故意写坏 import 或失败的无关测试冒充 RED。

`SqlglotQueryPolicy.evaluate` 的判断顺序、固定 denylist、风险规则、reason code 顺序、relation/CTE 规则和 hash 输入必须与架构规格完全一致。blocked decision 只返回一个稳定 code，`risk=BLOCKED`，且 `prepared=None`。

## 必须执行的最终门禁

从 `backend/`：

```powershell
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv sync --check --locked
uv lock --check
uv run --locked pytest tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_agent_guidance_check.py
uv run --locked ruff format --check app/analytics tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_agent_guidance_check.py
make lint
```

从 repo root：

```powershell
git diff --check
git status --short
git diff --name-only
git diff -- backend/uv.lock
git rev-parse 'upstream-v2.1.0-rc0^{commit}'
git rev-parse 'upstream-v2.1.0-rc0^{tree}'
```

已知 native Windows 完整上游 suite 有 52 个经 A/B 证明的环境/平台 baseline failures。本轮不重复 45 分钟的 `make test`，也不运行 `make test-blocking-io`。必须写成 **NOT RUN（引用 Phase 1 baseline 原因）**，绝不能写成 PASS。最终 release 的全套验证将在 Linux CI/Docker 进行。

任何本轮要求执行的 focused/guidance/lint/lock 门禁失败，都不得声明 Phase 2A PASS。不要修改无关上游代码来掩盖失败。

## 提交纪律

只创建一个提交：

```text
feat: add deterministic SQL policy core
```

提交必须包含允许列表中的代码、测试、progress，以及 GPT 已创建且未经改写的 spec/plan/prompt。提交后工作树必须干净；`.reviews/` 与 `text.md` 不得被提交。

提交后生成 `.reviews/phase-02a-implementation-report.md`，然后停止，不得开始 Phase 2B。

## 最终回复格式

```text
PHASE 2A RESULT: PASS | FAIL

Commit:
- <full hash or NONE>
- Parent: <full hash>

Changed files:
- <path — purpose>

TDD evidence:
- Domain RED: <command / exit / actual failure>
- Port RED: <command / exit / actual failure>
- SQL policy RED: <command / exit / actual failure>
- GREEN: <commands / exits / test totals>

Dependency and lock:
- SQLGlot version: <actual>
- Lock coordinate check: PASS | FAIL
- Unrelated package drift: NO | YES

Security matrix:
- Explicit dialect + single statement/root allowlist: PASS | FAIL
- Forbidden AST + nested write: PASS | FAIL
- Wildcard/function/offset rejection: PASS | FAIL
- LIMIT bound + same-dialect reparse: PASS | FAIL
- Relations/risk/hash determinism: PASS | FAIL
- Prepared query executable authority: NO

Regression gates:
- <exact command / exit / actual output>
- Full native-Windows suite: NOT RUN — documented Phase 1 baseline

Boundary check:
- Harness/Gateway changed: NO
- Database connection/execution/EXPLAIN added: NO
- Permission/schema/audit/API/Agent/UI added: NO
- SQLGlot imported outside infrastructure: NO
- Unexpected dependency or lock drift: NO
- Baseline tag/tree changed: NO
- Phase 2B started: NO

Deviations:
- None | <exact deviation and reason>

Review artifact:
- .reviews/phase-02a-implementation-report.md
```

只报告真实执行结果。未运行、失败、超时或仅凭推测的命令不得写成 PASS。
