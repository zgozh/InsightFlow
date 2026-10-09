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

import asyncio
from collections.abc import Mapping

from langchain.tools import tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.analytics.agent.evidence import ANALYSIS_EVIDENCE_UNAVAILABLE, AnalyticsQueryEvidence, AnalyticsQueryToolResult, canonical_json, compute_result_digest
from app.analytics.agent.evidence_bridge import DurableAnalysisRunEvidenceCollector
from app.analytics.agent.roles import AnalysisRoleError, AnalysisRolesCapability, role_usage_fields
from app.analytics.agent.runtime import get_bound_analytics_services, trusted_principal, trusted_thread_run
from app.analytics.agent.stages import AnalysisStageError, emit_role_stage, stable_stage_code, stage_status_for_code
from app.analytics.application.metric_service import MetricService
from app.analytics.domain.datasource import DatasourceDefinition
from app.analytics.domain.metric import MetricDefinition
from deerflow.constants import ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY, ANALYSIS_ROLES_CONTEXT_KEY
from deerflow.persistence.thread_meta import THREAD_ANALYSIS_MODE_METADATA_KEY
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
        "expression": metric.expression,
        "dimensions": list(metric.dimensions),
        "version": metric.version,
        "status": metric.status.value,
    }


async def _emit_stage(
    roles: AnalysisRolesCapability | None,
    principal_id: str,
    thread_run: tuple[str, str] | None,
    stage: str,
    status: str,
    **fields: object,
) -> None:
    if roles is None or thread_run is None:
        return
    await emit_role_stage(
        roles,
        principal_id=principal_id,
        thread_id=thread_run[0],
        run_id=thread_run[1],
        stage=stage,
        status=status,
        **fields,
    )


def _risk_value(value: object) -> str | None:
    candidate = getattr(value, "value", value)
    candidate = candidate.upper() if type(candidate) is str else None
    return candidate if candidate in {"LOW", "MEDIUM", "HIGH", "BLOCKED"} else None


async def _run_plan_query(*, services: object, principal_id: str, datasource_id: str, sql: str, roles: AnalysisRolesCapability | None, thread_run: tuple[str, str] | None) -> object:
    try:
        planned = await services.plan_query.execute(principal_id=principal_id, datasource_id=datasource_id, raw_sql=sql)
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_run, "authorization", "cancelled", code="cancelled")
        except AnalysisStageError:
            pass
        raise
    except Exception:
        await _emit_stage(roles, principal_id, thread_run, "authorization", "failed", code="unavailable")
        raise
    receipt = getattr(planned, "receipt", None)
    metadata = getattr(planned, "metadata", None)
    if receipt is None or metadata is None:
        code = stable_stage_code(getattr(planned, "code", None))
        await _emit_stage(roles, principal_id, thread_run, "authorization", stage_status_for_code(code), code=code)
    else:
        fields: dict[str, object] = {"code": stable_stage_code(getattr(planned, "code", None), fallback="ok")}
        risk = _risk_value(getattr(metadata, "risk", None))
        if risk is not None:
            fields["risk"] = risk
        await _emit_stage(roles, principal_id, thread_run, "authorization", "succeeded", **fields)
    return planned


