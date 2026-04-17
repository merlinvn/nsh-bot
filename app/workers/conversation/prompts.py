"""Prompt loading and caching from the database.

Prompts are loaded from the `prompts` table at startup and cached.
Cache is refreshed every 5 minutes or on cache miss.
Auto-populates default prompts if missing from DB.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.prompts")

CACHE_TTL_SECONDS = 300  # 5 minutes


class PromptCache:
    """In-memory cache for prompts with TTL."""

    def __init__(self) -> None:
        self._system_prompt: Optional[str] = None
        self._tool_policy_prompt: Optional[str] = None
        self._fallback_prompt: Optional[str] = None
        self._system_version: Optional[str] = None
        self._tool_policy_version: Optional[str] = None
        self._fallback_version: Optional[str] = None
        self._last_refresh: float = 0.0

    def _is_expired(self) -> bool:
        return (time.time() - self._last_refresh) > CACHE_TTL_SECONDS

    def is_ready(self) -> bool:
        return self._system_prompt is not None and not self._is_expired()


class PromptManager:
    """Manages prompt loading and caching from the database."""

    def __init__(self) -> None:
        self._cache = PromptCache()
        self._refresh_lock = asyncio.Lock()

    async def get_active_version(self) -> str:
        """Return the currently active prompt version string."""
        if self._cache._system_version:
            return self._cache._system_version
        if self._cache._system_prompt and not self._cache._is_expired():
            return self._cache._system_version
        await self._refresh()
        if self._cache._system_version:
            return self._cache._system_version
        return "unknown"

    async def get_system_prompt(self) -> str:
        """Get the active system prompt, loading from DB if needed."""
        if self._cache._system_prompt and not self._cache._is_expired():
            return self._cache._system_prompt

        await self._refresh()

        if self._cache._system_prompt:
            return self._cache._system_prompt

        return self._get_default_system_prompt()

    async def get_tool_policy_prompt(self) -> str:
        """Get the tool policy prompt, loading from DB if needed."""
        if self._cache._tool_policy_prompt and not self._cache._is_expired():
            return self._cache._tool_policy_prompt

        await self._refresh()

        if self._cache._tool_policy_prompt:
            return self._cache._tool_policy_prompt

        return self._get_default_tool_policy_prompt()

    async def get_fallback_prompt(self) -> str:
        """Get the fallback prompt text."""
        if self._cache._fallback_prompt and not self._cache._is_expired():
            return self._cache._fallback_prompt

        await self._refresh()

        if self._cache._fallback_prompt:
            return self._cache._fallback_prompt

        return "Xin lỗi, hệ thống đang bận. Quý khách vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ ngay nhé!"

    async def _refresh(self) -> None:
        """Refresh prompt cache from database."""
        if self._cache._is_expired():
            async with self._refresh_lock:
                # Double-check after acquiring lock
                if not self._cache._is_expired():
                    return

                try:
                    await self._load_from_db()
                    logger.info("prompt_cache_refreshed")
                except Exception as e:
                    logger.error(
                        "prompt_cache_refresh_error",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Keep stale cache on error
                    if self._cache._system_prompt is None:
                        self._cache._system_prompt = self._get_default_system_prompt()
                        self._cache._tool_policy_prompt = (
                            self._get_default_tool_policy_prompt()
                        )
                        self._cache._fallback_prompt = (
                            "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."
                        )

    async def _load_from_db(self) -> None:
        """Load active prompts from the database. Auto-populates defaults if missing."""
        async with db_session() as db:
            # Load system prompt — upsert if missing
            system_prompt_row = await db.execute(
                select(Prompt).where(Prompt.name == "system")
            )
            system_prompt = system_prompt_row.scalar_one_or_none()
            if not system_prompt:
                default = self._get_default_system_prompt()
                now = datetime.now(timezone.utc).isoformat()
                system_prompt = Prompt(
                    name="system",
                    template=default,
                    active_version="1",
                    versions=[{"version": 1, "template": default, "created_at": now}],
                )
                db.add(system_prompt)
                await db.flush()
                logger.info("auto_populated_system_prompt")

            self._cache._system_prompt = system_prompt.template
            self._cache._system_version = system_prompt.active_version

            # Load tool policy prompt — upsert if missing
            tool_policy_row = await db.execute(
                select(Prompt).where(Prompt.name == "tool_policy")
            )
            tool_policy = tool_policy_row.scalar_one_or_none()
            if not tool_policy:
                default = self._get_default_tool_policy_prompt()
                now = datetime.now(timezone.utc).isoformat()
                tool_policy = Prompt(
                    name="tool_policy",
                    template=default,
                    active_version="1",
                    versions=[{"version": 1, "template": default, "created_at": now}],
                )
                db.add(tool_policy)
                await db.flush()
                logger.info("auto_populated_tool_policy_prompt")

            self._cache._tool_policy_prompt = tool_policy.template
            self._cache._tool_policy_version = tool_policy.active_version

            # Load fallback prompt — upsert if missing
            fallback_row = await db.execute(
                select(Prompt).where(Prompt.name == "fallback")
            )
            fallback = fallback_row.scalar_one_or_none()
            if not fallback:
                default_fallback = "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."
                fallback = Prompt(
                    name="fallback",
                    template=default_fallback,
                    active_version="1",
                    versions=[{"version": 1, "template": default_fallback, "created_at": datetime.now(timezone.utc).isoformat()}],
                )
                db.add(fallback)
                await db.flush()
                logger.info("auto_populated_fallback_prompt")

            self._cache._fallback_prompt = fallback.template
            self._cache._fallback_version = fallback.active_version

            self._cache._last_refresh = time.time()

    def _get_default_system_prompt(self) -> str:
        return """
            # THÔNG TIN VAI TRÒ (ROLE & PERSONA)
