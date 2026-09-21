from dataclasses import replace

import pytest

from app.analytics.application import SemanticQueryAuthorizer
from app.analytics.domain import (
    MAX_QUERY_ROWS,
    AuthorizationDecisionCode,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    ColumnSensitivity,
    DatasourceEngine,
    PrincipalAccessPolicy,
    QueryPolicyRequest,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)
from app.analytics.infrastructure import SqlglotQueryPolicy, SqlglotSemanticAuthorizer

_ORDER_COLUMNS = (
    ColumnSchema(name="id", data_type="INT"),
    ColumnSchema(name="customer_id", data_type="INT"),
    ColumnSchema(name="amount", data_type="INT"),
    ColumnSchema(name="email", data_type="TEXT", sensitivity=ColumnSensitivity.PII),
    ColumnSchema(name="internal_note", data_type="TEXT", sensitivity=ColumnSensitivity.SENSITIVE),
)
_CUSTOMER_COLUMNS = (
    ColumnSchema(name="id", data_type="INT"),
    ColumnSchema(name="region", data_type="TEXT"),
)
_ALL_FUNCTIONS = ("count", "sum", "cast")


def _orders_relation(schema="public"):
    return RelationSchema(name="orders", schema=schema, columns=_ORDER_COLUMNS)


def _customers_relation(schema="public"):
    return RelationSchema(name="customers", schema=schema, columns=_CUSTOMER_COLUMNS)


def _snapshot(*, engine=DatasourceEngine.POSTGRESQL, default_schema="public", relations=None, version="s1"):
    return SchemaSnapshot(
        datasource_id="ds-1",
        engine=engine,
        version=version,
        default_schema=default_schema,
        relations=relations if relations is not None else (_orders_relation(), _customers_relation()),
    )


def _order_rules(*, schema="public", overrides=None):
    access = {
        "id": ColumnAccess.ALLOW,
        "customer_id": ColumnAccess.ALLOW,
        "amount": ColumnAccess.ALLOW,
        "email": ColumnAccess.ALLOW,
        "internal_note": ColumnAccess.ALLOW,
    }
    access.update(overrides or {})
    return RelationAccessRule(
        name="orders",
        schema=schema,
        columns=tuple(ColumnAccessRule(name=name, access=value) for name, value in access.items()),
    )


def _policy(*, relations=None, functions=_ALL_FUNCTIONS, datasource_id="ds-1", principal_id="user-1", version="p1"):
    if relations is None:
        relations = (
            _order_rules(),
            RelationAccessRule(
                name="customers",
                schema="public",
                columns=(
                    ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),
                    ColumnAccessRule(name="region", access=ColumnAccess.ALLOW),
                ),
            ),
        )
    return PrincipalAccessPolicy(
        datasource_id=datasource_id,
        principal_id=principal_id,
        version=version,
        relations=relations,
        allowed_functions=functions,
    )


def _prepared(sql, *, engine=DatasourceEngine.POSTGRESQL, max_rows=1_000):
    decision = SqlglotQueryPolicy().evaluate(QueryPolicyRequest(sql=sql, engine=engine, max_rows=max_rows))
    assert decision.allowed is True, decision
    assert decision.prepared is not None
    return decision.prepared


def _authorizer():
    return SqlglotSemanticAuthorizer(query_policy=SqlglotQueryPolicy())


def _authorize(sql, *, snapshot=None, policy=None, max_rows=1_000, engine=DatasourceEngine.POSTGRESQL, prepared=None):
    resolved = prepared if prepared is not None else _prepared(sql, engine=engine, max_rows=max_rows)
    return _authorizer().authorize(
        prepared=resolved,
        schema=snapshot if snapshot is not None else _snapshot(engine=engine),
        policy=policy if policy is not None else _policy(),
    )


def _authorize_prepared(prepared, *, snapshot=None, policy=None):
    return _authorizer().authorize(
        prepared=prepared,
        schema=snapshot if snapshot is not None else _snapshot(),
        policy=policy if policy is not None else _policy(),
    )


