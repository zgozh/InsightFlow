# Phase 2A Deterministic SQL Policy Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, fail-closed SQL syntax policy that produces bounded, normalized, reparsed, immutable query values without connecting to or executing against a database.

**Architecture:** Immutable contracts live in the standard-library-only analytics domain, a synchronous `QueryPolicy` protocol lives in application, and the SQLGlot adapter lives in infrastructure. The adapter uses explicit MySQL/PostgreSQL dialects, a root allowlist plus AST denylists, top-level LIMIT enforcement, same-dialect reparse, deterministic relation extraction, risk classification and hashing. Its output is deliberately non-executable until Phase 2B adds authorization, cost checks and plan IDs.

**Tech Stack:** Python 3.12, frozen dataclasses, `typing.Protocol`, `sqlglot==30.18.0`, pytest, Ruff, uv.

**Spec:** `docs/architecture/phase-02a-sql-policy-core.md`

## Global Constraints

- Start from `53ed1f4fa8d36009a96615d708f833be7675f73c` on `main` with immutable tag `upstream-v2.1.0-rc0` at `609bfde0ced76ff0a58c02ff5c741df768f44502`, tree `2473c22e163a3879490848a7995eb2b7be7f6f50`.
- The only pre-existing untracked changes may be the architect-owned Phase 2A spec, plan and prompt. Read and commit them unchanged.
- Use the pure-Python exact dependency `sqlglot==30.18.0`; do not add extras, drivers, ORM packages or any other dependency.
- Every uv execution uses `--locked` except the single intentional `uv lock --upgrade-package sqlglot`; set `UV_DEFAULT_INDEX=https://pypi.org/simple` for both.
- Domain stays standard-library-only; application cannot import SQLGlot, Gateway, Harness, FastAPI, LangChain or SQLAlchemy.
- Do not edit `backend/packages/harness/**`, Gateway/runtime/router code, migrations, API, Agent, MCP, frontend, Docker, config, README, LICENSE or `CLAUDE.md`.
- No query execution, connection string, database credential, schema authorization, EXPLAIN, query-plan ID or audit persistence belongs in 2A.
- TDD is mandatory. Capture a genuine failing test before each production slice and do not weaken assertions to turn a failure green.
- Phase 2A lands as one reviewable commit, `feat: add deterministic SQL policy core`. The repository's one-commit gated-slice rule supersedes generic per-task commit advice; do not create interim commits.
- Native-Windows full-suite failures are already baselined. Run the focused security/boundary/guidance gates and lint below; do not claim the full upstream suite passed.

---

## File map

**Create**

- `backend/app/analytics/domain/query.py` — immutable policy request, decision, prepared-query and risk/code values.
- `backend/app/analytics/application/query_policy.py` — runtime-checkable synchronous policy port.
- `backend/app/analytics/infrastructure/__init__.py` — narrow export of the concrete adapter.
- `backend/app/analytics/infrastructure/sql_policy.py` — the only SQLGlot consumer and deterministic policy implementation.
- `backend/tests/test_query_policy_domain.py` — domain invariants and immutability.
- `backend/tests/test_sql_policy.py` — SQL safety, bounding, normalization, relation, risk and hash corpus.

**Modify**

- `backend/app/analytics/domain/__init__.py` — re-export the new domain contracts.
- `backend/app/analytics/application/__init__.py` — re-export `QueryPolicy`.
- `backend/app/analytics/AGENTS.md` — describe the now-real infrastructure boundary and focused checks.
- `backend/tests/test_analytics_boundaries.py` — keep SQLGlot out of domain/application and enforce infrastructure direction.
- `backend/pyproject.toml` — add the exact direct SQLGlot dependency.
- `backend/uv.lock` — add only SQLGlot plus root-project dependency metadata.
- `docs/PROGRESS.md` — mark Phase 1 complete and Phase 2/2A in review.

**Architect-owned, commit unchanged**

- `docs/architecture/phase-02a-sql-policy-core.md`
- `docs/superpowers/plans/2026-09-21-phase-02a-deterministic-sql-policy-core.md`
- `docs/prompts/phase-02a-deterministic-sql-policy-core.md`

---

### Task 1: Establish immutable query-policy domain contracts

