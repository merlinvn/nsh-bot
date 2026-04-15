"""Tests for MCPToolBackend — routes all 6 MCP tools."""

import pytest
from unittest.mock import AsyncMock, patch

from app.workers.mcp.backend import MCPToolBackend


class TestMCPToolBackend:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self):
        backend = MCPToolBackend()
        with pytest.raises(ValueError, match="Unknown tool"):
            await backend.call("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_success(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        # patch where get_redis_client is looked up (local import inside call())
        with patch("app.core.redis.get_redis_client", return_value=mock_redis):
            backend = MCPToolBackend()
            result = await backend.call("calculate_shipping_quote", {
                "service_type": "fast",
                "actual_weight_kg": 30,
                "length_cm": 20,
                "width_cm": 20,
                "height_cm": 20,
            })

        assert result["status"] == "quoted"

    @pytest.mark.asyncio
    async def test_lookup_customer_found(self):
        backend = MCPToolBackend()
        result = await backend.call("lookup_customer", {"query": "0912345678"})
        assert result["found"] is True
        assert result["customer"]["phone"] == "0912345678"

    @pytest.mark.asyncio
    async def test_lookup_customer_not_found(self):
        backend = MCPToolBackend()
        result = await backend.call("lookup_customer", {"query": "Người không tồn tại"})
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_get_order_status_found(self):
        backend = MCPToolBackend()
        result = await backend.call("get_order_status", {"order_id": "ORD-001"})
        assert result["found"] is True
        assert result["order"]["order_id"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        backend = MCPToolBackend()
        result = await backend.call("get_order_status", {"order_id": "ORD-INVALID"})
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_create_support_ticket(self):
        backend = MCPToolBackend()
        result = await backend.call("create_support_ticket", {
            "subject": "Hoàn tiền",
            "description": "Tôi muốn được hoàn tiền",
            "priority": "high",
        })
        assert result["success"] is True
        assert result["ticket_id"].startswith("TKT-")

    @pytest.mark.asyncio
    async def test_handoff_request(self):
        backend = MCPToolBackend()
        result = await backend.call("handoff_request", {"reason": "Customer wants human"})
        assert result["success"] is True
        assert "chuyển" in result["message"].lower()


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