def _assert_blocked(decision, code):
    assert decision.allowed is False, decision
    assert decision.risk is QueryRisk.BLOCKED, decision
    assert decision.codes == (code,), decision
    assert decision.authorized is None


def _assert_high(decision, reason):
    assert decision.allowed is False, decision
    assert decision.risk is QueryRisk.HIGH, decision
    assert reason in decision.codes, decision
    assert decision.codes[-1] is AuthorizationDecisionCode.APPROVAL_REQUIRED, decision
    assert decision.authorized is None


# --- approvals -------------------------------------------------------------


def test_authentic_simple_query_is_approved():
    decision = _authorize("SELECT id FROM orders")

    assert decision.allowed is True
    assert decision.risk is QueryRisk.LOW
    assert decision.codes == (AuthorizationDecisionCode.APPROVED,)
    assert decision.authorized is not None
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)
    assert decision.authorized.functions == ()


def test_allowlisted_count_is_approved():
    decision = _authorize("SELECT COUNT(*) AS n FROM orders")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ()
    assert decision.authorized.functions == ("count",)


def test_allowlisted_sum_is_approved():
    decision = _authorize("SELECT SUM(amount) AS total FROM orders")

    assert decision.allowed is True
    assert decision.authorized.columns == ("public.orders.amount",)
    assert decision.authorized.functions == ("sum",)


def test_allowlisted_cast_is_approved():
    decision = _authorize("SELECT CAST(id AS TEXT) AS label FROM orders")

    assert decision.allowed is True
    assert decision.authorized.functions == ("cast",)


def test_table_alias_resolves_to_the_physical_relation():
    decision = _authorize("SELECT o.id AS order_id FROM orders AS o")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)


def test_qualified_join_is_approved_with_medium_risk():
    decision = _authorize("SELECT o.id AS order_id, c.region AS region FROM orders AS o JOIN customers AS c ON o.customer_id = c.id")

    assert decision.allowed is True
    assert decision.risk is QueryRisk.MEDIUM
    assert decision.authorized.relations == ("public.customers", "public.orders")
    assert decision.authorized.columns == (
        "public.customers.id",
        "public.customers.region",
        "public.orders.customer_id",
        "public.orders.id",
    )


def test_using_join_is_approved_and_not_treated_as_cartesian():
    decision = _authorize("SELECT o.id AS order_id FROM orders AS o JOIN customers AS c USING (id)")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.customers", "public.orders")


def test_cte_resolves_to_physical_lineage_and_excludes_the_alias():
    decision = _authorize("WITH totals AS (SELECT id FROM orders) SELECT id FROM totals")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)


def test_non_correlated_subquery_resolves_to_physical_lineage():
    decision = _authorize("SELECT nested.id AS id FROM (SELECT id FROM orders) AS nested")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)


def test_mysql_engine_is_supported():
    decision = _authorize("SELECT id FROM orders", engine=DatasourceEngine.MYSQL)

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)


def test_approved_spec_is_not_execution_authority():
    decision = _authorize("SELECT id FROM orders")
    authorized = decision.authorized

    assert not hasattr(authorized, "plan_id")
    assert not hasattr(authorized, "execute")
    assert authorized.prepared == _prepared("SELECT id FROM orders")


def test_original_prepared_sql_is_not_mutated_by_authorization():
    prepared = _prepared("SELECT id FROM orders")
    original = prepared.sql

    _authorizer().authorize(prepared=prepared, schema=_snapshot(), policy=_policy())

    assert prepared.sql == original


def test_adapter_satisfies_the_application_port():
    assert isinstance(_authorizer(), SemanticQueryAuthorizer)


# --- forgery ---------------------------------------------------------------


def test_forged_query_hash_is_rejected():
    prepared = _prepared("SELECT id FROM orders")
    forged = replace(prepared, query_hash="b" * 64)

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


def test_forged_relation_inventory_is_rejected():
    prepared = _prepared("SELECT id FROM orders")
    forged = replace(prepared, relations=("public.secrets",))

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