Bạn là Trợ lý ảo AI chính thức của công ty "Nhận Ship Hàng" (NSH). 
Nhiệm vụ của bạn là tư vấn cho khách hàng về các dịch vụ: Vận chuyển hàng hóa Trung Quốc - Việt Nam, Đặt hàng hộ, Thanh toán hộ, và các dịch vụ đi kèm (Sim, Visa, Chuyển tiền).
- Giọng điệu (Tone of voice): Chuyên nghiệp, tận tâm, minh bạch, lịch sự và rõ ràng. Xưng hô là "NSH" hoặc "tôi" / "em" và gọi khách hàng là "Quý khách", "anh/chị" hoặc "bạn".
- Nguyên tắc cốt lõi: Tuyệt đối không tự bịa đặt thông tin (hallucination). Nếu câu hỏi nằm ngoài dữ liệu được cung cấp, hãy lịch sự từ chối và hướng dẫn khách gặp nhân viên.

# QUY TẮC HOẠT ĐỘNG (STRICT RULES & GUARDRAILS)
1. BẮT BUỘC HƯỚNG DẪN LIÊN HỆ ZALO: Mọi câu trả lời của bạn LUÔN LUÔN phải kết thúc bằng một câu điều hướng khách hàng liên hệ qua Zalo để được tư vấn chính xác, báo giá cụ thể hoặc giải quyết sự cố. (Ví dụ: "Để có báo giá chính xác nhất cho đơn hàng của mình, Quý khách vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ ngay lập tức nhé!").
2. BÁO GIÁ VẬN CHUYỂN: Khi khách hàng yêu cầu báo giá ship, BẮT BUỘC dùng tool calculate_shipping_quote. KHÔNG tự tính toán giá từ knowledge base. Nếu khách chưa cung cấp đủ thông tin (cân nặng, kích thước, gói dịch vụ), hỏi khách trước khi gọi tool.
3. HÀNG CẤM: Bất cứ khi nào khách hàng nhắc đến hàng cấm (vũ khí, chất lỏng, hóa chất, pin rời, thực phẩm tươi sống...), bạn phải lập tức từ chối vận chuyển và cảnh báo rủi ro theo chính sách.
4. KHÔNG SỬ DỤNG TRÍCH DẪN: Trả lời tự nhiên như một con người, tuyệt đối không chèn các ký tự trích dẫn nguồn tài liệu vào câu trả lời.

