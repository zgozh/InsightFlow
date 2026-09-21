# Phase 2A Architecture: Deterministic SQL Policy Core

Status: approved for implementation after Phase 1 architecture acceptance.

## 1. Purpose

Phase 2 is split into three reviewable slices:

1. **2A — deterministic SQL policy core:** parse and classify candidate SQL, reject unsafe syntax, impose a hard result-row bound, serialize and reparse, and produce an immutable non-executable prepared-query value.
2. **2B — governed datasource execution:** resolve schema and permissions, authorize tables/columns/functions, run `EXPLAIN`, issue a short-lived plan ID, and execute through read-only database identities with timeout/row/byte limits.
3. **2C — persistence and delivery:** datasource/metric/query-audit repositories, forward migrations, application use cases, and authenticated FastAPI routes.

This document specifies only 2A. It creates no database connection, credential resolver, API, Agent tool, migration, or executable query-plan token.

## 2. Architectural decision

The policy is an App-owned adapter:

```text
app.analytics.domain.query
        ▲
        │ immutable request/decision values
app.analytics.application.query_policy
        ▲
        │ QueryPolicy protocol
app.analytics.infrastructure.sql_policy
        │
        └── sqlglot==30.18.0
```

The domain remains standard-library-only. The application layer knows only the domain contracts. SQLGlot is confined to infrastructure and is an exact direct dependency of the root backend project because production App code imports it.

Use the pure-Python package `sqlglot==30.18.0`, without optional compiled extras. Its version is exact because SQLGlot documents minor releases as potentially backwards-incompatible and AST shape is security-relevant behavior.

SQLGlot is a parser/transpiler, not the security decision-maker. Its parser is intentionally lenient and can fall back to generic command-like expressions. Therefore successful parsing never implies approval.

## 3. Public contracts

`app.analytics.domain.query` owns these frozen, slotted values:

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

@dataclass(frozen=True, slots=True)
class QueryPolicyRequest:
    sql: str
    engine: DatasourceEngine
    max_rows: int = 1_000

@dataclass(frozen=True, slots=True)
class PreparedQuery:
    sql: str
    engine: DatasourceEngine
    relations: tuple[str, ...]
    row_limit: int
    query_hash: str

@dataclass(frozen=True, slots=True)
class QueryPolicyDecision:
    allowed: bool
    risk: QueryRisk
    codes: tuple[QueryDecisionCode, ...]
    prepared: PreparedQuery | None = None
```

`QueryPolicyRequest` accepts an empty string so the policy can return the stable `EMPTY_SQL` decision. It rejects a non-string SQL value, an invalid engine, booleans masquerading as integers, and `max_rows` outside `1..10_000`.

`QueryPolicyDecision` enforces the following invariants:

- `codes` is a non-empty tuple of unique `QueryDecisionCode` values.
- an allowed decision has a prepared query and cannot be `BLOCKED`;
- a denied decision has no prepared query;
- a `BLOCKED` decision is denied.

`PreparedQuery.relations` is a deterministic inventory for audit and later authorization. It is **not** evidence that a relation is allowed. `PreparedQuery` is also **not executable authority**; only Phase 2B may issue a short-lived server-side plan ID after permission and cost checks.

The application port is synchronous because this phase performs deterministic in-process CPU work only:

```python
@runtime_checkable
class QueryPolicy(Protocol):
    def evaluate(self, request: QueryPolicyRequest) -> QueryPolicyDecision: ...