def test_forged_row_limit_is_rejected():
    prepared = _prepared("SELECT id FROM orders LIMIT 5")
    forged = replace(prepared, row_limit=7)

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


def test_forged_row_limit_above_the_hard_ceiling_is_rejected():
    prepared = _prepared("SELECT id FROM orders")
    forged = replace(prepared, row_limit=MAX_QUERY_ROWS + 1)

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


def test_forged_engine_is_rejected():
    prepared = _prepared("SELECT id FROM orders", engine=DatasourceEngine.POSTGRESQL)
    forged = replace(prepared, engine=DatasourceEngine.MYSQL)

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


def test_phase_2a_blocked_sql_cannot_be_smuggled_in_as_prepared():
    prepared = _prepared("SELECT id FROM orders")
    forged = replace(prepared, sql="SELECT id FROM orders; DROP TABLE orders")

    _assert_blocked(_authorize_prepared(forged), AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)


# --- relations and columns -------------------------------------------------


def test_unknown_relation_is_rejected():
    _assert_blocked(_authorize("SELECT id FROM missing_table"), AuthorizationDecisionCode.UNKNOWN_RELATION)


def test_relation_absent_from_the_policy_is_rejected():
    policy = _policy(relations=(_order_rules(),))

    _assert_blocked(
        _authorize("SELECT c.id AS id FROM customers AS c", policy=policy),
        AuthorizationDecisionCode.RELATION_NOT_ALLOWED,
    )


def test_physical_table_is_checked_even_without_a_projected_column():
    policy = _policy(relations=(_order_rules(),))

    _assert_blocked(
        _authorize("SELECT COUNT(*) AS n FROM customers", policy=policy),
        AuthorizationDecisionCode.RELATION_NOT_ALLOWED,
    )


def test_unknown_column_is_denied_by_qualification_validation():
    # qualify(validate_qualify_columns=True) rejects unresolvable columns before lineage work,
    # so the stable fail-closed code is ANALYSIS_ERROR rather than UNKNOWN_COLUMN.
    _assert_blocked(_authorize("SELECT missing_column FROM orders"), AuthorizationDecisionCode.ANALYSIS_ERROR)


def test_ambiguous_unqualified_relation_is_rejected():
    snapshot = _snapshot(
        default_schema="analytics",
        relations=(_orders_relation("public"), _orders_relation("other")),
    )
    policy = _policy(relations=(_order_rules(schema="public"), _order_rules(schema="other")))

    _assert_blocked(
        _authorize("SELECT id FROM orders", snapshot=snapshot, policy=policy),
        AuthorizationDecisionCode.ANALYSIS_ERROR,
    )


def test_column_absent_from_the_policy_rule_is_rejected():
    reduced = RelationAccessRule(
        name="orders",
        schema="public",
        columns=(
            ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),
            ColumnAccessRule(name="customer_id", access=ColumnAccess.ALLOW),
        ),
    )
    policy = _policy(relations=(reduced,))

    _assert_blocked(_authorize("SELECT amount FROM orders", policy=policy), AuthorizationDecisionCode.COLUMN_NOT_ALLOWED)


def test_denied_column_is_rejected():
    policy = _policy(relations=(_order_rules(overrides={"email": ColumnAccess.DENY}),))

    _assert_blocked(_authorize("SELECT email FROM orders", policy=policy), AuthorizationDecisionCode.COLUMN_NOT_ALLOWED)


def test_aggregate_only_column_used_directly_is_rejected():
    policy = _policy(relations=(_order_rules(overrides={"amount": ColumnAccess.AGGREGATE_ONLY}),))

    _assert_blocked(_authorize("SELECT amount FROM orders", policy=policy), AuthorizationDecisionCode.COLUMN_NOT_ALLOWED)


# --- functions -------------------------------------------------------------


