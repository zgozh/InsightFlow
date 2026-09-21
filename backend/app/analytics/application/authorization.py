from typing import Protocol, runtime_checkable

from app.analytics.application.ports import DatasourceCatalog
from app.analytics.domain import (
    AuthorizationDecisionCode,
    DatasourceStatus,
    PreparedQuery,
    PrincipalAccessPolicy,
    QueryAuthorizationDecision,
    QueryRisk,
    SchemaSnapshot,
)


@runtime_checkable
class SchemaCatalog(Protocol):
    async def get_current(self, *, datasource_id: str) -> SchemaSnapshot | None: ...


@runtime_checkable
class AccessPolicyCatalog(Protocol):
    async def get_effective(self, *, principal_id: str, datasource_id: str) -> PrincipalAccessPolicy | None: ...


@runtime_checkable
class SemanticQueryAuthorizer(Protocol):
    def authorize(
        self,
        *,
        prepared: PreparedQuery,
        schema: SchemaSnapshot,
        policy: PrincipalAccessPolicy,
    ) -> QueryAuthorizationDecision: ...


def _denied(code: AuthorizationDecisionCode) -> QueryAuthorizationDecision:
    return QueryAuthorizationDecision(allowed=False, risk=QueryRisk.BLOCKED, codes=(code,))


class AuthorizePreparedQuery:
    """Orchestrates catalog lookups before delegating to the semantic authorizer."""

    def __init__(
        self,
        *,
        datasource_catalog: DatasourceCatalog,
        schema_catalog: SchemaCatalog,
        policy_catalog: AccessPolicyCatalog,
        authorizer: SemanticQueryAuthorizer,
    ) -> None:
        self._datasource_catalog = datasource_catalog
        self._schema_catalog = schema_catalog
        self._policy_catalog = policy_catalog
        self._authorizer = authorizer

    async def execute(self, *, principal_id: str, datasource_id: str, prepared: PreparedQuery) -> QueryAuthorizationDecision:
        datasource = await self._datasource_catalog.get_accessible(principal_id=principal_id, datasource_id=datasource_id)
        if datasource is None or datasource.status is not DatasourceStatus.ACTIVE:
            return _denied(AuthorizationDecisionCode.DATASOURCE_NOT_ACCESSIBLE)
        if datasource.engine is not prepared.engine:
            return _denied(AuthorizationDecisionCode.PREPARED_QUERY_MISMATCH)

        schema = await self._schema_catalog.get_current(datasource_id=datasource_id)
        if schema is None or schema.datasource_id != datasource_id or schema.engine is not datasource.engine:
            return _denied(AuthorizationDecisionCode.SCHEMA_UNAVAILABLE)

        policy = await self._policy_catalog.get_effective(principal_id=principal_id, datasource_id=datasource_id)
        if policy is None or policy.datasource_id != datasource_id or policy.principal_id != principal_id:
            return _denied(AuthorizationDecisionCode.POLICY_UNAVAILABLE)

        return self._authorizer.authorize(prepared=prepared, schema=schema, policy=policy)
