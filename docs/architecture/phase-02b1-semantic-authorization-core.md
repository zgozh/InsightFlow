# Phase 2B1 Architecture: Semantic Query Authorization Core

Status: approved design for implementation after Phase 2A acceptance.

## 1. Scope

Phase 2B is split again to keep the database boundary reviewable:

- **2B1 — semantic authorization core:** validate that a Phase 2A `PreparedQuery` is authentic, resolve its physical tables/columns/functions against an immutable schema snapshot, apply an effective principal policy, and produce a non-executable authorization result.
- **2B2 — governed execution:** secret resolution, database adapters, `EXPLAIN`, cost limits, short-lived plan IDs, read-only transactions, timeout/row/byte caps and result sanitization.

2B1 is offline and deterministic. It adds no driver, connection, ORM, migration, API, Agent tool, Docker service or executable plan.

## 2. Dependency direction

```text
domain: schema + access-policy + authorization values
        ▲
application: catalogs + SemanticQueryAuthorizer port + AuthorizePreparedQuery use case
        ▲
infrastructure: SqlglotSemanticAuthorizer
        │
        ├── QueryPolicy (re-validates Phase 2A input)
        └── sqlglot==30.18.0 (already pinned)
```

Domain remains standard-library-only. Application never imports SQLGlot. Infrastructure may use SQLGlot but cannot import Gateway, Harness, FastAPI or LangChain.

## 3. Immutable domain contracts

### Schema vocabulary

```python
class ColumnSensitivity(StrEnum):
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    PII = "pii"

@dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    data_type: str
    sensitivity: ColumnSensitivity = ColumnSensitivity.STANDARD

@dataclass(frozen=True, slots=True)
class RelationSchema:
    name: str
    schema: str
    columns: tuple[ColumnSchema, ...]
    catalog: str | None = None

@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    datasource_id: str
    engine: DatasourceEngine
    version: str
    default_schema: str
    relations: tuple[RelationSchema, ...]
```

### Access-policy vocabulary

```python
class ColumnAccess(StrEnum):
    ALLOW = "allow"
    AGGREGATE_ONLY = "aggregate_only"
    DENY = "deny"

@dataclass(frozen=True, slots=True)
class ColumnAccessRule:
    name: str
    access: ColumnAccess

@dataclass(frozen=True, slots=True)
class RelationAccessRule:
    name: str
    schema: str
    columns: tuple[ColumnAccessRule, ...]
    catalog: str | None = None

@dataclass(frozen=True, slots=True)
class PrincipalAccessPolicy:
    datasource_id: str
    principal_id: str
    version: str
    relations: tuple[RelationAccessRule, ...]
    allowed_functions: tuple[str, ...] = ()
```

Identifiers and versions are non-empty trimmed strings. Tuples are immutable and duplicate-free. Function names are stored lowercase/case-folded and duplicate-free. Missing relations, columns and functions are denied by default.

### Authorization vocabulary

```python
class AuthorizationDecisionCode(StrEnum):
    APPROVED = "approved"
    DATASOURCE_NOT_ACCESSIBLE = "datasource_not_accessible"
    SCHEMA_UNAVAILABLE = "schema_unavailable"
    POLICY_UNAVAILABLE = "policy_unavailable"
    PREPARED_QUERY_MISMATCH = "prepared_query_mismatch"
    ANALYSIS_ERROR = "analysis_error"
    CORRELATED_SUBQUERY_NOT_ALLOWED = "correlated_subquery_not_allowed"
    UNKNOWN_RELATION = "unknown_relation"
    RELATION_NOT_ALLOWED = "relation_not_allowed"
    UNKNOWN_COLUMN = "unknown_column"
    COLUMN_NOT_ALLOWED = "column_not_allowed"
    FUNCTION_NOT_ALLOWED = "function_not_allowed"
    SENSITIVE_COLUMN = "sensitive_column"
    CROSS_SCHEMA = "cross_schema"
    CARTESIAN_JOIN = "cartesian_join"
    APPROVAL_REQUIRED = "approval_required"

@dataclass(frozen=True, slots=True)
class AuthorizedQuerySpec:
    prepared: PreparedQuery
    datasource_id: str
    principal_id: str
    schema_version: str
    policy_version: str
    relations: tuple[str, ...]
    columns: tuple[str, ...]
    functions: tuple[str, ...]
    risk: QueryRisk

@dataclass(frozen=True, slots=True)
class QueryAuthorizationDecision:
    allowed: bool
    risk: QueryRisk
    codes: tuple[AuthorizationDecisionCode, ...]
    authorized: AuthorizedQuerySpec | None = None
```

