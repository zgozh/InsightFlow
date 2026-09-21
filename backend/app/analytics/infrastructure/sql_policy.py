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
    if any(_function_name(function) in _DANGEROUS_FUNCTIONS for function in statement.find_all(exp.Func)):
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
    if isinstance(value, exp.Neg) and isinstance(value.this, exp.Literal) and value.this.is_int:
        return -int(value.this.this), QueryDecisionCode.INVALID_LIMIT
    return None, QueryDecisionCode.NON_LITERAL_LIMIT


def _physical_relations(statement: exp.Expression) -> tuple[str, ...]:
    cte_aliases = {cte.alias_or_name.casefold() for cte in statement.find_all(exp.CTE) if cte.alias_or_name}
    relations: set[str] = set()
    for table in statement.find_all(exp.Table):
        if not table.name:
            continue
        if not table.catalog and not table.db and table.name.casefold() in cte_aliases:
            continue
        relation = ".".join(part for part in (table.catalog, table.db, table.name) if part)
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
            code = QueryDecisionCode.MULTIPLE_STATEMENTS if len(reparsed) > 1 else QueryDecisionCode.PARSE_ERROR
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
        query_hash = hashlib.sha256(f"{request.engine.value}\0{normalized_sql}".encode()).hexdigest()
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
