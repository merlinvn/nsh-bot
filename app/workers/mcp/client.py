"""MCPClient — unified tool definitions from all MCP domain servers.

LLMProcessor uses this to get ALL tool definitions.
All tools are now MCP-based (shipping, customer, support).
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.workers.mcp.server import MCPServer
from app.workers.mcp.backend import MCPToolBackend


class MCPClient:
    """Unified tool provider across all MCP domains.

    AgentRunner gets tool definitions from here.
    Tool execution goes through MCPToolBackend.
    """

    def __init__(self, tenant_id: str = "nsh") -> None:
        self._server = MCPServer()
        self._backend = MCPToolBackend(tenant_id=tenant_id)
        self._tool_definitions: list[dict[str, Any]] | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all tool definitions from all MCP domains (sync cache)."""
        if self._tool_definitions is None:
            # _all_tool_definitions is sync, call directly
            from app.workers.mcp.server import _all_tool_definitions
            self._tool_definitions = _all_tool_definitions()
        return self._tool_definitions

    @property
    def backend(self) -> MCPToolBackend:
        """The tool execution backend."""
        return self._backend
