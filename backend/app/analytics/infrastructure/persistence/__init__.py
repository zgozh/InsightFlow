"""Analytics 持久化适配器的窄出口（Phase 2C1）。

只导出 composition 真正需要的适配器；`models` / `codec` 保持内部构件，避免上层绕过应用端口
直接操作 ORM 或 JSON 形状。
"""

from app.analytics.infrastructure.persistence.audit_log import SqlQueryAuditLog
from app.analytics.infrastructure.persistence.bootstrap import AnalyticsSchemaBootstrapError, bootstrap_analytics_schema
from app.analytics.infrastructure.persistence.catalogs import (
    SqlAccessPolicyRepository,
    SqlDatasourceRepository,
    SqlMetricRepository,
    SqlSchemaSnapshotRepository,
)
from app.analytics.infrastructure.persistence.plan_store import SqlExecutionPlanStore

__all__ = [
    "AnalyticsSchemaBootstrapError",
    "SqlAccessPolicyRepository",
    "SqlDatasourceRepository",
    "SqlExecutionPlanStore",
    "SqlMetricRepository",
    "SqlQueryAuditLog",
    "SqlSchemaSnapshotRepository",
    "bootstrap_analytics_schema",
]