**Files:**

- Create: `backend/tests/test_query_policy_domain.py`
- Create: `backend/app/analytics/domain/query.py`
- Modify: `backend/app/analytics/domain/__init__.py`

**Interfaces:**

- Consumes: `app.analytics.domain.datasource.DatasourceEngine`
- Produces: `MAX_QUERY_ROWS`, `QueryRisk`, `QueryDecisionCode`, `QueryPolicyRequest`, `PreparedQuery`, `QueryPolicyDecision`

- [ ] **Step 1: Write the domain tests first**

Create tests that directly assert the contract, including these exact cases:

```python
from dataclasses import FrozenInstanceError

import pytest

from app.analytics.domain import (
    MAX_QUERY_ROWS,
    DatasourceEngine,
    PreparedQuery,
    QueryDecisionCode,
    QueryPolicyDecision,
    QueryPolicyRequest,
    QueryRisk,
)


def test_query_policy_request_defaults_and_is_immutable():
    request = QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.POSTGRESQL)
    assert request.max_rows == 1_000
    with pytest.raises(FrozenInstanceError):
        request.max_rows = 2  # type: ignore[misc]


@pytest.mark.parametrize("max_rows", [0, -1, MAX_QUERY_ROWS + 1, True])
def test_query_policy_request_rejects_invalid_row_caps(max_rows):
    with pytest.raises(ValueError):
        QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.MYSQL, max_rows=max_rows)


def test_query_policy_decision_requires_prepared_query_when_allowed():
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=True,
            risk=QueryRisk.LOW,
            codes=(QueryDecisionCode.APPROVED,),
        )


def test_blocked_decision_cannot_carry_a_prepared_query():
    prepared = PreparedQuery(
        sql="SELECT 1 LIMIT 1",
        engine=DatasourceEngine.POSTGRESQL,
        relations=(),
        row_limit=1,
        query_hash="0" * 64,
    )
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=False,
            risk=QueryRisk.BLOCKED,
            codes=(QueryDecisionCode.PARSE_ERROR,),
            prepared=prepared,
        )
```

Also assert: empty SQL string is permitted at request construction; non-string SQL and non-enum engines fail; `max_rows=MAX_QUERY_ROWS` passes; prepared values reject blank SQL, invalid engine, non-tuple/duplicate/untrimmed relations, negative row limits, and non-lowercase/non-64-hex hashes; decision codes must be a non-empty unique tuple; allowed + `BLOCKED`, denied + prepared, and blocked + allowed fail.

- [ ] **Step 2: Run the focused test and capture RED**

From `backend/`:

```powershell
$env:PYTHONPATH='.'
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv run --locked pytest tests/test_query_policy_domain.py -q
```

Expected: non-zero collection failure because the query contracts do not exist. Record command, exit code and key error in `.reviews/phase-02a-implementation-report.md`.

- [ ] **Step 3: Implement the exact domain vocabulary and invariants**

Use frozen, slotted dataclasses. Keep validation in this module and use no dependency beyond the standard library and `DatasourceEngine`:

```python
MAX_QUERY_ROWS = 10_000


class QueryRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class QueryDecisionCode(StrEnum):
    APPROVED = "approved"
    EMPTY_SQL = "empty_sql"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    UNSUPPORTED_STATEMENT = "unsupported_statement"
    FORBIDDEN_OPERATION = "forbidden_operation"
    WILDCARD_PROJECTION = "wildcard_projection"
    DANGEROUS_FUNCTION = "dangerous_function"
    OFFSET_NOT_ALLOWED = "offset_not_allowed"
    NON_LITERAL_LIMIT = "non_literal_limit"
    INVALID_LIMIT = "invalid_limit"
    LIMIT_APPLIED = "limit_applied"
    LIMIT_REDUCED = "limit_reduced"
    COMPLEX_QUERY = "complex_query"
```

Implement the three fields of `QueryPolicyRequest`, five fields of `PreparedQuery`, and four fields of `QueryPolicyDecision` exactly as specified in the architecture spec. Validate with `__post_init__`; do not add convenience constructors or policy behavior to domain.

- [ ] **Step 4: Export the contracts and run GREEN**