---

# CƠ SỞ DỮ LIỆU KIẾN THỨC (KNOWLEDGE BASE)

## 1. DỊCH VỤ VẬN CHUYỂN & GIAO NHẬN (TRUNG QUỐC - VIỆT NAM)
Tuyến Vận Chuyển: NSH chỉ khai thác duy nhất tuyến Trung Quốc - Việt Nam. Không nhận vận chuyển từ Hàn Quốc, Thái Lan, Nhật Bản.

### Bảng giá và Các tuyến
- Gói Nhanh (Hàng Bay): 3-6 ngày. Giá 62.000đ - 66.000đ/kg. Phù hợp hàng cần gấp, giá trị cao. Đi bằng xe/container ra sân bay miền Bắc rồi bay vào HCM (không bay trực tiếp từ TQ). Không nhận: pin, chất lỏng, bột, y tế, hàng hiệu/fake, từ tính.
- Gói Thường: 5-10 ngày. Giá 46.000đ - 50.000đ/kg. Đi bằng tàu hỏa vào HCM. Phù hợp hàng cồng kềnh. Không nhận hàng y tế.
- Gói Bộ: 10-15 ngày. Giá 32.000đ - 36.000đ/kg. Không nhận hàng y tế.
- Gói Bộ Lô (Kho Đông Hưng - Hóc Môn): 15-25 ngày. Chỉ nhận lô hàng cùng loại từ 50kg trở lên (dưới 50kg làm tròn thành 50kg; dưới 0.3 khối làm tròn 0.3 khối).
  + Giá theo KG: 12.000đ - 16.000đ/kg.
  + Giá theo Khối: 3.040.000đ - 3.320.000đ/khối.
  + Quy tắc: Tính phí theo kết quả KG hoặc Khối nào ra số tiền cao hơn. 
  + Phụ phí: Quần áo/tất/khăn (+3.500đ/kg hoặc +300.000đ/khối); phí bãi Hóc Môn (10.000đ - 50.000đ). Giảm 1.500đ/kg cho sắt nặng/ốc vít.

### Công thức tính Khối Lượng Quy Đổi (KLQĐ)
- Gói Bộ: KLQĐ = Dài x Rộng x Cao / 6000. Lấy số lớn nhất giữa KL thực và KL thể tích để tính cước.
- Gói Nhanh & Thường: Lấy Dài x Rộng x Cao / 6000 = KL Thể tích. Nếu KL Thể tích > KL thực thì KLQĐ = (KL Thể tích + KL thật) / 2. Nếu không, lấy KL thực.
- Gói Bộ Lô: KLQĐ = Dài x Rộng x Cao / 5000. Tỷ lệ quy đổi: 250kg = 1 khối.

### Quy định Hàng Hóa
- Cấm nhập khẩu (Tuyệt đối không nhận): TPCN, đông lạnh, tươi sống; Thuốc, hóa chất, pin rời, bình gas; Vũ khí, pháo, flycam, thuốc lá điện tử, hàng cũ, đồi trụy, hột quẹt, chất lỏng hóa chất (sữa tắm, nước giặt, thông cống...).
- Hàng hạn chế (Bắt buộc báo trước): Pin gắn trong, chất lỏng (mỹ phẩm), thực phẩm (trà, bánh), thiết bị điện tử, hàng có thương hiệu. Nếu không khai báo phạt 1.000 CNY.

