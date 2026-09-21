# InsightFlow Phase 1 Analytics Domain Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a dependency-light `app.analytics` domain boundary with immutable datasource/metric contracts, async application ports, and executable architecture tests before database, API, or Agent integration begins.

**Architecture:** Phase 1 adds only the `domain` and `application` layers that already have concrete contracts. Domain code uses the Python standard library only; application ports may depend on the domain but not Gateway, Harness, FastAPI, LangChain, SQLAlchemy, or provider SDKs. Infrastructure, Agent, and API layers are intentionally created only in the phases that deliver working adapters, tools, and routes.

**Tech Stack:** Python 3.12+, frozen dataclasses, `StrEnum`, `typing.Protocol`, pytest, Ruff.

**Spec:** `docs/architecture/architecture-refactoring-report.md` sections 6, 8, 9, 11, 14 and 16; `docs/decisions/0001-insightflow-hard-fork.md`.

## Global Constraints

- Upstream remains fixed at DeerFlow `v2.1.0-rc0`; never move `upstream-v2.1.0-rc0`.
- Preserve the dependency direction `app -> harness`; Harness must never import `app`.
- Do not rename the `deerflow.*` Python namespace.
- Phase 1 does not add SQL parsing, database drivers, ORM models, migrations, routers, tools, subagents, UI, or dependencies.
- Domain code must not import FastAPI, LangChain, SQLAlchemy, Pydantic, `deerflow`, `app.gateway`, or provider SDKs.
- No datasource credential value, DSN, hostname, username, or password belongs in the domain model; only an opaque `secret_ref` is represented.
- Use TDD: capture a real failing test run before implementation and a passing run after implementation.
- Create one rollbackable phase commit; do not amend Phase 0 commits.
- Do not install or update dependencies and do not modify a lockfile.

---

### Task 1: Add the analytics domain boundary and executable contracts

**Files:**
- Create: `backend/app/analytics/AGENTS.md`
- Create: `backend/app/analytics/__init__.py`
- Create: `backend/app/analytics/domain/__init__.py`
- Create: `backend/app/analytics/domain/datasource.py`
- Create: `backend/app/analytics/domain/metric.py`
- Create: `backend/app/analytics/application/__init__.py`
- Create: `backend/app/analytics/application/ports.py`
- Create: `backend/tests/test_analytics_domain.py`
- Create: `backend/tests/test_analytics_boundaries.py`
- Modify: `docs/PROGRESS.md`
- Commit unchanged architect-authored files: `docs/superpowers/plans/2026-09-21-phase-01-analytics-domain-boundary.md`, `docs/prompts/phase-01-analytics-domain-boundary.md`

**Interfaces:**
- Produces: `DatasourceEngine`, `DatasourceStatus`, `DatasourceDefinition`
- Produces: `MetricStatus`, `MetricDefinition`
- Produces: async `DatasourceCatalog` and `MetricCatalog` protocols
- Consumes: Python standard library only in `domain`; domain contracts only in `application`

- [ ] **Step 1: Verify the reviewed starting point**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse upstream-v2.1.0-rc0
git rev-parse 'upstream-v2.1.0-rc0^{tree}'
```

Expected:

- `HEAD` is `aa516bd4f1120aafaa00a9ce1f5105fcda5cf2b3`.
- Baseline tag is `609bfde0ced76ff0a58c02ff5c741df768f44502`.
- Baseline tree is `2473c22e163a3879490848a7995eb2b7be7f6f50`.
- Only the architect-authored Phase 1 plan and prompt may be untracked. Stop if any other path is dirty.

- [ ] **Step 2: Write the domain tests before production code**

Create `backend/tests/test_analytics_domain.py` with tests equivalent to the following. Keep the assertions; do not weaken them to fit an implementation.

```python
from dataclasses import FrozenInstanceError

import pytest

from app.analytics.domain import (
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    MetricDefinition,
    MetricStatus,
)


