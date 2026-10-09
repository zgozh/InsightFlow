"""认证 Analytics API 测试（Phase 2C2 任务 5）。

这些测试在**真实** SQLite 控制面上跑（管理 → plan → execute），只把业务数据库 gateway 换成
替身：

- 未认证 401、非管理员 403、PAT 无管理员能力、未装配 503；
- 客户端伪造 `principal_id` / `owner_id` / limits / prepared / authorized / version / credential
  一律 422，且验证错误不回显 raw SQL 或 plan token；
- 普通用户的 datasource 响应不含 owner/secret_ref；任何响应都不含解析后的 credential；
- owner 不匹配与不存在统一 404，版本冲突 409；
- plan/execute 的正常拒绝是 200 + 稳定 code，成功时 token 只出现一次；
- 审计读取 exact-principal、keyset 分页、最大 100。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.analytics import api as analytics_api
from app.analytics import composition
from app.analytics.composition import build_analytics_services
from app.analytics.domain import (
    ColumnAccess,
    ColumnAccessRule,
    ColumnSchema,
    DatasourceEngine,
    QueryCostEstimate,
    QueryExecutionResult,
    RelationAccessRule,
    RelationSchema,
)
from app.gateway.auth_disabled import AUTH_SOURCE_PAT, AUTH_SOURCE_SESSION

_SQL = "SELECT id FROM orders LIMIT 10"
_ADMIN = "admin-1"
_USER = "user-9"


class _StubGateway:
    def __init__(self, **kwargs):
        self.explain_calls = 0
        self.execute_calls = 0

    async def explain(self, *, datasource, authorized, limits):
        self.explain_calls += 1
        return QueryCostEstimate(engine=DatasourceEngine.POSTGRESQL, estimated_rows=10, engine_cost=Decimal("12.5"), plan_digest="c" * 64)

    async def execute(self, *, datasource, authorized, limits):
        self.execute_calls += 1
        return QueryExecutionResult(columns=("id",), rows=((1,),), row_count=1, byte_count=21, truncated=False)


def _build_app(services):
    app = FastAPI()
    app.state.analytics_services = services
    analytics_api.install_request_error_handler(app)

    @app.middleware("http")
    async def _identity(request, call_next):
        token = request.headers.get("x-test-user")
        if token:
            user_id, _, role = token.partition(":")
            request.state.user = SimpleNamespace(id=user_id, system_role=role or "user")
            request.state.auth_source = AUTH_SOURCE_PAT if role == "pat" else AUTH_SOURCE_SESSION
        return await call_next(request)

    app.include_router(analytics_api.router)
    return app


@pytest_asyncio.fixture
async def services(tmp_path, monkeypatch):
    monkeypatch.setattr(composition, "SQLAlchemyDatasourceQueryGateway", lambda **kwargs: _StubGateway(**kwargs))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}", poolclass=NullPool, echo=False)
    # 默认配置：不覆盖任何限额，用真实的 1000/1000 证明小 LIMIT 查询也能建 plan。
    backend = SimpleNamespace(database=SimpleNamespace(backend="sqlite"))
    try:
        built = await build_analytics_services(config=backend, engine=engine, session_factory=async_sessionmaker(engine, expire_on_commit=False), backend="sqlite")
        yield built
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def configured(services):
    """一个已建好的 datasource + schema + 给 _USER 的精确策略。"""

    datasource = await services.administration.create_datasource(owner_id=_ADMIN, name="Warehouse", engine=DatasourceEngine.POSTGRESQL, secret_ref="env://ANALYTICS_DS", default_schema="public")
    await services.administration.replace_schema(
        owner_id=_ADMIN,
        datasource_id=datasource.id,
        version="s1",
        default_schema="public",
        relations=(RelationSchema(name="orders", schema="public", columns=(ColumnSchema(name="id", data_type="integer"),)),),
        expected_version=None,
    )
    await services.administration.replace_policy(
        owner_id=_ADMIN,
        datasource_id=datasource.id,
        principal_id=_USER,
        version="p1",
        relations=(RelationAccessRule(name="orders", schema="public", columns=(ColumnAccessRule(name="id", access=ColumnAccess.ALLOW),)),),
        allowed_functions=(),
        expected_version=None,
    )
    return datasource


def _without_key(payload: dict) -> dict:
    return {name: value for name, value in payload.items() if name != "key"}


def _client(services) -> TestClient:
    return TestClient(_build_app(services))


def _as(client: TestClient, identity: str):
    client.headers.update({"x-test-user": identity})
    return client


# --- 认证与可用性 -----------------------------------------------------------


def test_unauthenticated_requests_are_rejected(services):
    client = _client(services)

    assert client.get("/api/analytics/datasources").status_code == 401
    assert client.get("/api/analytics/admin/datasources").status_code == 401
    assert client.post("/api/analytics/query-plans", json={"datasource_id": "ds-1", "sql": _SQL}).status_code == 401


def test_non_admin_callers_cannot_reach_the_admin_surface(services):
    client = _as(_client(services), f"{_USER}:user")

    assert client.get("/api/analytics/admin/datasources").status_code == 403
    assert client.post("/api/analytics/admin/datasources", json={"name": "x", "engine": "postgresql", "secret_ref": "env://X"}).status_code == 403


def test_a_personal_access_token_never_carries_admin_capability(services):
    client = _as(_client(services), f"{_ADMIN}:pat")

    assert client.get("/api/analytics/admin/audits", params={"principal_id": _USER}).status_code == 403
    # 普通用户接口仍然可用：PAT 只是没有管理员能力，不是没有身份。
    assert client.get("/api/analytics/datasources").status_code == 200


def test_an_unmounted_control_plane_is_a_stable_503(services):
    app = _build_app(None)
    client = _as(TestClient(app), f"{_USER}:user")

    response = client.get("/api/analytics/datasources")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "analytics_unavailable"}}


# --- 客户端伪造字段 ---------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"principal_id": "user-1"},
        {"owner_id": "user-1"},
        {"limits": {"max_result_rows": 999999}},
        {"prepared": {"sql": "SELECT 1"}},
        {"authorized": {"principal_id": "user-1"}},
        {"schema_version": "s1"},
        {"policy_version": "p1"},
        {"credential": {"password": "hunter2"}},
    ],
)
def test_forged_fields_are_rejected(services, extra):
    client = _as(_client(services), f"{_USER}:user")
    payload = {"sql": _SQL}
    payload.update(extra)

    response = client.post("/api/analytics/query-plans", json=payload)

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_analytics_request"}}


def test_a_forged_execution_body_is_rejected(services):
    client = _as(_client(services), f"{_USER}:user")

    response = client.post("/api/analytics/query-executions", json={"plan_id": "token", "principal_id": "user-1"})

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_analytics_request"}}


def test_validation_errors_never_echo_the_raw_sql_or_the_token(services):
    client = _as(_client(services), f"{_USER}:user")
    secret_sql = "SELECT secret_column FROM private_table WHERE id = 42"

    bad_sql = client.post("/api/analytics/query-plans", json={"datasource_id": "ds-1", "sql": {"nested": secret_sql}})
    extra = client.post("/api/analytics/query-plans", json={"datasource_id": "ds-1", "sql": secret_sql, "principal_id": secret_sql})
    bad_token = client.post("/api/analytics/query-executions", json={"plan_id": {"nested": "raw-plan-token-value"}})

    for response in (bad_sql, extra, bad_token):
        assert response.status_code == 422
        rendered = response.text
        assert secret_sql not in rendered
        assert "raw-plan-token-value" not in rendered
        assert "secret_column" not in rendered
        assert response.json() == {"detail": {"code": "invalid_analytics_request"}}


# --- 用户目录 ---------------------------------------------------------------


def test_user_datasource_responses_hide_the_owner_and_the_secret_reference(services, configured):
    client = _as(_client(services), f"{_USER}:user")

    response = client.get("/api/analytics/datasources")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["datasources"]] == [configured.id]
    assert set(body["datasources"][0]) == {"id", "name", "engine", "default_schema", "status"}
    assert "secret_ref" not in response.text
    assert "owner_id" not in response.text


def test_admin_datasource_responses_expose_the_reference_but_never_a_resolved_credential(services, configured):
    client = _as(_client(services), f"{_ADMIN}:admin")

    response = client.get(f"/api/analytics/admin/datasources/{configured.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["secret_ref"] == "env://ANALYTICS_DS"
    assert body["owner_id"] == _ADMIN
    assert "password" not in response.text and "hunter2" not in response.text


def test_a_user_without_a_policy_sees_an_empty_catalogue(services, configured):
    client = _as(_client(services), "user-without-policy:user")

    assert client.get("/api/analytics/datasources").json() == {"datasources": []}


# --- 管理 CRUD --------------------------------------------------------------


def test_admin_datasource_crud_uses_server_generated_ids(services):
    client = _as(_client(services), f"{_ADMIN}:admin")

    created = client.post("/api/analytics/admin/datasources", json={"name": "Warehouse", "engine": "postgresql", "secret_ref": "env://ANALYTICS_DS", "default_schema": "public"})
    assert created.status_code == 200
    datasource_id = created.json()["id"]
    assert created.json()["status"] == "active"

    # 客户端提交 ID 会被拒绝。
    assert client.post("/api/analytics/admin/datasources", json={"id": "mine", "name": "x", "engine": "postgresql", "secret_ref": "env://X"}).status_code == 422

    updated = client.put(f"/api/analytics/admin/datasources/{datasource_id}", json={"name": "Renamed", "secret_ref": "env://OTHER", "default_schema": None, "status": "disabled"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed" and updated.json()["status"] == "disabled"
    assert client.get("/api/analytics/admin/datasources").json()["datasources"][0]["id"] == datasource_id


def test_admin_can_manage_schema_and_policy_but_foreign_ids_are_404(services, configured):
    client = _as(_client(services), f"{_ADMIN}:admin")

    assert client.get(f"/api/analytics/admin/datasources/{configured.id}/schema").json()["version"] == "s1"
    conflict = client.put(
        f"/api/analytics/admin/datasources/{configured.id}/schema",
        json={"version": "s2", "default_schema": "public", "expected_version": "stale", "relations": [{"name": "orders", "schema": "public", "columns": [{"name": "id", "data_type": "integer"}]}]},
    )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": {"code": "analytics_version_conflict"}}

    replaced = client.put(
        f"/api/analytics/admin/datasources/{configured.id}/schema",
        json={"version": "s2", "default_schema": "public", "expected_version": "s1", "relations": [{"name": "orders", "schema": "public", "columns": [{"name": "customer", "data_type": "text"}]}]},
    )
    assert replaced.status_code == 200 and replaced.json()["version"] == "s2"

    assert client.get(f"/api/analytics/admin/datasources/{configured.id}/policies/{_USER}").json()["principal_id"] == _USER
    assert client.delete(f"/api/analytics/admin/datasources/{configured.id}/policies/{_USER}").status_code == 200
    assert client.get(f"/api/analytics/admin/datasources/{configured.id}/policies/{_USER}").status_code == 404

    # owner 不匹配统一 404，而不是 403（不泄露"存在但不是你的"）。
    other = _as(_client(services), "someone-else:admin")
    assert other.get(f"/api/analytics/admin/datasources/{configured.id}").status_code == 404
    assert other.get(f"/api/analytics/admin/datasources/{configured.id}/schema").status_code == 404


def test_admin_metric_lifecycle_and_version_conflicts(services):
    client = _as(_client(services), f"{_ADMIN}:admin")
    payload = {"key": "revenue", "name": "Revenue", "description": "Total revenue", "expression": "sum(amount)", "dimensions": ["region"], "version": 1, "status": "draft"}

    created = client.post("/api/analytics/admin/metrics", json=payload)
    assert created.status_code == 200 and created.json()["key"] == "revenue"

    payload["version"] = 2
    payload["status"] = "active"
    assert client.put("/api/analytics/admin/metrics/revenue", json=_without_key(payload)).json()["version"] == 2
    # key 只来自路径：把它写进 body 会被拒绝。
    assert client.put("/api/analytics/admin/metrics/revenue", json=payload).status_code == 422

    payload["version"] = 1
    conflict = client.put("/api/analytics/admin/metrics/revenue", json=_without_key(payload))
    assert conflict.status_code == 409

    assert client.get("/api/analytics/admin/metrics").json()["metrics"][0]["key"] == "revenue"
    assert client.get("/api/analytics/admin/metrics/missing").status_code == 404

    assert client.delete("/api/analytics/admin/metrics/revenue").status_code == 200
    assert client.get("/api/analytics/admin/metrics/revenue").json()["status"] == "retired"


def test_admin_metric_owner_comes_from_the_session_not_the_body(services):
    client = _as(_client(services), f"{_ADMIN}:admin")

    response = client.post("/api/analytics/admin/metrics", json={"key": "revenue", "owner_id": "user-1", "name": "Revenue", "description": "d", "expression": "sum(x)", "version": 1, "status": "draft"})

    assert response.status_code == 422


def test_metric_grants_require_admin_and_are_visible_only_after_explicit_grant(services):
    path = "/api/analytics/admin/metrics/revenue/grants/user-9"
    anonymous = _client(services)
    ordinary = _as(_client(services), f"{_USER}:user")
    admin = _as(_client(services), f"{_ADMIN}:admin")
    foreign_admin = _as(_client(services), "admin-2:admin")

    payload = {"key": "revenue", "name": "Revenue", "description": "Total revenue", "expression": "sum(amount)", "version": 1, "status": "active"}
    assert admin.post("/api/analytics/admin/metrics", json=payload).status_code == 200

    assert anonymous.get("/api/analytics/admin/metrics/revenue/grants").status_code == 401
    assert ordinary.get("/api/analytics/admin/metrics/revenue/grants").status_code == 403
    assert ordinary.put(path).status_code == 403
    assert ordinary.delete(path).status_code == 403
    assert ordinary.get("/api/analytics/metrics").json() == {"metrics": []}
    assert admin.get("/api/analytics/metrics").json()["metrics"][0]["key"] == "revenue"

    granted = admin.put(path)
    assert granted.status_code == 200 and granted.json() == {"principal_id": _USER, "granted": True}
    assert admin.put(path).json() == {"principal_id": _USER, "granted": True}
    ordinary_catalog = ordinary.get("/api/analytics/metrics")
    assert ordinary_catalog.status_code == 200
    assert ordinary_catalog.json()["metrics"][0]["key"] == "revenue"
    assert admin.get("/api/analytics/admin/metrics/revenue/grants").json() == {"principal_ids": [_USER]}
    assert admin.get("/api/analytics/metrics").json()["metrics"][0]["key"] == "revenue"

    assert admin.put(path, json={}).status_code == 422
    assert foreign_admin.get("/api/analytics/admin/metrics/revenue/grants").status_code == 404
    assert foreign_admin.put(path).status_code == 404
    assert foreign_admin.delete(path).status_code == 404

    revoked = admin.delete(path)
    assert revoked.status_code == 200 and revoked.json() == {"removed": True}
    assert admin.delete(path).json() == {"removed": True}
    assert ordinary.get("/api/analytics/metrics").json() == {"metrics": []}


def test_metric_grant_routes_reject_invalid_principals_and_only_accept_path_identity(services):
    admin = _as(_client(services), f"{_ADMIN}:admin")
    payload = {"key": "revenue", "name": "Revenue", "description": "Total revenue", "expression": "sum(amount)", "version": 1, "status": "draft"}
    assert admin.post("/api/analytics/admin/metrics", json=payload).status_code == 200

    assert admin.put("/api/analytics/admin/metrics/revenue/grants/bad%0Auser").status_code == 422
    assert admin.get("/api/analytics/admin/metrics/revenue/grants?principal_id=other").json() == {"principal_ids": []}
    assert admin.put("/api/analytics/admin/metrics/revenue/grants/user-9", json={"principal_id": "other"}).status_code == 422


# --- plan / execute ---------------------------------------------------------


def test_plan_returns_a_stable_code_and_the_token_only_on_success(services, configured):
    client = _as(_client(services), f"{_USER}:user")

    denied = client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": "DELETE FROM orders"})
    assert denied.status_code == 200
    assert denied.json() == {"code": "unsupported_statement"}

    created = client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL})
    assert created.status_code == 200
    body = created.json()
    assert body["code"] == "plan_created"
    assert isinstance(body["plan_id"], str) and body["plan_id"]
    assert body["estimated_rows"] == 10 and body["engine_cost"] == "12.5"
    # raw SQL 绝不出现在响应里。
    assert _SQL not in created.text


def test_a_small_limit_query_reaches_the_plan_use_case_with_the_default_server_cap(services, configured):
    """配置的 max_result_rows 是全局上限，不是每条查询必须达到的下限。

    `SELECT ... LIMIT 10` 必须在默认配置下直接建出 plan：服务端把传输行上限自动收紧为
    min(1000, 10) = 10，而不是因为 1000 > 10 判 `authorization_stale`。
    """

    client = _as(_client(services), f"{_USER}:user")

    response = client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL})

    assert response.status_code == 200
    assert response.json()["code"] == "plan_created"
    assert response.json()["plan_id"]


def test_the_client_still_cannot_supply_any_limit(services, configured):
    client = _as(_client(services), f"{_USER}:user")

    for forged in ({"limits": {"max_result_rows": 999999}}, {"max_result_rows": 10}, {"query_max_rows": 10}):
        payload = {"datasource_id": configured.id, "sql": _SQL}
        payload.update(forged)
        response = client.post("/api/analytics/query-plans", json=payload)
        assert response.status_code == 422
        assert response.json() == {"detail": {"code": "invalid_analytics_request"}}


def test_an_unknown_datasource_is_denied_with_a_stable_code(services):
    client = _as(_client(services), f"{_USER}:user")

    response = client.post("/api/analytics/query-plans", json={"datasource_id": "missing", "sql": _SQL})

    assert response.status_code == 200
    assert response.json() == {"code": "datasource_unavailable"}


def test_execute_is_one_shot_and_returns_a_bounded_result(services, configured):
    client = _as(_client(services), f"{_USER}:user")
    plan_id = client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL}).json()["plan_id"]

    executed = client.post("/api/analytics/query-executions", json={"plan_id": plan_id})

    assert executed.status_code == 200
    body = executed.json()
    assert body["code"] == "executed"
    assert body["result"] == {"columns": ["id"], "rows": [[1]], "row_count": 1, "byte_count": 21, "truncated": False}
    assert plan_id not in executed.text

    again = client.post("/api/analytics/query-executions", json={"plan_id": plan_id})
    assert again.status_code == 200 and again.json() == {"code": "plan_unavailable"}


# --- 审计读取 ---------------------------------------------------------------


def test_audits_are_exact_principal_and_never_cross_tenant(services, configured):
    user_client = _as(_client(services), f"{_USER}:user")
    plan_id = user_client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL}).json()["plan_id"]
    user_client.post("/api/analytics/query-executions", json={"plan_id": plan_id})

    page = user_client.get("/api/analytics/audits").json()
    assert [record["phase"] for record in page["audits"]] == ["execute", "plan"]
    assert {record["principal_id"] for record in page["audits"]} == {_USER}
    assert page["has_more"] is False
    assert "sql" not in page["audits"][0] and "plan_id" not in page["audits"][0]

    assert _as(_client(services), "user-without-audits:user").get("/api/analytics/audits").json()["audits"] == []


def test_audit_keyset_pagination_is_stable(services, configured):
    client = _as(_client(services), f"{_USER}:user")
    for _ in range(3):
        plan_id = client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL}).json()["plan_id"]

    first = client.get("/api/analytics/audits", params={"limit": 2}).json()
    assert len(first["audits"]) == 2 and first["has_more"] is True
    assert first["next_before_started_at"] and first["next_before_id"]

    second = client.get("/api/analytics/audits", params={"limit": 2, "before_started_at": first["next_before_started_at"], "before_id": first["next_before_id"]}).json()
    assert len(second["audits"]) == 1

    ids = {record["id"] for record in first["audits"]} | {record["id"] for record in second["audits"]}
    assert len(ids) == 3
    assert plan_id is not None


def test_audit_page_size_is_bounded(services):
    client = _as(_client(services), f"{_USER}:user")

    assert client.get("/api/analytics/audits", params={"limit": 0}).status_code == 422
    assert client.get("/api/analytics/audits", params={"limit": 101}).status_code == 422


def test_admin_audits_require_an_exact_principal(services, configured):
    client = _as(_client(services), f"{_ADMIN}:admin")
    user_client = _as(_client(services), f"{_USER}:user")
    user_client.post("/api/analytics/query-plans", json={"datasource_id": configured.id, "sql": _SQL})

    assert client.get("/api/analytics/admin/audits").status_code == 422
    assert client.get("/api/analytics/admin/audits", params={"principal_id": ""}).status_code == 422

    page = client.get("/api/analytics/admin/audits", params={"principal_id": _USER}).json()
    assert [record["principal_id"] for record in page["audits"]] == [_USER]
    assert client.get("/api/analytics/admin/audits", params={"principal_id": "*"}).json()["audits"] == []


# --- 报告索引读取（Phase 4） ------------------------------------------------

_REPORT_FIELDS = {"id", "principal_id", "thread_id", "run_id", "artifact_path", "title", "status", "evidence_ids", "created_at"}
_EVIDENCE = "a" * 64


async def _publish(services, *, principal_id=_USER, thread_id="thread-1", run_id="run-1", artifact_path="/mnt/user-data/outputs/report.md", title="2026 Q3 经营分析"):
    """直接调用应用用例发布索引：这与 Lead-only 工具走的是同一个入口。"""

    return await services.publish_report.execute(
        principal_id=principal_id,
        thread_id=thread_id,
        run_id=run_id,
        title=title,
        artifact_path=artifact_path,
        evidence_ids=[_EVIDENCE],
    )


def test_report_listing_requires_authentication(services):
    assert _client(services).get("/api/analytics/reports").status_code == 401


@pytest.mark.asyncio
async def test_report_listing_is_exactly_principal_scoped(services):
    await _publish(services)
    await _publish(services, principal_id="someone-else", thread_id="thread-2", run_id="run-2")

    page = _as(_client(services), f"{_USER}:user").get("/api/analytics/reports").json()

    assert [report["principal_id"] for report in page["reports"]] == [_USER]
    assert page["has_more"] is False
    assert page["next_before_created_at"] is None and page["next_before_id"] is None


@pytest.mark.asyncio
async def test_a_report_response_only_carries_index_fields(services):
    await _publish(services)

    report = _as(_client(services), f"{_USER}:user").get("/api/analytics/reports").json()["reports"][0]

    assert set(report) == _REPORT_FIELDS
    # 索引里没有 artifact 内容，也没有任何"已签发的 URL"。
    assert report["artifact_path"] == "/mnt/user-data/outputs/report.md"
    assert report["status"] == "published"
    assert report["evidence_ids"] == [_EVIDENCE]
    for banned in ("content", "url", "sql", "rows", "token", "secret_ref", "download_url"):
        assert banned not in report


@pytest.mark.asyncio
async def test_report_keyset_pagination_is_stable(services):
    for index in range(3):
        await _publish(services, artifact_path=f"/mnt/user-data/outputs/report-{index}.md")
    client = _as(_client(services), f"{_USER}:user")

    first = client.get("/api/analytics/reports", params={"limit": 2}).json()
    assert len(first["reports"]) == 2 and first["has_more"] is True
    assert first["next_before_created_at"] and first["next_before_id"]

    second = client.get("/api/analytics/reports", params={"limit": 2, "before_created_at": first["next_before_created_at"], "before_id": first["next_before_id"]}).json()
    assert len(second["reports"]) == 1 and second["has_more"] is False

    ids = {report["id"] for report in first["reports"]} | {report["id"] for report in second["reports"]}
    assert len(ids) == 3


@pytest.mark.asyncio
async def test_a_half_specified_report_cursor_is_rejected(services):
    await _publish(services)
    client = _as(_client(services), f"{_USER}:user")

    half = client.get("/api/analytics/reports", params={"before_id": "report-1"})
    assert half.status_code == 422
    assert half.json() == {"detail": {"code": "invalid_analytics_request"}}


@pytest.mark.asyncio
async def test_report_page_size_is_bounded(services):
    client = _as(_client(services), f"{_USER}:user")

    assert client.get("/api/analytics/reports", params={"limit": 0}).status_code == 422
    assert client.get("/api/analytics/reports", params={"limit": 101}).status_code == 422


def test_admin_report_listing_requires_an_admin_and_an_exact_principal(services):
    client = _as(_client(services), f"{_ADMIN}:admin")

    assert _as(_client(services), f"{_USER}:user").get("/api/analytics/admin/reports", params={"principal_id": _USER}).status_code == 403
    assert _as(_client(services), f"{_ADMIN}:pat").get("/api/analytics/admin/reports", params={"principal_id": _USER}).status_code == 403
    assert client.get("/api/analytics/admin/reports").status_code == 422
    assert client.get("/api/analytics/admin/reports", params={"principal_id": ""}).status_code == 422


@pytest.mark.asyncio
async def test_admin_report_listing_needs_an_exact_principal(services):
    await _publish(services)
    client = _as(_client(services), f"{_ADMIN}:admin")

    assert client.get("/api/analytics/admin/reports", params={"principal_id": "*"}).json()["reports"] == []
    page = client.get("/api/analytics/admin/reports", params={"principal_id": _USER}).json()
    assert [report["principal_id"] for report in page["reports"]] == [_USER]