An allowed decision must carry an `AuthorizedQuerySpec` and risk LOW or MEDIUM. A denied HIGH decision ends with `APPROVAL_REQUIRED`; a BLOCKED decision carries no authorized value. `AuthorizedQuerySpec` has no `plan_id`, connection, credential or execute method and is not database authority.

## 4. Application ports and use case

```python
@runtime_checkable
class SchemaCatalog(Protocol):
    async def get_current(self, *, datasource_id: str) -> SchemaSnapshot | None: ...

@runtime_checkable
class AccessPolicyCatalog(Protocol):
    async def get_effective(
        self, *, principal_id: str, datasource_id: str
    ) -> PrincipalAccessPolicy | None: ...

@runtime_checkable
class SemanticQueryAuthorizer(Protocol):
    def authorize(
        self,
        *,
        prepared: PreparedQuery,
        schema: SchemaSnapshot,
        policy: PrincipalAccessPolicy,
    ) -> QueryAuthorizationDecision: ...
```

`AuthorizePreparedQuery.execute(principal_id, datasource_id, prepared)` performs:

1. `DatasourceCatalog.get_accessible`; missing/disabled means `DATASOURCE_NOT_ACCESSIBLE`.
2. Reject an engine mismatch as `PREPARED_QUERY_MISMATCH`.
3. Load current schema; missing or identity/engine mismatch means `SCHEMA_UNAVAILABLE`.
4. Load effective policy; missing or identity mismatch means `POLICY_UNAVAILABLE`.
5. Delegate to `SemanticQueryAuthorizer`.

Catalog exceptions are not converted into approvals. Tests may assert they propagate; API error mapping belongs to 2C.

## 5. Semantic authorization algorithm

`SqlglotSemanticAuthorizer` receives a `QueryPolicy` dependency and evaluates in this order:

1. Re-run Phase 2A on `prepared.sql` using `max(1, prepared.row_limit)` and the same engine. Require an allowed decision and exact `PreparedQuery` equality. Otherwise return `PREPARED_QUERY_MISMATCH`. This prevents hand-crafted domain values from bypassing syntax policy.
2. Parse with the explicit engine dialect.
3. Build SQLGlot schema mapping from `SchemaSnapshot` and call `qualify()` on a copy with column validation enabled and partial qualification disabled.
4. Convert parser/optimizer/schema ambiguity failures to `ANALYSIS_ERROR` without exposing SQLGlot messages.
5. Reject any scope with external/correlated columns as `CORRELATED_SUBQUERY_NOT_ALLOWED`. Correlated lineage is deliberately outside V1.
6. Traverse scopes. Resolve physical `exp.Table` sources; derived CTE/subquery sources are skipped at the outer scope because their inner scopes provide the physical lineage.
7. Validate every physical relation against both schema and policy. Unknown wins before not-allowed.
8. Validate every physical column against schema and its relation rule. Ambiguous or unresolved columns fail closed.
9. Extract every `exp.Func` name case-insensitively. Every function, including `COUNT`, `SUM`, `CAST` and anonymous functions, must be explicitly allowlisted. This is the complete authorization boundary; Phase 2A's dangerous-function denylist is only defense in depth.
10. Direct use of `DENY` or `AGGREGATE_ONLY` columns returns `COLUMN_NOT_ALLOWED`. An `AGGREGATE_ONLY` column under an `exp.AggFunc` becomes HIGH with `SENSITIVE_COLUMN` and `APPROVAL_REQUIRED`.
11. Any referenced `SENSITIVE` or `PII` column becomes HIGH with `SENSITIVE_COLUMN` and `APPROVAL_REQUIRED`, even if its column rule says ALLOW.
12. A relation outside `default_schema` becomes HIGH with `CROSS_SCHEMA` and `APPROVAL_REQUIRED` after it has passed explicit relation permission.
13. A CROSS join or join without `ON`/`USING` becomes HIGH with `CARTESIAN_JOIN` and `APPROVAL_REQUIRED`.
14. If no HIGH condition exists, preserve MEDIUM from Phase 2A; otherwise use LOW. Return sorted unique canonical relation, column and function inventories followed by `APPROVED`.

