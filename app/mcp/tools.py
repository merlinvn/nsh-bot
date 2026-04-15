"""MCP tool definitions for shipping quote tools."""

from __future__ import annotations

from typing import Any


CALCULATE_SHIPPING_QUOTE_DESCRIPTION = (
    "Gọi ngay khi khách hỏi báo giá ship. "
    "Chỉ cần: service_type, actual_weight_kg, length_cm, width_cm, height_cm. "
    'service_type: fast="hàng nhanh"(3-6 ngày), standard="hàng thường"(5-9 ngày), bundle="hàng bộ"(10-15 ngày), lot="hàng lô"(15-25 ngày, tối thiểu 50kg). '
    "Khi tool trả status=quoted: sử dụng nội dung message_to_customer để trả lời. Thông báo khách là đây là ước tính, chi tiết cụ thể cho từng loại hàng thì liên hệ Zalo"
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
