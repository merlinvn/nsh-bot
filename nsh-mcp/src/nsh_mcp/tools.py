"""MCP tool definitions for shipping quote tools."""

from __future__ import annotations

from typing import Any


CALCULATE_SHIPPING_QUOTE_DESCRIPTION = (
    "Tính cước vận chuyển dựa trên cân nặng, kích thước, và loại dịch vụ. "
    "Tham số bắt buộc: service_type, actual_weight_kg, length_cm, width_cm, height_cm, product_description. "
    'service_type: fast="hàng nhanh"(3-6 ngày), standard="hàng thường"(5-9 ngày), bundle="hàng bộ"(10-15 ngày), lot="hàng lô"(15-25 ngày, tối thiểu 50kg). '
    "Khi tool trả status=quoted: sử dụng nội dung message_to_customer để trả lời chi tiết từng công thức tính cho khách. Thông báo khách là đây là ước tính, chi tiết cụ thể cho từng loại hàng thì liên hệ Zalo. "
    "LƯU Ý — CẤM kí gửi: vũ khí hình dạng (súng, dao, bất kể chất liệu), bột màu trắng, hóa chất không rõ nguồn gốc, hóa chất dễ cháy nổ (bình gas...), gỗ quý, chất kích thích, động thực vật tươi sống. "
    "Hàng hiệu / điện tử cao cấp (tai nghe, camera, pin sạc dự phòng hãng cao cấp): CHỈ NHẬN kí gửi 1-2kg, giá trị dưới 2.000.000đ. Vượt quá giới hạn → báo manual_review. "
    "Hàng chứa Pin / Nam châm / Chất lỏng / Bột / Gel: KHÔNG đi gói nhanh (fast), chỉ dùng standard/bundle/lot. "
    "GHI CHÚ theo nhóm hàng — khi product_description thuộc nhóm nào, THÊM cảnh báo vào message_to_customer: "
    "Nhóm DỄ VỠ (thủy tinh, gốm, men sứ, gỗ ép — ly, chén, bóng đèn, lavabo, bồn tắm, kệ gỗ, tủ gỗ…): khuyến nghị đóng gỗ hoặc túi khí, Nhanshiphang không chịu trách nhiệm nếu không đóng gói. "
    "Nhóm DỄ MÓP (inox mỏng rỗng, nhôm rỗng, nhựa giòn rỗng — chảo, nồi, bình đun nước, bình thủy, hộp nhựa…): khuyến nghị đóng gỗ hoặc túi khí. "
    "Nhóm GIÁ TRỊ CAO DỄ MÓC (camera, đồng hồ, linh kiện máy tính, tivi, tủ lạnh): khuyến nghị đóng gỗ, tự chịu trách nhiệm nếu mất hoặc hỏng. "
    "Nhóm DỄ BỊ RẠCH THỦNG (hàng fake quần áo/giày dép/túi xách, hàng có thương hiệu với vỏ hộp khó thay thế — đồ chơi mô hình thương hiệu Mỹ/Nhật…): cân nhắc gói bảo vệ bổ sung. "
    "Nhóm DỄ BUNG / THẤM / LÂY LAN (hóa chất như mực in/hương liệu, bột có màu sắc sặc sỡ/gia vị): không đóng chung với hàng khác, cần đóng túi kín. "
    "NHẮC KHÁCH cân nhắc kĩ lưỡng việc thêm phí đóng gỗ hoặc đóng túi khí để tránh tổn thất trong quá trình vận chuyển."
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
                        "description": "Mô tả sản phẩm (vd: 'tai nghe Sony', 'thuốc', 'thú bông', 'vali rỗng'). BẮT BUỘC. Dùng kiểm tra hàng cấm, hàng giới hạn (hiệu/điện tử cao cấp), hàng dễ vỡ, và gợi ý đóng gỗ/túi khí khi cần.",
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
                    "product_description",
                ],
            },
        },
    ]