HIGH is intentionally unreachable as an allowed result in V1. Later approval workflow must be a new explicit design, not a boolean switch.

## 6. Canonical identifiers

The adapter uses SQLGlot's selected dialect to normalize identifiers. Relation keys are `catalog.schema.table` when a catalog exists and `schema.table` otherwise; column keys append `.column`. Any normalization collision or lookup ambiguity returns `ANALYSIS_ERROR`.

### Identifier case and quoting (Phase 2B1 Fix 01)

物理对象的 catalog/schema/relation/column 一律按真实元数据名称精确匹配。适配器先用 SQLGlot 的方言标识符规范化处理 AST 副本，再与 `SchemaSnapshot` 的真实名称比对；不得用全局 `casefold()` 模拟方言规则，也不得让 SQLGlot 自动折叠真实元数据名称（schema 映射使用 `MappingSchema(..., normalize=False)`）。

- PostgreSQL：未加引号的 `orders` / `Orders` / `ORDERS` 折叠为 `orders`；`"orders"` 精确匹配小写真实对象；`"Orders"` 只精确匹配真实名称为 `Orders` 的对象；`"ORDERS"` 只精确匹配真实名称为 `ORDERS` 的对象；不存在精确对象时必须拒绝。
- MySQL：本阶段没有 `lower_case_table_names` 证据，只有元数据与查询大小写完全一致才放行，无法确认的大小写不一致安全拒绝。这是允许少量误拒绝、不允许任何误授权的安全策略。

`PrincipalAccessPolicy` 的 relation/column 规则必须精确对应解析到的真实 `SchemaSnapshot` 对象；大小写不同的策略规则不能授权另一个真实对象，否则返回 `RELATION_NOT_ALLOWED` / `COLUMN_NOT_ALLOWED`。只有 SQL 函数 allowlist 保持大小写不敏感。

`AuthorizedQuerySpec.relations` 与 `.columns` 记录 `SchemaSnapshot` 的真实名称，而不是查询文本中的大小写。Phase 2B2 的 MySQL schema adapter 必须先读取或显式配置该服务器的 `lower_case_table_names` 语义，再决定是否扩展 `SchemaSnapshot` 契约；2B1 不引入连接、驱动或服务器探测。

The physical inventories are evidence for authorization and future audit. Phase 2B2 must recheck schema and policy versions before issuing a plan ID to prevent time-of-check/time-of-use drift.

## 7. Acceptance matrix

- authentic simple query is approved and records exact relation/column/function inventories;
- forged or stale-looking `PreparedQuery` is rejected before semantic analysis;
- unknown, ambiguous and unauthorized relations/columns fail closed;
- functions are default-deny; `nextval`, `setval`, `GET_LOCK`, advisory locks and unknown UDFs fail unless explicitly allowlisted;
- explicitly allowlisted `COUNT`/`SUM` work;
- aliases, joins, CTEs and non-correlated subqueries resolve to physical lineage;
- correlated subqueries are rejected;
- policy-denied and direct aggregate-only columns are rejected;
- aggregate-only, sensitive and PII use returns denied HIGH + `APPROVAL_REQUIRED`;
- cross-schema and Cartesian queries return denied HIGH + `APPROVAL_REQUIRED`;
- inaccessible datasource and missing/mismatched schema or policy return stable application codes;
- no SQLGlot import leaks into domain/application;
- no plan ID, database execution, driver, dependency or lockfile change exists.

## 8. Docker note and next gate

Docker is available on the development machine. It is intentionally unused in 2B1. Phase 2B2 will use disposable Docker-backed PostgreSQL and MySQL integration environments to prove database-specific read-only, timeout, EXPLAIN and cancellation behaviour; unit mocks alone will not be accepted for that execution boundary.

2B2 cannot begin until this authorization core passes architecture review.
