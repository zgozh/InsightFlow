# Phase 2C1 Durable Analytics Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repository requires one final Phase 2C1 commit, so preserve RED/GREEN evidence in the ignored review report instead of making intermediate commits.

**Goal:** Persist the Analytics catalogs, one-shot execution plans, and query-audit ledger in the application database without exposing HTTP or Agent delivery surfaces.

**Architecture:** `app.analytics` owns a separate SQLAlchemy metadata and Alembic chain, injected with the already-created application `AsyncEngine` and `async_sessionmaker`. Catalogs remain principal-scoped and default-deny; SQL plans are atomically deleted-and-returned by the database; every real business-database operation is preceded by a durable audit-start row.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Alembic, SQLite for offline tests, PostgreSQL 16 for the explicit integration gate, pytest/pytest-asyncio, Ruff.

**Spec:** `docs/architecture/phase-02c1-durable-analytics-control-plane.md`

## Global Constraints

- Start from `456b57a302b5fe95531a43b11361653a1a8e7d8f`; parent must remain the accepted Phase 2B2 Fix 01 commit `09cbd28a49e2718ff4d72c52a3ae49e78ce295d1`.
- Fixed baseline tag remains `upstream-v2.1.0-rc0` at commit `609bfde0ced76ff0a58c02ff5c741df768f44502`, tree `2473c22e163a3879490848a7995eb2b7be7f6f50`.
- One final commit only: `feat: add durable analytics control plane`. Do not amend the architecture commit.
- New/modified comments, docstrings, complex test explanations, architecture docs and review report are Chinese-first. Python identifiers, API-independent protocol names, enum values and database identifiers remain English.
- No FastAPI routes, Gateway lifespan/composition, config schema, Agent Tool, MCP, frontend, Redis, queue, background cleanup worker, new container or Phase 2C2 work.
- Do not modify `backend/pyproject.toml` or `backend/uv.lock`; SQLAlchemy and Alembic already exist. Every `uv` command uses `--locked` and sets `UV_DEFAULT_INDEX=https://pypi.org/simple` when the local environment requires it.
- Application/domain dependency boundaries stay intact. Analytics infrastructure may import SQLAlchemy/Alembic but not `deerflow`, `app.gateway`, FastAPI or LangChain.
- Never log or persist raw plan tokens, credentials, DSNs, driver error text, original user SQL, raw EXPLAIN JSON or result values. Only the short-lived plan payload may contain canonical Phase 2A SQL and opaque `secret_ref`.
- Keep total new/modified production Python files at or below 22. Stop and report before exceeding it.

---

## File Structure

### Domain and application

- Create `backend/app/analytics/domain/audit.py` — immutable audit values and enums.
- Modify `backend/app/analytics/domain/execution.py` — add `AUDIT_UNAVAILABLE` only.
- Modify `backend/app/analytics/domain/__init__.py` — explicit exports.
- Create `backend/app/analytics/application/persistence_ports.py` — repository/audit protocols and stable persistence exceptions.
- Modify `backend/app/analytics/application/execution_ports.py` — add `ExecutionPlanStore.revoke()`.
- Modify `backend/app/analytics/application/execution.py` — mandatory audit gate around plan/execute external I/O.
- Modify `backend/app/analytics/application/__init__.py` — explicit exports.

### Infrastructure

- Create `backend/app/analytics/infrastructure/persistence/__init__.py` — narrow public adapter exports.
- Create `backend/app/analytics/infrastructure/persistence/models.py` — `AnalyticsBase` and six `analytics_*` tables.
- Create `backend/app/analytics/infrastructure/persistence/codec.py` — explicit versioned JSON codecs.
- Create `backend/app/analytics/infrastructure/persistence/catalogs.py` — datasource/schema/policy/metric repositories.
- Create `backend/app/analytics/infrastructure/persistence/plan_store.py` — SQL one-shot plan store.
- Create `backend/app/analytics/infrastructure/persistence/audit_log.py` — SQL audit start/finish adapter.
- Create `backend/app/analytics/infrastructure/persistence/bootstrap.py` — fail-closed Analytics Alembic bootstrap.
- Create `backend/app/analytics/infrastructure/persistence/migrations/alembic.ini`.
- Create `backend/app/analytics/infrastructure/persistence/migrations/env.py`.
- Create `backend/app/analytics/infrastructure/persistence/migrations/script.py.mako`.
- Create `backend/app/analytics/infrastructure/persistence/migrations/versions/0001_analytics_control_plane.py`.
- Modify `backend/app/analytics/infrastructure/execution_plan_store.py` — implement in-memory `revoke()` for protocol parity.
- Modify `backend/app/analytics/infrastructure/__init__.py` — export only production adapters needed by later composition.
- Modify `backend/packages/harness/deerflow/persistence/migrations/_env_filters.py` — exclude the App-owned `analytics_` prefix from the host migration view without importing App.