async def _run_query_execution(
    *,
    services: object,
    principal_id: str,
    plan_id: str,
    roles: AnalysisRolesCapability | None,
    thread_run: tuple[str, str] | None,
    risk: str | None,
) -> object:
    fields: dict[str, object] = {"risk": risk} if risk is not None else {}
    await _emit_stage(roles, principal_id, thread_run, "execution", "running", **fields)
    try:
        executed = await services.execute_query.execute(principal_id=principal_id, plan_id=plan_id)
    except asyncio.CancelledError:
        try:
            await _emit_stage(roles, principal_id, thread_run, "execution", "cancelled", code="cancelled", **fields)
        except AnalysisStageError:
            pass
        raise
    except Exception:
        await _emit_stage(roles, principal_id, thread_run, "execution", "failed", code="unavailable", **fields)
        raise
    if getattr(executed, "result", None) is None:
        code = stable_stage_code(getattr(executed, "code", None))
        await _emit_stage(roles, principal_id, thread_run, "execution", stage_status_for_code(code), code=code, **fields)
    return executed


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

    context = getattr(runtime, "context", None)
    analysis_mode = context.get(THREAD_ANALYSIS_MODE_METADATA_KEY) if isinstance(context, Mapping) else None
    roles = context.get(ANALYSIS_ROLES_CONTEXT_KEY) if analysis_mode is True and isinstance(context, Mapping) else None
    identity = trusted_thread_run(runtime) if analysis_mode is True else None
    if analysis_mode is True and (not isinstance(roles, AnalysisRolesCapability) or identity is None or not roles.matches(principal_id, *identity)):
        return _payload(_UNAVAILABLE)

    try:
        if analysis_mode is True:
            await _emit_stage(roles, principal_id, identity, "catalog", "running")
        try:
            datasources = await services.datasources.list_accessible(principal_id=principal_id)
            metrics = await MetricService(services.metrics).list_active_for_principal(principal_id=principal_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            if analysis_mode is True:
                await _emit_stage(roles, principal_id, identity, "catalog", "failed", code="unavailable")
            return _payload(_UNAVAILABLE)
        if analysis_mode is True:
            await _emit_stage(roles, principal_id, identity, "catalog", "succeeded", code="ok")
    except Exception:  # noqa: BLE001 - 目录失败不得泄漏数据库异常文本
        return _payload(_UNAVAILABLE)

    return canonical_json(
        {
            "code": "ok",
            "datasources": [_datasource_view(datasource) for datasource in datasources],
            "metrics": [_metric_view(metric) for metric in metrics],
        }
    )


async def _plan_and_execute(
    *,
    services,
    principal_id: str,
    datasource_id: str,
    sql: str,
    evidence_collector: DurableAnalysisRunEvidenceCollector | None = None,
    thread_run: tuple[str, str] | None = None,
    tool_call_id: str | None = None,
    roles: AnalysisRolesCapability | None = None,
) -> str | Command:
    """一次调用内完成 plan → execute；token 只存在于这个函数的局部变量。"""

    try:
        await _emit_stage(roles, principal_id, thread_run, "authorization", "running")
        planned = await _run_plan_query(services=services, principal_id=principal_id, datasource_id=datasource_id, sql=sql, roles=roles, thread_run=thread_run)
    except Exception:  # noqa: BLE001 - 未知失败默认拒绝且不泄漏异常文本
        return _payload(_UNAVAILABLE)

    receipt = planned.receipt
    metadata = planned.metadata
    if receipt is None or metadata is None:
        # 正常拒绝：只回稳定 code，绝不回任何内部元数据。
        return AnalyticsQueryToolResult(code=planned.code).to_json()

    token = receipt.plan_id
    estimate = receipt.estimate
    risk = _risk_value(metadata.risk)
    del planned, receipt
    try:
        executed = await _run_query_execution(
            services=services,
            principal_id=principal_id,
            plan_id=token,
            roles=roles,
            thread_run=thread_run,
            risk=risk,
        )
    except Exception:  # noqa: BLE001 - 执行失败同样脱敏；token 已被 claim，不重试
        return _payload(_UNAVAILABLE)
    finally:
        # token 到此为止：不写日志、不进结果、不进异常。
        token = ""  # noqa: F841 - 显式丢弃引用
    del token

    if executed.result is None:
        return AnalyticsQueryToolResult(code=executed.code).to_json()

    result = executed.result
    try:
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
        tool_result = AnalyticsQueryToolResult(
            code=executed.code,
            columns=result.columns,
            rows=result.rows,
            truncated=result.truncated,
            evidence=evidence,
        )
        result_json = tool_result.to_json()
    except Exception:  # noqa: BLE001 - malformed query output gets a stable terminal stage
        try:
            await _emit_stage(roles, principal_id, thread_run, "execution", "failed", code="unavailable", **({"risk": risk} if risk is not None else {}))
        except AnalysisStageError:
            pass
        return _payload(_UNAVAILABLE)
    if evidence_collector is not None:
        if (
            thread_run is None
            or not isinstance(tool_call_id, str)
            or not tool_call_id
            or tool_call_id != tool_call_id.strip()
            or not await evidence_collector.record_success_durable(
                principal_id=principal_id,
                thread_id=thread_run[0],
                run_id=thread_run[1],
                result=tool_result,
            )
        ):
            await _emit_stage(roles, principal_id, thread_run, "execution", "failed", code="evidence_unavailable")
            return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
        success_fields: dict[str, object] = {
            "code": stable_stage_code(executed.code, fallback="ok"),
            "row_count": len(result.rows),
            "byte_count": len(result_json.encode("utf-8", errors="strict")),
            "evidence_ids": [evidence.evidence_id],
        }
        if risk is not None:
            success_fields["risk"] = risk
        await _emit_stage(roles, principal_id, thread_run, "execution", "succeeded", **success_fields)
        artifact_path = evidence_collector.artifact_path(evidence.evidence_id)
        return Command(
            update={
                "artifacts": [artifact_path],
                "messages": [ToolMessage(content=result_json, tool_call_id=tool_call_id, name=QUERY_TOOL_NAME)],
            }
        )
    return result_json


@tool(QUERY_TOOL_NAME, parse_docstring=True)
async def query_business_data(datasource_id: str, sql: str, runtime: Runtime) -> str | Command:
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

    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return _payload(_UNAVAILABLE)
    analysis_mode = context.get(THREAD_ANALYSIS_MODE_METADATA_KEY)
    collector_value = context.get(ANALYSIS_EVIDENCE_COLLECTOR_CONTEXT_KEY)
    roles_value = context.get(ANALYSIS_ROLES_CONTEXT_KEY)
    if analysis_mode is not None and type(analysis_mode) is not bool:
        return _payload(_UNAVAILABLE)
    if analysis_mode is True:
        if not isinstance(collector_value, DurableAnalysisRunEvidenceCollector):
            return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
        if not isinstance(roles_value, AnalysisRolesCapability):
            return _payload("analysis_role_unavailable")
        thread_run = trusted_thread_run(runtime)
        tool_call_id = getattr(runtime, "tool_call_id", None)
        if thread_run is None or not collector_value.matches(principal_id, *thread_run) or not isinstance(tool_call_id, str) or not tool_call_id or tool_call_id != tool_call_id.strip():
            return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
        if not roles_value.matches(principal_id, *thread_run):
            return _payload("analysis_role_unavailable")
        evidence_collector = collector_value
    elif collector_value is not None or roles_value is not None:
        # 仅有 run-scoped collector 不足以将普通聊天变成 analysis run；模式由 Gateway 清洗后的 marker 决定。
        return _payload(ANALYSIS_EVIDENCE_UNAVAILABLE)
    else:
        evidence_collector = None
        thread_run = None
        tool_call_id = None

    if not isinstance(datasource_id, str) or not datasource_id.strip() or datasource_id != datasource_id.strip():
        return _payload(_INVALID_REQUEST)
    if not isinstance(sql, str) or not sql.strip():
        return _payload(_INVALID_REQUEST)
    if len(sql) > MAX_SQL_CHARACTERS:
        return _payload(_INVALID_REQUEST)

    if analysis_mode is True:
        try:
            await _emit_stage(roles_value, principal_id, thread_run, "catalog", "running")
            try:
                datasource = await services.datasources.get_accessible(principal_id=principal_id, datasource_id=datasource_id)
                metrics = await MetricService(services.metrics).list_active_for_principal(principal_id=principal_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                await _emit_stage(roles_value, principal_id, thread_run, "catalog", "failed", code="unavailable")
                return _payload("analysis_role_unavailable")
            if type(datasource) is not DatasourceDefinition:
                await _emit_stage(roles_value, principal_id, thread_run, "catalog", "failed", code="unavailable")
                return _payload("analysis_role_unavailable")
            await _emit_stage(roles_value, principal_id, thread_run, "catalog", "succeeded", code="ok")
            sql_started = False
            try:
                async with roles_value.serialize_query(principal_id, thread_run[0], thread_run[1]):
                    await _emit_stage(roles_value, principal_id, thread_run, "sql", "running")
                    sql_started = True
                    try:
                        refined = await roles_value.refine_sql(
                            principal_id,
                            thread_run[0],
                            thread_run[1],
                            datasource_id,
                            sql,
                            metrics,
                        )
                    except asyncio.CancelledError:
                        raise
                    except AnalysisRoleError as exc:
                        code = stable_stage_code(exc.reason)
                        await _emit_stage(roles_value, principal_id, thread_run, "sql", stage_status_for_code(code), code=code)
                        return _payload(f"analysis_role_{exc.reason}")
                    except Exception:
                        await _emit_stage(roles_value, principal_id, thread_run, "sql", "failed", code="unavailable")
                        return _payload("analysis_role_unavailable")
                    if type(refined.sql) is not str or not refined.sql.strip():
                        await _emit_stage(roles_value, principal_id, thread_run, "sql", "failed", code="invalid_response")
                        return _payload("analysis_role_invalid_response")
                    await _emit_stage(roles_value, principal_id, thread_run, "sql", "succeeded", code="ok", **role_usage_fields(refined))
                    return await _plan_and_execute(
                        services=services,
                        principal_id=principal_id,
                        datasource_id=datasource_id,
                        sql=refined.sql,
                        evidence_collector=evidence_collector,
                        thread_run=thread_run,
                        tool_call_id=tool_call_id,
                        roles=roles_value,
                    )
            except AnalysisRoleError as exc:
                if not sql_started:
                    code = stable_stage_code(exc.reason)
                    await _emit_stage(roles_value, principal_id, thread_run, "sql", "running")
                    await _emit_stage(roles_value, principal_id, thread_run, "sql", stage_status_for_code(code), code=code)
                return _payload(f"analysis_role_{exc.reason}")
        except Exception:  # noqa: BLE001 - capability/catalog/query failures stay stable
            return _payload("analysis_role_unavailable")

    return await _plan_and_execute(
        services=services,
        principal_id=principal_id,
        datasource_id=datasource_id,
        sql=sql,
        evidence_collector=evidence_collector,
        thread_run=thread_run,
        tool_call_id=tool_call_id,
    )


__all__ = ["CATALOG_TOOL_NAME", "MAX_SQL_CHARACTERS", "QUERY_TOOL_NAME", "compute_result_digest", "inspect_business_catalog", "query_business_data"]