def test_datasource_definition_is_immutable_and_contains_only_secret_reference():
    datasource = DatasourceDefinition(
        id="sales-primary",
        owner_id="user-1",
        name="Sales warehouse",
        engine=DatasourceEngine.POSTGRESQL,
        secret_ref="env:SALES_DATABASE_SECRET",
        default_schema="analytics",
    )

    assert datasource.status is DatasourceStatus.ACTIVE
    assert datasource.secret_ref == "env:SALES_DATABASE_SECRET"
    assert not hasattr(datasource, "password")
    assert not hasattr(datasource, "dsn")
    with pytest.raises(FrozenInstanceError):
        datasource.name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize("field", ["id", "owner_id", "name", "secret_ref"])
def test_datasource_definition_rejects_blank_required_values(field: str):
    values = {
        "id": "sales-primary",
        "owner_id": "user-1",
        "name": "Sales warehouse",
        "engine": DatasourceEngine.MYSQL,
        "secret_ref": "env:SALES_DATABASE_SECRET",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        DatasourceDefinition(**values)


def test_datasource_definition_rejects_untrimmed_schema():
    with pytest.raises(ValueError, match="default_schema"):
        DatasourceDefinition(
            id="sales-primary",
            owner_id="user-1",
            name="Sales warehouse",
            engine=DatasourceEngine.MYSQL,
            secret_ref="env:SALES_DATABASE_SECRET",
            default_schema=" analytics ",
        )


def test_datasource_engine_values_are_stable_storage_contracts():
    assert DatasourceEngine.MYSQL.value == "mysql"
    assert DatasourceEngine.POSTGRESQL.value == "postgresql"


def test_metric_definition_is_immutable_and_keeps_tuple_dimensions():
    metric = MetricDefinition(
        key="gross_revenue",
        owner_id="user-1",
        name="Gross revenue",
        description="Booked revenue before deductions",
        expression="sum(order_amount)",
        dimensions=("region", "channel"),
        version=2,
        status=MetricStatus.ACTIVE,
    )

    assert metric.dimensions == ("region", "channel")
    with pytest.raises(FrozenInstanceError):
        metric.version = 3  # type: ignore[misc]


@pytest.mark.parametrize("key", ["", " GrossRevenue", "gross-revenue", "1st_metric"])
def test_metric_definition_rejects_invalid_machine_key(key: str):
    with pytest.raises(ValueError, match="key"):
        MetricDefinition(
            key=key,
            owner_id="user-1",
            name="Gross revenue",
            description="Booked revenue before deductions",
            expression="sum(order_amount)",
        )


def test_metric_definition_rejects_duplicate_or_blank_dimensions():
    base = {
        "key": "gross_revenue",
        "owner_id": "user-1",
        "name": "Gross revenue",
        "description": "Booked revenue before deductions",
        "expression": "sum(order_amount)",
    }

    with pytest.raises(ValueError, match="dimensions"):
        MetricDefinition(**base, dimensions=("region", "region"))
    with pytest.raises(ValueError, match="dimensions"):
        MetricDefinition(**base, dimensions=("region", " "))


def test_metric_definition_rejects_non_positive_version():
    with pytest.raises(ValueError, match="version"):
        MetricDefinition(
            key="gross_revenue",
            owner_id="user-1",
            name="Gross revenue",
            description="Booked revenue before deductions",
            expression="sum(order_amount)",
            version=0,
        )
```

- [ ] **Step 3: Write architecture tests before production code**

Create `backend/tests/test_analytics_boundaries.py`:

```python
import ast
from pathlib import Path

from app.analytics.application.ports import DatasourceCatalog, MetricCatalog


ANALYTICS_ROOT = Path(__file__).parent.parent / "app" / "analytics"
DOMAIN_ALLOWED_ROOTS = {"__future__", "dataclasses", "enum", "re"}
APPLICATION_BANNED_PREFIXES = (
    "app.gateway",
    "deerflow",
    "fastapi",
    "langchain",
    "sqlalchemy",
)


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


def test_analytics_domain_uses_only_the_standard_library():
    violations: list[str] = []
    for path in sorted((ANALYTICS_ROOT / "domain").rglob("*.py")):
        for line, module in _imports(path):
            if module.startswith("app.analytics.domain"):
                continue
            if module.split(".", 1)[0] not in DOMAIN_ALLOWED_ROOTS:
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics domain dependency violations:\n" + "\n".join(violations)


def test_analytics_application_does_not_depend_on_delivery_or_runtime_layers():
    violations: list[str] = []
    for path in sorted((ANALYTICS_ROOT / "application").rglob("*.py")):
        for line, module in _imports(path):
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in APPLICATION_BANNED_PREFIXES):
                violations.append(f"{path.relative_to(ANALYTICS_ROOT)}:{line} imports {module}")
    assert not violations, "Analytics application dependency violations:\n" + "\n".join(violations)


