from dataclasses import fields

import pytest
import sqlglot

from app.analytics.application import QueryPolicy
from app.analytics.domain import (
    DatasourceEngine,
    QueryDecisionCode,
    QueryPolicyRequest,
    QueryRisk,
)
from app.analytics.infrastructure import SqlglotQueryPolicy

ENGINES = list(DatasourceEngine)
DIALECT_BY_ENGINE = {
    DatasourceEngine.MYSQL: "mysql",
    DatasourceEngine.POSTGRESQL: "postgres",
}
DENYLISTED_FUNCTIONS = (
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
)


def _evaluate(sql: str, engine: DatasourceEngine, max_rows: int = 1_000):
    return SqlglotQueryPolicy().evaluate(QueryPolicyRequest(sql=sql, engine=engine, max_rows=max_rows))


def _approved(sql: str, engine: DatasourceEngine, max_rows: int = 1_000):
    decision = _evaluate(sql, engine, max_rows)
    assert decision.allowed is True, decision
    assert decision.prepared is not None
    assert decision.risk is not QueryRisk.BLOCKED
    return decision


def _blocked(sql: str, engine: DatasourceEngine, code: QueryDecisionCode, max_rows: int = 1_000):
    decision = _evaluate(sql, engine, max_rows)
    assert decision.allowed is False, decision
    assert decision.risk is QueryRisk.BLOCKED
    assert decision.codes == (code,), decision
    assert decision.prepared is None
    return decision


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("", QueryDecisionCode.EMPTY_SQL),
        ("   ", QueryDecisionCode.EMPTY_SQL),
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


def test_select_into_outfile_fails_closed_at_parse_time():
    # SQLGlot 30.18.0 rejects `INTO OUTFILE` outright in both dialects, so this export
    # syntax surfaces as PARSE_ERROR rather than via the exp.Into denylist. The
    # decision is still denied, BLOCKED, and carries no prepared query.
    for engine in ENGINES:
        _blocked("SELECT * INTO OUTFILE 'x' FROM t", engine, QueryDecisionCode.PARSE_ERROR)


@pytest.mark.parametrize(
    ("engine", "sql"),
    [
        (DatasourceEngine.POSTGRESQL, "SELECT id INTO new_table FROM t"),
        (DatasourceEngine.MYSQL, "SELECT id INTO @v FROM t"),
    ],
)
def test_select_into_an_export_target_is_forbidden(engine, sql):
    _blocked(sql, engine, QueryDecisionCode.FORBIDDEN_OPERATION)


def test_postgres_copy_is_unsupported():
    _blocked("COPY t TO '/tmp/x'", DatasourceEngine.POSTGRESQL, QueryDecisionCode.UNSUPPORTED_STATEMENT)