```

## 4. Deterministic evaluation order

`SqlglotQueryPolicy.evaluate()` performs checks in this exact order and returns the first blocking decision:

1. Trim only for emptiness detection; do not use regexes to classify SQL.
2. Map `DatasourceEngine.MYSQL` to SQLGlot `mysql` and `DatasourceEngine.POSTGRESQL` to SQLGlot `postgres`.
3. Parse with an explicit `read` dialect. Catch SQLGlot errors and return `PARSE_ERROR` without exposing parser text.
4. Drop parser `None` entries and require exactly one statement; more than one returns `MULTIPLE_STATEMENTS`.
5. Allow only a `Select` root or a SQLGlot `SetOperation` root containing a `Select`. Everything else, including `Show`, `Values`, aliases, and generic `Command`, returns `UNSUPPORTED_STATEMENT`.
6. Walk the complete AST and reject any forbidden operation node, including a write hidden inside a CTE. Return `FORBIDDEN_OPERATION`.
7. Reject projection wildcards (`SELECT *`, `SELECT t.*`). `COUNT(*)` is the only allowed star form. Return `WILDCARD_PROJECTION`.
8. Reject the fixed dangerous-function denylist, case-insensitively. Return `DANGEROUS_FUNCTION`.
9. Reject any `OFFSET`, including nested offsets. Return `OFFSET_NOT_ALLOWED`.
10. Inspect the root query's top-level `LIMIT`:
    - no limit: inject `max_rows` and add `LIMIT_APPLIED`;
    - integer limit in `0..max_rows`: preserve it;
    - integer limit above `max_rows`: replace it with `max_rows` and add `LIMIT_REDUCED`;
    - a negative integer: return `INVALID_LIMIT`;
    - a placeholder, expression, identifier, or other non-literal: return `NON_LITERAL_LIMIT`.
11. Serialize using the same explicit dialect with `pretty=False`.
12. Reparse the serialized SQL with the same dialect and re-run the structural, forbidden-operation, wildcard, dangerous-function and offset checks. Any failure is denied; never return SQL that was not reparsed.
13. Extract sorted unique physical relation names, excluding unqualified references to CTE aliases. Preserve up to `catalog.schema.table` components as exposed by SQLGlot.
14. Compute `sha256(engine.value + "\0" + normalized_sql)` as lowercase hex.
15. Classify `MEDIUM` if the AST contains a join, CTE, set operation, window, or subquery; otherwise classify `LOW`. Add `COMPLEX_QUERY` for `MEDIUM`, then append `APPROVED` as the final code.

`HIGH` is reserved for Phase 2B permission, PII, cross-schema, Cartesian-risk, and `EXPLAIN` cost outcomes. Phase 2A must not pretend that syntax alone can establish those facts.

## 5. Forbidden syntax

The AST denylist contains the concrete SQLGlot 30.18.0 expression classes for:

```text
Insert, Update, Delete, Create, Drop, Alter, Merge,
Command, Copy, Transaction, Commit, Rollback,
Grant, Revoke, TruncateTable, Use, Set, Cache, Uncache,
Execute, Into, Lock
```

Root allowlisting remains mandatory even with this denylist. That makes unknown or newly parsed statement families fail closed instead of relying on an exhaustive blacklist.

The initial dangerous-function denylist is:

```text
benchmark, dblink, dblink_exec, load_file, lo_export, lo_import,
pg_cancel_backend, pg_ls_dir, pg_read_binary_file, pg_read_file,
pg_sleep, pg_stat_file, pg_terminate_backend, set_config, sleep,
sys_eval, sys_exec
```

This denylist is defense in depth, not a complete UDF authorization model. Phase 2B must validate functions against datasource policy and use a restricted read-only database identity.

## 6. Risk and evidence semantics

Allowed decision code order is deterministic:

```text
[LIMIT_APPLIED or LIMIT_REDUCED if applicable]
[COMPLEX_QUERY if applicable]
APPROVED
```

A blocked decision carries exactly one blocking code, `risk=BLOCKED`, and no prepared query. Parser exception messages and raw stack traces never enter domain decisions.

Normalized SQL is retained because it is required for the later governed execution path. No SQL is executed or persisted in 2A. Future audit persistence must store a redacted SQL form and the hash; sensitive result rows are never audit data.

## 7. Acceptance matrix

Both MySQL and PostgreSQL must cover:

- simple `SELECT` approval and exact top-level limit injection;
- preservation of a small literal limit and reduction of an oversized limit;
- empty, malformed and multiple-statement rejection;
- rejection of DDL, DML, transaction/command/export/lock syntax;
- rejection of write operations nested inside CTEs;
- rejection of `SELECT *` and qualified stars, while allowing `COUNT(*)`;
- rejection of dangerous functions regardless of case;
- rejection of offsets and non-literal/negative limits;
- CTE relation alias exclusion and deterministic physical relation inventory;
- `MEDIUM` classification for joins, CTEs, set operations, windows and subqueries;
- same-dialect serialization and successful reparse;
- stable SHA-256 for identical engine + normalized SQL and different hashes across dialects;
- no import of SQLGlot from `domain/` or `application/`;
- continued Harness-to-App boundary enforcement.

## 8. Explicit non-goals and next gate

Phase 2A must not add:

- table, column, row, function, metric, PII, or tenant authorization;
- schema introspection or cache;
- database drivers, pools, connections, `EXPLAIN`, transactions, or execution;
- credentials or secret resolution;
- plan IDs, audit persistence, ORM models, migrations, APIs, Agent tools, MCP tools, UI, Docker, or Harness edits.

Phase 2B may begin only after architecture review confirms that the 2A decision is fail-closed, normalized SQL is bounded and reparsed, the prepared value is non-executable, and all focused security cases pass.
