"""Pydantic schemas for Zalo webhook payloads."""
from typing import Any

from pydantic import BaseModel, Field


class ZaloSender(BaseModel):
    """Zalo sender information from webhook payload."""
    id: str = Field(..., description="Zalo user ID of the sender")


class ZaloMessage(BaseModel):
    """Zalo message object from webhook payload."""
    message_id: str | None = Field(None, alias="message_id", description="Unique Zalo message ID")
    text: str = Field("", description="Message text content")
    # Additional common fields Zalo may send
    media: dict | None = Field(None, description="Media attachment if present")

    model_config = {"populate_by_name": True}


class ZaloWebhookPayload(BaseModel):
    """Full Zalo webhook event payload."""
    event_name: str = Field(..., alias="event_name")
    sender: dict[str, Any] | None = Field(None, description="Sender info dict from Zalo")
    message: dict[str, Any] | None = Field(None, description="Message info dict from Zalo")
    oa_id: str | None = Field(None, alias="oa_id")
    app_id: int | None = Field(None, alias="app_id")
    user_id: str | None = Field(None, alias="user_id")
    user_external_id: str | None = Field(None, alias="user_external_id")
    timestamp: int | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class WebhookResponse(BaseModel):
    """Response returned by the webhook endpoint."""
    success: bool = True
