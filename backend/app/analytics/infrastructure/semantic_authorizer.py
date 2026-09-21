from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from app.analytics.application import QueryPolicy
from app.analytics.domain import (
    MAX_QUERY_ROWS,
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    ColumnSensitivity,
    DatasourceEngine,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryAuthorizationDecision,
    QueryPolicyRequest,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)

_DIALECT_BY_ENGINE = {
    DatasourceEngine.MYSQL: "mysql",
    DatasourceEngine.POSTGRESQL: "postgres",
}


class _DenialError(Exception):
    """Internal carrier for a stable blocking decision code."""

    def __init__(self, code: AuthorizationDecisionCode) -> None:
        super().__init__(code.value)
        self.code = code


class _AmbiguityError(Exception):
    """Raised when an identifier resolves to more than one schema or policy entity."""


def _blocked(code: AuthorizationDecisionCode) -> QueryAuthorizationDecision:
    return QueryAuthorizationDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(code,),
    )


def _canonical_relation(catalog: str | None, schema: str, name: str) -> str:
    return ".".join(part for part in (catalog, schema, name) if part)


def _function_name(function: exp.Func) -> str:
    if isinstance(function, exp.Anonymous):
        return function.name.casefold()
    return function.sql_name().casefold()


def _physical_sources(scope: Scope) -> list[tuple[str, exp.Table]]:
    """Physical table sources of a scope; CTE/subquery references are derived, not physical."""

    physical: list[tuple[str, exp.Table]] = []
    for table in scope.tables:
        source = scope.selected_sources.get(table.alias_or_name)
        if source is not None and isinstance(source[1], Scope):
            continue
        physical.append((table.alias_or_name, table))
    return physical


def _qualify_mapping(snapshot: SchemaSnapshot) -> dict:
    mapping: dict = {}
    for relation in snapshot.relations:
        columns = {column.name: column.data_type for column in relation.columns}
        node = mapping
        if relation.catalog:
            node = node.setdefault(relation.catalog, {})
        node = node.setdefault(relation.schema, {})
        node[relation.name] = columns
    return mapping


class _SchemaIndex:
    def __init__(self, snapshot: SchemaSnapshot) -> None:
        self._snapshot = snapshot
        self._by_name: dict[str, list[RelationSchema]] = {}
        self._qualify_mapping = _qualify_mapping(snapshot)
        for relation in snapshot.relations:
            self._by_name.setdefault(relation.name.casefold(), []).append(relation)

    @property
    def qualify_mapping(self) -> dict:
        return self._qualify_mapping

    def resolve(self, table: exp.Table) -> RelationSchema | None:
        name = table.name.casefold()
        catalog = table.catalog.casefold() if table.catalog else None
        database = table.db.casefold() if table.db else None
        candidates = self._by_name.get(name, [])
        if catalog is None and database is None:
            default_schema = self._snapshot.default_schema.casefold()
            preferred = [relation for relation in candidates if relation.schema.casefold() == default_schema]
            candidates = preferred or candidates
        else:
            candidates = [relation for relation in candidates if (database is None or relation.schema.casefold() == database) and (catalog is None or (relation.catalog or "").casefold() == catalog)]
        if not candidates:
            return None
        if len(candidates) > 1:
            raise _AmbiguityError(name)
        return candidates[0]

    def column(self, relation: RelationSchema, name: str) -> ColumnSchema | None:
        folded = name.casefold()
        for column in relation.columns:
            if column.name.casefold() == folded:
                return column
        return None


class _PolicyIndex:
    def __init__(self, policy: PrincipalAccessPolicy) -> None:
        self._by_key: dict[str, RelationAccessRule] = {}
        for rule in policy.relations:
            key = _canonical_relation(rule.catalog, rule.schema, rule.name).casefold()
            if key in self._by_key:
                raise _AmbiguityError(key)
            self._by_key[key] = rule
        self._allowed_functions = frozenset(policy.allowed_functions)

    def relation_rule(self, relation: RelationSchema) -> RelationAccessRule | None:
        key = _canonical_relation(relation.catalog, relation.schema, relation.name).casefold()
        return self._by_key.get(key)

    def column_rule(self, rule: RelationAccessRule, name: str) -> ColumnAccessRule | None:
        folded = name.casefold()
        for column in rule.columns:
            if column.name.casefold() == folded:
                return column
        return None

    def function_allowed(self, name: str) -> bool:
        return name.casefold() in self._allowed_functions