@pytest.mark.parametrize("engine", ENGINES)
def test_write_nested_inside_a_cte_is_forbidden(engine):
    _blocked(
        "WITH changed AS (DELETE FROM t RETURNING id) SELECT id FROM changed",
        engine,
        QueryDecisionCode.FORBIDDEN_OPERATION,
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_count_star_is_the_only_allowed_star_form(engine):
    decision = _approved("SELECT COUNT(*) FROM orders", engine)
    assert decision.prepared.relations == ("orders",)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("function", DENYLISTED_FUNCTIONS)
def test_dangerous_function_denylist_is_case_insensitive(engine, function):
    _blocked(f"SELECT {function.upper()}(1)", engine, QueryDecisionCode.DANGEROUS_FUNCTION)


@pytest.mark.parametrize("engine", ENGINES)
def test_mixed_case_dangerous_function_is_rejected(engine):
    _blocked("SELECT SlEeP(1)", engine, QueryDecisionCode.DANGEROUS_FUNCTION)


@pytest.mark.parametrize("engine", ENGINES)
def test_unbounded_query_receives_exactly_the_request_cap(engine):
    decision = _approved("SELECT id FROM orders", engine, max_rows=250)

    assert decision.prepared.row_limit == 250
    assert decision.codes == (QueryDecisionCode.LIMIT_APPLIED, QueryDecisionCode.APPROVED)
    assert decision.risk is QueryRisk.LOW


@pytest.mark.parametrize("engine", ENGINES)
def test_small_literal_limit_is_preserved(engine):
    decision = _approved("SELECT id FROM orders LIMIT 5", engine, max_rows=1_000)

    assert decision.prepared.row_limit == 5
    assert decision.codes == (QueryDecisionCode.APPROVED,)


@pytest.mark.parametrize("engine", ENGINES)
def test_oversized_literal_limit_is_reduced(engine):
    decision = _approved("SELECT id FROM orders LIMIT 5000", engine, max_rows=100)

    assert decision.prepared.row_limit == 100
    assert decision.codes == (QueryDecisionCode.LIMIT_REDUCED, QueryDecisionCode.APPROVED)


@pytest.mark.parametrize("engine", ENGINES)
def test_zero_literal_limit_is_preserved_verbatim(engine):
    decision = _approved("SELECT id FROM orders LIMIT 0", engine, max_rows=1_000)

    assert decision.prepared.row_limit == 0
    assert decision.codes == (QueryDecisionCode.APPROVED,)


@pytest.mark.parametrize("engine", ENGINES)
def test_allowed_code_order_for_a_complex_unbounded_query(engine):
    decision = _approved("SELECT o.id FROM orders AS o JOIN returns AS r ON o.id = r.id", engine, max_rows=100)

    assert decision.codes == (
        QueryDecisionCode.LIMIT_APPLIED,
        QueryDecisionCode.COMPLEX_QUERY,
        QueryDecisionCode.APPROVED,
    )
    assert decision.risk is QueryRisk.MEDIUM


@pytest.mark.parametrize("engine", ENGINES)
def test_cte_alias_is_excluded_from_physical_relations(engine):
    decision = _approved("WITH totals AS (SELECT id FROM orders) SELECT id FROM totals", engine)

    assert decision.prepared.relations == ("orders",)
    assert decision.risk is QueryRisk.MEDIUM
    assert QueryDecisionCode.COMPLEX_QUERY in decision.codes


@pytest.mark.parametrize("engine", ENGINES)
def test_relations_are_sorted_unique_and_keep_qualified_components(engine):
    decision = _approved(
        "SELECT o.id FROM analytics.public.orders AS o JOIN public.returns AS r ON o.id = r.id",
        engine,
    )

    assert decision.prepared.relations == ("analytics.public.orders", "public.returns")


@pytest.mark.parametrize("engine", ENGINES)
def test_duplicate_physical_relations_are_deduplicated(engine):
    decision = _approved("SELECT o.id FROM orders AS o JOIN orders AS o2 ON o.id = o2.id", engine)

    assert decision.prepared.relations == ("orders",)


@pytest.mark.parametrize("engine", ENGINES)
def test_simple_select_is_low_risk(engine):
    decision = _approved("SELECT id, region FROM orders WHERE region = 'emea'", engine)

    assert decision.risk is QueryRisk.LOW
    assert QueryDecisionCode.COMPLEX_QUERY not in decision.codes


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT o.id FROM orders AS o JOIN returns AS r ON o.id = r.id",
        "WITH totals AS (SELECT id FROM orders) SELECT id FROM totals",
        "SELECT id FROM orders UNION SELECT id FROM returns",
        "SELECT row_number() OVER (PARTITION BY region) AS rn FROM orders",
        "SELECT id FROM (SELECT id FROM orders) AS nested",
    ],
)
def test_complex_shapes_are_medium_risk(engine, sql):
    decision = _approved(sql, engine)

    assert decision.risk is QueryRisk.MEDIUM
    assert QueryDecisionCode.COMPLEX_QUERY in decision.codes


@pytest.mark.parametrize("engine", ENGINES)
def test_normalized_sql_is_one_statement_in_the_same_dialect(engine):
    decision = _approved("SELECT id FROM orders", engine)
    dialect = DIALECT_BY_ENGINE[engine]

    reparsed = [statement for statement in sqlglot.parse(decision.prepared.sql, read=dialect) if statement is not None]

    assert len(reparsed) == 1
    assert reparsed[0].sql(dialect=dialect, pretty=False) == decision.prepared.sql


@pytest.mark.parametrize("engine", ENGINES)
def test_query_hash_is_stable_across_repeat_evaluation(engine):
    first = _approved("SELECT id FROM orders", engine)
    second = _approved("SELECT id FROM orders", engine)

    assert first.prepared.query_hash == second.prepared.query_hash
    assert len(first.prepared.query_hash) == 64
    assert first.prepared.query_hash == first.prepared.query_hash.lower()


def test_query_hash_differs_across_dialects_for_identical_text():
    mysql = _approved("SELECT id FROM orders", DatasourceEngine.MYSQL)
    postgres = _approved("SELECT id FROM orders", DatasourceEngine.POSTGRESQL)

    assert mysql.prepared.sql == postgres.prepared.sql
    assert mysql.prepared.query_hash != postgres.prepared.query_hash