### Tests and orchestration

- Create `backend/tests/test_analytics_audit_domain.py`.
- Create `backend/tests/test_analytics_persistence_codec.py`.
- Create `backend/tests/test_analytics_persistence_migrations.py`.
- Create `backend/tests/test_analytics_persistence_repositories.py`.
- Create `backend/tests/test_analytics_sql_plan_store.py`.
- Create `backend/tests/test_analytics_sql_audit_log.py`.
- Create `backend/tests/test_analytics_persistence_postgresql.py`.
- Modify `backend/tests/test_query_execution_use_cases.py`.
- Modify `backend/tests/test_execution_plan_store.py`.
- Modify `backend/tests/test_analytics_boundaries.py`.
- Modify `backend/tests/test_persistence_migrations_env.py`.
- Modify `scripts/test_analytics_databases.py` — add the PostgreSQL persistence file to the existing explicit PostgreSQL gate; do not change MySQL coverage.
- Modify `backend/app/analytics/AGENTS.md` and `docs/PROGRESS.md`.
- Add this plan and `docs/prompts/phase-02c1-durable-analytics-control-plane.md` to the final commit.

---

### Task 1: Add audit domain values and persistence ports

**Files:** domain audit/execution/init, application persistence ports/execution ports/init, `test_analytics_audit_domain.py`, boundary tests.

**Interfaces:**

```python
class QueryAuditPhase(StrEnum):
    POLICY = "policy"
    AUTHORIZATION = "authorization"
    PLAN = "plan"
    EXECUTE = "execute"

class QueryAuditStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"

@dataclass(frozen=True, slots=True)
class QueryAuditStart:
    principal_id: str
    datasource_id: str | None
    phase: QueryAuditPhase
    started_at: datetime
    query_hash: str | None = None
    risk: QueryRisk | None = None
    schema_version: str | None = None
    policy_version: str | None = None

@dataclass(frozen=True, slots=True)
class QueryAuditCompletion:
    audit_id: str
    decision_code: str
    finished_at: datetime
    risk: QueryRisk | None = None
    estimated_rows: int | None = None
    engine_cost: Decimal | None = None
    plan_digest: str | None = None
    row_count: int | None = None
    byte_count: int | None = None
    truncated: bool | None = None
    latency_ms: int | None = None
```

`QueryAuditStart` validates trimmed identities, optional 64-character lowercase digest, aware time and paired schema/policy metadata. `QueryAuditCompletion` validates a trimmed opaque audit ID/decision, aware time, non-negative integer measurements, finite non-negative Decimal, optional 64-character plan digest, and real bool for nullable flags. It carries no SQL, result rows or exception text.

Application protocols:

```python
class PersistenceConflictError(Exception):
    def __init__(self, reason: str) -> None: ...

class PersistenceDataError(Exception):
    def __init__(self, reason: str) -> None: ...

@runtime_checkable
class DatasourceAdminRepository(Protocol): ...

@runtime_checkable
class SchemaSnapshotRepository(SchemaCatalog, Protocol):
    async def replace(self, snapshot: SchemaSnapshot, *, expected_version: str | None) -> None: ...

@runtime_checkable
class AccessPolicyRepository(AccessPolicyCatalog, Protocol):
    async def replace(self, policy: PrincipalAccessPolicy, *, expected_version: str | None) -> None: ...
    async def remove(self, *, datasource_id: str, principal_id: str) -> None: ...

@runtime_checkable
class MetricRepository(MetricCatalog, Protocol): ...

@runtime_checkable
class QueryAuditLog(Protocol):
    async def start(self, entry: QueryAuditStart) -> str: ...
    async def finish(self, completion: QueryAuditCompletion) -> None: ...
```

Add `AUDIT_UNAVAILABLE = "audit_unavailable"` to `ExecutionDecisionCode` and
`revoke(*, token_digest: str) -> None` to `ExecutionPlanStore`.