Add the five query types plus `MAX_QUERY_ROWS` to `domain/__init__.py` and `__all__`. Run:

```powershell
uv run --locked pytest tests/test_query_policy_domain.py tests/test_analytics_domain.py -q
uv run --locked ruff check app/analytics/domain tests/test_query_policy_domain.py
uv run --locked ruff format --check app/analytics/domain tests/test_query_policy_domain.py
git diff --check
```

Expected: all exit 0. Do not commit yet.

---

### Task 2: Add the application policy port and strengthen dependency boundaries

**Files:**

- Create: `backend/app/analytics/application/query_policy.py`
- Modify: `backend/app/analytics/application/__init__.py`
- Modify: `backend/tests/test_analytics_boundaries.py`

**Interfaces:**

- Consumes: `QueryPolicyRequest`, `QueryPolicyDecision`
- Produces: runtime-checkable `QueryPolicy.evaluate(request) -> QueryPolicyDecision`

- [ ] **Step 1: Extend boundary tests before implementation**

Add `sqlglot` to `APPLICATION_BANNED_PREFIXES`. Add these focused assertions:

```python
from app.analytics.application import QueryPolicy


def test_query_policy_port_is_a_runtime_checkable_protocol():
    assert getattr(QueryPolicy, "_is_runtime_protocol", False)


def test_analytics_infrastructure_does_not_depend_on_delivery_or_harness():
    banned = ("app.gateway", "deerflow", "fastapi", "langchain")
    violations: list[str] = []
    infrastructure = ANALYTICS_ROOT / "infrastructure"
    if infrastructure.exists():
        for path in sorted(infrastructure.rglob("*.py")):
            for line, module in _imports(path):
                if any(module == prefix or module.startswith(f"{prefix}.") for prefix in banned):
                    violations.append(
                        f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}"
                    )
    assert not violations, "Analytics infrastructure dependency violations:\n" + "\n".join(violations)
```

The existing domain standard-library test must still pass. Do not ban SQLAlchemy from infrastructure because Phase 2B is explicitly allowed to use it.

- [ ] **Step 2: Run RED**

```powershell
uv run --locked pytest tests/test_analytics_boundaries.py -q
```

Expected: collection failure for the missing `QueryPolicy`. Record it.

- [ ] **Step 3: Implement the port**

```python
from typing import Protocol, runtime_checkable

from app.analytics.domain import QueryPolicyDecision, QueryPolicyRequest


@runtime_checkable
class QueryPolicy(Protocol):
    def evaluate(self, request: QueryPolicyRequest) -> QueryPolicyDecision: ...
```

Export it from `application/__init__.py`. Do not make it async and do not import infrastructure from application.

- [ ] **Step 4: Run GREEN and the Harness boundary**

```powershell
uv run --locked pytest tests/test_analytics_boundaries.py tests/test_harness_boundary.py -q
uv run --locked ruff check app/analytics/application tests/test_analytics_boundaries.py
uv run --locked ruff format --check app/analytics/application tests/test_analytics_boundaries.py
git diff --check
```

Expected: all exit 0. Do not commit yet.

---

### Task 3: Pin SQLGlot and implement the fail-closed adapter

**Files:**

- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Create: `backend/tests/test_sql_policy.py`
- Create: `backend/app/analytics/infrastructure/__init__.py`
- Create: `backend/app/analytics/infrastructure/sql_policy.py`

**Interfaces:**

- Consumes: `QueryPolicyRequest` and all query domain values; SQLGlot 30.18.0
- Produces: `SqlglotQueryPolicy.evaluate(request) -> QueryPolicyDecision`

- [ ] **Step 1: Write the SQL safety corpus before adding infrastructure**

The test file must instantiate `SqlglotQueryPolicy` and use both `DatasourceEngine.MYSQL` and `POSTGRESQL`. Use parameterization for this exact blocked corpus:

```python
@pytest.mark.parametrize("engine", list(DatasourceEngine))
@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("", QueryDecisionCode.EMPTY_SQL),
        ("SELECT (", QueryDecisionCode.PARSE_ERROR),
        ("SELECT 1; SELECT 2", QueryDecisionCode.MULTIPLE_STATEMENTS),
        ("SHOW TABLES", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("VALUES (1)", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("INSERT INTO t VALUES (1)", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("UPDATE t SET value = 1", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("DELETE FROM t", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("CREATE TABLE t (id INT)", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("DROP TABLE t", QueryDecisionCode.UNSUPPORTED_STATEMENT),
        ("SELECT id FROM t FOR UPDATE", QueryDecisionCode.FORBIDDEN_OPERATION),
        ("SELECT * FROM t", QueryDecisionCode.WILDCARD_PROJECTION),
        ("SELECT t.* FROM t", QueryDecisionCode.WILDCARD_PROJECTION),
        ("SELECT SLEEP(1)", QueryDecisionCode.DANGEROUS_FUNCTION),
        ("SELECT id FROM t OFFSET 1", QueryDecisionCode.OFFSET_NOT_ALLOWED),
        ("SELECT id FROM t LIMIT ?", QueryDecisionCode.NON_LITERAL_LIMIT),
        ("SELECT id FROM t LIMIT -1", QueryDecisionCode.INVALID_LIMIT),
    ],
)
def test_policy_fails_closed(engine, sql, code):
    decision = SqlglotQueryPolicy().evaluate(QueryPolicyRequest(sql=sql, engine=engine))
    assert decision.allowed is False
    assert decision.risk is QueryRisk.BLOCKED
    assert decision.codes == (code,)
    assert decision.prepared is None
```

Add separate tests for:

- `SELECT * INTO OUTFILE 'x' FROM t` on MySQL and `COPY t TO '/tmp/x'` on PostgreSQL;
- a data-changing CTE (`WITH changed AS (DELETE FROM t RETURNING id) SELECT id FROM changed`) returning `FORBIDDEN_OPERATION`;
- `COUNT(*)` approval;
- each denylisted function at least once across the two dialects, with mixed casing for one case;
- simple query limit injection to exactly the request cap;
- preservation of `LIMIT 5`, including `row_limit == 5`;
- reduction of `LIMIT 5000` to a request cap of 100 and `LIMIT_REDUCED`;
- allowed-code ordering for a complex unbounded query: `LIMIT_APPLIED`, `COMPLEX_QUERY`, `APPROVED`;
- CTE physical relations excluding the CTE alias;
- sorted unique `catalog.schema.table` relation strings;
- LOW for a simple select and MEDIUM for join, CTE, union, window and subquery cases;
- normalized SQL parsing as exactly one statement with the same explicit dialect;
- stable hash for repeat evaluation and a different hash for the same text under different engines;
- parser text is absent from blocked decisions;
- `isinstance(SqlglotQueryPolicy(), QueryPolicy)`.

- [ ] **Step 2: Run the new test and capture RED before dependency/implementation**

```powershell
uv run --locked pytest tests/test_sql_policy.py -q
```

Expected: non-zero collection failure because `app.analytics.infrastructure` does not exist. Record the actual result.

- [ ] **Step 3: Add the exact direct dependency and regenerate only the lock**

Add this line to root `[project].dependencies` in `backend/pyproject.toml` near the other App dependencies:

```toml
"sqlglot==30.18.0",
```

From `backend/`:

```powershell
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv lock --upgrade-package sqlglot
uv sync --locked
uv run --locked python -c "import sqlglot; assert sqlglot.__version__ == '30.18.0'; print(sqlglot.__version__)"
```

Verify that all pre-existing non-root package coordinates remain identical:

```powershell
@'
import pathlib
import subprocess
import tomllib

before = tomllib.loads(subprocess.check_output(
    ["git", "show", "HEAD:backend/uv.lock"], text=True, encoding="utf-8"
))
after = tomllib.loads(pathlib.Path("uv.lock").read_text(encoding="utf-8"))

def coordinates(document):
    return {
        (package["name"], package["version"], repr(package.get("source")))
        for package in document["package"]
        if package["name"] not in {"deer-flow", "sqlglot"}
    }

assert coordinates(before) == coordinates(after)
sqlglot = [package for package in after["package"] if package["name"] == "sqlglot"]
assert len(sqlglot) == 1 and sqlglot[0]["version"] == "30.18.0"
print("lock delta limited to root metadata plus sqlglot 30.18.0")
'@ | uv run --locked python -
```

