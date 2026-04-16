"""MCP tool definitions for shipping quote tools."""

from __future__ import annotations

from typing import Any


CALCULATE_SHIPPING_QUOTE_DESCRIPTION = (
    "Gọi ngay khi khách hỏi báo giá ship. "
    "Chỉ cần: service_type, actual_weight_kg, length_cm, width_cm, height_cm, product_description. "
    'service_type: fast="hàng nhanh"(3-6 ngày), standard="hàng thường"(5-9 ngày), bundle="hàng bộ"(10-15 ngày), lot="hàng lô"(15-25 ngày, tối thiểu 50kg). '
    "Khi tool trả status=quoted: sử dụng nội dung message_to_customer để trả lời. Thông báo khách là đây là ước tính, chi tiết cụ thể cho từng loại hàng thì liên hệ Zalo. "
    "LƯU Ý — KHÔNG BÁO GIÁ cho các hàng cấm vận chuyển: vũ khí (súng, dao...), hóa chất không rõ nguồn gốc, chất dễ cháy nổ (bình gas...), chất kích thích, động thực vật tươi sống. "
    "Hàng hạn chế (hàng hiệu/điện tử cao cấp, hàng chứa pin/nam châm/chất lỏng/bột/gel) → không đi gói nhanh, có thể cần liên hệ Zalo xác nhận."
)


def get_mcp_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "calculate_shipping_quote",
            "description": CALCULATE_SHIPPING_QUOTE_DESCRIPTION,
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "enum": ["fast", "standard", "bundle", "lot"],
                        "description": "Loại dịch vụ",
                    },
                    "actual_weight_kg": {
                        "type": "number",
                        "description": "Cân nặng (kg)",
                    },
                    "length_cm": {
                        "type": "number",
                        "description": "Chiều dài (cm)",
                    },
                    "width_cm": {
                        "type": "number",
                        "description": "Chiều rộng (cm)",
                    },
                    "height_cm": {
                        "type": "number",
                        "description": "Chiều cao (cm)",
                    },
                    "product_description": {
                        "type": "string",
                        "description": "Mô tả sản phẩm (vd: 'thuốc', 'mỹ phẩm', 'quần áo', 'điện tử'). Dùng để kiểm tra hàng cấm/giới hạn trước khi báo giá.",
                    },
                    "lot_surcharge_type": {
                        "type": "string",
                        "enum": ["clothing", "fragile"],
                        "description": "Phụ phí hàng lô theo loại: clothing='quần áo' (+3.000đ/kg), fragile='hàng khó' (+7.000đ/kg). Bỏ trống nếu không có phụ phí.",
                    },
                },
                "required": [
                    "service_type",
                    "actual_weight_kg",
                    "length_cm",
                    "width_cm",
                    "height_cm",
                ],
            },
        },
    ]
