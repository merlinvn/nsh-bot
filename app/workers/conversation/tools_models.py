"""Pydantic models for non-MCP tool input validation.

MCP tools (calculate_shipping_quote, explain_quote_breakdown) use schemas
defined in app.workers.mcp.tools instead of these models.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class LookupCustomerInput(BaseModel):
    """Input for lookup_customer tool."""
    query: str = Field(description="Phone number or name to search for")


class GetOrderStatusInput(BaseModel):
    """Input for get_order_status tool."""
    order_id: str = Field(description="The order ID to look up")


class CreateSupportTicketInput(BaseModel):
    """Input for create_support_ticket tool."""
    subject: str = Field(description="Brief subject/summary of the issue")
    description: str = Field(description="Detailed description of the issue")
    priority: Literal["low", "medium", "high"] = Field(default="medium")


class HandoffRequestInput(BaseModel):
    """Input for handoff_request tool."""
    reason: str = Field(description="Reason for the handoff request")
