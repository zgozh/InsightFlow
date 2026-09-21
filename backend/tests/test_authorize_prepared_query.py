import pytest

from app.analytics.application import (
    AccessPolicyCatalog,
    AuthorizePreparedQuery,
    SchemaCatalog,
    SemanticQueryAuthorizer,
)
from app.analytics.domain import (
    AuthorizationDecisionCode,
    AuthorizedQuerySpec,
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceDefinition,
    DatasourceEngine,
    DatasourceStatus,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryAuthorizationDecision,
    QueryRisk,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)


class _DatasourceCatalog:
    def __init__(self, datasource, *, error=None):
        self._datasource = datasource
        self._error = error
        self.get_calls: list[tuple[str, str]] = []

    async def list_accessible(self, *, principal_id):
        return () if self._datasource is None else (self._datasource,)

    async def get_accessible(self, *, principal_id, datasource_id):
        self.get_calls.append((principal_id, datasource_id))
        if self._error is not None:
            raise self._error
        return self._datasource


class _SchemaCatalog:
    def __init__(self, snapshot, *, error=None):
        self._snapshot = snapshot
        self._error = error
        self.calls: list[str] = []

    async def get_current(self, *, datasource_id):
        self.calls.append(datasource_id)
        if self._error is not None:
            raise self._error
        return self._snapshot


class _PolicyCatalog:
    def __init__(self, policy, *, error=None):
        self._policy = policy
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def get_effective(self, *, principal_id, datasource_id):
        self.calls.append((principal_id, datasource_id))
        if self._error is not None:
            raise self._error
        return self._policy


class _Authorizer:
    def __init__(self, decision):
        self._decision = decision
        self.calls: list[dict] = []

    def authorize(self, *, prepared, schema, policy):
        self.calls.append({"prepared": prepared, "schema": schema, "policy": policy})
        return self._decision


def _datasource(engine=DatasourceEngine.POSTGRESQL, status=DatasourceStatus.ACTIVE):
    return DatasourceDefinition(
        id="ds-1",
        owner_id="user-1",
        name="Warehouse",
        engine=engine,
        secret_ref="env:SECRET",
        default_schema="public",
        status=status,
    )


def _prepared(engine=DatasourceEngine.POSTGRESQL):
    return PreparedQuery(
        sql="SELECT id FROM orders LIMIT 10",
        engine=engine,
        relations=("orders",),
        row_limit=10,
        query_hash="a" * 64,
    )


def _schema(datasource_id="ds-1", engine=DatasourceEngine.POSTGRESQL, version="s1"):
    return SchemaSnapshot(
        datasource_id=datasource_id,
        engine=engine,
        version=version,
        default_schema="public",
        relations=(
            RelationSchema(
                name="orders",
                schema="public",
                columns=(ColumnSchema(name="id", data_type="INT"),),
            ),
        ),
    )


def _policy(datasource_id="ds-1", principal_id="user-1", version="p1"):
    return PrincipalAccessPolicy(
        datasource_id=datasource_id,
        principal_id=principal_id,
        version=version,
        relations=(
            RelationAccessRule(
                name="orders",
                schema="public",
                columns=(ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),),
            ),
        ),
        allowed_functions=("count",),
    )


def _authorized(prepared, risk=QueryRisk.LOW):
    return AuthorizedQuerySpec(
        prepared=prepared,
        datasource_id="ds-1",
        principal_id="user-1",
        schema_version="s1",
        policy_version="p1",
        relations=("public.orders",),
        columns=("public.orders.id",),
        functions=(),
        risk=risk,
    )


def _allowed_decision(prepared, risk=QueryRisk.LOW):
    return QueryAuthorizationDecision(
        allowed=True,
        risk=risk,
        codes=(AuthorizationDecisionCode.APPROVED,),
        authorized=_authorized(prepared, risk),
    )


def _build(datasource_catalog, schema_catalog, policy_catalog, authorizer):
    return AuthorizePreparedQuery(
        datasource_catalog=datasource_catalog,
        schema_catalog=schema_catalog,
        policy_catalog=policy_catalog,
        authorizer=authorizer,
    )


