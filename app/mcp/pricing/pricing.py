"""Pure pricing calculation engine — weight + dimensions only."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PricingConfig:
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


@dataclass
class QuoteInput:
    """Input for shipping quote — weight and dimensions only."""

    service_type: Literal["fast", "standard", "bundle", "lot"]
    actual_weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float


@dataclass
class QuoteResult:
    """Output from shipping quote calculation."""

    status: Literal["need_clarification", "quoted", "rejected", "manual_review"]
    message_to_customer: str = ""
    missing_fields: list[str] = field(default_factory=list)
    reason: str = ""
    quote_data: dict = field(default_factory=dict)


def round_up_half(x: float) -> float:
    return math.ceil(x * 2) / 2


def tier_price(
    tiers: dict[str, list[tuple[float, int]]], service: str, kg: float
) -> int | None:
    for max_kg, price in tiers.get(service, []):
        if kg <= max_kg:
            return price
    return None


def calculate_quote(
    tenant_id: str, input_data: QuoteInput, config: PricingConfig
) -> QuoteResult:
    """Calculate shipping quote — weight + dimensions only.

    Formulas from ShippingCostCalculation:
    - Nhanh/Thuong: W = max(actual, (actual + volumetric)/2)
    - Bo: W = max(actual, volumetric)
    - Bo Lo: W = max(actual, volumetric/5000)
    """
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

    if missing_fields:
        return QuoteResult(
            status="need_clarification",
            message_to_customer="Anh/chị cho em xin đầy đủ thông tin để báo giá chính xác nhé.",
            missing_fields=missing_fields,
        )

    volume = input_data.length_cm * input_data.width_cm * input_data.height_cm

    if input_data.service_type in ("fast", "standard"):
        volumetric_kg = volume / 6000
        if volumetric_kg > input_data.actual_weight_kg:
            chargeable_kg = (volumetric_kg + input_data.actual_weight_kg) / 2
        else:
            chargeable_kg = input_data.actual_weight_kg
    elif input_data.service_type == "bundle":
        volumetric_kg = volume / 6000
        chargeable_kg = max(volumetric_kg, input_data.actual_weight_kg)
    elif input_data.service_type == "lot":
        volumetric_kg = volume / 5000
        chargeable_kg = max(volumetric_kg, input_data.actual_weight_kg)
        if input_data.actual_weight_kg < config.lot_minimum_kg:
            return QuoteResult(
                status="manual_review",
                message_to_customer=f"Hàng lô tối thiểu {config.lot_minimum_kg}kg. Anh/chị vui lòng liên hệ Zalo 098.2128.029.",
                reason=f"Hàng lô dưới {config.lot_minimum_kg}kg.",
            )
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
            message_to_customer="Đơn hàng trên 500kg cần báo giá riêng. Liên hệ Zalo 098.2128.029.",
        )

    unit_price = tier_price(config.tiers, input_data.service_type, chargeable_kg)
    if unit_price is None:
        return QuoteResult(
            status="manual_review",
            message_to_customer="Cần kiểm tra giá. Liên hệ Zalo 098.2128.029.",
        )

    total_vnd = int(chargeable_kg * unit_price)

    # Find which tier bracket this falls into
    tiers = config.tiers.get(input_data.service_type, [])
    bracket_label = ""
    for max_kg, price in tiers:
        if abs(price - unit_price) < 1:  # match by price
            for mk, mp in tiers:
                if mp == price and chargeable_kg <= mk:
                    bracket_label = f"1-{mk}kg: {price:,}đ/kg"
                    break

    service_labels = {
        "fast": "Gói Nhanh (Hàng Bay)",
        "standard": "Gói Thường",
        "bundle": "Gói Bộ",
        "lot": "Gói Bộ Lô",
    }

    L, W_val, H = input_data.length_cm, input_data.width_cm, input_data.height_cm
    actual = input_data.actual_weight_kg
    vol_div = 5000 if input_data.service_type == "lot" else 6000
    vol_kg = volume / vol_div

    # Determine formula explanation
    if input_data.service_type in ("fast", "standard"):
        if vol_kg > actual:
            formula_desc = f"vì KLQD({vol_kg:.1f}kg) > TLT({actual}kg) → lấy trung bình"
            charge_desc = f"(TLT + KLQD)/2 = ({actual} + {vol_kg:.1f})/2 = {(actual + vol_kg) / 2:.1f}kg"
        else:
            formula_desc = f"vì TLT({actual}kg) >= KLQD({vol_kg:.1f}kg) → lấy TLT"
            charge_desc = f"TLT = {actual}kg"
    elif input_data.service_type == "bundle":
        if vol_kg > actual:
            formula_desc = f"vì KLQD({vol_kg:.1f}kg) > TLT({actual}kg)"
            charge_desc = f"max(TLT, KLQD) = {vol_kg:.1f}kg"
        else:
            formula_desc = f"vì TLT({actual}kg) >= KLQD({vol_kg:.1f}kg)"
            charge_desc = f"max(TLT, KLQD) = {actual}kg"
    else:  # lot
        if vol_kg > actual:
            formula_desc = f"vì KLQD({vol_kg:.1f}kg) > TLT({actual}kg)"
            charge_desc = f"max(TLT, KLQD/5000) = {vol_kg:.1f}kg"
        else:
            formula_desc = f"vì TLT({actual}kg) >= KLQD({vol_kg:.1f}kg)"
            charge_desc = f"max(TLT, KLQD/5000) = {actual}kg"

    lines = [
        f"📦 **BÁO GIÁ VẬN CHUYỂN**",
        f"",
        f"**1. Thông tin khách cung cấp:**",
        f"   • Dịch vụ: {service_labels.get(input_data.service_type, input_data.service_type)}",
        f"   • Cân nặng thực (TLT): {actual} kg",
        f"   • Kích thước: {L} × {W_val} × {H} cm",
        f"",
        f"**2. Tính khối lượng quy đổi (KLQD):**",
        f"   Công thức: (Dài × Rộng × Cao) / {vol_div}",
        f"   = ({L} × {W_val} × {H}) / {vol_div}",
        f"   = {volume:,} / {vol_div}",
        f"   = **{vol_kg:.1f} kg**",
        f"",
        f"**3. Tính cân nặng tính cước:**",
    ]

    if input_data.service_type in ("fast", "standard"):
        lines.append(f"   Công thức: max(TLT, (TLT + KLQD)/2)")
    elif input_data.service_type == "bundle":
        lines.append(f"   Công thức: max(TLT, KLQD)")
    else:
        lines.append(f"   Công thức: max(TLT, KLQD/5000)")

    lines.extend(
        [
            f"   {formula_desc}",
            f"   → {charge_desc}",
            f"   → Cân nặng tính cước: **{chargeable_kg} kg**",
            f"",
            f"**4. Báo giá:**",
            f"   Đơn giá: {unit_price:,}đ/kg (bậc {bracket_label})",
            f"   Cước = {chargeable_kg} × {unit_price:,} = **{total_vnd:,}đ**",
            f"",
            f"💵 **TỔNG CỘNG: {total_vnd:,}đ**",
            f"⏱️ ETA: {config.eta.get(input_data.service_type, 'N/A')}",
        ]
    )

    return QuoteResult(
        status="quoted",
        message_to_customer="\n".join(lines),
        quote_data={
            "tenant_id": tenant_id,
            "service_type": input_data.service_type,
            "volume_cm3": volume,
            "volumetric_kg": round(vol_kg, 2),
            "actual_weight_kg": actual,
            "chargeable_weight_kg": chargeable_kg,
            "unit_price_vnd_per_kg": unit_price,
            "total_vnd": total_vnd,
            "eta": config.eta.get(input_data.service_type, "N/A"),
        },
    )
