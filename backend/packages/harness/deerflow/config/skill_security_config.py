"""Configuration for skill installation security screening."""

from pydantic import BaseModel, Field


class SkillSecurityConfig(BaseModel):
    """LLM moderation policy for user and administrator skill writes."""

    moderation_model_name: str | None = Field(
        default=None,
        description="Optional model for skill security moderation; defaults to the primary chat model.",
    )
    security_fail_closed: bool = Field(
        default=True,
        description=("When the moderation model is unavailable, block non-executable skill content if True. Executable content remains blocked either way."),
    )
