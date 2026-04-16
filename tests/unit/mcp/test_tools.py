"""Tests for MCP tool definitions from nsh_mcp.tools."""

import pytest

from nsh_mcp.tools import get_mcp_tool_definitions, CALCULATE_SHIPPING_QUOTE_DESCRIPTION


class TestMcpToolDefinitions:
    def test_returns_list(self):
        tools = get_mcp_tool_definitions()
        assert isinstance(tools, list)

    def test_has_calculate_shipping_quote(self):
        tools = get_mcp_tool_definitions()
        tool_names = [t["name"] for t in tools]
        assert "calculate_shipping_quote" in tool_names

    def test_calculate_shipping_quote_has_required_fields(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "calculate_shipping_quote")
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "service_type" in schema["properties"]
        assert "actual_weight_kg" in schema["properties"]
        assert "length_cm" in schema["properties"]
        assert "width_cm" in schema["properties"]
        assert "height_cm" in schema["properties"]
        assert "product_description" in schema["properties"]

    def test_product_description_required(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "calculate_shipping_quote")
        schema = tool["input_schema"]
        assert "product_description" in schema["required"]

    def test_service_type_enum(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "calculate_shipping_quote")
        service_prop = tool["input_schema"]["properties"]["service_type"]
        assert service_prop["type"] == "string"
        assert service_prop["enum"] == ["fast", "standard", "bundle", "lot"]

    def test_count(self):
        tools = get_mcp_tool_definitions()
        assert len(tools) == 1  # only calculate_shipping_quote

    def test_lot_surcharge_type_enum(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "calculate_shipping_quote")
        lot_prop = tool["input_schema"]["properties"]["lot_surcharge_type"]
        assert lot_prop["enum"] == ["clothing", "fragile"]

    def test_description_mentions_product_description_required(self):
        assert "product_description" in CALCULATE_SHIPPING_QUOTE_DESCRIPTION