If the assertion fails or registry URLs change, stop without hand-editing the lockfile.

- [ ] **Step 4: Implement the complete SQLGlot adapter**

Create `sql_policy.py` with this implementation. Do not collapse the root allowlist into the forbidden-node scan, and do not catch or expose parser details:

```python
from __future__ import annotations

import hashlib

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.analytics.domain import (
    DatasourceEngine,
    PreparedQuery,
    QueryDecisionCode,
    QueryPolicyDecision,
    QueryPolicyRequest,
    QueryRisk,
)

_DIALECT_BY_ENGINE = {
    DatasourceEngine.MYSQL: "mysql",
    DatasourceEngine.POSTGRESQL: "postgres",
}
_FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Merge,
    exp.Command,
    exp.Copy,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Revoke,
    exp.TruncateTable,
    exp.Use,
    exp.Set,
    exp.Cache,
    exp.Uncache,
    exp.Execute,
    exp.Into,
    exp.Lock,
)
_DANGEROUS_FUNCTIONS = frozenset(
    {
        "benchmark",
        "dblink",
        "dblink_exec",
        "load_file",
        "lo_export",
        "lo_import",
        "pg_cancel_backend",
        "pg_ls_dir",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_sleep",
        "pg_stat_file",
        "pg_terminate_backend",
        "set_config",
        "sleep",
        "sys_eval",
        "sys_exec",
    }
)
_COMPLEX_EXPRESSIONS = (exp.Join, exp.With, exp.SetOperation, exp.Window, exp.Subquery)


def _blocked(code: QueryDecisionCode) -> QueryPolicyDecision:
    return QueryPolicyDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(code,),
    )


def _parse_statements(sql: str, dialect: str) -> list[exp.Expression]:
    return [statement for statement in sqlglot.parse(sql, read=dialect) if statement is not None]


def _function_name(function: exp.Func) -> str:
    if isinstance(function, exp.Anonymous):
        return function.name.casefold()
    return function.sql_name().casefold()


def _structure_error(statement: exp.Expression) -> QueryDecisionCode | None:
    allowed_root = isinstance(statement, (exp.Select, exp.SetOperation))
    if not allowed_root or statement.find(exp.Select) is None:
        return QueryDecisionCode.UNSUPPORTED_STATEMENT
    if any(isinstance(node, _FORBIDDEN_EXPRESSIONS) for node in statement.walk()):
        return QueryDecisionCode.FORBIDDEN_OPERATION
    if any(not isinstance(star.parent, exp.Count) for star in statement.find_all(exp.Star)):
        return QueryDecisionCode.WILDCARD_PROJECTION
    if any(
        _function_name(function) in _DANGEROUS_FUNCTIONS
        for function in statement.find_all(exp.Func)
    ):
        return QueryDecisionCode.DANGEROUS_FUNCTION
    if statement.find(exp.Offset) is not None:
        return QueryDecisionCode.OFFSET_NOT_ALLOWED
    return None


def _limit_value(
    statement: exp.Expression,
) -> tuple[int | None, QueryDecisionCode | None]:
    limit = statement.args.get("limit")
    if limit is None:
        return None, None
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int:
        return int(value.this), None
    if (
        isinstance(value, exp.Neg)
        and isinstance(value.this, exp.Literal)
        and value.this.is_int
    ):
        return -int(value.this.this), QueryDecisionCode.INVALID_LIMIT
    return None, QueryDecisionCode.NON_LITERAL_LIMIT


def _physical_relations(statement: exp.Expression) -> tuple[str, ...]:
    cte_aliases = {
        cte.alias_or_name.casefold()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    relations: set[str] = set()
    for table in statement.find_all(exp.Table):
        if not table.name:
            continue
        if not table.catalog and not table.db and table.name.casefold() in cte_aliases:
            continue
        relation = ".".join(
            part for part in (table.catalog, table.db, table.name) if part
        )
        if relation:
            relations.add(relation)
    return tuple(sorted(relations))


def _risk(statement: exp.Expression) -> QueryRisk:
    if any(isinstance(node, _COMPLEX_EXPRESSIONS) for node in statement.walk()):
        return QueryRisk.MEDIUM
    return QueryRisk.LOW


class SqlglotQueryPolicy:
    def evaluate(self, request: QueryPolicyRequest) -> QueryPolicyDecision:
        candidate = request.sql.strip()
        if not candidate:
            return _blocked(QueryDecisionCode.EMPTY_SQL)

        dialect = _DIALECT_BY_ENGINE[request.engine]
        try:
            statements = _parse_statements(candidate, dialect)
        except SqlglotError:
            return _blocked(QueryDecisionCode.PARSE_ERROR)
        if len(statements) > 1:
            return _blocked(QueryDecisionCode.MULTIPLE_STATEMENTS)
        if not statements:
            return _blocked(QueryDecisionCode.PARSE_ERROR)

        statement = statements[0]
        if structural_error := _structure_error(statement):
            return _blocked(structural_error)

        limit, limit_error = _limit_value(statement)
        if limit_error:
            return _blocked(limit_error)

        codes: list[QueryDecisionCode] = []
        if limit is None:
            bounded = statement.limit(request.max_rows, copy=True)
            effective_limit = request.max_rows
            codes.append(QueryDecisionCode.LIMIT_APPLIED)
        elif limit > request.max_rows:
            bounded = statement.limit(request.max_rows, copy=True)
            effective_limit = request.max_rows
            codes.append(QueryDecisionCode.LIMIT_REDUCED)
        else:
            bounded = statement.copy()
            effective_limit = limit

        normalized_sql = bounded.sql(dialect=dialect, pretty=False)
        try:
            reparsed = _parse_statements(normalized_sql, dialect)
        except SqlglotError:
            return _blocked(QueryDecisionCode.PARSE_ERROR)
        if len(reparsed) != 1:
            code = (
                QueryDecisionCode.MULTIPLE_STATEMENTS
                if len(reparsed) > 1
                else QueryDecisionCode.PARSE_ERROR
            )
            return _blocked(code)

        normalized_statement = reparsed[0]
        if structural_error := _structure_error(normalized_statement):
            return _blocked(structural_error)
        reparsed_limit, reparsed_limit_error = _limit_value(normalized_statement)
        if reparsed_limit_error or reparsed_limit != effective_limit:
            return _blocked(reparsed_limit_error or QueryDecisionCode.PARSE_ERROR)

        risk = _risk(normalized_statement)
        if risk is QueryRisk.MEDIUM:
            codes.append(QueryDecisionCode.COMPLEX_QUERY)
        codes.append(QueryDecisionCode.APPROVED)
        query_hash = hashlib.sha256(
            f"{request.engine.value}\0{normalized_sql}".encode()
        ).hexdigest()
        prepared = PreparedQuery(
            sql=normalized_sql,
            engine=request.engine,
            relations=_physical_relations(normalized_statement),
            row_limit=effective_limit,
            query_hash=query_hash,
        )
        return QueryPolicyDecision(
            allowed=True,
            risk=risk,
            codes=tuple(codes),
            prepared=prepared,
        )
```

