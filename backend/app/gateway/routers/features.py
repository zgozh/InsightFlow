"""Read-only feature-flag endpoint for the frontend bootstrap.

Reports which optional features are exposed over HTTP so the frontend can gate
UI and avoid firing requests that the backend would reject. Config-only flags
read through ``get_config`` so edits to ``config.yaml`` take effect on the next
request, while startup-scoped capabilities report the runtime that actually
started.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.gateway.conversation_access import conversation_references_enabled
from app.gateway.deps import get_config
from app.gateway.run_models import MAX_CONVERSATION_REFERENCES
from deerflow.config.app_config import AppConfig

router = APIRouter(prefix="/api", tags=["features"])


class McpTasksFeature(BaseModel):
    """Availability of the durable MCP task runtime."""

    enabled: bool = Field(..., description="Whether durable MCP task APIs and UI are available")


class ConversationReferencesFeature(BaseModel):
    """Availability of explicit conversation references on run requests."""

    enabled: bool = Field(..., description="Whether the opt-in read_conversation tool is configured, so run requests may carry conversation_references")
    max_references: int = Field(..., description="Maximum conversation references accepted on one run request")


class FeaturesResponse(BaseModel):
    """Frontend-facing feature availability flags."""

    mcp_tasks: McpTasksFeature
    conversation_references: ConversationReferencesFeature


@router.get(
    "/features",
    response_model=FeaturesResponse,
    summary="List Feature Flags",
    description="Report which optional features are available, so the frontend can gate UI before issuing requests.",
)
async def list_features(request: Request, config: AppConfig = Depends(get_config)) -> FeaturesResponse:
    """Return availability of optional frontend features."""
    return FeaturesResponse(
        # MCP task bindings and the submitter are startup-scoped. Report the
        # capability that actually started rather than a hot-reloaded config
        # value that would require a Gateway restart to take effect.
        mcp_tasks=McpTasksFeature(enabled=bool(getattr(request.app.state, "mcp_tasks_available", False))),
        # Same predicate as run admission (``prepare_conversation_reader``), read
        # through ``get_config`` so enabling the tool in config.yaml shows up
        # without a restart. A UI with no entry point still needs no change here.
        conversation_references=ConversationReferencesFeature(
            enabled=conversation_references_enabled(config),
            max_references=MAX_CONVERSATION_REFERENCES,
        ),
    )
