"""Pure pricing calculation engine — no I/O, no hardcoded values."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class QuoteInput:
    """Input for shipping quote calculation."""
    service_type: Literal["fast", "standard", "bundle", "lot"]
    actual_weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    product_category: str = ""
    is_same_item_lot: bool = False
    is_fragile: bool = False
    contains_battery: bool = False
    contains_liquid: bool = False
    contains_powder: bool = False
    is_medical_item: bool = False
    is_fake_or_branded_sensitive: bool = False
    is_cosmetic: bool = False
    needs_insurance: bool = False
    declared_goods_value_vnd: float = 0


@dataclass
class QuoteResult:
    """Output from shipping quote calculation."""
    status: Literal["need_clarification", "quoted", "rejected", "manual_review"]
    message_to_customer: str = ""
    missing_fields: list[str] = field(default_factory=list)
    reason: str = ""
    quote_data: dict = field(default_factory=dict)


def round_up_half(x: float) -> float:
    """Round up to nearest 0.5 kg."""
    return math.ceil(x * 2) / 2


def tier_price(tiers: dict[str, list[tuple[float, int]]], service: str, kg: float) -> int | None:
    """Return unit price VND/kg for the weight bracket, or None if not found."""
    for max_kg, price in tiers.get(service, []):
        if kg <= max_kg:
            return price
    return None


def calculate_quote(tenant_id: str, input_data: QuoteInput, config: "PricingConfig") -> QuoteResult:
    """Calculate shipping quote using tenant pricing config.

    Pure function — all pricing data comes from config parameter.
    """
    # Collect missing fields
    missing_fields = []
    for field_name, value in [
        ("service_type", input_data.service_type),
        ("actual_weight_kg", input_data.actual_weight_kg),
        ("length_cm", input_data.length_cm),
        ("width_cm", input_data.width_cm),
        ("height_cm", input_data.height_cm),
    ]:
        if value in (None, 0, ""):
            missing_fields.append(field_name)

    if input_data.service_type == "lot" and not input_data.is_same_item_lot:
        if "is_same_item_lot" not in missing_fields:
            missing_fields.append("is_same_item_lot")

    if missing_fields:
        return QuoteResult(
            status="need_clarification",
            message_to_customer="Anh/chị cho em xin đầy đủ thông tin để báo giá chính xác nhé.",
            missing_fields=missing_fields,
        )

    # --- Restrictions ---
    if input_data.service_type == "fast":
        if (
            input_data.contains_battery
            or input_data.contains_liquid
            or input_data.contains_powder
            or input_data.is_medical_item
        ):
            return QuoteResult(
                status="rejected",
                message_to_customer="Rất tiếc gói nhanh không nhận pin, chất lỏng, bột hoặc hàng y tế. Anh/chị vui lòng chọn gói khác.",
                reason="Gói nhanh không nhận pin/chất lỏng/bột/y tế.",
            )

    if input_data.service_type in ("standard", "bundle") and input_data.is_medical_item:
        return QuoteResult(
            status="rejected",
            message_to_customer="Gói đã chọn không nhận hàng y tế. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            reason="Hàng y tế không được chấp nhận cho gói standard/bundle.",
        )

    if input_data.is_cosmetic:
        return QuoteResult(
            status="manual_review",
            message_to_customer="Mặt hàng mỹ phẩm cần báo giá riêng. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            reason="Mỹ phẩm cần báo giá riêng.",
        )

    if input_data.is_fake_or_branded_sensitive:
        return QuoteResult(
            status="manual_review",
            message_to_customer="Mặt hàng này cần kiểm tra thêm trước khi báo giá. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            reason="Hàng nhạy cảm / fake / branded sensitive cần kiểm tra tay.",
        )

    # --- Volumetric calculation ---
    volume = input_data.length_cm * input_data.width_cm * input_data.height_cm
    volumetric_divisor = config.volumetric_divisor.get(input_data.service_type, 6000)

    if input_data.service_type in ("fast", "standard"):
        volumetric_kg = volume / volumetric_divisor
        if volumetric_kg > input_data.actual_weight_kg:
            chargeable_kg = (volumetric_kg + input_data.actual_weight_kg) / 2
        else:
            chargeable_kg = input_data.actual_weight_kg
    elif input_data.service_type == "bundle":
        volumetric_kg = volume / volumetric_divisor
        chargeable_kg = max(volumetric_kg, input_data.actual_weight_kg)
    elif input_data.service_type == "lot":
        if not input_data.is_same_item_lot or input_data.actual_weight_kg < config.lot_minimum_kg:
            return QuoteResult(
                status="manual_review",
                message_to_customer="Hàng lô cần cùng một loại hàng và tối thiểu 50kg/lô. Anh/chị vui lòng kiểm tra lại.",
                reason="Hàng lô cần cùng một loại và tối thiểu 50kg.",
            )
        chargeable_kg = volume / volumetric_divisor
    else:
        return QuoteResult(
            status="need_clarification",
            message_to_customer="Anh/chị muốn đi nhanh, thường, bộ hay hàng lô?",
            missing_fields=["service_type"],
        )

    chargeable_kg = round_up_half(chargeable_kg)

    if chargeable_kg > config.max_chargeable_kg:
        return QuoteResult(
            status="manual_review",
            message_to_customer="Đơn hàng từ 501kg trở lên cần kiểm tra và báo giá riêng. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
            reason="Từ 501kg trở lên cần báo giá riêng.",
        )

    unit_price = tier_price(config.tiers, input_data.service_type, chargeable_kg)
    if unit_price is None:
        return QuoteResult(
            status="manual_review",
            message_to_customer="Đơn này cần kiểm tra thêm để báo giá chính xác. Anh/chị vui lòng liên hệ Zalo 098.2128.029.",
            reason="Không tìm thấy đơn giá phù hợp.",
        )

    subtotal_vnd = int(chargeable_kg * unit_price)
    surcharges: list[dict] = []

    if input_data.service_type == "lot":
        cat = input_data.product_category.lower() if input_data.product_category else ""
        if any(x in cat for x in ["tất", "khăn", "quần áo"]):
            fee = int(chargeable_kg * config.surcharges.get("lot_clothing_per_kg", 3000))
            subtotal_vnd += fee
            surcharges.append({"reason": "Phụ phí tất/khăn/quần áo", "amount_vnd": fee})

        if input_data.is_fragile:
            fee = int(chargeable_kg * config.surcharges.get("lot_fragile_per_kg", 7000))
            subtotal_vnd += fee
            surcharges.append({"reason": "Phụ phí hàng dễ vỡ", "amount_vnd": fee})

    insurance_fee_vnd = 0
    if input_data.needs_insurance and input_data.declared_goods_value_vnd > 0:
        insurance_fee_vnd = int(input_data.declared_goods_value_vnd * config.insurance_rate)

    total_vnd = subtotal_vnd + insurance_fee_vnd

    discounts: list[dict] = []
    discount_amount = config.discounts.get("voucher_over_100kg", 0)
    if chargeable_kg > 100 and discount_amount > 0:
        discounts.append(
            {
                "reason": "Voucher giao nội địa HCM cho hàng trên 100kg",
                "amount_vnd": discount_amount,
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
        f"📦 **Gói dịch vụ:** {service_labels.get(input_data.service_type, input_data.service_type)} ({config.eta.get(input_data.service_type, 'N/A')})",
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

    return QuoteResult(
        status="quoted",
        message_to_customer=message_to_customer,
        quote_data={
            "tenant_id": tenant_id,
            "service_type": input_data.service_type,
            "chargeable_weight_kg": chargeable_kg,
            "unit_price_vnd_per_kg": unit_price,
            "subtotal_vnd": subtotal_vnd,
            "insurance_fee_vnd": insurance_fee_vnd,
            "total_vnd": total_vnd,
            "eta": config.eta.get(input_data.service_type, "N/A"),
            "surcharges": surcharges,
            "discounts": discounts,
        },
    )


@dataclass
class PricingConfig:
    """Pricing configuration for a tenant — loaded from JSON."""
    tenant_id: str
    tiers: dict[str, list[tuple[float, int]]]
    volumetric_divisor: dict[str, float]
    eta: dict[str, str]
    surcharges: dict[str, int | float]
    insurance_rate: float
    discounts: dict[str, int | float]
    max_chargeable_kg: float = 500
    lot_minimum_kg: float = 50
    cache_ttl_seconds: int = 900