- [ ] Write RED tests for all audit invariants, runtime-checkable ports, the new decision code and `revoke` protocol shape.
- [ ] Run `uv run --locked pytest tests/test_analytics_audit_domain.py tests/test_analytics_boundaries.py tests/test_query_execution_domain.py -q`; record the expected failures.
- [ ] Implement the minimal domain values/protocols/exports, keeping domain standard-library-only and application runtime-independent.
- [ ] Run the same tests GREEN plus focused Ruff check/format.

### Task 2: Implement explicit codecs and ORM tables

**Files:** persistence `models.py`, `codec.py`, codec tests.

Use a private `AnalyticsBase(DeclarativeBase)`; never subclass or mutate Harness `Base`. Define exactly:

- `analytics_datasources`
- `analytics_schema_snapshots`
- `analytics_access_policies`
- `analytics_metrics`
- `analytics_execution_plans`
- `analytics_query_audits`

Use named unique/check constraints and indexes described by the spec. Cross-chain user foreign keys are forbidden. Internal analytics references may use named FKs, but datasource deletion remains unsupported and audit history must not cascade away.

Codec API:

```python
PLAN_PAYLOAD_VERSION = 1
MAX_PLAN_PAYLOAD_BYTES = 1024 * 1024

def encode_schema_snapshot(value: SchemaSnapshot) -> str: ...
def decode_schema_snapshot(payload: str) -> SchemaSnapshot: ...
def encode_access_policy(value: PrincipalAccessPolicy) -> str: ...
def decode_access_policy(payload: str) -> PrincipalAccessPolicy: ...
def encode_dimensions(value: tuple[str, ...]) -> str: ...
def decode_dimensions(payload: str) -> tuple[str, ...]: ...
def encode_stored_plan(value: StoredExecutionPlan) -> str: ...
def decode_stored_plan(payload: str, *, payload_version: int) -> StoredExecutionPlan: ...
```

Use explicit dictionaries and exact key-set checks. JSON uses `ensure_ascii=False`, compact separators and `sort_keys=True`; Decimal is a canonical finite string; datetimes are aware ISO 8601 normalized to UTC. Reconstruct every nested domain dataclass on decode. Convert any malformed/oversized payload to `PersistenceDataError` with a stable reason and no payload text.

- [ ] Write RED round-trip tests covering PostgreSQL/MySQL values, nested relations/columns/functions, exact tuple restoration and equality.
- [ ] Add RED corruption tests for unknown/missing keys, unknown version/enum, duplicate values, naive datetime, float cost, non-finite values, unknown nested shape and 1 MiB overflow.
- [ ] Implement tables and codecs, then run the new file GREEN and Ruff.
- [ ] Add a source assertion that codec code contains no `pickle`, dynamic import, `repr(` fallback or unchecked `dataclasses.asdict` persistence.

### Task 3: Add the independent Analytics migration chain

**Files:** migration skeleton/revision/bootstrap, host env filter, migration tests.

The Analytics Alembic env must use `AnalyticsBase.metadata`, `version_table="analytics_alembic_version"`, and a caller-supplied existing connection via `config.attributes["connection"]`. It must not create a second engine from a DSN during production bootstrap. The initial revision creates the exact six-table model and named indexes; downgrade drops only those tables in reverse dependency order.

`bootstrap_analytics_schema(engine, *, backend: str) -> None` must:

1. serialize same-process calls per engine;
2. open an engine transaction;
3. use a distinct fixed PostgreSQL advisory lock, or SQLite `PRAGMA busy_timeout=30000` plus database write serialization;
4. reflect Analytics tables/version state;
5. reject unknown/multiple/empty-but-populated revision states;
6. run `alembic upgrade head` through the supplied connection;
7. leave errors fatal and sanitized.

Modify the host `_env_filters.py` with a constant fixed prefix set containing only `"analytics_"`. `include_object` must exclude tables, indexes and constraints below that prefix. Do not reuse the mutable extension prefix registry and do not import `app.analytics` from Harness.

- [ ] Write RED SQLite migration tests for empty upgrade, repeated upgrade, downgrade/upgrade, exact head/version table, model-vs-migration table parity and unknown/empty/multiple revision rejection.
- [ ] Write RED host-filter tests showing `analytics_datasources`, `analytics_alembic_version` and child indexes/constraints are excluded while similar names such as `analytic_events` remain included.
- [ ] Implement the migration chain/bootstrap/filter and run both new and existing migration-filter suites GREEN.
- [ ] Run `git diff --check` and focused Ruff before moving on.

