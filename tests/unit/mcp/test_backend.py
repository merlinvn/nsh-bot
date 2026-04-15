"""Tests for MCPToolBackend."""

import pytest
from unittest.mock import AsyncMock, patch

from app.workers.mcp.backend import MCPToolBackend, MCP_TOOL_HANDLERS


class TestMCPToolBackend:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self):
        backend = MCPToolBackend()
        with pytest.raises(ValueError, match="Unknown tool"):
            await backend.call("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_unknown_tool_raises(self):
        backend = MCPToolBackend()
        with pytest.raises(ValueError, match="Unknown tool"):
            await backend.call("nonexistent", {"service_type": "fast"})

    @pytest.mark.asyncio
    async def test_tool_handlers_registered(self):
        assert "calculate_shipping_quote" in MCP_TOOL_HANDLERS
        assert "explain_quote_breakdown" in MCP_TOOL_HANDLERS


class TestMcpEngineIntegration:
    """Integration tests for MCP engine with mocked Redis."""

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_with_mocked_redis(self):
        from app.workers.mcp.engine import mcp_calculate_shipping_quote

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # cache miss
        mock_redis.setex = AsyncMock()

        tool_input = {
            "service_type": "fast",
            "actual_weight_kg": 30,
            "length_cm": 20,
            "width_cm": 20,
            "height_cm": 20,
        }

        result = await mcp_calculate_shipping_quote(mock_redis, tool_input, tenant_id="nsh")

        assert result["status"] == "quoted"
        assert result["message_to_customer"] != ""
        assert result["quote_data"]["unit_price_vnd_per_kg"] == 68500
        assert result["quote_data"]["chargeable_weight_kg"] == 30.0
        assert result["_cached"] is False

        # Should have stored in cache
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_cache_hit(self):
        from app.workers.mcp.engine import mcp_calculate_shipping_quote
        import json

        mock_redis = AsyncMock()
        cached = json.dumps({
            "status": "quoted",
            "message_to_customer": "Cached quote",
            "missing_fields": [],
            "reason": "",
            "quote_data": {"total_vnd": 99999, "unit_price_vnd_per_kg": 68500},
        })
        mock_redis.get = AsyncMock(return_value=cached)

        tool_input = {
            "service_type": "fast",
            "actual_weight_kg": 30,
            "length_cm": 20,
            "width_cm": 20,
            "height_cm": 20,
        }

        result = await mcp_calculate_shipping_quote(mock_redis, tool_input, tenant_id="nsh")

        assert result["status"] == "quoted"
        assert result["_cached"] is True
        assert result["quote_data"]["total_vnd"] == 99999

    @pytest.mark.asyncio
    async def test_explain_quote_breakdown(self):
        from app.workers.mcp.engine import mcp_explain_quote_breakdown

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        tool_input = {
            "service_type": "fast",
            "actual_weight_kg": 30,
            "length_cm": 20,
            "width_cm": 20,
            "height_cm": 20,
        }

        result = await mcp_explain_quote_breakdown(mock_redis, tool_input, tenant_id="nsh")

        assert result["status"] == "quoted"
        assert result["explanation"] is not None
        assert "giải thích" in result["explanation"] or "chi tiết" in result["explanation"]
