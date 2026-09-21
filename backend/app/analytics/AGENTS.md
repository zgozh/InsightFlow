# Analytics Domain Guide

`app.analytics` owns InsightFlow's business-analysis domain. It may import the generic `deerflow.*` Harness only from future composition/agent adapters; Harness must never import this package.

## Layer rules

- `domain/`: standard library only; immutable business contracts and deterministic policies.
- `application/`: use cases and ports; may import `domain/`, never delivery/runtime frameworks.
- `infrastructure/`: real adapters. `sql_policy.py` and `semantic_authorizer.py` are the only modules allowed to import `sqlglot`; the rest arrives with MySQL/PostgreSQL/repository work in Phase 2B2/2C.
- `agent/`: added with real tools and immutable Agent definitions in Phase 3.
- `api/`: added with real FastAPI routes in Phase 2C; routes call application use cases.

SQLGlot is a lenient parser, not a security validator. Successful parsing is never approval: the adapter allowlists the statement root, scans the whole AST for forbidden nodes, then serializes and re-parses before returning anything. Keep the pinned `sqlglot==30.18.0` exact — AST shape is security-relevant behaviour.

Normalized and prepared SQL accepts no SQL comments or optimizer hints, no session/property assignment (`SELECT @x := id`), and no unbound parameters (`?`, `:name`, `@name`, PostgreSQL `$n`). If a later phase supports parameterized execution it must first add an explicit immutable binding contract to the domain and then relax this rule deliberately — never widen the current policy in place.

`PreparedQuery` is syntax-approved and row-bounded, and is deliberately **not** executable authority. It is not a permission grant and not a query-plan token.

## Semantic authorization (Phase 2B1)

`SqlglotSemanticAuthorizer` never trusts a `PreparedQuery` because of its Python type: it re-runs Phase 2A with the same engine and row limit and requires exact equality, so a hand-built value cannot bypass syntax policy.

Authorization is default-deny. Every physical relation and every column must appear in both the schema snapshot and the effective principal policy; every SQL function — including `COUNT`, `SUM`, `CAST` and anonymous calls — must be explicitly allowlisted. `nextval`, `setval`, `GET_LOCK`, advisory locks and unknown UDFs are therefore denied; the Phase 2A dangerous-function denylist is only defense in depth and never an authorization mechanism. CTE and non-correlated subquery sources resolve through to physical tables; correlated subqueries fail closed rather than being guessed.

`PreparedQuery.relations` is a Phase 2A syntax artifact and is never used as a permission input — permissions come only from the qualified physical lineage.

`AuthorizedQuerySpec` records the reconciled lineage and the schema/policy versions, and is deliberately **not** executable authority: it has no plan ID, connection, credential or execute method. A HIGH result (sensitive/PII column, cross-schema relation, Cartesian join, aggregate-only column under an aggregate) is always **denied** with `APPROVAL_REQUIRED`; V1 has no path that turns HIGH into an approval.

Phase 2B2 owns secret resolution, database adapters, `EXPLAIN` cost checks, short-lived server-side plan IDs, read-only transactions, timeout/row/byte caps and result sanitization. It must recheck the schema and policy versions before issuing a plan ID, because a `PreparedQuery` or `AuthorizedQuerySpec` can go stale. Never hand either value to a database.

Never store or pass a raw datasource password/DSN in domain objects. Domain objects carry only an opaque `secret_ref`; credential resolution belongs to infrastructure. Every new dependency direction must remain covered by `tests/test_analytics_boundaries.py`.

## Commands

Every `uv` command uses `--locked` so a user-level mirror index cannot rewrite `uv.lock`; the only exception is the intentional `uv lock --upgrade-package <name>`, which must be followed by the coordinate-drift check in the phase plan.

```bash
PYTHONPATH=. uv run --locked pytest tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py tests/test_agent_guidance_check.py -q
uv run --locked ruff check app/analytics tests/test_semantic_authorizer.py tests/test_authorize_prepared_query.py tests/test_query_authorization_domain.py tests/test_query_policy_domain.py tests/test_sql_policy.py tests/test_analytics_boundaries.py
```
