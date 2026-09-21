# Analytics Domain Guide

`app.analytics` owns InsightFlow's business-analysis domain. It may import the generic `deerflow.*` Harness only from future composition/agent adapters; Harness must never import this package.

## Layer rules

- `domain/`: standard library only; immutable business contracts and deterministic policies.
- `application/`: use cases and async ports; may import `domain/`, never delivery/runtime frameworks.
- `infrastructure/`: added with real MySQL/PostgreSQL/SQLGlot/repository adapters in Phase 2.
- `agent/`: added with real tools and immutable Agent definitions in Phase 3.
- `api/`: added with real FastAPI routes in Phase 2; routes call application use cases.

Never store or pass a raw datasource password/DSN in domain objects. Domain objects carry only an opaque `secret_ref`; credential resolution belongs to infrastructure. Every new dependency direction must remain covered by `tests/test_analytics_boundaries.py`.

Run focused checks from `backend/`:

```bash
PYTHONPATH=. uv run --locked pytest tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py -q
uv run --locked ruff check app/analytics tests/test_analytics_domain.py tests/test_analytics_boundaries.py
```
