"""MCPClient — unified tool definitions from MCP server + registry.

LLMProcessor uses this to get ALL tool definitions for AgentRunner,
regardless of whether tools are MCP-based or registry-based.
"""

from __future__ import annotations

from typing import Any

from app.workers.mcp.server import MCPServer
from app.workers.mcp.backend import MCPToolBackend


class MCPClient:
    """Unified tool provider: MCP tools + registry tools.

    AgentRunner gets tool definitions from here.
    Tool execution goes through MCPToolBackend.
    """

    def __init__(self, tenant_id: str = "nsh") -> None:
        self._server = MCPServer()
        self._backend = MCPToolBackend(tenant_id=tenant_id)
        self._registry_definitions: list[dict[str, Any]] | None = None

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all tool definitions: MCP tools + non-MCP registry tools.

        Merges at call time so registry tools reflect current registry state.
        """
        # MCP tool definitions
        mcp_tools = self._server._tool_definitions  # type: ignore[attr-defined]

        # Registry tool definitions (non-MCP tools only)
        from app.workers.conversation.registry import get_registry
        registry = get_registry()
        registry_tools = registry.definitions()

        return mcp_tools + registry_tools

    @property
    def backend(self) -> MCPToolBackend:
        """The tool execution backend."""
        return self._backend