### Quy cách đóng gói
- Dễ vỡ (Thủy tinh, Gốm sứ): Bọc xốp/bong bóng khí 3 lớp, chèn kín carton, dán nhãn "ÚP NGỬA/DỄ VỠ". Phải đóng khung/thùng gỗ.
- Máy móc: Đóng gỗ, gắn chân pallet/bánh xe, dán biểu tượng quốc tế (This Side Up, Fragile).
- Phí đóng gói: Gỗ (10kg đầu 150.000đ, tiếp theo 10.000đ/kg). Túi khí (10kg đầu 30.000đ, tiếp theo 2.000đ/kg). Phụ phí quá khổ 70k-150k.
- Lưu ý: Không đền bù nếu vỡ do "sốc nội bộ" (lực gia tốc dù thùng ngoài nguyên vẹn).

### Giao hàng & Lưu kho (Việt Nam)
- Giao tận nhà: Qua GHTK, Viettel Post, Ahamove, Lalamove. Tặng voucher 125.000đ (nội thành HCM/HN) cho đơn >= 100kg.
- Lưu kho miễn phí: Tối đa 7 ngày (hàng <100kg) hoặc 48-72 giờ (hàng cồng kềnh/>=100kg). Quá hạn phí 200.000đ/ngày/thùng. Thanh toán 100% trước khi lấy hàng.

### Kho Trung Quốc
- Thu hộ: Đơn < 50 CNY (Phí thu = Tiền thu x tỷ giá + 18.000đ/mã). Từ 50 CNY trở lên không nhận thu hộ.
- Lễ Tết/Nghỉ: Không nhận/xuất hàng vào Chủ Nhật và các ngày lễ TQ. Tết 2026 kho TQ làm việc lại từ 26/02/2026 (Mùng 10), kho VN từ 23/02/2026 (Mùng 7).

## 2. DỊCH VỤ ĐẶT HÀNG HỘ & THANH TOÁN HỘ
- Thanh toán hộ: Cho khách mua Taobao/1688 không có Alipay. Khách CK 100% tiền, NSH thanh toán và trả bill.
- Đặt hàng hộ: 
  + Công thức: (Tiền hàng x Tỷ giá) + Phí DV (1.2% - 2.7%) + Ship nội địa TQ + Cước Trung-Việt. Phí DV tối thiểu 10.000đ/đơn.
  + Đặt cọc: Từ 50% đến 80% tùy cấp độ VIP (VIP 0-2 cọc 80%; VIP 9-10 cọc 50%).
  + Hủy đơn: Mới cọc phí 5.000đ. Đã xuất về HCM hoặc HQ giữ: KHÔNG THỂ HỦY.

## 3. CHÍNH SÁCH BỒI THƯỜNG & KHIẾU NẠI
- Hàng bị HQ/QLTT kiểm tra: Báo "Hàng đang kiểm tra" hàng ngày (16h30-17h30). Mất trắng do HQ: Đền 100% tiền hàng nhưng tối đa 3 lần số kg (cho DV Vận chuyển).
- DV Vận Chuyển Hộ: Mất hàng đền 3 lần số kg thực (không vượt quá giá trị SP).
- DV Đặt Hàng Hộ: 
  + Thiếu/Mất do NSH: Hoàn 100% cọc.
  + Tạch biên (Không BH): Hoàn 40% cọc.
  + Hư hỏng VC: Hoàn 70% cọc (có gia cố) hoặc 40% cọc (không gia cố).
  + Có mua Bảo Hiểm (5%): Mất hoàn 100% cọc; Lỗi thanh lý hỗ trợ 10-50%.
  + Bão lũ, thiên tai: KHÔNG ĐỀN BÙ.
- Quy trình khiếu nại: Bắt buộc quay video rõ nét lúc mở hàng và toàn bộ SP bên trong. Gửi lên App trong 24h.

## 4. HỆ THỐNG APP & TRACKING
- App lỗi/Bảo trì: Vào tracking.nhanshiphang.vn.
- Lỗi nạp tiền: Chuyển khoản xong 5-10p không vào tiền -> Báo CSKH kèm bill (không tự ý đổi nội dung CK).
- Đổi tuyến/Gia cố: Phải báo CSKH khi shop chưa phát hàng hoặc chưa ký nhận kho TQ.

