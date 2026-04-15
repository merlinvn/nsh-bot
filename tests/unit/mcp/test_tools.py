"""Tests for MCP tool definitions."""

import pytest

from app.workers.mcp.tools import get_mcp_tool_definitions, CALCULATE_SHIPPING_QUOTE_DESCRIPTION


class TestMcpToolDefinitions:
    def test_returns_list(self):
        tools = get_mcp_tool_definitions()
        assert isinstance(tools, list)

    def test_has_calculate_shipping_quote(self):
        tools = get_mcp_tool_definitions()
        tool_names = [t["name"] for t in tools]
        assert "calculate_shipping_quote" in tool_names

    def test_has_explain_quote_breakdown(self):
        tools = get_mcp_tool_definitions()
        tool_names = [t["name"] for t in tools]
        assert "explain_quote_breakdown" in tool_names

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

    def test_explain_quote_breakdown_has_required_fields(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "explain_quote_breakdown")
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert "service_type" in schema["properties"]
        assert "actual_weight_kg" in schema["properties"]

    def test_service_type_enum(self):
        tools = get_mcp_tool_definitions()
        tool = next(t for t in tools if t["name"] == "calculate_shipping_quote")
        service_prop = tool["input_schema"]["properties"]["service_type"]
        assert service_prop["type"] == "string"
        assert service_prop["enum"] == ["fast", "standard", "bundle", "lot"]

    def test_count(self):
        tools = get_mcp_tool_definitions()
        assert len(tools) == 2