def test_count_is_rejected_when_not_allowlisted():
    policy = _policy(functions=("sum", "cast"))

    _assert_blocked(
        _authorize("SELECT COUNT(*) AS n FROM orders", policy=policy),
        AuthorizationDecisionCode.FUNCTION_NOT_ALLOWED,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT nextval('seq') AS v FROM orders",
        "SELECT setval('seq', 1) AS v FROM orders",
        "SELECT GET_LOCK('lock', 1) AS v FROM orders",
        "SELECT pg_advisory_lock(1) AS v FROM orders",
        "SELECT unknown_udf(id) AS v FROM orders",
    ],
)
def test_side_effect_and_unknown_functions_are_default_denied(sql):
    _assert_blocked(_authorize(sql), AuthorizationDecisionCode.FUNCTION_NOT_ALLOWED)


def test_function_check_is_case_insensitive():
    decision = _authorize("SELECT COUNT(*) AS n FROM orders", policy=_policy(functions=("COUNT",)))

    assert decision.allowed is True
    assert decision.authorized.functions == ("count",)


# --- correlated ------------------------------------------------------------


def test_correlated_subquery_is_rejected():
    sql = "SELECT o.id AS id FROM orders AS o WHERE EXISTS (SELECT 1 AS one FROM customers AS c WHERE c.id = o.customer_id)"

    _assert_blocked(_authorize(sql), AuthorizationDecisionCode.CORRELATED_SUBQUERY_NOT_ALLOWED)


# --- HIGH conditions -------------------------------------------------------


def test_aggregate_only_column_under_an_aggregate_requires_approval():
    policy = _policy(relations=(_order_rules(overrides={"amount": ColumnAccess.AGGREGATE_ONLY}),))

    _assert_high(
        _authorize("SELECT SUM(amount) AS total FROM orders", policy=policy),
        AuthorizationDecisionCode.SENSITIVE_COLUMN,
    )


@pytest.mark.parametrize(
    ("sql", "column"),
    [
        ("SELECT email FROM orders", "email"),
        ("SELECT internal_note FROM orders", "internal_note"),
    ],
)
def test_sensitive_and_pii_columns_require_approval(sql, column):
    _assert_high(_authorize(sql), AuthorizationDecisionCode.SENSITIVE_COLUMN)


def test_pii_column_inside_a_non_correlated_subquery_requires_approval():
    sql = "SELECT nested.email AS email FROM (SELECT email FROM orders) AS nested"

    _assert_high(_authorize(sql), AuthorizationDecisionCode.SENSITIVE_COLUMN)


def test_explicitly_permitted_cross_schema_relation_requires_approval():
    snapshot = _snapshot(relations=(_orders_relation("public"), _orders_relation("other")))
    policy = _policy(relations=(_order_rules(schema="public"), _order_rules(schema="other")))

    _assert_high(
        _authorize("SELECT id FROM other.orders", snapshot=snapshot, policy=policy),
        AuthorizationDecisionCode.CROSS_SCHEMA,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT o.id AS id FROM orders AS o CROSS JOIN customers AS c",
        "SELECT o.id AS id FROM orders AS o, customers AS c",
    ],
)
def test_cartesian_joins_require_approval(sql):
    _assert_high(_authorize(sql), AuthorizationDecisionCode.CARTESIAN_JOIN)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT email FROM orders",
        "SELECT o.id AS id FROM orders AS o CROSS JOIN customers AS c",
    ],
)
def test_no_high_decision_is_ever_allowed(sql):
    decision = _authorize(sql)

    assert decision.risk is QueryRisk.HIGH
    assert decision.allowed is False
    assert decision.authorized is None


# --- hygiene ---------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT missing_column FROM orders",
        "SELECT missing_table.id AS id FROM missing_table",
        "SELECT nextval('seq') AS v FROM orders",
        "SELECT o.id AS id FROM orders AS o WHERE EXISTS (SELECT 1 AS one FROM customers AS c WHERE c.id = o.customer_id)",
        "SELECT email FROM orders",
    ],
)
def test_denials_never_leak_parser_text(sql):
    decision = _authorize(sql)
    rendered = repr(decision).lower()

    assert decision.allowed is False
    assert decision.authorized is None
    assert "sqlglot" not in rendered
    assert "traceback" not in rendered
    assert "optimizeerror" not in rendered
    assert "line:" not in rendered