@pytest.mark.asyncio
async def test_inaccessible_datasource_is_denied():
    use_case = _build(
        _DatasourceCatalog(None),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.allowed is False
    assert decision.risk is QueryRisk.BLOCKED
    assert decision.codes == (AuthorizationDecisionCode.DATASOURCE_NOT_ACCESSIBLE,)
    assert decision.authorized is None


@pytest.mark.parametrize("status", [DatasourceStatus.DISABLED, DatasourceStatus.UNHEALTHY])
@pytest.mark.asyncio
async def test_disabled_or_unhealthy_datasource_is_denied(status):
    use_case = _build(
        _DatasourceCatalog(_datasource(status=status)),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.allowed is False
    assert decision.codes == (AuthorizationDecisionCode.DATASOURCE_NOT_ACCESSIBLE,)


@pytest.mark.asyncio
async def test_engine_mismatch_is_rejected_before_schema_loading():
    schema_catalog = _SchemaCatalog(_schema())
    use_case = _build(
        _DatasourceCatalog(_datasource(engine=DatasourceEngine.MYSQL)),
        schema_catalog,
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(
        principal_id="user-1",
        datasource_id="ds-1",
        prepared=_prepared(engine=DatasourceEngine.POSTGRESQL),
    )

    assert decision.allowed is False
    assert decision.codes == (AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH,)
    assert schema_catalog.calls == []


@pytest.mark.asyncio
async def test_missing_schema_is_unavailable():
    schema_catalog = _SchemaCatalog(None)
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        schema_catalog,
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.allowed is False
    assert decision.risk is QueryRisk.BLOCKED
    assert decision.codes == (AuthorizationDecisionCode.SCHEMA_UNAVAILABLE,)
    assert schema_catalog.calls == ["ds-1"]


@pytest.mark.asyncio
async def test_schema_datasource_identity_mismatch_is_unavailable():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema(datasource_id="ds-other")),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.codes == (AuthorizationDecisionCode.SCHEMA_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_schema_engine_mismatch_is_unavailable():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema(engine=DatasourceEngine.MYSQL)),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.codes == (AuthorizationDecisionCode.SCHEMA_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_missing_policy_is_unavailable():
    policy_catalog = _PolicyCatalog(None)
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema()),
        policy_catalog,
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.allowed is False
    assert decision.risk is QueryRisk.BLOCKED
    assert decision.codes == (AuthorizationDecisionCode.POLICY_UNAVAILABLE,)
    assert policy_catalog.calls == [("user-1", "ds-1")]


@pytest.mark.asyncio
async def test_policy_datasource_identity_mismatch_is_unavailable():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy(datasource_id="ds-other")),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.codes == (AuthorizationDecisionCode.POLICY_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_policy_principal_identity_mismatch_is_unavailable():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy(principal_id="user-other")),
        _Authorizer(_allowed_decision(_prepared())),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision.codes == (AuthorizationDecisionCode.POLICY_UNAVAILABLE,)


@pytest.mark.asyncio
async def test_successful_path_delegates_the_loaded_values():
    prepared = _prepared()
    snapshot = _schema()
    policy = _policy()
    authorizer = _Authorizer(_allowed_decision(prepared))
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(snapshot),
        _PolicyCatalog(policy),
        authorizer,
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=prepared)

    assert decision.allowed is True
    assert decision.authorized is not None
    assert len(authorizer.calls) == 1
    assert authorizer.calls[0] == {"prepared": prepared, "schema": snapshot, "policy": policy}


@pytest.mark.asyncio
async def test_denied_decision_from_the_authorizer_is_returned_unchanged():
    denial = QueryAuthorizationDecision(
        allowed=False,
        risk=QueryRisk.BLOCKED,
        codes=(AuthorizationDecisionCode.UNKNOWN_RELATION,),
    )
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy()),
        _Authorizer(denial),
    )

    decision = await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())

    assert decision is denial


@pytest.mark.asyncio
async def test_datasource_catalog_errors_propagate_instead_of_becoming_approvals():
    use_case = _build(
        _DatasourceCatalog(_datasource(), error=RuntimeError("catalog down")),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    with pytest.raises(RuntimeError, match="catalog down"):
        await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())


@pytest.mark.asyncio
async def test_schema_catalog_errors_propagate_instead_of_becoming_approvals():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema(), error=RuntimeError("schema down")),
        _PolicyCatalog(_policy()),
        _Authorizer(_allowed_decision(_prepared())),
    )

    with pytest.raises(RuntimeError, match="schema down"):
        await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())


@pytest.mark.asyncio
async def test_policy_catalog_errors_propagate_instead_of_becoming_approvals():
    use_case = _build(
        _DatasourceCatalog(_datasource()),
        _SchemaCatalog(_schema()),
        _PolicyCatalog(_policy(), error=RuntimeError("policy down")),
        _Authorizer(_allowed_decision(_prepared())),
    )

    with pytest.raises(RuntimeError, match="policy down"):
        await use_case.execute(principal_id="user-1", datasource_id="ds-1", prepared=_prepared())


def test_use_case_ports_are_runtime_checkable_and_fakes_conform():
    assert getattr(SchemaCatalog, "_is_runtime_protocol", False)
    assert getattr(AccessPolicyCatalog, "_is_runtime_protocol", False)
    assert getattr(SemanticQueryAuthorizer, "_is_runtime_protocol", False)
    assert isinstance(_SchemaCatalog(_schema()), SchemaCatalog)
    assert isinstance(_PolicyCatalog(_policy()), AccessPolicyCatalog)


def test_semantic_authorizer_port_is_synchronous():
    # A coroutine function would break the deterministic in-process contract.
    assert not hasattr(_Authorizer(_allowed_decision(_prepared())).authorize, "__await__")
