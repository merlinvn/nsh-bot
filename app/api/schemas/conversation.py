"""Pydantic schemas for conversation endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DeliveryAttemptResponse(BaseModel):
    """A single delivery attempt record."""
    id: UUID
    attempt_no: int
    status: str
    response: dict | None = None
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ToolCallResponse(BaseModel):
    """A single tool call record."""
    id: UUID
    tool_name: str
    input: dict
    output: dict
    success: bool
    error: str | None = None
    latency_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageWithDetails(BaseModel):
    """A message with its associated tool calls and delivery attempts."""
    id: UUID
    direction: str
    text: str
    model: str | None = None
    latency_ms: int | None = None
    token_usage: dict | None = None
    message_id: str
    prompt_version: str
    created_at: datetime
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    delivery_attempts: list[DeliveryAttemptResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConversationList(BaseModel):
    """Summary view of a conversation (for list endpoint)."""
    id: UUID
    external_user_id: str
    conversation_key: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(0, description="Total messages in the conversation")

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    """Full conversation detail with messages, tool calls, and delivery attempts."""
    id: UUID
    external_user_id: str
    conversation_key: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageWithDetails] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PaginatedConversationList(BaseModel):
    """Paginated list of conversations."""
    items: list[ConversationList]
    total: int
    page: int
    size: int
    pages: int
