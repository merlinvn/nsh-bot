"""Pydantic schemas for prompt management endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """A single version entry within a prompt."""
    version: str
    template: str
    created_at: datetime
    active: bool
    created_by: str | None = None


class PromptResponse(BaseModel):
    """Response for a prompt with its versions."""
    id: UUID
    name: str
    template: str
    versions: list[PromptVersion]
    active_version: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptActivateRequest(BaseModel):
    """Request to activate a specific prompt version."""
    name: str = Field(..., description="Prompt name")
    version: str = Field(..., description="Version string to activate (e.g., 'v2.0')")
