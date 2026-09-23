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


def test_features_reports_agents_api_as_a_constant_false() -> None:
    """The custom-agent API was removed in Phase 5; the key stays for the frontend type."""
    with TestClient(_app_with_config()) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json() == {
        "agents_api": {"enabled": False},
        "mcp_tasks": {"enabled": False},
        "subagent_batches": {
            "enabled": False,
            "repository_available": False,
            "worker_running": False,
            "max_running": 3,
        },
        "conversation_references": {"enabled": False, "max_references": 3},
    }
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


def test_features_reports_subagent_batches_as_constant_false_capability() -> None:
    """The durable batch runtime was removed in Phase 5B; the key stays for the
    frontend type, and only the ordinary-subagent ``max_running`` stays live."""
    with TestClient(_app_with_config()) as client:
        response = client.get("/api/features")
    assert response.status_code == 200
    assert response.json()["subagent_batches"] == {
        "enabled": False,
        "repository_available": False,
        "worker_running": False,
        "max_running": 3,
    }
