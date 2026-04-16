"""MCP tool definitions for shipping quote tools."""

from __future__ import annotations

from typing import Any


CALCULATE_SHIPPING_QUOTE_DESCRIPTION = (
    "Gọi ngay khi khách hỏi báo giá ship. "
    "Chỉ cần: service_type, actual_weight_kg, length_cm, width_cm, height_cm, product_description. "
    'service_type: fast="hàng nhanh"(3-6 ngày), standard="hàng thường"(5-9 ngày), bundle="hàng bộ"(10-15 ngày), lot="hàng lô"(15-25 ngày, tối thiểu 50kg). '
    "Khi tool trả status=quoted: sử dụng nội dung message_to_customer để trả lời chi tiết từng công thức tính cho khách. Thông báo khách là đây là ước tính, chi tiết cụ thể cho từng loại hàng thì liên hệ Zalo. "
    "LƯU Ý — CẤM kí gửi: vũ khí hình dạng (súng, dao, bất kể chất liệu), bột màu trắng, hóa chất không rõ nguồn gốc, hóa chất dễ cháy nổ (bình gas...), gỗ quý, chất kích thích, động thực vật tươi sống. "
    "Hàng hiệu / điện tử cao cấp (tai nghe, camera, pin sạc dự phòng hãng cao cấp): CHỈ NHẬN kí gửi 1-2kg, giá trị dưới 2.000.000đ. Vượt quá giới hạn → báo manual_review. "
    "Hàng chứa Pin / Nam châm / Chất lỏng / Bột / Gel: KHÔNG đi gói nhanh (fast), chỉ dùng standard/bundle/lot. "
    "Hàng dễ vỡ (thủy tinh, gốm, điện tử dễ vỡ): tư vấn đóng gỗ hoặc túi khí, ghi chú trong product_description để tính phí đóng gói nếu cần. "
    "Hàng nhẹ cồng kềnh (thú bông, thùng, hộp, vali rỗng): tính theo KLQĐ — không báo giá fast vì sẽ rất đắt, nên dùng standard/bundle."
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
                        "description": "Mô tả sản phẩm (vd: 'tai nghe Sony', 'thuốc', 'thú bông', 'vali rỗng'). Dùng để kiểm tra hàng cấm, hàng giới hạn (hiệu/điện tử cao cấp), hàng dễ vỡ, và gợi ý đóng gỗ/túi khí khi cần.",
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