### Task 4: Implement principal-scoped catalogs

**Files:** `catalogs.py`, repository tests.

Adapters take an injected `async_sessionmaker[AsyncSession]`; no globals. Required classes:

```python
class SqlDatasourceRepository(DatasourceCatalog, DatasourceAdminRepository): ...
class SqlSchemaSnapshotRepository(SchemaSnapshotRepository): ...
class SqlAccessPolicyRepository(AccessPolicyRepository): ...
class SqlMetricRepository(MetricRepository): ...
```

Required behavior:

- datasource accessible reads require an exact policy row for `(datasource_id, principal_id)` and active status; owner alone grants nothing;
- owned/admin reads use exact owner and never accept `None` as cross-user scope;
- datasource list order is `(name, id)`;
- schema/policy replace locks the current row, requires `expected_version`, treats exact equality as idempotent, rejects same-version drift and stale expected version with stable conflict reasons;
- policy removal is exact datasource+principal and idempotent;
- metric reads/writes are exact-owner and list by `(key, version)`; equal writes are idempotent, a changed same/lower version is rejected, a higher version replaces;
- every row decode re-runs domain invariants; corruption raises `PersistenceDataError`, never returns partial values.

- [ ] Write RED tests for two principals/two owners, including explicit attempts to read another user's datasource and metric.
- [ ] Add RED transaction/conflict/idempotency/corrupt-row tests.
- [ ] Implement repositories and run repository, domain, authorization and boundary suites GREEN.

### Task 5: Implement the SQL one-shot plan store

**Files:** `plan_store.py`, in-memory store parity, SQL/in-memory tests.

`SqlExecutionPlanStore` constructor:

```python
def __init__(
    self,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    max_entries: int,
) -> None: ...
```

Implement `put`, `claim`, `purge_expired`, and `revoke`. `claim` must execute one database `DELETE ... RETURNING` by digest, commit deletion, then validate principal/expiry/decode; validation failure returns `None` after consumption. Never SELECT before DELETE. PostgreSQL capacity uses one stable transaction advisory lock; SQLite begins an immediate write transaction. Purge before count, reject collisions/capacity with existing stable reasons, and keep the capacity transaction shorter than any external I/O.

`InMemoryExecutionPlanStore.revoke()` removes the digest under its existing lock and is idempotent.

- [ ] Write RED SQL-store tests for round-trip, token-digest-only storage, capacity, purge, revoke, wrong principal consumption, expiry consumption and corrupt payload consumption.
- [ ] Add a concurrency test using two independent session factories/repository instances; exactly one claim returns a plan.
- [ ] Add source/spy evidence that claim is delete-returning rather than select-then-delete and that no `asyncio.Lock` exists in the SQL adapter.
- [ ] Implement and run SQL-store plus existing in-memory store tests GREEN.

### Task 6: Make audit a mandatory execution gate

**Files:** `audit_log.py`, `application/execution.py`, execution/audit tests.

`SqlQueryAuditLog.start()` inserts a `started` row with a generated UUID and returns only that ID. `finish()` updates exactly one matching started row to completed; zero/multiple rows is a stable persistence error. Neither method accepts arbitrary dicts.

Refactor plan/execute use cases around a small internal finalization helper; do not duplicate audit error logic across every return. Required event ordering:

```text
plan: audit:start -> datasource -> authorize -> explain -> datasource -> authorize
      -> store:put -> audit:finish -> return PLAN_CREATED

execute: store:claim -> audit:start -> datasource -> authorize -> gateway:execute
         -> audit:finish -> return result
```

Rules:

- audit start failure returns `AUDIT_UNAVAILABLE` and performs zero subsequent business-database calls;
- plan finish failure revokes any inserted plan and never returns its token;
- execute finish failure returns no result and leaves the audit row started;
- cancel propagates `CancelledError`; use a bounded shielded best-effort finish without swallowing cancellation;
- audit values use query hash, risk, versions, cost/result counts and latency only—never SQL/result cells/errors/token digest;
- all old 2B2 ordering, triple authorization, cost, stale and one-shot tests continue to pass after their fakes receive the new required audit dependency.

- [ ] Write RED adapter tests and use-case ordering/failure/cancellation tests first.
- [ ] Implement the adapter and use-case refactor.
- [ ] Run `test_query_execution_use_cases.py`, plan-store/audit tests, Phase 2A/2B1 regressions and boundary tests GREEN.

