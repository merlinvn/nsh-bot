"""MCPToolBackend — pure router for all MCP tool domains.

Routes to the correct domain handler:
- Shipping: calculate_shipping_quote, explain_quote_breakdown
- Customer: lookup_customer, get_order_status
- Support: create_support_ticket, handoff_request

No registry dependency. MCPToolBackend is the single execution entry point.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.workers.shared.logging import get_logger

logger = get_logger("mcp.backend")


class MCPToolBackend:
    """Single tool execution backend — routes to domain MCP handlers."""

    def __init__(self, tenant_id: str = "nsh") -> None:
        self._tenant_id = tenant_id
        self._handlers: dict[str, Any] | None = None

    def _get_handlers(self) -> dict[str, Any]:
        """Lazily build the domain handler map."""
        if self._handlers is None:
            from app.workers.mcp.engine import (
                mcp_calculate_shipping_quote,
                mcp_explain_quote_breakdown,
            )
            from app.workers.mcp.customer import (
                lookup_customer,
                get_order_status,
            )
            from app.workers.mcp.support import (
                create_support_ticket,
                handoff_request,
            )

            self._handlers = {
                # Shipping
                "calculate_shipping_quote": mcp_calculate_shipping_quote,
                "explain_quote_breakdown": mcp_explain_quote_breakdown,
                # Customer
                "lookup_customer": lookup_customer,
                "get_order_status": get_order_status,
                # Support
                "create_support_ticket": create_support_ticket,
                "handoff_request": handoff_request,
            }
        return self._handlers

    async def execute(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """Alias of call() for ToolExecutor interface compatibility."""
        return await self.call(tool_name, tool_input)

    async def call(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """Execute a tool via the correct domain handler.

        Raises:
            ValueError: if the tool is unknown.
            asyncio.TimeoutError: if the tool exceeds its timeout.
        """
        handlers = self._get_handlers()
        handler = handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Shipping tools need redis + tenant_id
        if tool_name in ("calculate_shipping_quote", "explain_quote_breakdown"):
            from app.core.redis import get_redis_client
            redis_client = await get_redis_client()
            return await asyncio.wait_for(
                handler(redis_client, tool_input, tenant_id=self._tenant_id),
                timeout=5.0,
            )

        # Customer + support tools take plain input dict
        return await asyncio.wait_for(
            handler(tool_input),
            timeout=5.0,
        )
