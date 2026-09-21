from dataclasses import FrozenInstanceError, fields

import pytest

from app.analytics.domain import (
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
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)


def _prepared(**overrides):
    values = {
        "sql": "SELECT id FROM orders LIMIT 10",
        "engine": DatasourceEngine.POSTGRESQL,
        "relations": ("orders",),
        "row_limit": 10,
        "query_hash": "a" * 64,
    }
    values.update(overrides)
    return PreparedQuery(**values)


def _spec(**overrides):
    values = {
        "prepared": _prepared(),
        "datasource_id": "ds-1",
        "principal_id": "user-1",
        "schema_version": "s1",
        "policy_version": "p1",
        "relations": ("public.orders",),
        "columns": ("public.orders.id",),
        "functions": (),
        "risk": QueryRisk.LOW,
    }
    values.update(overrides)
    return AuthorizedQuerySpec(**values)


def test_column_sensitivity_values_are_stable_storage_contracts():
    assert ColumnSensitivity.STANDARD.value == "standard"
    assert ColumnSensitivity.SENSITIVE.value == "sensitive"
    assert ColumnSensitivity.PII.value == "pii"


def test_column_access_values_are_stable_storage_contracts():
    assert ColumnAccess.ALLOW.value == "allow"
    assert ColumnAccess.AGGREGATE_ONLY.value == "aggregate_only"
    assert ColumnAccess.DENY.value == "deny"


def test_authorization_decision_code_values_are_stable_storage_contracts():
    assert AuthorizationDecisionCode.APPROVED.value == "approved"
    assert AuthorizationDecisionCode.DATASOURCE_NOT_ACCESSIBLE.value == "datasource_not_accessible"
    assert AuthorizationDecisionCode.SCHEMA_UNAVAILABLE.value == "schema_unavailable"
    assert AuthorizationDecisionCode.POLICY_UNAVAILABLE.value == "policy_unavailable"
    assert AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH.value == "prepared_query_mismatch"
    assert AuthorizationDecisionCode.ANALYSIS_ERROR.value == "analysis_error"
    assert AuthorizationDecisionCode.CORRELATED_SUBQUERY_NOT_ALLOWED.value == "correlated_subquery_not_allowed"
    assert AuthorizationDecisionCode.UNKNOWN_RELATION.value == "unknown_relation"
    assert AuthorizationDecisionCode.RELATION_NOT_ALLOWED.value == "relation_not_allowed"
    assert AuthorizationDecisionCode.UNKNOWN_COLUMN.value == "unknown_column"
    assert AuthorizationDecisionCode.COLUMN_NOT_ALLOWED.value == "column_not_allowed"
    assert AuthorizationDecisionCode.FUNCTION_NOT_ALLOWED.value == "function_not_allowed"
    assert AuthorizationDecisionCode.SENSITIVE_COLUMN.value == "sensitive_column"
    assert AuthorizationDecisionCode.CROSS_SCHEMA.value == "cross_schema"
    assert AuthorizationDecisionCode.CARTESIAN_JOIN.value == "cartesian_join"
    assert AuthorizationDecisionCode.APPROVAL_REQUIRED.value == "approval_required"


def test_column_schema_is_frozen_and_slotted():
    column = ColumnSchema(name="id", data_type="INT", sensitivity=ColumnSensitivity.PII)

    assert column.sensitivity is ColumnSensitivity.PII
    assert not hasattr(column, "__dict__")
    with pytest.raises(FrozenInstanceError):
        column.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize("name", ["", "   ", " id ", None, 1])
def test_column_schema_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        ColumnSchema(name=name, data_type="INT")


@pytest.mark.parametrize("data_type", ["", "   ", " INT ", None, 1])
def test_column_schema_rejects_invalid_data_types(data_type):
    with pytest.raises(ValueError):
        ColumnSchema(name="id", data_type=data_type)


@pytest.mark.parametrize("sensitivity", ["pii", "STANDARD", None, 1])
def test_column_schema_rejects_non_enum_sensitivity(sensitivity):
    with pytest.raises(ValueError):
        ColumnSchema(name="id", data_type="INT", sensitivity=sensitivity)


def test_relation_schema_is_frozen_and_defaults_catalog_to_none():
    relation = RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="INT"),))

    assert relation.catalog is None
    with pytest.raises(FrozenInstanceError):
        relation.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize("catalog", ["", "   ", " cat ", 1])
def test_relation_schema_rejects_invalid_catalog(catalog):
    with pytest.raises(ValueError):
        RelationSchema(name="orders", schema="public", columns=(), catalog=catalog)


def test_relation_schema_requires_a_tuple_of_columns():
    with pytest.raises(ValueError):
        RelationSchema(name="orders", schema="public", columns=[ColumnSchema(name="id", data_type="INT")])


def test_relation_schema_rejects_duplicate_column_names():
    with pytest.raises(ValueError):
        RelationSchema(
            name="orders",
            schema="public",
            columns=(ColumnSchema(name="id", data_type="INT"), ColumnSchema(name="id", data_type="BIGINT")),
        )


