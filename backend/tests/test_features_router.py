from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.deps import get_config
from app.gateway.routers import features


def _app_with_config(
    *,
    mcp_tasks_available: bool = False,
    conversation_references_enabled: bool = False,
) -> FastAPI:
    app = FastAPI()
    app.state.mcp_tasks_available = mcp_tasks_available
    app.include_router(features.router)
    tools = []
    if conversation_references_enabled:
        tools.append(SimpleNamespace(name="read_conversation", use="deerflow.tools.conversation:read_conversation", model_extra={}))
    fake_config = SimpleNamespace(
        tools=tools,
        subagent_runtime=SimpleNamespace(max_running=3),
    )
    app.dependency_overrides[get_config] = lambda: fake_config
    return app


def test_features_omits_removed_agents_api() -> None:
    with TestClient(_app_with_config()) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json() == {
        "mcp_tasks": {"enabled": False},
        "conversation_references": {"enabled": False, "max_references": 3},
    }
    assert "agents_api" not in response.json()
    assert "browser_control" not in response.json()


def test_features_reports_conversation_references_when_the_tool_is_configured() -> None:
    with TestClient(_app_with_config(conversation_references_enabled=True)) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json()["conversation_references"] == {"enabled": True, "max_references": 3}


def test_features_reports_mcp_tasks_startup_capability() -> None:
    with TestClient(_app_with_config(mcp_tasks_available=True)) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json()["mcp_tasks"] == {"enabled": True}


def test_features_omits_removed_subagent_batches_capability() -> None:
    with TestClient(_app_with_config()) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert "subagent_batches" not in response.json()
