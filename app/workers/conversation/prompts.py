"""Prompt loading and caching from the database.

Prompts are loaded from the `prompts` table at startup and cached.
Cache is refreshed every 5 minutes or on cache miss.
"""

import asyncio
import time
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

    def get_active_version(self) -> str:
        """Return the currently active prompt version string."""
        if self._cache._system_version:
            return self._cache._system_version
        return "unknown"

    def get_system_prompt(self) -> str:
        """Get the active system prompt, loading from DB if needed."""
        if self._cache._system_prompt and not self._cache._is_expired():
            return self._cache._system_prompt

        # Trigger async refresh if possible, but return cached or default
        asyncio.create_task(self._refresh())
        if self._cache._system_prompt:
            return self._cache._system_prompt

        # Return default if cache miss and no event loop
        return self._get_default_system_prompt()

    def get_tool_policy_prompt(self) -> str:
        """Get the tool policy prompt, loading from DB if needed."""
        if self._cache._tool_policy_prompt and not self._cache._is_expired():
            return self._cache._tool_policy_prompt

        asyncio.create_task(self._refresh())
        if self._cache._tool_policy_prompt:
            return self._cache._tool_policy_prompt

        return self._get_default_tool_policy_prompt()

    def get_fallback_prompt(self) -> str:
        """Get the fallback prompt text."""
        if self._cache._fallback_prompt and not self._cache._is_expired():
            return self._cache._fallback_prompt

        asyncio.create_task(self._refresh())
        if self._cache._fallback_prompt:
            return self._cache._fallback_prompt

        return "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."

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
                        self._cache._tool_policy_prompt = self._get_default_tool_policy_prompt()
                        self._cache._fallback_prompt = "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."

    async def _load_from_db(self) -> None:
        """Load active prompts from the database."""
        async with db_session() as db:
            # Load system prompt
            system_prompt_row = await db.execute(
                select(Prompt).where(Prompt.name == "system")
            )
            system_prompt = system_prompt_row.scalar_one_or_none()
            if system_prompt and system_prompt.versions:
                versions = system_prompt.versions
                active_version_str = system_prompt.active_version
                for version_entry in versions:
                    if version_entry.get("version") == active_version_str:
                        self._cache._system_prompt = version_entry.get(
                            "template", system_prompt.template
                        )
                        self._cache._system_version = active_version_str
                        break
                else:
                    # Active version not found in versions array, fall back to template
                    self._cache._system_prompt = system_prompt.template
                    self._cache._system_version = system_prompt.active_version
            elif system_prompt:
                self._cache._system_prompt = system_prompt.template
                self._cache._system_version = system_prompt.active_version

            # Load tool policy prompt
            tool_policy_row = await db.execute(
                select(Prompt).where(Prompt.name == "tool_policy")
            )
            tool_policy = tool_policy_row.scalar_one_or_none()
            if tool_policy and tool_policy.versions:
                versions = tool_policy.versions
                active_version_str = tool_policy.active_version
                for version_entry in versions:
                    if version_entry.get("version") == active_version_str:
                        self._cache._tool_policy_prompt = version_entry.get(
                            "template", tool_policy.template
                        )
                        self._cache._tool_policy_version = active_version_str
                        break
                else:
                    self._cache._tool_policy_prompt = tool_policy.template
                    self._cache._tool_policy_version = tool_policy.active_version
            elif tool_policy:
                self._cache._tool_policy_prompt = tool_policy.template
                self._cache._tool_policy_version = tool_policy.active_version

            # Load fallback prompt
            fallback_row = await db.execute(
                select(Prompt).where(Prompt.name == "fallback")
            )
            fallback = fallback_row.scalar_one_or_none()
            if fallback:
                self._cache._fallback_prompt = fallback.template
                self._cache._fallback_version = fallback.active_version

            self._cache._last_refresh = time.time()

    def _get_default_system_prompt(self) -> str:
        return (
            "Bạn là một nhân viên chăm sóc khách hàng (CSKH) cho một doanh nghiệp Việt Nam. "
            "Nhiệm vụ của bạn là hỗ trợ khách hàng qua Zalo OA.\n\n"
            "Quy tắc quan trọng:\n"
            "1. Trả lời ngắn gọn, lịch sự, và hữu ích (tối đa 3-4 câu)\n"
            "2. Không bịa đặt thông tin — nếu không biết, hãy nói rõ\n"
            "3. Sử dụng công cụ khi cần thiết để tra cứu thông tin khách hàng hoặc đơn hàng\n"
            "4. Nếu vấn đề không thể giải quyết, mời khách hàng liên hệ lại sau\n"
            "5. Luôn sử dụng tiếng Việt và giọng điệu thân thiện, chuyên nghiệp\n"
            "6. Không tiết lộ rằng bạn là AI — hãy cư xử như một nhân viên CSKH thật thụ\n"
        )

    def _get_default_tool_policy_prompt(self) -> str:
        return (
            "Hướng dẫn sử dụng công cụ:\n"
            "- lookup_customer: Tìm khách hàng bằng số điện thoại hoặc tên. Dùng khi khách cung cấp thông tin cá nhân.\n"
            "- get_order_status: Tra cứu trạng thái đơn hàng. Dùng khi khách hỏi về đơn hàng.\n"
            "- create_support_ticket: Tạo phiếu hỗ trợ cho vấn đề cần xử lý thủ công.\n"
            "- handoff_request: Yêu cầu chuyển cuộc trò chuyện cho nhân viên người. Chỉ dùng khi khách yêu cầu rõ ràng.\n\n"
            "Quy tắc:\n"
            "- Chỉ gọi tối đa 2 công cụ mỗi lần phản hồi\n"
            "- Tổng số bước gọi LLM không quá 3 lần\n"
            "- Nếu công cụ trả lỗi, thông báo cho khách và đề xuất hướng khắc phục\n"
        )
