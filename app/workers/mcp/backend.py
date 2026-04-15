"""MCPToolBackend — implements ToolBackend protocol for MCP tools."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.core.redis import get_redis_client
from app.workers.mcp.engine import mcp_calculate_shipping_quote, mcp_explain_quote_breakdown
from app.workers.shared.logging import get_logger

if TYPE_CHECKING:
    from app.workers.conversation.registry import ToolBackend

logger = get_logger("mcp.backend")


TOOL_HANDLERS: dict[str, Any] = {
    "calculate_shipping_quote": mcp_calculate_shipping_quote,
    "explain_quote_breakdown": mcp_explain_quote_breakdown,
}


class MCPToolBackend:
    """MCP tool backend — implements ToolBackend protocol.

    Routes tool calls to the MCP engine layer which handles
    cache-aside + pricing engine computation.
    """

    def __init__(self, tenant_id: str = "nsh") -> None:
        self._tenant_id = tenant_id

    async def call(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """Execute a tool via MCP engine + Redis cache.

        Raises:
            ValueError: if the tool is unknown or disabled.
            asyncio.TimeoutError: if the tool exceeds its timeout.
        """
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown MCP tool: {tool_name}")

        redis_client = await get_redis_client()

        try:
            return await asyncio.wait_for(
                handler(redis_client, tool_input, tenant_id=self._tenant_id),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.error("mcp_tool_timeout", extra={"tool_name": tool_name})
            raise
