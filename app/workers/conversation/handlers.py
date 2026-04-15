"""Tool handler functions for the conversation worker.

Each handler is a module-level async function that receives a **validated
Pydantic input model** and returns a dict. The validation is performed by
LocalToolBackend before the handler is called, so handlers can assume their
inputs conform to the schema — no None checks or type casting needed.

This separation allows handlers to be swapped independently of the executor,
and makes it straightforward to replace a local handler with an MCP-backed
or HTTP-backed one in the future.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.workers.shared.logging import get_logger
from app.workers.conversation.tools_models import (
    CalculateShippingQuoteInput,
    CreateSupportTicketInput,
    DelegateToQuoteAgentInput,
    ExplainQuoteBreakdownInput,
    GetOrderStatusInput,
    HandoffRequestInput,
    LookupCustomerInput,
)

logger = get_logger("conversation-worker.handlers")


# ---------------------------------------------------------------------------
# Phase 1 handlers
# ---------------------------------------------------------------------------


async def lookup_customer(input: LookupCustomerInput) -> dict:
    """Find customer by phone number or name.

    Phase 1: mock implementation using hardcoded customer data.
    Replace with a real database query in production.
    """
    query = input.query.strip()

    if not query:
        return {"found": False, "error": "Query is required"}

    phone_pattern = re.compile(r"^[\d\-\+\s]{7,15}$")
    is_phone = bool(phone_pattern.match(query))

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


async def get_order_status(input: GetOrderStatusInput) -> dict:
    """Query order status by order ID.

    Phase 1: mock implementation using hardcoded order data.
    Replace with a real API call in production.
    """
    order_id = input.order_id.strip()

    if not order_id:
        return {"found": False, "error": "order_id is required"}

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


async def create_support_ticket(input: CreateSupportTicketInput) -> dict:
    """Open a support ticket.

    Phase 1: logs the ticket and returns a mock ID.
    Replace with a real ticketing system integration in production.
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

    logger.info(
        "support_ticket_created",
        extra={
            "ticket_id": ticket_id,
            "subject": input.subject,
            "priority": input.priority,
        },
    )

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": f"Đã tạo phiếu hỗ trợ #{ticket_id}. Chúng tôi sẽ liên hệ sớm.",
    }


async def handoff_request(input: HandoffRequestInput) -> dict:
    """Flag conversation for human handoff.

    Phase 1: logs the request. Replace with a real queue/notification
    integration in production.
    """
    logger.info(
        "handoff_requested",
        extra={"reason": input.reason},
    )

    return {
        "success": True,
        "message": "Yêu cầu chuyển đã được ghi nhận. Đại diện chăm sóc khách hàng sẽ liên hệ sớm.",
        "estimated_wait": "5-10 phút",
    }


# ---------------------------------------------------------------------------
# New Phase 1 tools
# ---------------------------------------------------------------------------


async def delegate_to_quote_agent(input: DelegateToQuoteAgentInput) -> dict:
    """Delegate to the quote subagent.

    Returns a marker dict that the processor uses to invoke the quote subagent.
    The processor intercepts this marker and runs the quote agent loop.
    """
    return {
        "delegated": True,
        "customer_message": input.customer_message,
        "known_context": input.known_context,
        "reason": input.reason,
    }


async def calculate_shipping_quote(input: CalculateShippingQuoteInput) -> dict:
    """Calculate shipping quote via MCP engine (pricing engine + Redis cache).

    This handler delegates to MCPToolBackend which handles:
    - Config loading from JSON
    - Redis cache-aside
    - Engine pricing calculation
    """
    from app.workers.mcp.backend import MCPToolBackend

    backend = MCPToolBackend()
    return await backend.call("calculate_shipping_quote", input.model_dump())


async def explain_quote_breakdown(input: ExplainQuoteBreakdownInput) -> dict:
    """Explain shipping quote pricing breakdown in Vietnamese.

    Delegates to MCP engine which computes the quote and formats
    the explanation in Vietnamese prose.
    """
    from app.workers.mcp.backend import MCPToolBackend

    backend = MCPToolBackend()
    return await backend.call("explain_quote_breakdown", input.model_dump())