class SqlglotSemanticAuthorizer:
    """Deterministic semantic authorization over an authentic Phase 2A prepared query."""

    def __init__(self, query_policy: QueryPolicy) -> None:
        self._query_policy = query_policy

    def authorize(
        self,
        *,
        prepared: PreparedQuery,
        schema: SchemaSnapshot,
        policy: PrincipalAccessPolicy,
    ) -> QueryAuthorizationDecision:
        max_rows = max(1, prepared.row_limit)
        if max_rows > MAX_QUERY_ROWS:
            return _blocked(AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)
        revalidated = self._query_policy.evaluate(
            QueryPolicyRequest(sql=prepared.sql, engine=prepared.engine, max_rows=max_rows),
        )
        if not revalidated.allowed or revalidated.prepared != prepared:
            return _blocked(AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)

        dialect = _DIALECT_BY_ENGINE[prepared.engine]
        try:
            statement = sqlglot.parse_one(prepared.sql, read=dialect)
        except SqlglotError:
            return _blocked(AuthorizationDecisionCode.ANALYSIS_ERROR)
        if statement is None:
            return _blocked(AuthorizationDecisionCode.ANALYSIS_ERROR)

        try:
            return self._analyze(statement, schema, policy, dialect, prepared, revalidated.risk)
        except _DenialError as denial:
            return _blocked(denial.code)
        except _AmbiguityError:
            return _blocked(AuthorizationDecisionCode.ANALYSIS_ERROR)

    def _analyze(
        self,
        statement: exp.Expression,
        schema: SchemaSnapshot,
        policy: PrincipalAccessPolicy,
        dialect: str,
        prepared: PreparedQuery,
        risk: QueryRisk,
    ) -> QueryAuthorizationDecision:
        schema_index = _SchemaIndex(schema)
        policy_index = _PolicyIndex(policy)

        for scope in traverse_scope(statement):
            for _alias, table in _physical_sources(scope):
                if schema_index.resolve(table) is None:
                    raise _DenialError(AuthorizationDecisionCode.UNKNOWN_RELATION)

        try:
            qualified = qualify(
                statement.copy(),
                schema=schema_index.qualify_mapping,
                dialect=dialect,
                validate_qualify_columns=True,
                allow_partial_qualification=False,
                identify=False,
                quote_identifiers=False,
            )
        except (SqlglotError, ValueError) as error:
            raise _DenialError(AuthorizationDecisionCode.ANALYSIS_ERROR) from error

        scopes = traverse_scope(qualified)
        for scope in scopes:
            if scope.external_columns:
                raise _DenialError(AuthorizationDecisionCode.CORRELATED_SUBQUERY_NOT_ALLOWED)

        default_schema = schema.default_schema.casefold()
        relations: set[str] = set()
        columns: set[str] = set()
        resolved_scopes: list[tuple[Scope, dict[str, tuple[RelationSchema, RelationAccessRule]]]] = []
        cross_schema = False

        for scope in scopes:
            physical: dict[str, tuple[RelationSchema, RelationAccessRule]] = {}
            for alias, table in _physical_sources(scope):
                relation = schema_index.resolve(table)
                if relation is None:
                    raise _DenialError(AuthorizationDecisionCode.UNKNOWN_RELATION)
                rule = policy_index.relation_rule(relation)
                if rule is None:
                    raise _DenialError(AuthorizationDecisionCode.RELATION_NOT_ALLOWED)
                physical[alias] = (relation, rule)
                relations.add(_canonical_relation(relation.catalog, relation.schema, relation.name))
                if relation.schema.casefold() != default_schema:
                    cross_schema = True
            resolved_scopes.append((scope, physical))

        aggregate_only_used = False
        sensitive_used = False
        for scope, physical in resolved_scopes:
            for column in scope.columns:
                alias = column.table
                entry = physical.get(alias) if alias else None
                if entry is None:
                    source = scope.selected_sources.get(alias) if alias else None
                    if source is not None and isinstance(source[1], Scope):
                        continue
                    raise _DenialError(AuthorizationDecisionCode.ANALYSIS_ERROR)
                relation, rule = entry
                schema_column = schema_index.column(relation, column.name)
                if schema_column is None:
                    raise _DenialError(AuthorizationDecisionCode.UNKNOWN_COLUMN)
                column_rule = policy_index.column_rule(rule, column.name)
                if column_rule is None or column_rule.access is ColumnAccess.DENY:
                    raise _DenialError(AuthorizationDecisionCode.COLUMN_NOT_ALLOWED)
                aggregated = column.find_ancestor(exp.AggFunc) is not None
                if column_rule.access is ColumnAccess.AGGREGATE_ONLY:
                    if not aggregated:
                        raise _DenialError(AuthorizationDecisionCode.COLUMN_NOT_ALLOWED)
                    aggregate_only_used = True
                if schema_column.sensitivity in (ColumnSensitivity.SENSITIVE, ColumnSensitivity.PII):
                    sensitive_used = True
                columns.add(f"{_canonical_relation(relation.catalog, relation.schema, relation.name)}.{schema_column.name}")

        functions: set[str] = set()
        for function in qualified.find_all(exp.Func):
            name = _function_name(function)
            if not policy_index.function_allowed(name):
                raise _DenialError(AuthorizationDecisionCode.FUNCTION_NOT_ALLOWED)
            functions.add(name)

        cartesian = any(join.args.get("on") is None and join.args.get("using") is None for join in qualified.find_all(exp.Join))

        high_codes: list[AuthorizationDecisionCode] = []
        if sensitive_used or aggregate_only_used:
            high_codes.append(AuthorizationDecisionCode.SENSITIVE_COLUMN)
        if cross_schema:
            high_codes.append(AuthorizationDecisionCode.CROSS_SCHEMA)
        if cartesian:
            high_codes.append(AuthorizationDecisionCode.CARTESIAN_JOIN)
        if high_codes:
            return QueryAuthorizationDecision(
                allowed=False,
                risk=QueryRisk.HIGH,
                codes=(*high_codes, AuthorizationDecisionCode.APPROVAL_REQUIRED),
            )

        authorized = AuthorizedQuerySpec(
            prepared=prepared,
            datasource_id=schema.datasource_id,
            principal_id=policy.principal_id,
            schema_version=schema.version,
            policy_version=policy.version,
            relations=tuple(sorted(relations)),
            columns=tuple(sorted(columns)),
            functions=tuple(sorted(functions)),
            risk=risk,
        )
        return QueryAuthorizationDecision(
            allowed=True,
            risk=risk,
            codes=(AuthorizationDecisionCode.APPROVED,),
            authorized=authorized,
        )
