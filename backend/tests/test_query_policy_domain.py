from dataclasses import FrozenInstanceError

import pytest

from app.analytics.domain import (
    MAX_QUERY_ROWS,
    DatasourceEngine,
    PreparedQuery,
    QueryDecisionCode,
    QueryPolicyDecision,
    QueryPolicyRequest,
    QueryRisk,
)


def _prepared(**overrides):
    values = {
        "sql": "SELECT 1 LIMIT 1",
        "engine": DatasourceEngine.POSTGRESQL,
        "relations": (),
        "row_limit": 1,
        "query_hash": "0" * 64,
    }
    values.update(overrides)
    return PreparedQuery(**values)


def test_query_policy_request_defaults_and_is_immutable():
    request = QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.POSTGRESQL)
    assert request.max_rows == 1_000
    with pytest.raises(FrozenInstanceError):
        request.max_rows = 2  # type: ignore[misc]


@pytest.mark.parametrize("max_rows", [0, -1, MAX_QUERY_ROWS + 1, True])
def test_query_policy_request_rejects_invalid_row_caps(max_rows):
    with pytest.raises(ValueError):
        QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.MYSQL, max_rows=max_rows)


def test_query_policy_decision_requires_prepared_query_when_allowed():
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=True,
            risk=QueryRisk.LOW,
            codes=(QueryDecisionCode.APPROVED,),
        )


def test_blocked_decision_cannot_carry_a_prepared_query():
    prepared = PreparedQuery(
        sql="SELECT 1 LIMIT 1",
        engine=DatasourceEngine.POSTGRESQL,
        relations=(),
        row_limit=1,
        query_hash="0" * 64,
    )
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=False,
            risk=QueryRisk.BLOCKED,
            codes=(QueryDecisionCode.PARSE_ERROR,),
            prepared=prepared,
        )


def test_max_query_rows_is_the_documented_hard_ceiling():
    assert MAX_QUERY_ROWS == 10_000


def test_query_policy_request_accepts_empty_sql_and_the_hard_ceiling():
    assert QueryPolicyRequest(sql="", engine=DatasourceEngine.MYSQL).sql == ""
    assert QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.MYSQL, max_rows=MAX_QUERY_ROWS).max_rows == MAX_QUERY_ROWS
    assert QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.MYSQL, max_rows=1).max_rows == 1


@pytest.mark.parametrize("sql", [None, 1, 1.5, b"SELECT 1", ["SELECT 1"]])
def test_query_policy_request_rejects_non_string_sql(sql):
    with pytest.raises(ValueError):
        QueryPolicyRequest(sql=sql, engine=DatasourceEngine.MYSQL)


@pytest.mark.parametrize("engine", ["mysql", "postgres", "POSTGRESQL", None, 1, True])
def test_query_policy_request_rejects_non_enum_engines(engine):
    with pytest.raises(ValueError):
        QueryPolicyRequest(sql="SELECT 1", engine=engine)


def test_query_policy_request_is_immutable_for_every_field():
    request = QueryPolicyRequest(sql="SELECT 1", engine=DatasourceEngine.MYSQL)
    for field in ("sql", "engine"):
        with pytest.raises(FrozenInstanceError):
            setattr(request, field, "changed")


def test_prepared_query_is_immutable():
    prepared = _prepared()
    with pytest.raises(FrozenInstanceError):
        prepared.row_limit = 2  # type: ignore[misc]


def test_prepared_query_accepts_a_valid_contract():
    prepared = _prepared(relations=("analytics.public.orders", "region"), row_limit=0, query_hash="a1" * 32)
    assert prepared.relations == ("analytics.public.orders", "region")
    assert prepared.row_limit == 0
    assert prepared.query_hash == "a1" * 32


@pytest.mark.parametrize("sql", ["", "   ", None, 1])
def test_prepared_query_rejects_blank_or_non_string_sql(sql):
    with pytest.raises(ValueError):
        _prepared(sql=sql)


def test_prepared_query_rejects_untrimmed_sql():
    with pytest.raises(ValueError):
        _prepared(sql=" SELECT 1 LIMIT 1 ")


@pytest.mark.parametrize("engine", ["postgres", "POSTGRESQL", None, 1, True])
def test_prepared_query_rejects_invalid_engine(engine):
    with pytest.raises(ValueError):
        _prepared(engine=engine)


def test_prepared_query_rejects_non_tuple_relations():
    with pytest.raises(ValueError):
        _prepared(relations=["region"])


def test_prepared_query_rejects_duplicate_relations():
    with pytest.raises(ValueError):
        _prepared(relations=("region", "region"))


@pytest.mark.parametrize("relations", [("region", " "), ("",), (" region ",)])
def test_prepared_query_rejects_blank_or_untrimmed_relations(relations):
    with pytest.raises(ValueError):
        _prepared(relations=relations)


