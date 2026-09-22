"""`/api/analytics` 的窄 FastAPI router（Phase 2C2 §6）。

职责边界：**只**做认证主体解析、管理员门禁、DTO ⇄ domain 映射与稳定错误映射。它永远不直接
调用业务数据库 gateway、plan store 或 repository —— 那些都在 `AnalyticsServices` 里的应用
用例之后，Phase 3 的 Agent Tool 复用同一批用例。

顺序保证：

- 管理员门禁是路由依赖，在请求体校验与任何 repository 调用之前执行；
- `principal_id` / `owner_id` 只来自认证上下文（`get_current_user`），请求体里的同名字段在
  DTO 层就被 422 拒绝；
- 不可用时（disabled / memory / 未装配）稳定 503，绝不降级成内存控制面。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.analytics.api.models import (
    MAX_PLAN_ID_CHARACTERS,
    MAX_SQL_CHARACTERS,
    AccessPolicyRequest,
    AccessPolicyView,
    AdminDatasourceListResponse,
    AdminDatasourceView,
    AnalyticsErrorResponse,
    ColumnAccessRuleView,
    ColumnSchemaView,
    DatasourceCreateRequest,
    DatasourceListResponse,
    DatasourceUpdateRequest,
    DatasourceView,
    MetricCreateRequest,
    MetricListResponse,
    MetricUpdateRequest,
    MetricView,
    QueryAuditPageResponse,
    QueryAuditView,
    QueryExecutionRequest,
    QueryExecutionResponse,
    QueryPlanRequest,
    QueryPlanResponse,
    QueryResultView,
    RelationAccessRuleView,
    RelationSchemaView,
    SchemaSnapshotRequest,
    SchemaSnapshotView,
)
from app.analytics.application import AnalyticsNotFoundError, AnalyticsStorageError, PersistenceConflictError, PersistenceDataError
from app.analytics.composition import AnalyticsServices
from app.analytics.domain import (
    ColumnAccessRule,
    ColumnSchema,
    DatasourceDefinition,
    MetricDefinition,
    PrincipalAccessPolicy,
    QueryAuditRecord,
    RelationAccessRule,
    RelationSchema,
    SchemaSnapshot,
)
from app.gateway.deps import get_current_user, require_admin_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_INVALID_REQUEST = {"code": "invalid_analytics_request"}
_NOT_FOUND = {"code": "analytics_not_found"}
_CONFLICT = {"code": "analytics_version_conflict"}
_UNAVAILABLE = {"code": "analytics_unavailable"}
_STORAGE_UNAVAILABLE = {"code": "analytics_storage_unavailable"}


def install_request_error_handler(app) -> None:
    """把 `/api/analytics` 下的 422 折叠成不含输入的稳定响应。

    FastAPI 默认把 Pydantic 的 `input` 原样放进 422 响应体；对 raw SQL 与 plan token 来说，
    那等于把敏感原值回显给客户端。其他路径继续走 FastAPI 的默认处理器，行为完全不变。
    """

    @app.exception_handler(RequestValidationError)
    async def _analytics_validation_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith(router.prefix):
            return JSONResponse(status_code=422, content={"detail": _INVALID_REQUEST})
        return await request_validation_exception_handler(request, exc)


async def _principal(request: Request) -> str:
    """主体只来自认证上下文；没有任何请求体字段参与。"""

    user_id = await get_current_user(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def _require_admin(request: Request) -> None:
    await require_admin_user(request, detail="Analytics administration requires an administrator")


async def _guarded(operation):
    """把应用层失败映射成稳定 HTTP 状态；驱动/存储异常文本一律不外泄。"""

    try:
        return await operation
    except HTTPException:
        raise
    except AnalyticsNotFoundError as error:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from error
    except PersistenceConflictError as error:
        raise HTTPException(status_code=409, detail=_CONFLICT) from error
    except (ValueError, TypeError) as error:
        # 领域不变量拒绝客户端输入：脱敏成 422，绝不回显原值。
        raise HTTPException(status_code=422, detail=_INVALID_REQUEST) from error
    except (AnalyticsStorageError, PersistenceDataError) as error:
        raise HTTPException(status_code=503, detail=_STORAGE_UNAVAILABLE) from error
    except Exception as error:  # noqa: BLE001 - 未知 repository/driver 失败同样脱敏
        raise HTTPException(status_code=503, detail=_STORAGE_UNAVAILABLE) from error


def _services(request: Request) -> AnalyticsServices:
    services = getattr(request.app.state, "analytics_services", None)
    if services is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    return services


# --- 映射 -------------------------------------------------------------------


def _datasource_view(datasource: DatasourceDefinition) -> DatasourceView:
    return DatasourceView(id=datasource.id, name=datasource.name, engine=datasource.engine, default_schema=datasource.default_schema, status=datasource.status)


def _admin_datasource_view(datasource: DatasourceDefinition) -> AdminDatasourceView:
    return AdminDatasourceView(
        id=datasource.id,
        owner_id=datasource.owner_id,
        name=datasource.name,
        engine=datasource.engine,
        secret_ref=datasource.secret_ref,
        default_schema=datasource.default_schema,
        status=datasource.status,
    )


def _metric_view(metric: MetricDefinition) -> MetricView:
    return MetricView(key=metric.key, name=metric.name, description=metric.description, expression=metric.expression, dimensions=metric.dimensions, version=metric.version, status=metric.status)


def _schema_view(snapshot: SchemaSnapshot) -> SchemaSnapshotView:
    return SchemaSnapshotView(
        datasource_id=snapshot.datasource_id,
        engine=snapshot.engine,
        version=snapshot.version,
        default_schema=snapshot.default_schema,
        relations=tuple(
            RelationSchemaView(
                name=relation.name,
                schema_=relation.schema,
                catalog=relation.catalog,
                columns=tuple(ColumnSchemaView(name=column.name, data_type=column.data_type, sensitivity=column.sensitivity) for column in relation.columns),
            )
            for relation in snapshot.relations
        ),
    )


def _policy_view(policy: PrincipalAccessPolicy) -> AccessPolicyView:
    return AccessPolicyView(
        datasource_id=policy.datasource_id,
        principal_id=policy.principal_id,
        version=policy.version,
        relations=tuple(
            RelationAccessRuleView(
                name=relation.name,
                schema_=relation.schema,
                catalog=relation.catalog,
                columns=tuple(ColumnAccessRuleView(name=column.name, access=column.access) for column in relation.columns),
            )
            for relation in policy.relations
        ),
        allowed_functions=policy.allowed_functions,
    )


def _audit_view(record: QueryAuditRecord) -> QueryAuditView:
    return QueryAuditView(
        id=record.id,
        principal_id=record.principal_id,
        datasource_id=record.datasource_id,
        phase=record.phase,
        status=record.status,
        query_hash=record.query_hash,
        risk=record.risk,
        decision_code=record.decision_code,
        schema_version=record.schema_version,
        policy_version=record.policy_version,
        estimated_rows=record.estimated_rows,
        engine_cost=record.engine_cost,
        plan_digest=record.plan_digest,
        row_count=record.row_count,
        byte_count=record.byte_count,
        truncated=record.truncated,
        latency_ms=record.latency_ms,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _audit_page(records: tuple[QueryAuditRecord, ...], limit: int) -> QueryAuditPageResponse:
    has_more = len(records) == limit
    last = records[-1] if records else None
    return QueryAuditPageResponse(
        audits=tuple(_audit_view(record) for record in records),
        has_more=has_more,
        # 只有确实还有下一页时才给游标：否则客户端会多跑一次空查询。
        next_before_started_at=last.started_at if (last is not None and has_more) else None,
        next_before_id=last.id if (last is not None and has_more) else None,
    )


def _metric(owner_id: str, key: str, payload) -> MetricDefinition:
    return MetricDefinition(
        key=key,
        owner_id=owner_id,
        name=payload.name,
        description=payload.description,
        expression=payload.expression,
        dimensions=payload.dimensions,
        version=payload.version,
        status=payload.status,
    )


def _relations(payload) -> tuple[RelationSchema, ...]:
    return tuple(
        RelationSchema(
            name=relation.name,
            schema=relation.schema_,
            catalog=relation.catalog,
            columns=tuple(ColumnSchema(name=column.name, data_type=column.data_type, sensitivity=column.sensitivity) for column in relation.columns),
        )
        for relation in payload
    )


def _access_rules(payload) -> tuple[RelationAccessRule, ...]:
    return tuple(
        RelationAccessRule(
            name=relation.name,
            schema=relation.schema_,
            catalog=relation.catalog,
            columns=tuple(ColumnAccessRule(name=column.name, access=column.access) for column in relation.columns),
        )
        for relation in payload
    )


async def _read_audits(request: Request, principal_id: str, limit: int | None, before_started_at: datetime | None, before_id: str | None) -> QueryAuditPageResponse:
    services = _services(request)
    page_size = services.config.audit_page_size if limit is None else limit
    if (before_started_at is None) != (before_id is None):
        raise HTTPException(status_code=422, detail=_INVALID_REQUEST)
    records = await _guarded(
        services.audit_reader.list_for_principal(
            principal_id=principal_id,
            limit=page_size,
            before_started_at=before_started_at,
            before_id=before_id,
        )
    )
    return _audit_page(records, page_size)


# --- 用户接口 ---------------------------------------------------------------


@router.get("/datasources", response_model=DatasourceListResponse)
async def list_datasources(request: Request, principal: str = Depends(_principal)) -> DatasourceListResponse:
    services = _services(request)
    datasources = await _guarded(services.datasources.list_accessible(principal_id=principal))
    return DatasourceListResponse(datasources=tuple(_datasource_view(datasource) for datasource in datasources))


@router.get("/metrics", response_model=MetricListResponse)
async def list_metrics(request: Request, principal: str = Depends(_principal)) -> MetricListResponse:
    services = _services(request)
    metrics = await _guarded(services.metrics.list_accessible(principal_id=principal))
    return MetricListResponse(metrics=tuple(_metric_view(metric) for metric in metrics))


@router.post("/query-plans", response_model=QueryPlanResponse, response_model_exclude_none=True)
async def create_query_plan(payload: QueryPlanRequest, request: Request, principal: str = Depends(_principal)) -> QueryPlanResponse:
    services = _services(request)
    raw_sql = payload.sql.get_secret_value()
    if not raw_sql.strip() or len(raw_sql) > MAX_SQL_CHARACTERS:
        # 不把原值放进 detail：长度或空值错误同样可能带上敏感片段。
        raise HTTPException(status_code=422, detail=_INVALID_REQUEST)

    delivery = await _guarded(services.plan_query.execute(principal_id=principal, datasource_id=payload.datasource_id, raw_sql=raw_sql))
    receipt = delivery.receipt
    return QueryPlanResponse(
        code=delivery.code,
        plan_id=None if receipt is None else receipt.plan_id,
        expires_at=None if receipt is None else receipt.expires_at,
        estimated_rows=None if receipt is None else receipt.estimate.estimated_rows,
        engine_cost=None if receipt is None else receipt.estimate.engine_cost,
        plan_digest=None if receipt is None else receipt.estimate.plan_digest,
    )


@router.post("/query-executions", response_model=QueryExecutionResponse, response_model_exclude_none=True)
async def execute_query_plan(payload: QueryExecutionRequest, request: Request, principal: str = Depends(_principal)) -> QueryExecutionResponse:
    services = _services(request)
    plan_id = payload.plan_id.get_secret_value()
    if not plan_id.strip() or len(plan_id) > MAX_PLAN_ID_CHARACTERS:
        raise HTTPException(status_code=422, detail=_INVALID_REQUEST)

    delivery = await _guarded(services.execute_query.execute(principal_id=principal, plan_id=plan_id))
    result = delivery.result
    return QueryExecutionResponse(
        code=delivery.code,
        result=None if result is None else QueryResultView(columns=result.columns, rows=result.rows, row_count=result.row_count, byte_count=result.byte_count, truncated=result.truncated),
    )


@router.get("/audits", response_model=QueryAuditPageResponse)
async def list_audits(
    request: Request,
    principal: str = Depends(_principal),
    limit: int | None = Query(default=None, ge=1, le=100),
    before_started_at: datetime | None = Query(default=None),
    before_id: str | None = Query(default=None),
) -> QueryAuditPageResponse:
    return await _read_audits(request, principal, limit, before_started_at, before_id)


# --- 管理员接口 -------------------------------------------------------------

admin_router = APIRouter(prefix="/admin", dependencies=[Depends(_require_admin)])


@admin_router.get("/datasources", response_model=AdminDatasourceListResponse)
async def admin_list_datasources(request: Request, principal: str = Depends(_principal)) -> AdminDatasourceListResponse:
    services = _services(request)
    datasources = await _guarded(services.administration.list_datasources(owner_id=principal))
    return AdminDatasourceListResponse(datasources=tuple(_admin_datasource_view(datasource) for datasource in datasources))


@admin_router.post("/datasources", response_model=AdminDatasourceView)
async def admin_create_datasource(payload: DatasourceCreateRequest, request: Request, principal: str = Depends(_principal)) -> AdminDatasourceView:
    services = _services(request)
    datasource = await _guarded(
        services.administration.create_datasource(
            owner_id=principal,
            name=payload.name,
            engine=payload.engine,
            secret_ref=payload.secret_ref,
            default_schema=payload.default_schema,
        )
    )
    return _admin_datasource_view(datasource)


@admin_router.get("/datasources/{datasource_id}", response_model=AdminDatasourceView)
async def admin_get_datasource(datasource_id: str, request: Request, principal: str = Depends(_principal)) -> AdminDatasourceView:
    services = _services(request)
    datasource = await _guarded(services.administration.get_datasource(owner_id=principal, datasource_id=datasource_id))
    if datasource is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _admin_datasource_view(datasource)


@admin_router.put("/datasources/{datasource_id}", response_model=AdminDatasourceView)
async def admin_update_datasource(datasource_id: str, payload: DatasourceUpdateRequest, request: Request, principal: str = Depends(_principal)) -> AdminDatasourceView:
    services = _services(request)
    datasource = await _guarded(
        services.administration.update_datasource(
            owner_id=principal,
            datasource_id=datasource_id,
            name=payload.name,
            secret_ref=payload.secret_ref,
            default_schema=payload.default_schema,
            status=payload.status,
        )
    )
    if datasource is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _admin_datasource_view(datasource)


@admin_router.get("/datasources/{datasource_id}/schema", response_model=SchemaSnapshotView)
async def admin_get_schema(datasource_id: str, request: Request, principal: str = Depends(_principal)) -> SchemaSnapshotView:
    services = _services(request)
    snapshot = await _guarded(services.administration.get_schema(owner_id=principal, datasource_id=datasource_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _schema_view(snapshot)


@admin_router.put("/datasources/{datasource_id}/schema", response_model=SchemaSnapshotView)
async def admin_replace_schema(datasource_id: str, payload: SchemaSnapshotRequest, request: Request, principal: str = Depends(_principal)) -> SchemaSnapshotView:
    services = _services(request)
    snapshot = await _guarded(
        services.administration.replace_schema(
            owner_id=principal,
            datasource_id=datasource_id,
            version=payload.version,
            default_schema=payload.default_schema,
            relations=_relations(payload.relations),
            expected_version=payload.expected_version,
        )
    )
    return _schema_view(snapshot)


@admin_router.get("/datasources/{datasource_id}/policies/{principal_id}", response_model=AccessPolicyView)
async def admin_get_policy(datasource_id: str, principal_id: str, request: Request, principal: str = Depends(_principal)) -> AccessPolicyView:
    services = _services(request)
    policy = await _guarded(services.administration.get_policy(owner_id=principal, datasource_id=datasource_id, principal_id=principal_id))
    if policy is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _policy_view(policy)


@admin_router.put("/datasources/{datasource_id}/policies/{principal_id}", response_model=AccessPolicyView)
async def admin_replace_policy(datasource_id: str, principal_id: str, payload: AccessPolicyRequest, request: Request, principal: str = Depends(_principal)) -> AccessPolicyView:
    services = _services(request)
    policy = await _guarded(
        services.administration.replace_policy(
            owner_id=principal,
            datasource_id=datasource_id,
            principal_id=principal_id,
            version=payload.version,
            relations=_access_rules(payload.relations),
            allowed_functions=payload.allowed_functions,
            expected_version=payload.expected_version,
        )
    )
    return _policy_view(policy)


@admin_router.delete("/datasources/{datasource_id}/policies/{principal_id}")
async def admin_remove_policy(datasource_id: str, principal_id: str, request: Request, principal: str = Depends(_principal)) -> dict:
    services = _services(request)
    await _guarded(services.administration.remove_policy(owner_id=principal, datasource_id=datasource_id, principal_id=principal_id))
    return {"removed": True}


@admin_router.get("/metrics", response_model=MetricListResponse)
async def admin_list_metrics(request: Request, principal: str = Depends(_principal)) -> MetricListResponse:
    services = _services(request)
    metrics = await _guarded(services.administration.list_metrics(owner_id=principal))
    return MetricListResponse(metrics=tuple(_metric_view(metric) for metric in metrics))


@admin_router.post("/metrics", response_model=MetricView)
async def admin_create_metric(payload: MetricCreateRequest, request: Request, principal: str = Depends(_principal)) -> MetricView:
    services = _services(request)
    metric = await _guarded(services.administration.save_metric(owner_id=principal, metric=_metric(principal, payload.key, payload)))
    return _metric_view(metric)


@admin_router.get("/metrics/{metric_key}", response_model=MetricView)
async def admin_get_metric(metric_key: str, request: Request, principal: str = Depends(_principal)) -> MetricView:
    services = _services(request)
    metric = await _guarded(services.administration.get_metric(owner_id=principal, metric_key=metric_key))
    if metric is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _metric_view(metric)


@admin_router.put("/metrics/{metric_key}", response_model=MetricView)
async def admin_update_metric(metric_key: str, payload: MetricUpdateRequest, request: Request, principal: str = Depends(_principal)) -> MetricView:
    services = _services(request)
    metric = await _guarded(services.administration.save_metric(owner_id=principal, metric=_metric(principal, metric_key, payload)))
    return _metric_view(metric)


@admin_router.delete("/metrics/{metric_key}", response_model=MetricView)
async def admin_retire_metric(metric_key: str, request: Request, principal: str = Depends(_principal)) -> MetricView:
    services = _services(request)
    await _guarded(services.administration.retire_metric(owner_id=principal, metric_key=metric_key))
    metric = await _guarded(services.administration.get_metric(owner_id=principal, metric_key=metric_key))
    if metric is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _metric_view(metric)


@admin_router.get("/audits", response_model=QueryAuditPageResponse)
async def admin_list_audits(
    request: Request,
    principal_id: str = Query(min_length=1, max_length=64),
    limit: int | None = Query(default=None, ge=1, le=100),
    before_started_at: datetime | None = Query(default=None),
    before_id: str | None = Query(default=None),
) -> QueryAuditPageResponse:
    # 跨用户列表被显式禁止：必须给出精确 principal，`*` 不是通配符，只是一个匹配不到的值。
    return await _read_audits(request, principal_id, limit, before_started_at, before_id)


router.include_router(admin_router)

__all__ = ["AnalyticsErrorResponse", "admin_router", "install_request_error_handler", "router"]
