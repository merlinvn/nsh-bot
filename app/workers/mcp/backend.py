"""MCPToolBackend — implements ToolBackend protocol for all tools (MCP + registry).

Routes MCP tools to the pricing engine, non-MCP tools to the registry handlers.
This is the single tool execution path for LLMProcessor.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.core.redis import get_redis_client
from app.workers.mcp.engine import mcp_calculate_shipping_quote, mcp_explain_quote_breakdown
from app.workers.shared.logging import get_logger

if TYPE_CHECKING:
    from app.workers.conversation.registry import ToolBackend

logger = get_logger("mcp.backend")

# MCP tool handlers — these go to the pricing engine
MCP_TOOL_HANDLERS: dict[str, Any] = {
    "calculate_shipping_quote": mcp_calculate_shipping_quote,
    "explain_quote_breakdown": mcp_explain_quote_breakdown,
}


class MCPToolBackend:
    """Single tool execution backend for all tools.

    MCP tools: delegate to pricing engine (cache-aside + Redis)
    Non-MCP tools: delegate to LocalToolBackend (registry handlers)
    """

    def __init__(self, tenant_id: str = "nsh") -> None:
        self._tenant_id = tenant_id
        self._local_backend: "LocalToolBackend | None" = None

    def _get_local_backend(self) -> "LocalToolBackend":
        """Lazily create LocalToolBackend for non-MCP tools."""
        if self._local_backend is None:
            from app.workers.conversation.registry import get_registry, LocalToolBackend
            self._local_backend = LocalToolBackend(get_registry())
        return self._local_backend

    async def call(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """Execute a tool (MCP or registry-based).

        Raises:
            ValueError: if the tool is unknown.
            asyncio.TimeoutError: if the tool exceeds its timeout.
        """
        handler = MCP_TOOL_HANDLERS.get(tool_name)
        if handler is not None:
            redis_client = await get_redis_client()
            return await asyncio.wait_for(
                handler(redis_client, tool_input, tenant_id=self._tenant_id),
                timeout=5.0,
            )

        # Non-MCP tool — delegate to registry
        return await asyncio.wait_for(
            self._get_local_backend().call(tool_name, tool_input),
            timeout=5.0,
        )