def test_catalog_ports_are_runtime_checkable_protocols():
    assert getattr(DatasourceCatalog, "_is_runtime_protocol", False)
    assert getattr(MetricCatalog, "_is_runtime_protocol", False)
```

- [ ] **Step 4: Run the focused tests and capture RED evidence**

From `backend/` run:

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/test_analytics_domain.py tests/test_analytics_boundaries.py -q
```

Expected: non-zero exit during collection because `app.analytics` does not exist. Record the exit code and the `ModuleNotFoundError` in `.reviews/phase-01-implementation-report.md`. Do not create production files before this run.

- [ ] **Step 5: Implement datasource contracts**

Create `backend/app/analytics/domain/datasource.py`:

```python
from dataclasses import dataclass
from enum import StrEnum


class DatasourceEngine(StrEnum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class DatasourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"


def _require_trimmed(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class DatasourceDefinition:
    id: str
    owner_id: str
    name: str
    engine: DatasourceEngine
    secret_ref: str
    default_schema: str | None = None
    status: DatasourceStatus = DatasourceStatus.ACTIVE

    def __post_init__(self) -> None:
        for field_name in ("id", "owner_id", "name", "secret_ref"):
            _require_trimmed(getattr(self, field_name), field_name)
        if not isinstance(self.engine, DatasourceEngine):
            raise ValueError("engine must be a DatasourceEngine")
        if not isinstance(self.status, DatasourceStatus):
            raise ValueError("status must be a DatasourceStatus")
        if self.default_schema is not None:
            _require_trimmed(self.default_schema, "default_schema")
```

- [ ] **Step 6: Implement metric contracts**

Create `backend/app/analytics/domain/metric.py`:

```python
import re
from dataclasses import dataclass
from enum import StrEnum

from app.analytics.domain.datasource import _require_trimmed


_METRIC_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class MetricStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    owner_id: str
    name: str
    description: str
    expression: str
    dimensions: tuple[str, ...] = ()
    version: int = 1
    status: MetricStatus = MetricStatus.DRAFT

    def __post_init__(self) -> None:
        for field_name in ("owner_id", "name", "description", "expression"):
            _require_trimmed(getattr(self, field_name), field_name)
        if not isinstance(self.key, str) or _METRIC_KEY.fullmatch(self.key) is None:
            raise ValueError("key must match ^[a-z][a-z0-9_]{0,63}$")
        if not isinstance(self.status, MetricStatus):
            raise ValueError("status must be a MetricStatus")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.dimensions, tuple):
            raise ValueError("dimensions must be a tuple")
        for dimension in self.dimensions:
            _require_trimmed(dimension, "dimensions")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("dimensions must not contain duplicates")
```

- [ ] **Step 7: Export domain contracts without eager infrastructure imports**

Create `backend/app/analytics/__init__.py`:

```python
"""InsightFlow business analytics application domain."""
```

Create `backend/app/analytics/domain/__init__.py`:

```python
from app.analytics.domain.datasource import DatasourceDefinition, DatasourceEngine, DatasourceStatus
from app.analytics.domain.metric import MetricDefinition, MetricStatus

__all__ = [
    "DatasourceDefinition",
    "DatasourceEngine",
    "DatasourceStatus",
    "MetricDefinition",
    "MetricStatus",
]
```

- [ ] **Step 8: Implement async application ports**

Create `backend/app/analytics/application/ports.py`:

```python
from typing import Protocol, runtime_checkable

from app.analytics.domain import DatasourceDefinition, MetricDefinition


@runtime_checkable
class DatasourceCatalog(Protocol):
    async def list_accessible(self, *, principal_id: str) -> tuple[DatasourceDefinition, ...]: ...

    async def get_accessible(self, *, principal_id: str, datasource_id: str) -> DatasourceDefinition | None: ...


@runtime_checkable
class MetricCatalog(Protocol):
    async def list_accessible(self, *, principal_id: str) -> tuple[MetricDefinition, ...]: ...

    async def get_accessible(self, *, principal_id: str, metric_key: str) -> MetricDefinition | None: ...
```

Create `backend/app/analytics/application/__init__.py`:

```python
from app.analytics.application.ports import DatasourceCatalog, MetricCatalog

__all__ = ["DatasourceCatalog", "MetricCatalog"]
```

- [ ] **Step 9: Document the local architecture rules**

Create `backend/app/analytics/AGENTS.md` with these enforceable rules:

```markdown
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
PYTHONPATH=. uv run pytest tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py -q
uv run ruff check app/analytics tests/test_analytics_domain.py tests/test_analytics_boundaries.py
```
```

- [ ] **Step 10: Run focused GREEN verification**

From `backend/` run:

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/test_analytics_domain.py tests/test_analytics_boundaries.py tests/test_harness_boundary.py -q
uv run ruff check app/analytics tests/test_analytics_domain.py tests/test_analytics_boundaries.py
uv run ruff format --check app/analytics tests/test_analytics_domain.py tests/test_analytics_boundaries.py
```

Expected: all commands exit 0. Record test totals and Ruff output.

- [ ] **Step 11: Update the factual progress ledger**

In `docs/PROGRESS.md`:

- Change Phase 0 to `Complete`, evidence ``936758c`, `aa516bd`; architecture report; ADR 0001``, next gate `Phase 1 implementation`.
- Change Phase 1 to `In progress`, evidence `Phase 1 plan; analytics domain/boundary tests`, next gate `Phase 1 review`.
- Do not mark Phase 1 complete before architecture review.
- Do not change size budgets or later-phase statuses.

- [ ] **Step 12: Run required backend regression gates**

From `backend/` run, without installing or updating dependencies:

```powershell
make test
make test-blocking-io
make lint
```

Expected: all commands exit 0. If an existing unrelated baseline failure occurs, capture the exact failing command and output, leave Phase 1 uncommitted, and stop for review rather than weakening tests or changing unrelated code.

- [ ] **Step 13: Verify change boundaries and commit once**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
```

The changed set must contain only the files listed in this task. Then commit once:

```powershell
git add backend/app/analytics backend/tests/test_analytics_domain.py backend/tests/test_analytics_boundaries.py docs/PROGRESS.md docs/superpowers/plans/2026-09-21-phase-01-analytics-domain-boundary.md docs/prompts/phase-01-analytics-domain-boundary.md
git commit -m "feat: establish analytics domain boundary"
```

- [ ] **Step 14: Produce review evidence and stop**

Create ignored `.reviews/phase-01-implementation-report.md` containing:

- Full commit hash and parent.
- Changed paths and `git diff --stat aa516bd..HEAD`.
- RED command, non-zero exit code, and actual failure.
- GREEN and full regression commands, exit codes, test totals, and key output.
- Confirmation of no dependency, migration, route, UI, Docker, Harness, namespace, or baseline-tag changes.
- Deviations, written as `None` only if there were none.

Do not begin Phase 2.

## Plan self-review

- Spec coverage: the plan creates the concrete domain/application boundary and tests the dependency rules approved in ADR 0001.
- Scope control: SQL, persistence, APIs, tools, Agent registration and UI remain outside Phase 1.
- Type consistency: application ports consume the exact frozen domain contracts exported by `app.analytics.domain`.
- Security boundary: the only credential-related field is opaque `secret_ref`; no raw connection material is modeled.
- Rollback: one phase commit can be reverted without touching the immutable upstream baseline.