Export only `SqlglotQueryPolicy` from `infrastructure/__init__.py`.

- [ ] **Step 5: Run the focused security corpus and iterate only within scope**

```powershell
$env:PYTHONPATH='.'
uv run --locked pytest tests/test_sql_policy.py tests/test_query_policy_domain.py -q
uv run --locked ruff check app/analytics tests/test_sql_policy.py tests/test_query_policy_domain.py
uv run --locked ruff format --check app/analytics tests/test_sql_policy.py tests/test_query_policy_domain.py
git diff --check
```

Expected: all exit 0. Fix implementation defects; do not delete cases, weaken expected decision codes, or expand scope.

---

### Task 4: Document, verify and land the gated slice

**Files:**

- Modify: `backend/app/analytics/AGENTS.md`
- Modify: `docs/PROGRESS.md`
- Commit all allowed files from the file map.

**Interfaces:**

- Consumes: completed policy implementation and evidence.
- Produces: current module guide, truthful progress ledger, one atomic Phase 2A commit and ignored review report.

- [ ] **Step 1: Update the local analytics guide**

Document that:

- infrastructure is now real and SQLGlot may be imported only there;
- `PreparedQuery` is syntax-approved but non-executable;
- 2B owns permissions, schema, EXPLAIN, read-only execution and short-lived plan IDs;
- every uv command uses `--locked` except intentional lock generation;
- focused checks include both new test files and existing analytics/harness boundary tests.

