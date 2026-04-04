"""Pydantic schemas for Zalo webhook payloads."""
from pydantic import BaseModel, Field


class ZaloSender(BaseModel):
    """Zalo sender information from webhook payload."""
    id: str = Field(..., description="Zalo user ID of the sender")


class ZaloMessage(BaseModel):
    """Zalo message object from webhook payload."""
    message_id: str = Field(..., alias="message_id", description="Unique Zalo message ID")
    text: str = Field("", description="Message text content")
    # Additional common fields Zalo may send
    media: dict | None = Field(None, description="Media attachment if present")

    model_config = {"populate_by_name": True}


class ZaloWebhookPayload(BaseModel):
    """Full Zalo webhook event payload."""
    event_name: str = Field(..., alias="event_name")
    sender: ZaloSender
    message: ZaloMessage

    model_config = {"populate_by_name": True, "extra": "allow"}


class WebhookResponse(BaseModel):
    """Response returned by the webhook endpoint."""
    success: bool = True
