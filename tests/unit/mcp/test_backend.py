"""Tests for MCPToolBackend (app.workers.mcp_client)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.workers.mcp_client import MCPToolBackend


class TestMCPToolBackend:
    """Tests for the async tool backend calling nsh-mcp via HTTP JSON-RPC."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
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
            backend = MCPToolBackend(base_urls=["http://nsh-mcp:8080"])
            result = await backend.call("lookup_customer", {"query": "0912345678"})

        assert result["found"] is True
        assert result["customer"]["phone"] == "0912345678"

    @pytest.mark.asyncio
    async def test_call_tool_all_servers_fail(self):
        import httpx

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")
            backend = MCPToolBackend(base_urls=["http://nsh-mcp:8080", "http://backup-mcp:8080"])
            with pytest.raises(RuntimeError, match="All MCP servers failed"):
                await backend.call("lookup_customer", {"query": "0912345678"})

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        """execute() wraps call() result in _ToolResult with .output attribute."""
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": '{"success": true}'}]},
            "id": 1,
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = lambda: mock_response
            mock_post.return_value.raise_for_status = lambda: None
            backend = MCPToolBackend(base_urls=["http://nsh-mcp:8080"])
            result = await backend.execute("handoff_request", {"reason": "test"})
        assert result.output["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_server_error_continues_to_next(self):
        """If one server returns an error JSON-RPC response, try the next."""
        error_response = {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": 1}
        success_response = {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": '{"found": false}'}]},
            "id": 1,
        }

        call_count = [0]

        def mock_json():
            resp = error_response if call_count[0] == 0 else success_response
            call_count[0] += 1
            return resp

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = mock_json
            mock_post.return_value.raise_for_status = lambda: None
            backend = MCPToolBackend(base_urls=["http://nsh-mcp:8080", "http://backup-mcp:8080"])
            result = await backend.call("lookup_customer", {"query": "0912345678"})

        assert result["found"] is False
        assert call_count[0] == 2


class TestMcpEngineIntegration:
    """Integration tests for pricing engine via MCPToolBackend (no real HTTP)."""

    @pytest.mark.asyncio
    async def test_calculate_shipping_quote_success(self):
        """MCPToolBackend calls nsh-mcp and returns parsed result."""
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "content": [{
                    "type": "text",
                    "text": '{"status": "quoted", "message_to_customer": "Test quote", "missing_fields": [], "reason": "", "quote_data": {"total_vnd": 2055000}, "notes": []}'
                }]
            },
            "id": 1,
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = lambda: mock_response
            mock_post.return_value.raise_for_status = lambda: None
            backend = MCPToolBackend(base_urls=["http://nsh-mcp:8080"])
            result = await backend.call("calculate_shipping_quote", {
                "service_type": "fast",
                "actual_weight_kg": 30,
                "length_cm": 20,
                "width_cm": 20,
                "height_cm": 20,
                "product_description": "thú bông",
            })

        assert result["status"] == "quoted"
        assert result["quote_data"]["total_vnd"] == 2055000
