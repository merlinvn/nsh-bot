"""Tests for MCPHTTPBackend — HTTP client for remote MCP server(s)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.workers.mcp.client import MCPHTTPBackend, MCPHTTPClient


class TestMCPHTTPClient:
    """Tests for the HTTP client with multiple URL support."""

    @pytest.mark.asyncio
    async def test_call_tool_first_server_success(self):
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "content": [{"type": "text", "text": '{"found": true, "customer": {"phone": "0912345678"}}'}]
            },
            "id": 1,
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = lambda: mock_response
            mock_post.return_value.raise_for_status = lambda: None
            client = MCPHTTPClient(base_urls=["http://nsh-mcp:8080"])
            result = await client.call_tool("lookup_customer", {"query": "0912345678"})

        assert result["found"] is True
        assert result["customer"]["phone"] == "0912345678"

    @pytest.mark.asyncio
    async def test_call_tool_all_servers_fail(self):
        import httpx

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")
            client = MCPHTTPClient(base_urls=["http://nsh-mcp:8080", "http://backup-mcp:8080"])
            with pytest.raises(RuntimeError, match="All MCP servers failed"):
                await client.call_tool("lookup_customer", {"query": "0912345678"})


class TestMCPHTTPBackend:
    """Tests for the async tool backend."""

    @pytest.mark.asyncio
    async def test_execute_alias_works(self):
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": '{"success": true}'}]},
            "id": 1,
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = lambda: mock_response
            mock_post.return_value.raise_for_status = lambda: None
            backend = MCPHTTPBackend(base_urls=["http://nsh-mcp:8080"])
            result = await backend.execute("handoff_request", {"reason": "test"})
        assert result["success"] is True


class TestMcpEngineIntegration:
    """Integration tests for pricing engine (no HTTP — tests engine directly)."""

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_with_mocked_redis(self):
        from app.workers.mcp.engine import mcp_calculate_shipping_quote

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

        result = await mcp_calculate_shipping_quote(mock_redis, tool_input, tenant_id="nsh")

        assert result["status"] == "quoted"
        assert result["quote_data"]["unit_price_vnd_per_kg"] == 68500
        assert result["_cached"] is False
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

        result = await mcp_calculate_shipping_quote(
            mock_redis,
            {"service_type": "fast", "actual_weight_kg": 30, "length_cm": 20, "width_cm": 20, "height_cm": 20},
            tenant_id="nsh",
        )

        assert result["_cached"] is True
        assert result["quote_data"]["total_vnd"] == 99999

    @pytest.mark.asyncio
    async def test_explain_quote_breakdown(self):
        from app.workers.mcp.engine import mcp_explain_quote_breakdown

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        result = await mcp_explain_quote_breakdown(
            mock_redis,
            {"service_type": "fast", "actual_weight_kg": 30, "length_cm": 20, "width_cm": 20, "height_cm": 20},
            tenant_id="nsh",
        )

        assert result["status"] == "quoted"
        assert result["explanation"] is not None