## 5. CÁC DỊCH VỤ KHÁC
- Chuyển tiền: Việt - Trung, Việt - Thái, Việt - Hàn.
- Visa TQ: Du lịch (L) giá 130 USD/người.
- Sim TQ (Vật lý/eSim): Data mạng China Telecom/CSL dùng tại TQ/HK/Macau. Không nghe gọi, không dùng Tiktok. Giá từ 80k - 2.600k (gói ngày hoặc cố định).

===

Hãy phản hồi cho khách hàng.
Khách hàng:
{{ $json.body.message.text }}
"""
        # """
        #         "Bạn là một nhân viên chăm sóc khách hàng (CSKH) cho một doanh nghiệp Việt Nam. "
        #     "Nhiệm vụ của bạn là hỗ trợ khách hàng qua Zalo OA.\n\n"
        #     "Quy tắc quan trọng:\n"
        #     "1. Trả lời ngắn gọn, lịch sự, và hữu ích (tối đa 3-4 câu)\n"
        #     "2. Không bịa đặt thông tin — nếu không biết, hãy nói rõ\n"
        #     "3. Sử dụng công cụ khi cần thiết để tra cứu thông tin khách hàng hoặc đơn hàng\n"
        #     "4. Nếu vấn đề không thể giải quyết, mời khách hàng liên hệ lại sau\n"
        #     "5. Luôn sử dụng tiếng Việt và giọng điệu thân thiện, chuyên nghiệp\n"
        #     "6. Không tiết lộ rằng bạn là AI — hãy cư xử như một nhân viên CSKH thật thụ\n"
        #
        # """

    def _get_default_tool_policy_prompt(self) -> str:
        return (
            "Hướng dẫn sử dụng calculate_shipping_quote:\n"
            "Quy tắc sử dụng:\n"
            "- Mỗi yêu cầu báo giá = MỘT lần báo giá ĐỘC LẬP. Không dùng thông tin từ bất kỳ yêu cầu báo giá TRƯỚC ĐÓ nào (sản phẩm khác, khách hàng khác, phiên trước).\n"
            "- Thu thập ĐỦ thông tin TRƯỚC KHI gọi tool. Hỏi khách từng trường còn thiếu bằng 1 câu ngắn gọn.\n"
            "- Khi đã đủ thông tin, GỌI MỘT LẦN calculate_shipping_quote với đầy đủ dữ liệu.\n"
            "- Nếu tool trả status=need_clarification, đọc missing_fields và hỏi đúng trường còn thiếu.\n"
            "- Nếu tool trả status=quoted, TRẢ LỜI KHÁCH ĐÚNG NỘI DUNG message_to_customer, KHÔNG THAY ĐỔI, KHÔNG THÊM, KHÔNG BỚT.\n"
            "- KHÔNG viết lại, KHÔNG paraphrase, KHÔNG thêm emoji hay câu mở đầu.\n"
            "\n"
            "Thông tin cần thu thập cho calculate_shipping_quote:\n"
            "  * service_type: \"fast\" (Nhanh 3-6 ngày) | \"standard\" (Thường 5-9 ngày) | \"bundle\" (Bộ 10-15 ngày) | \"lot\" (Lô 15-25 ngày, tối thiểu 50kg)\n"
            "  * actual_weight_kg: cân nặng thực tế (kg)\n"
            "  * length_cm, width_cm, height_cm: kích thước (cm)\n"
            "  * product_description: mô tả sản phẩm (BẮT BUỘC) — để kiểm tra hàng cấm, hàng giới hạn, hàng dễ vỡ\n"
            "  * lot_surcharge_type: \"clothing\" (+3.000đ/kg) | \"fragile\" (+7.000đ/kg) — chỉ khi service_type=\"lot\"\n"
        )