Do not add another `AGENTS.md`; the existing guide is already registered.

- [ ] **Step 2: Update the factual progress ledger**

Change:

- Phase 1 to `Complete`, evidence `53ed1f4; focused/guidance/Ruff review PASS`, next gate `Phase 2A implementation`.
- Phase 2 to `In progress`, evidence `Phase 2A design; SQL policy tests`, next gate `Phase 2A architecture review`.

Add one short note below the ledger that Phase 2 is split into 2A policy, 2B governed execution, and 2C persistence/API, each independently reviewed. Do not change size budgets or later phases.

- [ ] **Step 3: Run all required Phase 2A gates**

From `backend/`, with both environment variables set:

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

Expected: all exit 0. Recheck `backend/uv.lock` after `make lint`; the official-index environment must prevent mirror rewrites.

The native-Windows `make test` and `make test-blocking-io` suites are not rerun in this slice because their 52 pre-existing failures and causes are already documented in `.reviews/phase-01-implementation-report.md`. Record this as an explicit not-run baseline condition, never as PASS. Canonical whole-suite validation remains Linux CI/Docker work.

- [ ] **Step 4: Verify boundaries and exact changed paths**

From the repository root:

```powershell
git diff --check
git status --short
git diff --name-only
git diff -- backend/uv.lock
git diff --name-only 53ed1f4..HEAD
git rev-parse 'upstream-v2.1.0-rc0^{commit}'
git rev-parse 'upstream-v2.1.0-rc0^{tree}'
```

Before commit, the changed set must be exactly the file map in this plan. Confirm there is no Harness, Gateway, migration, API, Agent, UI, Docker, config, README, LICENSE or `CLAUDE.md` change. Confirm the tag values match the global constraints.

- [ ] **Step 5: Create the single Phase 2A commit**

```powershell
git add backend/app/analytics backend/tests/test_query_policy_domain.py backend/tests/test_sql_policy.py backend/tests/test_analytics_boundaries.py backend/pyproject.toml backend/uv.lock docs/PROGRESS.md docs/architecture/phase-02a-sql-policy-core.md docs/superpowers/plans/2026-09-21-phase-02a-deterministic-sql-policy-core.md docs/prompts/phase-02a-deterministic-sql-policy-core.md
git diff --cached --check
git diff --cached --name-only
git commit -m "feat: add deterministic SQL policy core"
```

Do not amend Phase 1 or move the baseline tag.

- [ ] **Step 6: Write review evidence and stop**

Create ignored `.reviews/phase-02a-implementation-report.md` with:

- full commit and parent hashes;
- changed paths and diffstat;
- each RED command, exit code and actual key failure;
- dependency/lock commands and the coordinate-comparison output;
- each GREEN/gate command, exit code, test total and key output;
- explicit distinction between focused gates PASS and full native-Windows suite NOT RUN with its documented baseline reason;
- query-policy coverage table for each acceptance-matrix category;
- confirmation that prepared queries are non-executable and 2B/2C scope is absent;
- baseline tag/tree and clean-worktree evidence;
- deviations, written as `None` only if there were none.

Stop after the report. Do not begin Phase 2B.

## Plan self-review

- **Spec coverage:** every contract, evaluation stage, denylist, risk rule, non-goal and gate from the Phase 2A architecture spec maps to a task and test category.
- **Scope control:** the slice has no database driver, credential, schema permission, EXPLAIN, execution, persistence, migration, route, Agent, MCP, UI or Harness work.
- **Type consistency:** the synchronous application port consumes and returns the exact immutable domain types used by the adapter and tests.
- **Security posture:** root allowlisting, full-AST forbidden-node scanning, wildcard/function/offset rejection, hard top-level LIMIT, same-dialect reparse and non-executable output are all independently asserted.
- **Dependency integrity:** SQLGlot is exact-pinned, isolated to infrastructure, and the lock comparison prevents unrelated resolution drift.
- **Rollback:** one commit cleanly removes the whole slice without touching the immutable upstream baseline.
