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
    customer_message: str = Field(
        description="Tin nhắn hiện tại của khách liên quan đến báo giá vận chuyển"
    )
    known_context: dict = Field(
        default_factory=dict,
        description=(
            "Thông tin đã biết từ hội thoại trước. "
            "Các trường có thể có: service_type, actual_weight_kg, length_cm, width_cm, height_cm, "
            "product_category, is_same_item_lot, is_fragile, contains_battery, contains_liquid, "
            "contains_powder, is_medical_item, is_fake_or_branded_sensitive, is_cosmetic, "
            "needs_insurance, declared_goods_value_vnd"
        ),
    )
    reason: str = Field(default="", description="Lý do chuyển sang subagent báo giá")


class CalculateShippingQuoteInput(BaseModel):
    """Input for calculate_shipping_quote tool.

    Supports all service tiers from the Phase 1 knowledge base.
    All dimensions are required for accurate volumetric calculation.
    """
    service_type: Literal["fast", "standard", "bundle", "lot"] = Field(
        default="standard",
        description=(
            "Service tier: fast (3-6 days, air), "
            "standard (5-10 days, rail), "
            "bundle (10-15 days, economy), "
            "lot (15-25 days, batch, min 50kg/same item lot)"
        ),
    )
    actual_weight_kg: float = Field(description="Package actual weight in kg (must be > 0)")
    length_cm: float = Field(description="Package length in cm (must be > 0)")
    width_cm: float = Field(description="Package width in cm (must be > 0)")
    height_cm: float = Field(description="Package height in cm (must be > 0)")
    product_category: str = Field(
        default="",
        description="Product category for surcharge calculation (e.g. 'quần áo', 'tất', 'thủy tinh')"
    )
    is_same_item_lot: bool = Field(
        default=False,
        description="Whether the lot is all the same item type (required for lot service)"
    )
    is_fragile: bool = Field(default=False, description="Whether the package contains fragile items")
    contains_battery: bool = Field(default=False, description="Contains battery")
    contains_liquid: bool = Field(default=False, description="Contains liquid")
    contains_powder: bool = Field(default=False, description="Contains powder")
    is_medical_item: bool = Field(default=False, description="Is a medical item")
    is_fake_or_branded_sensitive: bool = Field(
        default=False,
        description="Contains fake or branded-sensitive goods"
    )
    is_cosmetic: bool = Field(default=False, description="Is a cosmetic product")
    needs_insurance: bool = Field(default=False, description="Customer wants insurance")
    declared_goods_value_vnd: float = Field(
        default=0,
        description="Declared goods value in VND for insurance calculation"
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