@pytest.mark.parametrize("row_limit", [-1, -100, True, 1.5, "1", None])
def test_prepared_query_rejects_invalid_row_limits(row_limit):
    with pytest.raises(ValueError):
        _prepared(row_limit=row_limit)


@pytest.mark.parametrize(
    "query_hash",
    ["", "0" * 63, "0" * 65, "A" * 64, "Z" * 64, "g" * 64, "0" * 63 + "-", None],
)
def test_prepared_query_rejects_non_lowercase_or_non_hex_hashes(query_hash):
    with pytest.raises(ValueError):
        _prepared(query_hash=query_hash)


def test_query_risk_values_are_stable_storage_contracts():
    assert QueryRisk.LOW.value == "low"
    assert QueryRisk.MEDIUM.value == "medium"
    assert QueryRisk.HIGH.value == "high"
    assert QueryRisk.BLOCKED.value == "blocked"


def test_query_decision_code_values_are_stable_storage_contracts():
    assert QueryDecisionCode.APPROVED.value == "approved"
    assert QueryDecisionCode.EMPTY_SQL.value == "empty_sql"
    assert QueryDecisionCode.PARSE_ERROR.value == "parse_error"
    assert QueryDecisionCode.MULTIPLE_STATEMENTS.value == "multiple_statements"
    assert QueryDecisionCode.UNSUPPORTED_STATEMENT.value == "unsupported_statement"
    assert QueryDecisionCode.FORBIDDEN_OPERATION.value == "forbidden_operation"
    assert QueryDecisionCode.WILDCARD_PROJECTION.value == "wildcard_projection"
    assert QueryDecisionCode.DANGEROUS_FUNCTION.value == "dangerous_function"
    assert QueryDecisionCode.OFFSET_NOT_ALLOWED.value == "offset_not_allowed"
    assert QueryDecisionCode.NON_LITERAL_LIMIT.value == "non_literal_limit"
    assert QueryDecisionCode.INVALID_LIMIT.value == "invalid_limit"
    assert QueryDecisionCode.LIMIT_APPLIED.value == "limit_applied"
    assert QueryDecisionCode.LIMIT_REDUCED.value == "limit_reduced"
    assert QueryDecisionCode.COMPLEX_QUERY.value == "complex_query"


def test_query_policy_decision_rejects_empty_codes():
    with pytest.raises(ValueError):
        QueryPolicyDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=())


def test_query_policy_decision_rejects_duplicate_codes():
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=False,
            risk=QueryRisk.BLOCKED,
            codes=(QueryDecisionCode.PARSE_ERROR, QueryDecisionCode.PARSE_ERROR),
        )


def test_query_policy_decision_rejects_non_tuple_codes():
    with pytest.raises(ValueError):
        QueryPolicyDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=[QueryDecisionCode.PARSE_ERROR])


@pytest.mark.parametrize("codes", [("approved",), (QueryDecisionCode.APPROVED, "approved"), (None,)])
def test_query_policy_decision_rejects_non_enum_codes(codes):
    with pytest.raises(ValueError):
        QueryPolicyDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=codes)


@pytest.mark.parametrize("risk", ["blocked", "low", None, 1, True])
def test_query_policy_decision_rejects_non_enum_risk(risk):
    with pytest.raises(ValueError):
        QueryPolicyDecision(allowed=False, risk=risk, codes=(QueryDecisionCode.PARSE_ERROR,))


@pytest.mark.parametrize("allowed", [1, 0, "true", None])
def test_query_policy_decision_rejects_non_boolean_allowed(allowed):
    with pytest.raises(ValueError):
        QueryPolicyDecision(allowed=allowed, risk=QueryRisk.BLOCKED, codes=(QueryDecisionCode.PARSE_ERROR,))


def test_allowed_decision_cannot_be_blocked():
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=True,
            risk=QueryRisk.BLOCKED,
            codes=(QueryDecisionCode.APPROVED,),
            prepared=_prepared(),
        )


def test_denied_decision_cannot_carry_a_prepared_query():
    with pytest.raises(ValueError):
        QueryPolicyDecision(
            allowed=False,
            risk=QueryRisk.HIGH,
            codes=(QueryDecisionCode.FORBIDDEN_OPERATION,),
            prepared=_prepared(),
        )


def test_allowed_decision_keeps_its_prepared_query_and_allowed_code_order():
    decision = QueryPolicyDecision(
        allowed=True,
        risk=QueryRisk.MEDIUM,
        codes=(QueryDecisionCode.LIMIT_APPLIED, QueryDecisionCode.COMPLEX_QUERY, QueryDecisionCode.APPROVED),
        prepared=_prepared(),
    )

    assert decision.allowed is True
    assert decision.risk is QueryRisk.MEDIUM
    assert decision.codes[-1] is QueryDecisionCode.APPROVED
    assert decision.prepared is not None


def test_blocked_decision_is_valid_without_a_prepared_query():
    decision = QueryPolicyDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(QueryDecisionCode.PARSE_ERROR,),
    )

    assert decision.allowed is False
    assert decision.prepared is None
