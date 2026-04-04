"""Tests for prompt loading and caching."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.conversation.prompts import (
    CACHE_TTL_SECONDS,
    PromptCache,
    PromptManager,
)


class MockPrompt:
    """Mock Prompt model for DB results."""

    def __init__(self, name, template, active_version, versions=None):
        self.name = name
        self.template = template
        self.active_version = active_version
        self.versions = versions


def make_db_result(prompt):
    """Build a mock result object with scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=prompt)
    return result


async def make_mock_db_session(*prompts):
    """Build a mock DB session that returns prompts in order on execute calls."""
    mock_db = AsyncMock()
    results = [make_db_result(p) for p in prompts]
    results_iter = iter(results)

    async def fake_execute(query):
        try:
            return next(results_iter)
        except StopIteration:
            return make_db_result(None)

    mock_db.execute = fake_execute
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)
    return mock_db


@pytest.mark.asyncio
async def test_load_prompt_from_db():
    """Mock DB to return prompt record."""
    mock_system = MockPrompt(
        name="system",
        template="Bạn là nhân viên CSKH.",
        active_version="v1",
        versions=[{"version": "v1", "template": "Bạn là nhân viên CSKH."}],
    )
    mock_tool_policy = MockPrompt(
        name="tool_policy",
        template="Sử dụng lookup_customer khi cần.",
        active_version="v1",
    )
    mock_fallback = MockPrompt(
        name="fallback",
        template="Xin lỗi, hệ thống đang bận.",
        active_version="v1",
    )

    mock_db = await make_mock_db_session(mock_system, mock_tool_policy, mock_fallback)

    with patch("app.workers.conversation.prompts.db_session", return_value=mock_db):
        manager = PromptManager()
        await manager._load_from_db()

        assert manager._cache._system_prompt == "Bạn là nhân viên CSKH."
        assert manager._cache._system_version == "v1"
        assert manager._cache._tool_policy_prompt == "Sử dụng lookup_customer khi cần."
        assert manager._cache._fallback_prompt == "Xin lỗi, hệ thống đang bận."


@pytest.mark.asyncio
async def test_cache_refreshes_after_ttl():
    """Load prompt, wait past TTL, load again — verify DB queried twice."""
    call_count = 0

    async def counting_execute(query):
        nonlocal call_count
        call_count += 1
        prompt = MockPrompt("system", f"Loaded call #{call_count}", "v1")
        return make_db_result(prompt)

    mock_db = AsyncMock()
    mock_db.execute = counting_execute
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.workers.conversation.prompts.db_session", return_value=mock_db):
        manager = PromptManager()

        # First load — _load_from_db calls execute 3 times (system, tool_policy, fallback)
        await manager._load_from_db()
        assert call_count == 3
        # First execute call is for system prompt, so it gets "Loaded call #1"
        assert manager._cache._system_prompt == "Loaded call #1"

        # Advance time past TTL
        manager._cache._last_refresh = time.time() - (CACHE_TTL_SECONDS + 1)

        # Second load — should hit DB again
        await manager._load_from_db()
        assert call_count == 6  # 3 more calls
        # First call in second batch is for system prompt
        assert manager._cache._system_prompt == "Loaded call #4"


@pytest.mark.asyncio
async def test_fallback_prompt_if_db_unavailable():
    """Mock DB to raise error — verify default Vietnamese prompt used."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=Exception("Database connection failed"))
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.workers.conversation.prompts.db_session", return_value=mock_db),
        patch("app.workers.conversation.prompts.get_logger") as mock_get_logger,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        manager = PromptManager()
        await manager._refresh()

        # Should fall back to default system prompt (in Vietnamese)
        assert "CSKH" in manager._cache._system_prompt
        assert manager._cache._tool_policy_prompt is not None
        assert "lookup_customer" in manager._cache._tool_policy_prompt


def test_prompt_cache_is_expired():
    """Test cache expiration logic."""
    cache = PromptCache()
    cache._last_refresh = time.time() - (CACHE_TTL_SECONDS + 1)
    assert cache._is_expired() is True


def test_prompt_cache_not_expired():
    """Test cache not expired within TTL."""
    cache = PromptCache()
    cache._last_refresh = time.time()
    assert cache._is_expired() is False


def test_prompt_manager_get_active_version_unknown():
    """Test get_active_version returns 'unknown' when no cache."""
    manager = PromptManager()
    assert manager.get_active_version() == "unknown"


@pytest.mark.asyncio
async def test_prompt_manager_fallback_returns_vietnamese_text():
    """Test fallback prompt is Vietnamese text."""
    manager = PromptManager()
    fallback = manager.get_fallback_prompt()
    assert "Xin lỗi" in fallback
    assert "hệ thống" in fallback
    # Clean up background refresh tasks created during the test
    for task in asyncio.all_tasks():
        if task.get_name() and "refresh" in task.get_name():
            task.cancel()


def test_cache_ttl_is_300_seconds():
    """Verify cache TTL is 5 minutes (300 seconds)."""
    assert CACHE_TTL_SECONDS == 300