def test_relation_schema_accepts_an_empty_column_tuple():
    assert RelationSchema(name="orders", schema="public", columns=()).columns == ()


def test_schema_snapshot_is_frozen_and_carries_identity():
    snapshot = SchemaSnapshot(
        datasource_id="ds-1",
        engine=DatasourceEngine.MYSQL,
        version="s1",
        default_schema="public",
        relations=(RelationSchema(name="orders", schema="public", columns=()),),
    )

    assert snapshot.engine is DatasourceEngine.MYSQL
    assert snapshot.default_schema == "public"
    with pytest.raises(FrozenInstanceError):
        snapshot.version = "s2"  # type: ignore[misc]


@pytest.mark.parametrize("engine", ["mysql", "POSTGRESQL", None, 1])
def test_schema_snapshot_rejects_non_enum_engine(engine):
    with pytest.raises(ValueError):
        SchemaSnapshot(datasource_id="ds-1", engine=engine, version="s1", default_schema="public", relations=())


@pytest.mark.parametrize("version", ["", "   ", " s1 ", None])
def test_schema_snapshot_rejects_invalid_version(version):
    with pytest.raises(ValueError):
        SchemaSnapshot(
            datasource_id="ds-1",
            engine=DatasourceEngine.MYSQL,
            version=version,
            default_schema="public",
            relations=(),
        )


def test_schema_snapshot_rejects_non_tuple_relations():
    with pytest.raises(ValueError):
        SchemaSnapshot(
            datasource_id="ds-1",
            engine=DatasourceEngine.MYSQL,
            version="s1",
            default_schema="public",
            relations=[RelationSchema(name="orders", schema="public", columns=())],
        )


def test_schema_snapshot_rejects_duplicate_relation_keys():
    relation = RelationSchema(name="orders", schema="public", columns=())
    with pytest.raises(ValueError):
        SchemaSnapshot(
            datasource_id="ds-1",
            engine=DatasourceEngine.MYSQL,
            version="s1",
            default_schema="public",
            relations=(relation, relation),
        )


def test_column_access_rule_is_frozen_and_validates_access():
    rule = ColumnAccessRule(name="email", access=ColumnAccess.DENY)

    assert rule.access is ColumnAccess.DENY
    with pytest.raises(FrozenInstanceError):
        rule.name = "other"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ColumnAccessRule(name="email", access="deny")


def test_relation_access_rule_rejects_duplicate_columns():
    with pytest.raises(ValueError):
        RelationAccessRule(
            name="orders",
            schema="public",
            columns=(
                ColumnAccessRule(name="email", access=ColumnAccess.DENY),
                ColumnAccessRule(name="email", access=ColumnAccess.ALLOW),
            ),
        )


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


def test_policy_defaults_allowed_functions_to_an_empty_tuple():
    assert PrincipalAccessPolicy(datasource_id="ds-1", principal_id="user-1", version="p1", relations=()).allowed_functions == ()


def test_policy_is_frozen():
    policy = PrincipalAccessPolicy(datasource_id="ds-1", principal_id="user-1", version="p1", relations=())

    with pytest.raises(FrozenInstanceError):
        policy.version = "p2"  # type: ignore[misc]


@pytest.mark.parametrize("field", ["datasource_id", "principal_id", "version"])
@pytest.mark.parametrize("value", ["", "   ", " x ", None, 1])
def test_policy_rejects_invalid_identity_fields(field, value):
    values = {"datasource_id": "ds-1", "principal_id": "user-1", "version": "p1"}
    values[field] = value
    with pytest.raises(ValueError):
        PrincipalAccessPolicy(relations=(), **values)


def test_policy_casefolds_function_names_and_preserves_order():
    policy = PrincipalAccessPolicy(
        datasource_id="ds-1",
        principal_id="user-1",
        version="p1",
        relations=(),
        allowed_functions=("COUNT", "sum"),
    )

    assert policy.allowed_functions == ("count", "sum")


def test_policy_rejects_duplicate_functions_after_casefolding():
    with pytest.raises(ValueError):
        PrincipalAccessPolicy(
            datasource_id="ds-1",
            principal_id="user-1",
            version="p1",
            relations=(),
            allowed_functions=("sum", "SUM"),
        )


@pytest.mark.parametrize("functions", [["count"], ("",), ("  ",), (None,)])
def test_policy_rejects_invalid_function_collections(functions):
    with pytest.raises(ValueError):
        PrincipalAccessPolicy(
            datasource_id="ds-1",
            principal_id="user-1",
            version="p1",
            relations=(),
            allowed_functions=functions,
        )


def test_policy_rejects_duplicate_relations():
    relation = RelationAccessRule(name="orders", schema="public", columns=())
    with pytest.raises(ValueError):
        PrincipalAccessPolicy(datasource_id="ds-1", principal_id="user-1", version="p1", relations=(relation, relation))


def test_authorized_value_has_no_execution_authority():
    assert {field.name for field in fields(AuthorizedQuerySpec)} == {
        "prepared",
        "datasource_id",
        "principal_id",
        "schema_version",
        "policy_version",
        "relations",
        "columns",
        "functions",
        "risk",
    }
    spec = _spec()

    assert not hasattr(spec, "plan_id")
    assert not hasattr(spec, "execute")
    assert not hasattr(spec, "connection")
    assert not hasattr(spec, "credential")


