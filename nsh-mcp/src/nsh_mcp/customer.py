"""Customer MCP server — lookup_customer, get_order_status."""

from __future__ import annotations

import re
import uuid
from typing import Any

from nsh_mcp.logging import get_logger

logger = get_logger("mcp.customer")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

LOOKUP_CUSTOMER_DESCRIPTION = (
    "Find customer by phone number or name. "
    "Returns customer details if found, or not_found status if no match. "
    "Use when you need to look up a customer's information."
)

GET_ORDER_STATUS_DESCRIPTION = (
    "Query order status by order ID. "
    "Returns order details including status, items, total, and tracking info. "
    "Use when customer asks about their order status or delivery."
)


def get_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "lookup_customer",
            "description": LOOKUP_CUSTOMER_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Phone number or name to search for",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_order_status",
            "description": GET_ORDER_STATUS_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID to look up",
                    },
                },
                "required": ["order_id"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

MOCK_CUSTOMERS = [
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

MOCK_ORDERS = {
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


async def lookup_customer(input: dict[str, Any]) -> dict[str, Any]:
    """Find customer by phone number or name."""
    query = input.get("query", "").strip()

    if not query:
        return {"found": False, "error": "Query is required"}

    phone_pattern = re.compile(r"^[\d\-\+\s]{7,15}$")
    is_phone = bool(phone_pattern.match(query))

    if is_phone:
        for customer in MOCK_CUSTOMERS:
            if customer["phone"] == query or query in customer["phone"]:
                return {"found": True, "customer": customer}
    else:
        for customer in MOCK_CUSTOMERS:
            if query.lower() in customer["name"].lower():
                return {"found": True, "customer": customer}

    return {
        "found": False,
        "message": f"Không tìm thấy khách hàng với thông tin: {query}",
    }


async def get_order_status(input: dict[str, Any]) -> dict[str, Any]:
    """Query order status by order ID."""
    order_id = input.get("order_id", "").strip()

    if not order_id:
        return {"found": False, "error": "order_id is required"}

    order = MOCK_ORDERS.get(order_id)
    if order:
        return {"found": True, "order": order}

    return {
        "found": False,
        "message": f"Không tìm thấy đơn hàng: {order_id}",
    }