def test_denied_decisions_never_carry_an_authorized_value():
    for sql in ("SELECT missing_column FROM orders", "SELECT email FROM orders"):
        decision = _authorize(sql)
        assert decision.authorized is None


# --- 标识符大小写与引号语义（PostgreSQL / MySQL） -----------------------------
#
# PostgreSQL：未加引号的标识符按方言折叠为小写，加引号的标识符精确匹配真实名称。
# 授权血缘必须指向数据库实际会解析到的对象，因此大小写不同的策略规则不能授权另一个真实对象。
# MySQL：缺少 lower_case_table_names 证据时必须精确匹配，不确定的大小写不一致一律安全拒绝。

_LOWER_ORDER_COLUMNS = (ColumnSchema(name="id", data_type="INT"),)
_MIXED_ORDER_COLUMNS = (
    ColumnSchema(name="id", data_type="INT"),
    ColumnSchema(name="Region", data_type="TEXT"),
)


def _case_snapshot(*, engine=DatasourceEngine.POSTGRESQL, with_lower=True, with_mixed=True):
    relations = []
    if with_lower:
        relations.append(RelationSchema(name="orders", schema="public", columns=_LOWER_ORDER_COLUMNS))
    if with_mixed:
        relations.append(RelationSchema(name="Orders", schema="public", columns=_MIXED_ORDER_COLUMNS))
    return SchemaSnapshot(
        datasource_id="ds-1",
        engine=engine,
        version="s1",
        default_schema="public",
        relations=tuple(relations),
    )


def _case_policy(
    *,
    with_lower=True,
    with_mixed=True,
    lower_name="orders",
    mixed_name="Orders",
    lower_columns=("id",),
    mixed_columns=("id", "Region"),
    functions=_ALL_FUNCTIONS,
):
    rules = []
    if with_lower:
        rules.append(
            RelationAccessRule(
                name=lower_name,
                schema="public",
                columns=tuple(ColumnAccessRule(name=name, access=ColumnAccess.ALLOW) for name in lower_columns),
            )
        )
    if with_mixed:
        rules.append(
            RelationAccessRule(
                name=mixed_name,
                schema="public",
                columns=tuple(ColumnAccessRule(name=name, access=ColumnAccess.ALLOW) for name in mixed_columns),
            )
        )
    return PrincipalAccessPolicy(
        datasource_id="ds-1",
        principal_id="user-1",
        version="p1",
        relations=tuple(rules),
        allowed_functions=functions,
    )


@pytest.mark.parametrize("sql", ["SELECT id FROM orders", "SELECT id FROM ORDERS"])
def test_postgres_unquoted_relation_folds_to_the_lowercase_object(sql):
    decision = _authorize(sql, snapshot=_case_snapshot(), policy=_case_policy())

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)


def test_postgres_quoted_lowercase_relation_matches_only_the_lowercase_object():
    decision = _authorize('SELECT id FROM "orders"', snapshot=_case_snapshot(), policy=_case_policy())

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)


def test_postgres_quoted_mixed_case_relation_matches_only_the_mixed_case_object():
    decision = _authorize('SELECT id FROM "Orders"', snapshot=_case_snapshot(), policy=_case_policy())

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.Orders",)
    assert decision.authorized.columns == ("public.Orders.id",)


def test_postgres_quoted_uppercase_relation_without_a_real_object_is_rejected():
    _assert_blocked(
        _authorize('SELECT id FROM "ORDERS"', snapshot=_case_snapshot(), policy=_case_policy()),
        AuthorizationDecisionCode.UNKNOWN_RELATION,
    )


@pytest.mark.parametrize("sql", ["SELECT id FROM orders", 'SELECT id FROM "orders"'])
def test_postgres_lowercase_reference_cannot_reach_a_mixed_case_object(sql):
    # 真实对象只有 public.Orders；小写引用在 PostgreSQL 中指向不存在的 orders，必须拒绝而不是改写成 Orders。
    snapshot = _case_snapshot(with_lower=False)
    policy = _case_policy(with_lower=False)

    _assert_blocked(_authorize(sql, snapshot=snapshot, policy=policy), AuthorizationDecisionCode.UNKNOWN_RELATION)


