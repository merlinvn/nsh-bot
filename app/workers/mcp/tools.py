"""MCP tool definitions for shipping quote tools."""

from __future__ import annotations

from typing import Any


CALCULATE_SHIPPING_QUOTE_DESCRIPTION = (
    "Calculate shipping cost based on weight, dimensions, and service type. "
    "Returns a structured quote with status, message_to_customer, and quote_data. "
    "Supports service types: fast (3-6 days), standard (5-9 days), bundle (10-15 days), lot (15-25 days, min 50kg same-item lot). "
    "Use when a customer wants a shipping quote."
)

EXPLAIN_QUOTE_BREAKDOWN_DESCRIPTION = (
    "Explain in detail how the shipping cost was calculated, in Vietnamese. "
    "Use the same inputs as calculate_shipping_quote. "
    "Returns a human-readable explanation of the pricing breakdown."
)


def get_mcp_tool_definitions() -> list[dict[str, Any]]:
    """Return MCP-format tool definitions for all MCP tools."""
    return [
        {
            "name": "calculate_shipping_quote",
            "description": CALCULATE_SHIPPING_QUOTE_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "enum": ["fast", "standard", "bundle", "lot"],
                        "description": (
                            "Service tier: fast (3-6 days, air), "
                            "standard (5-9 days, rail), "
                            "bundle (10-15 days, economy), "
                            "lot (15-25 days, batch, min 50kg/same item lot)"
                        ),
                    },
                    "actual_weight_kg": {
                        "type": "number",
                        "description": "Package actual weight in kg (must be > 0)",
                    },
                    "length_cm": {
                        "type": "number",
                        "description": "Package length in cm (must be > 0)",
                    },
                    "width_cm": {
                        "type": "number",
                        "description": "Package width in cm (must be > 0)",
                    },
                    "height_cm": {
                        "type": "number",
                        "description": "Package height in cm (must be > 0)",
                    },
                    "product_category": {
                        "type": "string",
                        "description": "Product category for surcharge calculation (e.g. 'quần áo', 'tất', 'thủy tinh')",
                    },
                    "is_same_item_lot": {
                        "type": "boolean",
                        "description": "Whether the lot is all the same item type (required for lot service)",
                    },
                    "is_fragile": {
                        "type": "boolean",
                        "description": "Whether the package contains fragile items",
                    },
                    "contains_battery": {
                        "type": "boolean",
                        "description": "Contains battery",
                    },
                    "contains_liquid": {
                        "type": "boolean",
                        "description": "Contains liquid",
                    },
                    "contains_powder": {
                        "type": "boolean",
                        "description": "Contains powder",
                    },
                    "is_medical_item": {
                        "type": "boolean",
                        "description": "Is a medical item",
                    },
                    "is_fake_or_branded_sensitive": {
                        "type": "boolean",
                        "description": "Contains fake or branded-sensitive goods",
                    },
                    "is_cosmetic": {
                        "type": "boolean",
                        "description": "Is a cosmetic product",
                    },
                    "needs_insurance": {
                        "type": "boolean",
                        "description": "Customer wants insurance",
                    },
                    "declared_goods_value_vnd": {
                        "type": "number",
                        "description": "Declared goods value in VND for insurance calculation",
                    },
                },
                "required": ["service_type", "actual_weight_kg", "length_cm", "width_cm", "height_cm"],
            },
        },
        {
            "name": "explain_quote_breakdown",
            "description": EXPLAIN_QUOTE_BREAKDOWN_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "enum": ["fast", "standard", "bundle", "lot"],
                    },
                    "actual_weight_kg": {"type": "number"},
                    "length_cm": {"type": "number"},
                    "width_cm": {"type": "number"},
                    "height_cm": {"type": "number"},
                    "product_category": {"type": "string"},
                    "is_same_item_lot": {"type": "boolean"},
                    "is_fragile": {"type": "boolean"},
                    "contains_battery": {"type": "boolean"},
                    "contains_liquid": {"type": "boolean"},
                    "contains_powder": {"type": "boolean"},
                    "is_medical_item": {"type": "boolean"},
                    "is_fake_or_branded_sensitive": {"type": "boolean"},
                    "is_cosmetic": {"type": "boolean"},
                    "needs_insurance": {"type": "boolean"},
                    "declared_goods_value_vnd": {"type": "number"},
                },
                "required": ["service_type", "actual_weight_kg", "length_cm", "width_cm", "height_cm"],
            },
        },
    ]
