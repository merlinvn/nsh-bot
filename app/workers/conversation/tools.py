"""Tool registry and executors for the conversation worker.

Defines the tool whitelist and executes tools with proper timeouts and error handling.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.tools")

# Tool whitelist — only these tools can be called
TOOL_WHITELIST = frozenset([
    "lookup_customer",
    "get_order_status",
    "create_support_ticket",
    "handoff_request",
])

# Tool definitions in Anthropic tool schema format
TOOL_DEFINITIONS = [
    {
        "name": "lookup_customer",
        "description": "Find customer by phone number or name. Use this when a customer provides their phone number or name and you need to look up their account information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Phone number or name to search for",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_order_status",
        "description": "Query the status of an order by order ID. Use this when a customer asks about their order status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to look up",
                }
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "create_support_ticket",
        "description": "Open a support ticket for customer issues that cannot be resolved through the available tools. Use when a customer has a complaint, refund request, or needs human agent assistance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief subject/summary of the issue",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priority level",
                },
            },
            "required": ["subject", "description"],
        },
    },
    {
        "name": "handoff_request",
        "description": "Flag this conversation for immediate human agent handoff. Use this sparingly — only when the customer explicitly requests a human, or the issue requires human judgment beyond what tools can provide.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for the handoff request",
                },
            },
            "required": ["reason"],
        },
    },
]


@dataclass
class ToolResult:
    """Result from a tool execution."""
    output: dict
    success: bool


class ToolExecutor:
    """Executes tools from the whitelist with timeout and error handling."""

    def __init__(self) -> None:
        self._customer_cache: dict[str, Any] = {}
        self._order_cache: dict[str, Any] = {}

    async def execute(self, tool_name: str, tool_input: dict) -> ToolResult:
        """Execute a tool by name with input, returning the result.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Arguments for the tool

        Returns:
            ToolResult with output dict and success flag
        """
        if tool_name not in TOOL_WHITELIST:
            logger.warning("unknown_tool_rejected", extra={"tool_name": tool_name})
            return ToolResult(
                output={"error": f"Unknown tool: {tool_name}"},
                success=False,
            )

        # Route to specific handler
        handler = {
            "lookup_customer": self._lookup_customer,
            "get_order_status": self._get_order_status,
            "create_support_ticket": self._create_support_ticket,
            "handoff_request": self._handoff_request,
        }.get(tool_name)

        if handler is None:
            return ToolResult(
                output={"error": f"No handler for tool: {tool_name}"},
                success=False,
            )

        try:
            result = await asyncio.wait_for(
                handler(tool_input),
                timeout=self._get_timeout(tool_name),
            )
            return ToolResult(output=result, success=True)
        except asyncio.TimeoutError:
            logger.error("tool_timeout", extra={"tool_name": tool_name})
            return ToolResult(
                output={"error": f"Tool '{tool_name}' timed out"},
                success=False,
            )
        except Exception as e:
            logger.error(
                "tool_exception",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ToolResult(
                output={"error": str(e)},
                success=False,
            )

    def _get_timeout(self, tool_name: str) -> float:
        """Return timeout in seconds for each tool."""
        timeouts = {
            "lookup_customer": 5.0,
            "get_order_status": 5.0,
            "create_support_ticket": 5.0,
            "handoff_request": 3.0,
        }
        return timeouts.get(tool_name, 5.0)

    async def _lookup_customer(self, input: dict) -> dict:
        """Find customer by phone number or name.

        In Phase 1, this is a mock implementation.
        Replace with actual database/API call in production.
        """
        query = input.get("query", "").strip()

        if not query:
            return {"found": False, "error": "Query is required"}

        # Simple phone number detection
        phone_pattern = re.compile(r"^[\d\-\+\s]{7,15}$")
        is_phone = bool(phone_pattern.match(query))

        # Mock customer data
        mock_customers = [
            {
                "customer_id": "C001",
                "name": "Nguyen Van A",
                "phone": "0912345678",
                "email": "nguyenvana@example.com",
                "registered_at": "2025-01-15T10:30:00Z",
            },
            {
                "customer_id": "C002",
                "name": "Tran Thi B",
                "phone": "0987654321",
                "email": "tranthib@example.com",
                "registered_at": "2025-02-20T14:00:00Z",
            },
        ]

        if is_phone:
            for customer in mock_customers:
                if customer["phone"] == query or query in customer["phone"]:
                    return {"found": True, "customer": customer}
        else:
            for customer in mock_customers:
                if query.lower() in customer["name"].lower():
                    return {"found": True, "customer": customer}

        return {
            "found": False,
            "message": f"Không tìm thấy khách hàng với thông tin: {query}",
        }

    async def _get_order_status(self, input: dict) -> dict:
        """Query order status by order ID.

        In Phase 1, this is a mock implementation.
        """
        order_id = input.get("order_id", "").strip()

        if not order_id:
            return {"found": False, "error": "order_id is required"}

        # Mock order data
        mock_orders = {
            "ORD-001": {
                "order_id": "ORD-001",
                "customer_id": "C001",
                "status": "delivered",
                "items": ["Product A x1", "Product B x2"],
                "total": "450000 VND",
                "created_at": "2026-03-28T09:00:00Z",
                "delivered_at": "2026-04-01T15:30:00Z",
            },
            "ORD-002": {
                "order_id": "ORD-002",
                "customer_id": "C002",
                "status": "shipped",
                "items": ["Product C x1"],
                "total": "150000 VND",
                "created_at": "2026-04-02T11:00:00Z",
                "tracking": "SPX-123456789",
            },
        }

        order = mock_orders.get(order_id)
        if order:
            return {"found": True, "order": order}

        return {
            "found": False,
            "message": f"Không tìm thấy đơn hàng: {order_id}",
        }

    async def _create_support_ticket(self, input: dict) -> dict:
        """Open a support ticket.

        In Phase 1, this logs the ticket and returns a mock ID.
        Replace with actual ticketing system integration.
        """
        subject = input.get("subject", "").strip()
        description = input.get("description", "").strip()
        priority = input.get("priority", "medium")

        if not subject or not description:
            return {
                "success": False,
                "error": "subject and description are required",
            }

        # Mock ticket creation
        import uuid
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

        logger.info(
            "support_ticket_created",
            extra={
                "ticket_id": ticket_id,
                "subject": subject,
                "priority": priority,
            },
        )

        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": f"Đã tạo phiếu hỗ trợ #{ticket_id}. Chúng tôi sẽ liên hệ sớm.",
        }

    async def _handoff_request(self, input: dict) -> dict:
        """Flag conversation for human handoff.

        In Phase 1, this logs the request and marks the conversation.
        Replace with actual queue/notification system.
        """
        reason = input.get("reason", "").strip()

        logger.info(
            "handoff_requested",
            extra={"reason": reason},
        )

        return {
            "success": True,
            "message": "Yêu cầu chuyển đã được ghi nhận. Đại diện chăm sóc khách hàng sẽ liên hệ sớm.",
            "estimated_wait": "5-10 phút",
        }