@pytest.mark.parametrize("sql", ["SELECT id FROM Orders", "SELECT id FROM ORDERS"])
def test_postgres_unquoted_mixed_case_relation_never_resolves_to_the_mixed_case_object(sql):
    # 未加引号的 Orders/ORDERS 折叠为 orders，不能命中真实对象 public.Orders。
    snapshot = _case_snapshot(with_lower=False)
    policy = _case_policy(with_lower=False)

    _assert_blocked(_authorize(sql, snapshot=snapshot, policy=policy), AuthorizationDecisionCode.UNKNOWN_RELATION)


def test_postgres_quoted_mixed_case_column_preserves_real_casing():
    decision = _authorize('SELECT "Region" FROM "Orders"', snapshot=_case_snapshot(), policy=_case_policy())

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.Orders",)
    assert decision.authorized.columns == ("public.Orders.Region",)


@pytest.mark.parametrize("sql", ['SELECT Region FROM "Orders"', 'SELECT "region" FROM "Orders"', 'SELECT "REGION" FROM "Orders"'])
def test_postgres_column_case_mismatch_is_rejected(sql):
    # 未加引号的 Region 折叠为 region；"region"/"REGION" 与真实列 Region 不匹配。
    _assert_blocked(
        _authorize(sql, snapshot=_case_snapshot(), policy=_case_policy()),
        AuthorizationDecisionCode.ANALYSIS_ERROR,
    )


def test_case_mismatched_relation_policy_cannot_authorize():
    # 真实对象是 public.Orders，但策略规则写成了 orders，必须拒绝。
    snapshot = _case_snapshot(with_lower=False)
    policy = _case_policy(with_lower=True, with_mixed=False)

    _assert_blocked(
        _authorize('SELECT id FROM "Orders"', snapshot=snapshot, policy=policy),
        AuthorizationDecisionCode.RELATION_NOT_ALLOWED,
    )


def test_case_mismatched_column_policy_cannot_authorize():
    # 真实列是 Region，但策略规则写成了 region，必须拒绝。
    snapshot = _case_snapshot(with_lower=False)
    policy = _case_policy(with_lower=False, mixed_columns=("id", "region"))

    _assert_blocked(
        _authorize('SELECT "Region" FROM "Orders"', snapshot=snapshot, policy=policy),
        AuthorizationDecisionCode.COLUMN_NOT_ALLOWED,
    )


def test_mysql_authorizes_only_an_exact_case_match():
    snapshot = _case_snapshot(engine=DatasourceEngine.MYSQL, with_lower=False)
    policy = _case_policy(with_lower=False)

    decision = _authorize(
        "SELECT id FROM Orders",
        snapshot=snapshot,
        policy=policy,
        engine=DatasourceEngine.MYSQL,
    )

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.Orders",)


@pytest.mark.parametrize("sql", ["SELECT id FROM orders", 'SELECT id FROM "orders"'])
def test_mysql_rejects_case_mismatch_without_server_case_mode_evidence(sql):
    # 本阶段没有 lower_case_table_names 证据：不确定的大小写不一致必须安全拒绝，不能猜测服务器语义。
    snapshot = _case_snapshot(engine=DatasourceEngine.MYSQL, with_lower=False)
    policy = _case_policy(with_lower=False)

    _assert_blocked(
        _authorize(sql, snapshot=snapshot, policy=policy, engine=DatasourceEngine.MYSQL),
        AuthorizationDecisionCode.UNKNOWN_RELATION,
    )


def test_plain_lowercase_schema_still_authorizes_its_own_queries():
    decision = _authorize("SELECT id FROM orders")

    assert decision.allowed is True
    assert decision.authorized.relations == ("public.orders",)
    assert decision.authorized.columns == ("public.orders.id",)
