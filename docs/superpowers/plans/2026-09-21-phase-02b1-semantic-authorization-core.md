# Phase 2B1 Semantic Authorization Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an authentic Phase 2A `PreparedQuery` plus immutable schema and principal policy into a deterministic, non-executable semantic authorization decision.

**Architecture:** Standard-library-only domain values model schema, policy and decisions; application owns async catalogs and the orchestration use case; infrastructure owns SQLGlot qualification and physical lineage. All schema entities and functions are default-deny, HIGH decisions are denied in V1, and no database execution capability is added.

**Tech Stack:** Python 3.12, frozen dataclasses, async Protocol ports, SQLGlot 30.18.0 already pinned, pytest, Ruff, uv.

**Spec:** `docs/architecture/phase-02b1-semantic-authorization-core.md`

## Global Constraints

- Start from `f2d35d337b9c9f6abb96918fec0e0ee996402713` on `main` with a clean tree except the three architect-owned 2B1 documents.
- Keep `upstream-v2.1.0-rc0` at commit `609bfde0ced76ff0a58c02ff5c741df768f44502`, tree `2473c22e163a3879490848a7995eb2b7be7f6f50`.
- Add no dependency and do not change `backend/uv.lock`.
- Domain is standard-library-only; application cannot import SQLGlot or delivery/runtime frameworks.
- Do not add drivers, secrets, connections, SQL execution, EXPLAIN, plan IDs, ORM, migrations, API, Agent, MCP, UI or Docker changes.
- Revalidate every `PreparedQuery` through Phase 2A and require exact equality before semantic authorization.
- Tables, columns and functions are default-deny. HIGH is denied with `APPROVAL_REQUIRED`.
- Run uv with `UV_DEFAULT_INDEX=https://pypi.org/simple` and `--locked`.
- Use one commit: `feat: add semantic query authorization core`.
- The known native-Windows full-suite baseline remains NOT RUN; do not claim it passes.

## File map

Create:

- `backend/app/analytics/domain/schema.py`
- `backend/app/analytics/domain/access_policy.py`
- `backend/app/analytics/domain/authorization.py`
- `backend/app/analytics/application/authorization.py`
- `backend/app/analytics/infrastructure/semantic_authorizer.py`
- `backend/tests/test_query_authorization_domain.py`
- `backend/tests/test_authorize_prepared_query.py`
- `backend/tests/test_semantic_authorizer.py`

Modify:

- `backend/app/analytics/domain/__init__.py`
- `backend/app/analytics/application/__init__.py`
- `backend/app/analytics/infrastructure/__init__.py`
- `backend/app/analytics/AGENTS.md`
- `backend/tests/test_analytics_boundaries.py`
- `docs/PROGRESS.md`

Commit unchanged:

- `docs/architecture/phase-02b1-semantic-authorization-core.md`
- `docs/superpowers/plans/2026-09-21-phase-02b1-semantic-authorization-core.md`
- `docs/prompts/phase-02b1-semantic-authorization-core.md`

---

### Task 1: Add immutable schema, policy and authorization contracts

**Files:** domain modules, domain exports, `test_query_authorization_domain.py`.

**Produces:** every exact type and enum in spec section 3.

- [ ] Write failing tests first for frozen/slotted values, enum storage values, trimmed strings, enum types, tuple-only collections, duplicate relation/column/function rejection, lowercase function names, identity fields and decision invariants.

Representative required assertions:

```python
def test_policy_is_default_deny_when_collections_are_empty():
    policy = PrincipalAccessPolicy(
        datasource_id="ds-1",
        principal_id="user-1",
        version="p1",
        relations=(),
        allowed_functions=(),
    )
    assert policy.relations == ()
    assert policy.allowed_functions == ()


def test_allowed_decision_requires_non_high_authorized_value():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=True,
            risk=QueryRisk.HIGH,
            codes=(AuthorizationDecisionCode.APPROVED,),
        )


def test_authorized_value_has_no_execution_authority():
    assert {field.name for field in fields(AuthorizedQuerySpec)} == {
        "prepared", "datasource_id", "principal_id", "schema_version",
        "policy_version", "relations", "columns", "functions", "risk",
    }
```

- [ ] Run RED:

```powershell
uv run --locked pytest tests/test_query_authorization_domain.py -q
```

Expected: collection failure for missing contracts. Record it.

- [ ] Implement the exact spec contracts with frozen/slotted dataclasses and small local validators. Do not add behavior, repositories or serialization frameworks.

- [ ] Export the contracts from `domain/__init__.py`; run domain GREEN and Ruff:

```powershell
uv run --locked pytest tests/test_query_authorization_domain.py tests/test_query_policy_domain.py tests/test_analytics_domain.py -q
uv run --locked ruff check app/analytics/domain tests/test_query_authorization_domain.py
uv run --locked ruff format --check app/analytics/domain tests/test_query_authorization_domain.py
```

---

### Task 2: Add application ports and authorization orchestration

**Files:** `application/authorization.py`, application exports, `test_authorize_prepared_query.py`, boundary tests.

**Produces:** `SchemaCatalog`, `AccessPolicyCatalog`, `SemanticQueryAuthorizer`, `AuthorizePreparedQuery`.

- [ ] Write RED tests using minimal in-memory fakes for the four paths: inaccessible/disabled datasource, missing or mismatched schema, missing or mismatched policy, and successful delegation.

Required signatures:

