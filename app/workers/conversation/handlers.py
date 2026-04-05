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
    """Calculate shipping quote with tiered pricing, surcharges, and restrictions.

    Deterministic calculator using rates from the Phase 1 knowledge base.
    Returns structured JSON with status field.
    """
    import math

    def round_up_half(x: float) -> float:
        """Round up to nearest 0.5 kg."""
        return math.ceil(x * 2) / 2

    def tier_price(service: str, kg: float) -> int | None:
        """Return unit price VND/kg for the weight bracket, or None if not found."""
        tiers: dict[str, list[tuple[float, int]]] = {
            "fast": [
                (50, 68500),
                (150, 67500),
                (250, 66500),
                (350, 65500),
                (500, 64500),
            ],
            "standard": [
                (50, 52500),
                (150, 51500),
                (250, 40500),
                (350, 49500),
                (500, 48500),
            ],
            "bundle": [
                (50, 38000),
                (150, 37000),
                (250, 36000),
                (350, 35000),
                (500, 34000),
            ],
            "lot": [
                (150, 23500),
                (250, 22500),
                (350, 21500),
                (500, 20500),
            ],
        }
        for max_kg, price in tiers.get(service, []):
            if kg <= max_kg:
                return price
        return None

    # Collect missing fields
    missing_fields = []
    for field_name, value in [
        ("service_type", input.service_type),
        ("actual_weight_kg", input.actual_weight_kg),
        ("length_cm", input.length_cm),
        ("width_cm", input.width_cm),
        ("height_cm", input.height_cm),
    ]:
        if value in (None, 0, ""):
            missing_fields.append(field_name)

    if input.service_type == "lot" and not input.is_same_item_lot:
        if "is_same_item_lot" not in missing_fields:
            missing_fields.append("is_same_item_lot")

    if missing_fields:
        return {
            "status": "need_clarification",
            "message_to_customer": "Anh/chị cho em xin đầy đủ thông tin để báo giá chính xác nhé.",
            "missing_fields": missing_fields,
        }

    # --- Restrictions ---
    if input.service_type == "fast":
        if (
            input.contains_battery
            or input.contains_liquid
            or input.contains_powder
            or input.is_medical_item
        ):
            return {
                "status": "rejected",
                "message_to_customer": "Rất tiếc gói nhanh không nhận pin, chất lỏng, bột hoặc hàng y tế. Anh/chị vui lòng chọn gói khác.",
                "reason": "Gói nhanh không nhận pin/chất lỏng/bột/y tế.",
            }

    if input.service_type in ("standard", "bundle") and input.is_medical_item:
        return {
            "status": "rejected",
            "message_to_customer": "Gói đã chọn không nhận hàng y tế. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            "reason": "Hàng y tế không được chấp nhận cho gói standard/bundle.",
        }

    if input.is_cosmetic:
        return {
            "status": "manual_review",
            "message_to_customer": "Mặt hàng mỹ phẩm cần báo giá riêng. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            "reason": "Mỹ phẩm cần báo giá riêng.",
        }

    if input.is_fake_or_branded_sensitive:
        return {
            "status": "manual_review",
            "message_to_customer": "Mặt hàng này cần kiểm tra thêm trước khi báo giá. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            "reason": "Hàng nhạy cảm / fake / branded sensitive cần kiểm tra tay.",
        }

    # --- Volumetric calculation ---
    volume = input.length_cm * input.width_cm * input.height_cm

    if input.service_type in ("fast", "standard"):
        volumetric_kg = volume / 6000
        if volumetric_kg > input.actual_weight_kg:
            chargeable_kg = (volumetric_kg + input.actual_weight_kg) / 2
        else:
            chargeable_kg = input.actual_weight_kg
    elif input.service_type == "bundle":
        volumetric_kg = volume / 6000
        chargeable_kg = max(volumetric_kg, input.actual_weight_kg)
    elif input.service_type == "lot":
        if not input.is_same_item_lot or input.actual_weight_kg < 50:
            return {
                "status": "manual_review",
                "message_to_customer": "Hàng lô cần cùng một loại hàng và tối thiểu 50kg/lô. Anh/chị vui lòng kiểm tra lại.",
                "reason": "Hàng lô cần cùng một loại và tối thiểu 50kg.",
            }
        chargeable_kg = volume / 5000
    else:
        return {
            "status": "need_clarification",
            "message_to_customer": "Anh/chị muốn đi nhanh, thường, bộ hay hàng lô?",
            "missing_fields": ["service_type"],
        }

    chargeable_kg = round_up_half(chargeable_kg)

    if chargeable_kg > 500:
        return {
            "status": "manual_review",
            "message_to_customer": "Đơn hàng từ 501kg trở lên cần kiểm tra và báo giá riêng. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            "reason": "Từ 501kg trở lên cần báo giá riêng.",
        }

    unit_price = tier_price(input.service_type, chargeable_kg)
    if unit_price is None:
        return {
            "status": "manual_review",
            "message_to_customer": "Đơn này cần kiểm tra thêm để báo giá chính xác. Anh/chị vui lòng liên hệ Zalo 098.2128.029.",
            "reason": "Không tìm thấy đơn giá phù hợp.",
        }

    subtotal_vnd = int(chargeable_kg * unit_price)
    surcharges: list[dict] = []

    if input.service_type == "lot":
        cat = input.product_category.lower() if input.product_category else ""
        if any(x in cat for x in ["tất", "khăn", "quần áo"]):
            fee = int(chargeable_kg * 3000)
            subtotal_vnd += fee
            surcharges.append({"reason": "Phụ phí tất/khăn/quần áo", "amount_vnd": fee})

        if input.is_fragile:
            fee = int(chargeable_kg * 7000)
            subtotal_vnd += fee
            surcharges.append({"reason": "Phụ phí hàng dễ vỡ", "amount_vnd": fee})

    insurance_fee_vnd = 0
    if input.needs_insurance and input.declared_goods_value_vnd > 0:
        insurance_fee_vnd = int(input.declared_goods_value_vnd * 0.05)

    total_vnd = subtotal_vnd + insurance_fee_vnd

    eta_map = {
        "fast": "3-6 ngày",
        "standard": "5-9 ngày",
        "bundle": "10-15 ngày",
        "lot": "15-25 ngày",
    }

    discounts: list[dict] = []
    if chargeable_kg > 100:
        discounts.append(
            {
                "reason": "Voucher giao nội địa HCM cho hàng trên 100kg",
                "amount_vnd": 125000,
            }
        )

    service_labels = {
        "fast": "Gói Nhanh (Hàng Bay)",
        "standard": "Gói Thường",
        "bundle": "Gói Bộ",
        "lot": "Gói Bộ Lô (Kho Đông Hưng - Hóc Môn)",
    }

    # Build detailed breakdown message
    lines = [
        f"Dạ em báo giá cho anh/chị như sau:",
        f"",
        f"📦 **Gói dịch vụ:** {service_labels.get(input.service_type, input.service_type)} ({eta_map.get(input.service_type, 'N/A')})",
        f"⚖️ **Cân nặng tính cước:** {chargeable_kg}kg",
        f"💰 **Đơn giá:** {unit_price:,}đ/kg",
        f"📋 **Cước phí chính:** {subtotal_vnd:,}đ",
    ]

    if surcharges:
        for s in surcharges:
            lines.append(f"➕ **Phụ phí:** {s['reason']} (+{s['amount_vnd']:,}đ)")
    else:
        lines.append(f"✅ Không có phụ phí")

    if insurance_fee_vnd > 0:
        lines.append(f"🛡️ **Bảo hiểm (5%):** {insurance_fee_vnd:,}đ")

    if discounts:
        for d in discounts:
            lines.append(f"🎁 **Giảm giá:** {d['reason']} (-{d['amount_vnd']:,}đ)")

    lines.append(f"")
    lines.append(f"💵 **TỔNG CỘNG: {total_vnd:,}đ**")

    message_to_customer = "\n".join(lines)

    return {
        "status": "quoted",
        "message_to_customer": message_to_customer,
        "quote_data": {
            "service_type": input.service_type,
            "chargeable_weight_kg": chargeable_kg,
            "unit_price_vnd_per_kg": unit_price,
            "subtotal_vnd": subtotal_vnd,
            "insurance_fee_vnd": insurance_fee_vnd,
            "total_vnd": total_vnd,
            "eta": eta_map.get(input.service_type, "N/A"),
            "surcharges": surcharges,
            "discounts": discounts,
        },
    }
