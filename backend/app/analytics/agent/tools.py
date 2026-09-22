"""App-owned Analytics Agent 工具（Phase 3 §3）。

只有两个面向模型的工具，避免把内部端口逐个暴露：

- `inspect_business_catalog`：无身份参数，按认证 principal 返回白名单目录；
- `query_business_data`：参数恰为 `datasource_id` + `sql`，在**一次调用内**完成 plan → execute。

为什么 plan/execute 必须合成一个工具：plan token 是一次性能力令牌。拆成两个工具会让它进入
ToolMessage、checkpoint 与 run event，等于把可执行能力写进模型可见的历史。这里 token 只活在
函数局部变量里，`del` 之后连引用都不保留。

本模块只依赖应用服务与 Harness 的 runtime 类型；不 import SQLGlot、SQLAlchemy、驱动、
secret resolver 或 repository。
"""

from __future__ import annotations

from langchain.tools import tool

from app.analytics.agent.evidence import AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json, compute_result_digest
from app.analytics.agent.runtime import get_bound_analytics_services, trusted_principal
from app.analytics.domain.datasource import DatasourceDefinition
from app.analytics.domain.metric import MetricDefinition
from deerflow.tools.types import Runtime

CATALOG_TOOL_NAME = "inspect_business_catalog"
QUERY_TOOL_NAME = "query_business_data"

#: 与分析 API 相同的防御性上限：拒绝异常膨胀的输入，不是业务限额（Phase 2A 另有自己的边界）。
MAX_SQL_CHARACTERS = 20_000

_UNAVAILABLE = "analytics_unavailable"
_INVALID_REQUEST = "invalid_request"


def _payload(code: str) -> str:
    return canonical_json({"code": code})


def _datasource_view(datasource: DatasourceDefinition) -> dict:
    # 白名单：没有 owner、secret_ref、policy 或内部版本。
    return {
        "id": datasource.id,
        "name": datasource.name,
        "engine": datasource.engine.value,
        "default_schema": datasource.default_schema,
        "status": datasource.status.value,
    }


def _metric_view(metric: MetricDefinition) -> dict:
    return {
        "key": metric.key,
        "name": metric.name,
        "description": metric.description,
        "dimensions": list(metric.dimensions),
        "version": metric.version,
        "status": metric.status.value,
    }


@tool(CATALOG_TOOL_NAME, parse_docstring=True)
async def inspect_business_catalog(runtime: Runtime) -> str:
    """List the business datasources and metrics this user may use.

    Call this before writing SQL: it is the only source of valid datasource ids
    and of the metric definitions the user has registered. It returns no
    credentials, no ownership information and no access policies, and it takes
    no arguments because the caller identity comes from the signed-in session.

    Args:
        runtime: Injected tool runtime carrying the authenticated user context.

    Returns:
        A JSON object with a stable `code` plus `datasources` and `metrics`.
    """
    services = get_bound_analytics_services()
    if services is None:
        return _payload(_UNAVAILABLE)
    principal_id = trusted_principal(runtime)
    if principal_id is None:
        return _payload(_UNAVAILABLE)

    try:
        datasources = await services.datasources.list_accessible(principal_id=principal_id)
        metrics = await services.metrics.list_accessible(principal_id=principal_id)
    except Exception:  # noqa: BLE001 - 目录失败不得泄漏数据库异常文本
        return _payload(_UNAVAILABLE)

    return canonical_json(
        {
            "code": "ok",
            "datasources": [_datasource_view(datasource) for datasource in datasources],
            "metrics": [_metric_view(metric) for metric in metrics],
        }
    )


async def _plan_and_execute(*, services, principal_id: str, datasource_id: str, sql: str) -> str:
    """一次调用内完成 plan → execute；token 只存在于这个函数的局部变量。"""

    try:
        planned = await services.plan_query.execute(principal_id=principal_id, datasource_id=datasource_id, raw_sql=sql)
    except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏异常文本
        return _payload(_UNAVAILABLE)

    receipt = planned.receipt
    metadata = planned.metadata
    if receipt is None or metadata is None:
        # 正常拒绝：只回稳定 code，绝不回任何内部元数据。
        return AnalyticsQueryToolResult(code=planned.code).to_json()

    token = receipt.plan_id
    estimate = receipt.estimate
    del planned, receipt
    try:
        executed = await services.execute_query.execute(principal_id=principal_id, plan_id=token)
    except Exception:  # noqa: BLE001 - 执行失败同样脱敏；token 已被 claim，不重试
        return _payload(_UNAVAILABLE)
    finally:
        # token 到此为止：不写日志、不进结果、不进异常。
        token = ""  # noqa: F841 - 显式丢弃引用
    del token

    if executed.result is None:
        return AnalyticsQueryToolResult(code=executed.code).to_json()

    result = executed.result
    evidence = AnalyticsQueryEvidence.build(
        datasource_id=metadata.datasource_id,
        query_hash=metadata.query_hash,
        risk=metadata.risk,
        schema_version=metadata.schema_version,
        policy_version=metadata.policy_version,
        estimate=estimate,
        result=result,
        decision_code=executed.code,
    )
    return AnalyticsQueryToolResult(
        code=executed.code,
        columns=result.columns,
        rows=result.rows,
        truncated=result.truncated,
        evidence=evidence,
    ).to_json()


@tool(QUERY_TOOL_NAME, parse_docstring=True)
async def query_business_data(datasource_id: str, sql: str, runtime: Runtime) -> str:
    """Run one read-only business query and return bounded rows plus evidence.

    The query goes through the platform's governed path: syntax policy, semantic
    authorization against your access policy, an EXPLAIN cost gate, and a
    single-use execution plan. Arguments are exactly the datasource id from the
    catalog and the SQL text; limits, identity and versions are derived by the
    server and cannot be supplied here. Run one query at a time, copy the
    returned `evidence` verbatim into your analysis, and never restate numbers
    that no evidence covers.

    Args:
        datasource_id: The `id` returned by `inspect_business_catalog`.
        sql: A single read-only SELECT statement.
        runtime: Injected tool runtime carrying the authenticated user context.

    Returns:
        A JSON object with a stable `code`, bounded `columns`/`rows`, and an
        `evidence` envelope on success.
    """
    services = get_bound_analytics_services()
    if services is None:
        return _payload(_UNAVAILABLE)
    principal_id = trusted_principal(runtime)
    if principal_id is None:
        return _payload(_UNAVAILABLE)

    if not isinstance(datasource_id, str) or not datasource_id.strip() or datasource_id != datasource_id.strip():
        return _payload(_INVALID_REQUEST)
    if not isinstance(sql, str) or not sql.strip():
        return _payload(_INVALID_REQUEST)
    if len(sql) > MAX_SQL_CHARACTERS:
        return _payload(_INVALID_REQUEST)

    return await _plan_and_execute(services=services, principal_id=principal_id, datasource_id=datasource_id, sql=sql)


__all__ = ["CATALOG_TOOL_NAME", "MAX_SQL_CHARACTERS", "QUERY_TOOL_NAME", "compute_result_digest", "inspect_business_catalog", "query_business_data"]
