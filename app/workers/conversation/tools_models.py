"""Pydantic models for tool input/output validation.

Input models: used by the registry to generate LLM tool definitions,
and by handlers to validate incoming tool calls.

Output models: optional structured output for tools with complex responses
(e.g. calculate_shipping_quote).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------

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


class DelegateToQuoteAgentInput(BaseModel):
    """Input for delegate_to_quote_agent tool."""
    reason: str = Field(default="", description="Reason for delegation")


class CalculateShippingQuoteInput(BaseModel):
    """Input for calculate_shipping_quote tool.

    Supports all service tiers from the Phase 1 knowledge base.
    All dimensions are required for accurate volumetric calculation.
    """
    weight_kg: float = Field(description="Package weight in kg (must be > 0)")
    length_cm: float = Field(description="Package length in cm (must be > 0)")
    width_cm: float = Field(description="Package width in cm (must be > 0)")
    height_cm: float = Field(description="Package height in cm (must be > 0)")
    service_type: Literal["nhanh", "thuong", "bo", "bolo"] = Field(
        default="thuong",
        description=(
            "Service tier: nhanh (3-6 days, air), "
            "thuong (5-10 days, rail), "
            "bo (10-15 days, economy), "
            "bolo (15-25 days, batch, min 50kg/0.3m³)"
        ),
    )


# ---------------------------------------------------------------------------
# Tool output models (optional, for structured responses)
# ---------------------------------------------------------------------------

class QuoteData(BaseModel):
    """Structured quote data returned by calculate_shipping_quote."""
    chargeable_kg: float
    rate_per_kg: str
    estimated_total_vnd: str
    service_type: str
    service_label: str
    minimum_chargeable: str | None = None


class CalculateShippingQuoteOutput(BaseModel):
    """Structured output for calculate_shipping_quote."""
    success: bool
    chargeable_kg: float | None = None
    rate_per_kg: str | None = None
    estimated_total_vnd: str | None = None
    service_type: str | None = None
    service_label: str | None = None
    minimum_chargeable: str | None = None
    error: str | None = None