### Task 7: Add the explicit PostgreSQL 16 persistence gate

**Files:** PostgreSQL persistence integration test and root test script.

Reuse the existing PostgreSQL 16 service and tester credentials. The test creates a unique temporary schema, two independent engines/session factories and destroys the schema in `finally`. It must cover:

- bootstrap to Analytics head twice;
- two independent adapters concurrently claiming one plan, exactly one success;
- concurrent capacity checks never exceeding `max_entries`;
- stale `expected_version` replacement conflict without lost data;
- audit start failure preventing the fake business gateway from being called;
- audit finish failure suppressing the returned result.

Change `scripts/test_analytics_databases.py` so the PostgreSQL engine maps to both the existing business-runtime integration file and the new persistence integration file. Keep `--engine mysql` unchanged; `--engine all` continues to run both database families and cleans up in `finally`.

- [ ] Write the integration test with an explicit `ANALYTICS_TEST_POSTGRESQL=1` skip gate; ordinary pytest collection remains offline.
- [ ] Run its collection offline and prove it skips without Docker/env.
- [ ] Run `python scripts/test_analytics_databases.py --engine postgresql`, record exact image/version, counts and exit code.
- [ ] Run the combined real-database gate once at final acceptance only; do not repeatedly pull or restart containers during development.

### Task 8: Documentation, final gates and one commit

**Files:** analytics guide, progress ledger, prompt/plan and ignored review report.

- [ ] Update `backend/app/analytics/AGENTS.md` with App-owned migration ownership, exact principal scoping, short-lived canonical-SQL plan exception, atomic delete-returning claim, audit fail-closed ordering and commands.
- [ ] Update `docs/PROGRESS.md`: Phase 2 remains `In progress`; evidence includes accepted 2B2 Fix 01 and 2C1; next gate is `Phase 2C1 GPT 复验`. Do not mark Phase 2 complete or start 2C2.
- [ ] Record RED/GREEN evidence, migration head/table list, Postgres version, test counts, commit boundary, file budget and deviations in ignored `.reviews/phase-02c1-implementation-report.md`.
- [ ] Run lock and focused offline gates:

```powershell
$env:UV_DEFAULT_INDEX='https://pypi.org/simple'
uv lock --check
uv run --locked pytest tests/test_analytics_audit_domain.py tests/test_analytics_persistence_codec.py tests/test_analytics_persistence_migrations.py tests/test_analytics_persistence_repositories.py tests/test_analytics_sql_plan_store.py tests/test_analytics_sql_audit_log.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py tests/test_query_execution_domain.py tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_persistence_migrations_env.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_analytics_audit_domain.py tests/test_analytics_persistence_codec.py tests/test_analytics_persistence_migrations.py tests/test_analytics_persistence_repositories.py tests/test_analytics_sql_plan_store.py tests/test_analytics_sql_audit_log.py tests/test_analytics_persistence_postgresql.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py tests/test_analytics_boundaries.py tests/test_persistence_migrations_env.py
uv run --locked ruff format --check app/analytics tests/test_analytics_audit_domain.py tests/test_analytics_persistence_codec.py tests/test_analytics_persistence_migrations.py tests/test_analytics_persistence_repositories.py tests/test_analytics_sql_plan_store.py tests/test_analytics_sql_audit_log.py tests/test_analytics_persistence_postgresql.py tests/test_query_execution_use_cases.py tests/test_execution_plan_store.py
```

- [ ] Run `python scripts/test_analytics_databases.py --engine all` once after offline GREEN.
- [ ] Run `git diff --check`, exact changed-file boundary checks, tag/tree checks, lock hash comparison and production-file budget.
- [ ] Create exactly one implementation commit:

```text
feat: add durable analytics control plane
```

- [ ] Confirm clean worktree and stop. Phase 2C2 must remain unstarted.

## Self-Review

- Every persistence object, migration ownership rule, audit failure condition and security prohibition in the approved spec maps to a task and test.
- The plan introduces no delivery/API/config/Agent surface and no new dependency or container.
- The application layer receives protocols and immutable values only; SQLAlchemy remains infrastructure-only.
- Multi-worker correctness is proved with independent PostgreSQL connections, not an in-process lock.
- File decomposition is by catalog, plan, audit, codec and migration responsibility; it avoids per-table controller/service boilerplate.

