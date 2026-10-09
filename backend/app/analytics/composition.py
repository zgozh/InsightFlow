"""Analytics composition root（Phase 2C2 §4）。

只接收**已经建立**的共享应用 `AsyncEngine` 与 `async_sessionmaker`：Analytics 复用 Gateway
的应用数据库，不建第二个控制面数据库，也不自己解析 DSN。

装配顺序与失败语义：

1. 解析 `analytics:` 配置（严格；未知字段/非法值直接让启动失败）；
2. `enabled=false` 或 `database.backend=memory` → 返回 `None`，**不运行迁移**，
   所有 Analytics API 稳定 503，绝不退化成内存控制面；
3. SQL backend 必须有 engine 与 session factory，否则阻止启动；
4. 运行 `bootstrap_analytics_schema`（失败阻止启动，避免暴露半可用的查询 API）；
5. 构造 repositories、policy、authorizer、业务数据库 gateway、持久化 plan store、审计与应用服务；
6. 原子返回不可变服务包。

业务数据库 gateway 只在**执行阶段**使用；HTTP 层永远拿不到它，只能调用应用服务。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.application import (
    AnalysisEvidenceRepository,
    AnalyticsAdministration,
    AuthorizePreparedQuery,
    DatasourceCatalog,
    ExecuteAnalyticsQuery,
    ExecuteQueryPlan,
    ListAnalysisReports,
    MetricCatalog,
    PlanAnalyticsQuery,
    PublishAnalysisReport,
    QueryAuditReader,
)
from app.analytics.application.execution import CreateQueryExecutionPlan
from app.analytics.config import AnalyticsConfig
from app.analytics.domain import DatasourceEngine
from app.analytics.infrastructure import SecurePlanTokenIssuer, SqlglotQueryPolicy, SqlglotSemanticAuthorizer, SystemClock
from app.analytics.infrastructure.database_runtime import SQLAlchemyDatasourceQueryGateway
from app.analytics.infrastructure.datasource_secrets import EnvironmentDatasourceSecretResolver
from app.analytics.infrastructure.mysql_runtime import MySQLRuntime
from app.analytics.infrastructure.persistence import (
    SqlAccessPolicyRepository,
    SqlAnalysisEvidenceRepository,
    SqlAnalysisReportRepository,
    SqlDatasourceRepository,
    SqlExecutionPlanStore,
    SqlMetricRepository,
    SqlQueryAuditLog,
    SqlSchemaSnapshotRepository,
    bootstrap_analytics_schema,
)
from app.analytics.infrastructure.postgresql_runtime import PostgreSQLRuntime

logger = logging.getLogger(__name__)

#: plan store 的容量上限。它是部署级的服务端常量，不是客户端可覆盖的限额；签发路径每次都会
#: 先清理过期记录，因此它只约束"同一时刻未过期的 plan 数量"。
PLAN_STORE_MAX_ENTRIES = 1_000

_SQL_BACKENDS = ("sqlite", "postgres")


class AnalyticsCompositionError(RuntimeError):
    """启动期装配失败。只携带稳定 reason。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AnalyticsServices:
    """不可变服务包：只暴露 API/Agent 需要的应用入口。"""

    config: AnalyticsConfig
    datasources: DatasourceCatalog
    metrics: MetricCatalog
    administration: AnalyticsAdministration
    plan_query: PlanAnalyticsQuery
    execute_query: ExecuteAnalyticsQuery
    audit_reader: QueryAuditReader
    publish_report: PublishAnalysisReport
    list_reports: ListAnalysisReports
    # 过渡期保持默认 None，兼容尚未绑定耐久 evidence bridge 的测试/普通 API 构造。
    analysis_evidence_repository: AnalysisEvidenceRepository | None = None