@pytest.mark.parametrize("engine", ENGINES)
def test_parser_text_never_enters_a_blocked_decision(engine):
    decision = _blocked("SELECT (", engine, QueryDecisionCode.PARSE_ERROR)
    rendered = repr(decision).lower()

    assert "sqlglot" not in rendered
    assert "line" not in rendered
    assert "column" not in rendered
    assert "traceback" not in rendered


def test_adapter_satisfies_the_application_port():
    assert isinstance(SqlglotQueryPolicy(), QueryPolicy)


@pytest.mark.parametrize("engine", ENGINES)
def test_prepared_query_is_not_executable_authority(engine):
    decision = _approved("SELECT id FROM orders", engine)
    prepared = decision.prepared

    assert not hasattr(prepared, "plan_id")
    assert not hasattr(prepared, "execute")
    assert {field.name for field in fields(prepared)} == {"sql", "engine", "relations", "row_limit", "query_hash"}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 -- ordinary comment\n",
        "SELECT 1 /* ordinary comment */",
        "SELECT /*+ INDEX(t idx_t) */ id FROM t",
    ],
)
def test_sql_comments_are_rejected(engine, sql):
    _blocked(sql, engine, QueryDecisionCode.COMMENT_NOT_ALLOWED)


def test_mysql_executable_comment_is_rejected():
    _blocked(
        "SELECT 1 /*!50000 UNION SELECT SLEEP(10) */",
        DatasourceEngine.MYSQL,
        QueryDecisionCode.COMMENT_NOT_ALLOWED,
    )


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("literal", ["'-- not a comment'", "'/* not a comment */'"])
def test_comment_markers_inside_string_literals_are_allowed(engine, literal):
    _approved(f"SELECT {literal} AS label", engine)


def test_mysql_session_assignment_is_forbidden():
    _blocked(
        "SELECT @x := id FROM t",
        DatasourceEngine.MYSQL,
        QueryDecisionCode.FORBIDDEN_OPERATION,
    )


@pytest.mark.parametrize(
    ("engine", "sql"),
    [
        (DatasourceEngine.MYSQL, "SELECT id FROM t WHERE id = ?"),
        (DatasourceEngine.POSTGRESQL, "SELECT id FROM t WHERE id = ?"),
        (DatasourceEngine.MYSQL, "SELECT id FROM t WHERE id = :id"),
        (DatasourceEngine.POSTGRESQL, "SELECT id FROM t WHERE id = :id"),
        (DatasourceEngine.MYSQL, "SELECT id FROM t WHERE id = @id"),
        (DatasourceEngine.POSTGRESQL, "SELECT id FROM t WHERE id = $1"),
    ],
)
def test_unbound_query_parameters_are_rejected(engine, sql):
    _blocked(sql, engine, QueryDecisionCode.UNBOUND_PARAMETER)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM t WHERE id = ? LIMIT 5",
        "SELECT id FROM t WHERE id = :id ORDER BY id",
    ],
)
def test_unbound_parameters_outside_limit_are_rejected_before_bounding(engine, sql):
    _blocked(sql, engine, QueryDecisionCode.UNBOUND_PARAMETER)


def test_postgres_dollar_parameter_outside_limit_is_rejected():
    _blocked(
        "SELECT id FROM t WHERE id = $1 ORDER BY id",
        DatasourceEngine.POSTGRESQL,
        QueryDecisionCode.UNBOUND_PARAMETER,
    )


def test_mysql_treats_dollar_prefixed_token_as_an_identifier_not_a_parameter():
    # MySQL has no `$n` placeholder syntax and `$` is a legal identifier character, so
    # SQLGlot parses `$1` as a column reference rather than a bound-parameter carrier.
    # Only PostgreSQL exposes `$n` as a parameter, which the test above pins.
    decision = _approved("SELECT id FROM t WHERE id = $1", DatasourceEngine.MYSQL)

    assert QueryDecisionCode.UNBOUND_PARAMETER not in decision.codes


@pytest.mark.parametrize("engine", ENGINES)
def test_top_level_placeholder_limit_still_reports_non_literal_limit(engine):
    # The dedicated LIMIT check must win over the general unbound-parameter check.
    _blocked("SELECT id FROM t LIMIT ?", engine, QueryDecisionCode.NON_LITERAL_LIMIT)
