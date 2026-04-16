"""Binding layer: MCP tool calls → pricing engine."""

from __future__ import annotations

from typing import Any

from nsh_mcp.pricing.pricing import QuoteInput, calculate_quote
from nsh_mcp.pricing.config import load_pricing_config

DEFAULT_TENANT = "nsh"


async def mcp_calculate_shipping_quote(
    tool_input: dict[str, Any],
    tenant_id: str = DEFAULT_TENANT,
) -> dict[str, Any]:
    """Execute calculate_shipping_quote — weight, dimensions, product check."""
    config = load_pricing_config(tenant_id)
    input_data = QuoteInput(
        service_type=tool_input["service_type"],
        actual_weight_kg=tool_input["actual_weight_kg"],
        length_cm=tool_input["length_cm"],
        width_cm=tool_input["width_cm"],
        height_cm=tool_input["height_cm"],
        lot_surcharge_type=tool_input.get("lot_surcharge_type"),
        product_description=tool_input.get("product_description"),
    )

    result = calculate_quote(tenant_id, input_data, config)

    return {
        "status": result.status,
        "message_to_customer": result.message_to_customer,
        "missing_fields": result.missing_fields,
        "reason": result.reason,
        "quote_data": result.quote_data,
    }