def test_authorized_value_is_frozen():
    spec = _spec()

    with pytest.raises(FrozenInstanceError):
        spec.risk = QueryRisk.MEDIUM  # type: ignore[misc]


@pytest.mark.parametrize("risk", [QueryRisk.HIGH, QueryRisk.BLOCKED, "low", None, 1])
def test_authorized_value_rejects_non_success_risk(risk):
    with pytest.raises(ValueError):
        _spec(risk=risk)


@pytest.mark.parametrize("field", ["relations", "columns", "functions"])
def test_authorized_value_requires_tuples(field):
    with pytest.raises(ValueError):
        _spec(**{field: ["public.orders"]})


@pytest.mark.parametrize("field", ["relations", "columns", "functions"])
def test_authorized_value_rejects_duplicate_inventory_entries(field):
    with pytest.raises(ValueError):
        _spec(**{field: ("public.orders", "public.orders")})


@pytest.mark.parametrize("field", ["relations", "columns", "functions"])
@pytest.mark.parametrize("value", [("",), ("  ",), (" public.orders ",)])
def test_authorized_value_rejects_blank_or_untrimmed_inventory_entries(field, value):
    with pytest.raises(ValueError):
        _spec(**{field: value})


def test_authorized_value_requires_a_prepared_query():
    with pytest.raises(ValueError):
        _spec(prepared="SELECT 1")


def test_allowed_decision_requires_an_authorized_value():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(allowed=True, risk=QueryRisk.LOW, codes=(AuthorizationDecisionCode.APPROVED,))


def test_allowed_decision_requires_non_high_authorized_value():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=True,
            risk=QueryRisk.HIGH,
            codes=(AuthorizationDecisionCode.APPROVED,),
        )


def test_allowed_decision_cannot_be_blocked():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=True,
            risk=QueryRisk.BLOCKED,
            codes=(AuthorizationDecisionCode.APPROVED,),
            authorized=_spec(),
        )


def test_allowed_decision_rejects_a_risk_mismatch_with_its_authorized_value():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=True,
            risk=QueryRisk.MEDIUM,
            codes=(AuthorizationDecisionCode.APPROVED,),
            authorized=_spec(risk=QueryRisk.LOW),
        )


def test_allowed_decision_carries_its_authorized_value():
    spec = _spec()
    decision = QueryAuthorizationDecision(
        allowed=True,
        risk=QueryRisk.LOW,
        codes=(AuthorizationDecisionCode.APPROVED,),
        authorized=spec,
    )

    assert decision.allowed is True
    assert decision.authorized is spec


@pytest.mark.parametrize("codes", [(), ("approved",), (AuthorizationDecisionCode.APPROVED, AuthorizationDecisionCode.APPROVED)])
def test_decision_codes_must_be_a_non_empty_unique_enum_tuple(codes):
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=codes)


def test_decision_rejects_non_tuple_codes():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=[AuthorizationDecisionCode.APPROVED])


@pytest.mark.parametrize("allowed", [1, 0, "true", None])
def test_decision_rejects_non_boolean_allowed(allowed):
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(allowed=allowed, risk=QueryRisk.BLOCKED, codes=(AuthorizationDecisionCode.ANALYSIS_ERROR,))


@pytest.mark.parametrize("risk", ["high", "blocked", None, 1])
def test_decision_rejects_non_enum_risk(risk):
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(allowed=False, risk=risk, codes=(AuthorizationDecisionCode.ANALYSIS_ERROR,))


def test_denied_decision_cannot_carry_an_authorized_value():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=False,
            risk=QueryRisk.HIGH,
            codes=(AuthorizationDecisionCode.SENSITIVE_COLUMN, AuthorizationDecisionCode.APPROVAL_REQUIRED),
            authorized=_spec(),
        )


def test_blocked_denial_is_valid_without_an_authorized_value():
    decision = QueryAuthorizationDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(AuthorizationDecisionCode.UNKNOWN_RELATION,),
    )

    assert decision.authorized is None


def test_denied_high_decision_must_end_with_approval_required():
    decision = QueryAuthorizationDecision(
        allowed=False,
        risk=QueryRisk.HIGH,
        codes=(AuthorizationDecisionCode.CROSS_SCHEMA, AuthorizationDecisionCode.APPROVAL_REQUIRED),
    )

    assert decision.codes[-1] is AuthorizationDecisionCode.APPROVAL_REQUIRED


def test_denied_high_decision_without_approval_required_is_rejected():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=False,
            risk=QueryRisk.HIGH,
            codes=(AuthorizationDecisionCode.CROSS_SCHEMA,),
        )


def test_blocked_denial_cannot_end_with_approval_required():
    with pytest.raises(ValueError):
        QueryAuthorizationDecision(
            allowed=False,
            risk=QueryRisk.BLOCKED,
            codes=(AuthorizationDecisionCode.APPROVAL_REQUIRED,),
        )
