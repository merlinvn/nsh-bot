"""Binding layer: MCP tool calls → pricing engine + Redis cache."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import redis.asyncio

from app.workers.engine.pricing import QuoteInput, calculate_quote
from app.workers.engine.config import load_pricing_config
from app.workers.engine.cache import get_cached_quote, set_cached_quote

if TYPE_CHECKING:
    import redis.asyncio


DEFAULT_TENANT = "nsh"


async def mcp_calculate_shipping_quote(
    redis_client: "redis.asyncio.Redis",
    tool_input: dict[str, Any],
    tenant_id: str = DEFAULT_TENANT,
) -> dict[str, Any]:
    """Execute calculate_shipping_quote via the pricing engine + cache.

    This is the MCP tool handler for calculate_shipping_quote.
    """
    config = load_pricing_config(tenant_id)
    input_data = QuoteInput(
        service_type=tool_input["service_type"],
        actual_weight_kg=tool_input["actual_weight_kg"],
        length_cm=tool_input["length_cm"],
        width_cm=tool_input["width_cm"],
        height_cm=tool_input["height_cm"],
        product_category=tool_input.get("product_category", ""),
        is_same_item_lot=tool_input.get("is_same_item_lot", False),
        is_fragile=tool_input.get("is_fragile", False),
        contains_battery=tool_input.get("contains_battery", False),
        contains_liquid=tool_input.get("contains_liquid", False),
        contains_powder=tool_input.get("contains_powder", False),
        is_medical_item=tool_input.get("is_medical_item", False),
        is_fake_or_branded_sensitive=tool_input.get("is_fake_or_branded_sensitive", False),
        is_cosmetic=tool_input.get("is_cosmetic", False),
        needs_insurance=tool_input.get("needs_insurance", False),
        declared_goods_value_vnd=tool_input.get("declared_goods_value_vnd", 0),
    )

    # Check cache first
    cached = await get_cached_quote(redis_client, tenant_id, input_data)
    if cached is not None:
        return {
            "status": cached.status,
            "message_to_customer": cached.message_to_customer,
            "missing_fields": cached.missing_fields,
            "reason": cached.reason,
            "quote_data": cached.quote_data,
            "_cached": True,
        }

    # Compute fresh
    result = calculate_quote(tenant_id, input_data, config)

    # Store in cache (only cache "quoted" status — rejections need fresh check)
    if result.status == "quoted":
        await set_cached_quote(
            redis_client,
            tenant_id,
            input_data,
            result,
            ttl_seconds=config.cache_ttl_seconds,
        )

    return {
        "status": result.status,
        "message_to_customer": result.message_to_customer,
        "missing_fields": result.missing_fields,
        "reason": result.reason,
        "quote_data": result.quote_data,
        "_cached": False,
    }


async def mcp_explain_quote_breakdown(
    redis_client: "redis.asyncio.Redis",
    tool_input: dict[str, Any],
    tenant_id: str = DEFAULT_TENANT,
) -> dict[str, Any]:
    """Execute explain_quote_breakdown via the pricing engine.

    Uses the same engine as calculate_shipping_quote, but formats
    the quote_data as human-readable Vietnamese prose.
    """
    # Use the same flow as calculate_shipping_quote to get quote_data
    quote_result = await mcp_calculate_shipping_quote(redis_client, tool_input, tenant_id)

    if quote_result["status"] != "quoted":
        return {
            "status": quote_result["status"],
            "message_to_customer": quote_result["message_to_customer"],
            "explanation": None,
            "quote_data": quote_result.get("quote_data", {}),
        }

    qd = quote_result.get("quote_data", {})
    service_type = qd.get("service_type", tool_input.get("service_type", ""))

    service_labels = {
        "fast": "Gói Nhanh (Hàng Bay)",
        "standard": "Gói Thường",
        "bundle": "Gói Bộ",
        "lot": "Gói Bộ Lô (Kho Đông Hưng - Hóc Môn)",
    }

    eta_map = {
        "fast": "3-6 ngày",
        "standard": "5-9 ngày",
        "bundle": "10-15 ngày",
        "lot": "15-25 ngày",
    }

    lines = [
        "Dạ em giải thích chi tiết giá ship cho anh/chị như sau:",
        "",
        f"- **Gói dịch vụ:** {service_labels.get(service_type, service_type)} ({eta_map.get(service_type, 'N/A')})",
        f"- **Cân nặng tính cước:** {qd.get('chargeable_weight_kg', 'N/A')}kg",
        f"- **Đơn giá:** {qd.get('unit_price_vnd_per_kg', 'N/A'):,}đ/kg (áp dụng bậc cân nặng phù hợp)",
        f"- **Cước chính:** {qd.get('subtotal_vnd', 0):,}đ",
    ]

    surcharges = qd.get("surcharges", [])
    if surcharges:
        for s in surcharges:
            lines.append(f"- **Phụ phí:** {s['reason']} (+{s['amount_vnd']:,}đ)")
    else:
        lines.append("- **Phụ phí:** Không có")

    if qd.get("insurance_fee_vnd", 0) > 0:
        lines.append(f"- **Bảo hiểm (5%):** {qd['insurance_fee_vnd']:,}đ")

    discounts = qd.get("discounts", [])
    if discounts:
        for d in discounts:
            lines.append(f"- **Giảm giá:** {d['reason']} (-{d['amount_vnd']:,}đ)")

    lines.append("")
    lines.append(f"💵 **Tổng cộng: {qd.get('total_vnd', 0):,}đ**")

    explanation = "\n".join(lines)

    return {
        "status": quote_result["status"],
        "message_to_customer": quote_result["message_to_customer"],
        "explanation": explanation,
        "quote_data": qd,
    }