```python
class SchemaCatalog(Protocol):
    async def get_current(self, *, datasource_id: str) -> SchemaSnapshot | None: ...

class AccessPolicyCatalog(Protocol):
    async def get_effective(
        self, *, principal_id: str, datasource_id: str
    ) -> PrincipalAccessPolicy | None: ...

class SemanticQueryAuthorizer(Protocol):
    def authorize(
        self,
        *,
        prepared: PreparedQuery,
        schema: SchemaSnapshot,
        policy: PrincipalAccessPolicy,
    ) -> QueryAuthorizationDecision: ...
```

The use case constructor receives `DatasourceCatalog`, `SchemaCatalog`, `AccessPolicyCatalog` and `SemanticQueryAuthorizer`. `execute()` uses keyword-only `principal_id`, `datasource_id`, `prepared` and follows spec section 4 exactly.

- [ ] Run RED, implement minimal orchestration, then GREEN:

```powershell
uv run --locked pytest tests/test_authorize_prepared_query.py tests/test_analytics_boundaries.py -q
```

- [ ] Extend boundary tests so all three new protocols are runtime-checkable and domain/application still cannot import SQLGlot, Gateway, Harness, FastAPI, LangChain or SQLAlchemy. Do not ban SQLAlchemy from infrastructure because it belongs to 2B2.

---

### Task 3: Implement SQLGlot semantic authorization

**Files:** `infrastructure/semantic_authorizer.py`, infrastructure exports, `test_semantic_authorizer.py`.

**Produces:** `SqlglotSemanticAuthorizer(query_policy: QueryPolicy)` implementing `SemanticQueryAuthorizer`.

- [ ] Build reusable test fixtures with two relations:

```text
public.orders(id STANDARD, customer_id STANDARD, amount STANDARD,
              email PII, internal_note SENSITIVE)
public.customers(id STANDARD, region STANDARD)
```

The base policy permits both relations, standard columns, and only `count`, `sum`, `cast`. Separate fixtures add DENY and AGGREGATE_ONLY rules.

- [ ] Write RED tests for every spec acceptance category before production implementation. At minimum cover:

```text
approve: simple column query
approve: allowlisted COUNT(*) and SUM(amount)
approve: aliases, qualified JOIN, CTE and non-correlated subquery
block: forged PreparedQuery
block: unknown/ambiguous relation or column
block: relation/column absent from policy
block: COUNT when not allowlisted
block: nextval, setval, GET_LOCK, pg_advisory_lock, unknown_udf
block: correlated subquery
block: direct DENY or AGGREGATE_ONLY column
deny HIGH: aggregate-only column under aggregate
deny HIGH: PII/SENSITIVE column
deny HIGH: explicitly permitted cross-schema relation
deny HIGH: CROSS JOIN and join without ON/USING
```

For every denial assert `authorized is None` and no SQLGlot exception text appears in `repr(decision)`.

- [ ] Run RED and record actual failures:

```powershell
uv run --locked pytest tests/test_semantic_authorizer.py -q
```

- [ ] Implement the 14-step algorithm in spec section 5. Use explicit dialects, SQLGlot `qualify(..., validate_qualify_columns=True, allow_partial_qualification=False)` on a copy, and `traverse_scope()` for physical lineage.

Implementation requirements:

```text
- exact PreparedQuery revalidation happens first;
- identifier lookup is dialect-normalized and collision-safe;
- physical tables are checked even when no column is projected;
- derived sources are skipped only at the outer scope; their inner physical scopes are checked;
- any external/correlated column fails closed;
- exp.Func names are case-folded and all require explicit policy membership;
- errors are stable codes, never raw parser/optimizer messages;
- inventories are sorted unique tuples;
- no returned HIGH decision is allowed;
- original PreparedQuery SQL is not rewritten or mutated.
```

- [ ] Export only `SqlglotSemanticAuthorizer`, then run GREEN and the complete analytics set:

```powershell
uv run --locked pytest tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_sql_policy.py tests/test_query_policy_domain.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
```

---

### Task 4: Documentation, gates and atomic commit

- [ ] Update `backend/app/analytics/AGENTS.md` with the semantic default-deny rule, HIGH-denied rule, non-executable `AuthorizedQuerySpec`, and 2B2 ownership.

- [ ] Update `docs/PROGRESS.md`: Phase 2 remains In progress; evidence becomes ``2A `8a11d0e`, `f2d35d3`; 2B1 design/tests`` and next gate `Phase 2B1 architecture review`. Do not mark all Phase 2 complete.

- [ ] Run gates from `backend/`:

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

- [ ] Verify exact changed paths, clean lock diff, clean whitespace and fixed tag/tree. Full native-Windows suite remains NOT RUN with the recorded Phase 1 baseline.

- [ ] Commit all allowed files once:

```text
feat: add semantic query authorization core
```

- [ ] Append ignored `.reviews/phase-02b1-implementation-report.md` with RED/GREEN evidence, acceptance matrix, commit/parent, lock hash, boundary checks and deviations. Stop before 2B2.

## Plan self-review

- Every schema, policy, decision, port and algorithm requirement in the spec maps to a test and task.
- No database, driver, secret, EXPLAIN, plan ID, migration, API, Agent, Docker or dependency work is present.
- Unknown functions are default-deny, closing the known side-effect-function gap before execution exists.
- CTE/subquery lineage is supported; correlated lineage is explicitly rejected rather than guessed.
- HIGH remains denied and no authorization object carries execution authority.
