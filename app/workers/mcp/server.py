"""JSON-RPC 2.0 MCP server implementation (in-process).

Handles MCP protocol requests:
- tools/list: return available tool definitions
- tools/call: execute a tool by name

This is an in-process server — tool execution is handled by MCPToolBackend,
not a separate subprocess. This allows zero-copy integration with the
existing ToolExecutor without changing AgentRunner.
"""

from __future__ import annotations

import json
from typing import Any

from app.workers.mcp.tools import get_mcp_tool_definitions
from app.workers.mcp.backend import MCPToolBackend
from app.workers.shared.logging import get_logger

logger = get_logger("mcp.server")


class MCPServer:
    """In-process JSON-RPC 2.0 MCP server."""

    def __init__(self, backend: MCPToolBackend | None = None) -> None:
        self._backend = backend or MCPToolBackend()

    async def handle_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming JSON-RPC 2.0 request.

        Returns a JSON-RPC 2.0 response dict.
        Raises ValueError for unknown methods.
        """
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "neochat-shipping-mcp",
                        "version": "1.0.0",
                    },
                },
                "id": params.get("id"),
            }

        if method == "tools/list":
            tools = get_mcp_tool_definitions()
            return {
                "jsonrpc": "2.0",
                "result": {"tools": tools},
                "id": params.get("id"),
            }

        if method == "tools/call":
            tool_name = params.get("name")
            tool_input = params.get("arguments", {})
            try:
                result = await self._backend.call(tool_name, tool_input)
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False),
                            }
                        ]
                    },
                    "id": params.get("id"),
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {e}",
                        "data": {"tool": tool_name},
                    },
                    "id": params.get("id"),
                }

        raise ValueError(f"Unknown MCP method: {method}")

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return all MCP tool definitions."""
        return get_mcp_tool_definitions()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name and return its result."""
        return await self._backend.call(name, arguments)
