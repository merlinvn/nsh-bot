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

    Phase 1: returns an instruction to use calculate_shipping_quote.
    Phase 2+: would involve actual subagent orchestration.
    """
    return {
        "delegated": True,
        "message": "Vui lòng sử dụng tool calculate_shipping_quote để tính cước vận chuyển.",
        "reason": input.reason,
    }


async def calculate_shipping_quote(input: CalculateShippingQuoteInput) -> dict:
    """Calculate shipping quote based on package details.

    Deterministic calculator using rates from the Phase 1 knowledge base.
    Rates match the default system prompt in prompts.py.

    Service types (from prompts.py knowledge base):
    - nhanh  : 3-6 days, 62,000-66,000 VND/kg (air freight)
    - thuong : 5-10 days, 46,000-50,000 VND/kg (rail)
    - bo     : 10-15 days, 32,000-36,000 VND/kg (economy)
    - bolo   : 15-25 days, 12,000-16,000 VND/kg (batch, min 50kg / 0.3m³)
    """
    weight_kg = input.weight_kg
    length_cm = input.length_cm
    width_cm = input.width_cm
    height_cm = input.height_cm
    service_type = input.service_type

    # Volumetric weight calculation per service type rules
    if service_type in ("nhanh", "thuong"):
        volumetric_kg = (length_cm * width_cm * height_cm) / 6000
        if volumetric_kg > weight_kg:
            chargeable_kg = (volumetric_kg + weight_kg) / 2
        else:
            chargeable_kg = weight_kg

    elif service_type == "bo":
        volumetric_kg = (length_cm * width_cm * height_cm) / 6000
        chargeable_kg = max(volumetric_kg, weight_kg)

    elif service_type == "bolo":
        # Batch: minimum 50kg, minimum 0.3m³
        volumetric_m3 = (length_cm * width_cm * height_cm) / 1_000_000
        volumetric_kg_from_m3 = volumetric_m3 * 250  # 250kg = 1m³
        chargeable_kg = max(volumetric_kg_from_m3, weight_kg)
        chargeable_kg = max(50.0, chargeable_kg)
        volumetric_m3 = max(0.3, volumetric_m3)

    # Pricing (from prompts.py knowledge base)
    rates: dict[str, tuple[int, int]] = {
        "nhanh": (62_000, 66_000),
        "thuong": (46_000, 50_000),
        "bo": (32_000, 36_000),
        "bolo": (12_000, 16_000),
    }
    rate_min, rate_max = rates[service_type]

    total_min = int(chargeable_kg * rate_min)
    total_max = int(chargeable_kg * rate_max)

    service_labels: dict[str, str] = {
        "nhanh": "Gói Nhanh (Hàng Bay) - 3-6 ngày",
        "thuong": "Gói Thường - 5-10 ngày",
        "bo": "Gói Bộ - 10-15 ngày",
        "bolo": "Gói Bộ Lô (Kho Đông Hưng - Hóc Môn) - 15-25 ngày",
    }

    result: dict[str, Any] = {
        "success": True,
        "chargeable_kg": round(chargeable_kg, 2),
        "rate_per_kg": f"{rate_min:,}-{rate_max:,} VND/kg",
        "estimated_total_vnd": f"{total_min:,}-{total_max:,} VND",
        "service_type": service_type,
        "service_label": service_labels[service_type],
    }

    if service_type == "bolo":
        result["minimum_chargeable"] = "50kg hoặc 0.3m³"

    return result