async def build_analytics_services(
    *,
    config: object,
    engine: object,
    session_factory: async_sessionmaker[AsyncSession] | None,
    backend: str,
) -> AnalyticsServices | None:
    """按配置装配 Analytics 控制面；返回 `None` 表示"本进程不提供该能力"。"""

    analytics_config = AnalyticsConfig.from_app_config(config)

    if not analytics_config.enabled:
        logger.info("analytics.enabled is false; the analytics API stays unavailable")
        return None

    if backend == "memory":
        # memory backend 没有持久化能力：不迁移、不挂载，也不偷偷用内存 store。
        logger.warning("analytics requires a SQL application database; database.backend=memory leaves the analytics API unavailable")
        return None

    if backend not in _SQL_BACKENDS:
        raise AnalyticsCompositionError(f"analytics_backend_unsupported:{backend}")
    if engine is None or session_factory is None:
        raise AnalyticsCompositionError("analytics_engine_unavailable")

    # 迁移失败必须阻止启动：半可用的查询 API 比不可用更危险。
    await bootstrap_analytics_schema(engine, backend=backend)

    datasources = SqlDatasourceRepository(session_factory)
    schemas = SqlSchemaSnapshotRepository(session_factory)
    policies = SqlAccessPolicyRepository(session_factory)
    metrics = SqlMetricRepository(session_factory)
    audit_log = SqlQueryAuditLog(session_factory)
    reports = SqlAnalysisReportRepository(session_factory)
    evidence_repository = SqlAnalysisEvidenceRepository(session_factory)

    query_policy = SqlglotQueryPolicy()
    authorizer = SqlglotSemanticAuthorizer(query_policy=query_policy)
    authorize_prepared_query = AuthorizePreparedQuery(
        datasource_catalog=datasources,
        schema_catalog=schemas,
        policy_catalog=policies,
        authorizer=authorizer,
    )

    gateway = SQLAlchemyDatasourceQueryGateway(
        secret_resolver=EnvironmentDatasourceSecretResolver(),
        runtimes={
            DatasourceEngine.POSTGRESQL: PostgreSQLRuntime(),
            DatasourceEngine.MYSQL: MySQLRuntime(),
        },
    )
    clock = SystemClock()
    plan_store = SqlExecutionPlanStore(session_factory, max_entries=PLAN_STORE_MAX_ENTRIES)

    create_plan = CreateQueryExecutionPlan(
        datasource_catalog=datasources,
        authorize_prepared_query=authorize_prepared_query,
        gateway=gateway,
        plan_store=plan_store,
        audit_log=audit_log,
        clock=clock,
        token_issuer=SecurePlanTokenIssuer(),
    )
    execute_plan = ExecuteQueryPlan(
        datasource_catalog=datasources,
        authorize_prepared_query=authorize_prepared_query,
        gateway=gateway,
        plan_store=plan_store,
        audit_log=audit_log,
        clock=clock,
    )

    administration = AnalyticsAdministration(
        datasources=datasources,
        schemas=schemas,
        policies=policies,
        metrics=metrics,
        id_issuer=lambda: str(uuid.uuid4()),
    )
    plan_query = PlanAnalyticsQuery(
        config=analytics_config,
        datasource_catalog=datasources,
        query_policy=query_policy,
        authorize_prepared_query=authorize_prepared_query,
        create_plan=create_plan,
        audit_log=audit_log,
        clock=clock,
    )

    logger.info("analytics control plane mounted (backend=%s)", backend)
    return AnalyticsServices(
        config=analytics_config,
        datasources=datasources,
        metrics=metrics,
        administration=administration,
        plan_query=plan_query,
        execute_query=ExecuteAnalyticsQuery(execute_plan=execute_plan),
        audit_reader=audit_log,
        # 报告索引与查询执行共用同一批应用入口；id/created_at 一律由服务端派生。
        publish_report=PublishAnalysisReport(repository=reports, clock=clock, id_issuer=lambda: str(uuid.uuid4())),
        list_reports=ListAnalysisReports(repository=reports),
        analysis_evidence_repository=evidence_repository,
    )


__all__ = ["AnalyticsCompositionError", "AnalyticsServices", "PLAN_STORE_MAX_ENTRIES", "build_analytics_services"]
