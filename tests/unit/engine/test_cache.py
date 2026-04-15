"""Tests for Redis quote cache layer."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.workers.engine.pricing import QuoteInput, QuoteResult
from app.workers.engine.cache import build_cache_key, get_cached_quote, set_cached_quote


class TestBuildCacheKey:
    def test_same_inputs_same_key(self):
        input1 = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
        )
        input2 = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
        )
        key1 = build_cache_key("nsh", input1)
        key2 = build_cache_key("nsh", input2)
        assert key1 == key2

    def test_different_weight_different_key(self):
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        input2 = QuoteInput(service_type="fast", actual_weight_kg=31, length_cm=20, width_cm=20, height_cm=20)
        key1 = build_cache_key("nsh", input1)
        key2 = build_cache_key("nsh", input2)
        assert key1 != key2

    def test_different_service_different_key(self):
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        input2 = QuoteInput(service_type="standard", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        key1 = build_cache_key("nsh", input1)
        key2 = build_cache_key("nsh", input2)
        assert key1 != key2

    def test_different_tenant_different_key(self):
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        key1 = build_cache_key("nsh", input1)
        key2 = build_cache_key("other", input1)
        assert key1 != key2

    def test_key_format(self):
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        key = build_cache_key("nsh", input1)
        assert key.startswith("quote:nsh:")


class TestGetCachedQuote:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        result = await get_cached_quote(mock_redis, "nsh", input1)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_result(self):
        mock_redis = AsyncMock()
        cached_data = json.dumps({
            "status": "quoted",
            "message_to_customer": "Test message",
            "missing_fields": [],
            "reason": "",
            "quote_data": {"total_vnd": 205500},
        })
        mock_redis.get = AsyncMock(return_value=cached_data)
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        result = await get_cached_quote(mock_redis, "nsh", input1)
        assert result is not None
        assert result.status == "quoted"
        assert result.quote_data["total_vnd"] == 205500

    @pytest.mark.asyncio
    async def test_redis_error_returns_none_fail_open(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        result = await get_cached_quote(mock_redis, "nsh", input1)
        assert result is None


class TestSetCachedQuote:
    @pytest.mark.asyncio
    async def test_sets_with_ttl(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        result = QuoteResult(status="quoted", message_to_customer="Test", quote_data={"total_vnd": 1000})
        await set_cached_quote(mock_redis, "nsh", input1, result, ttl_seconds=300)
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 300  # TTL

    @pytest.mark.asyncio
    async def test_redis_error_silently_ignored(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))
        input1 = QuoteInput(service_type="fast", actual_weight_kg=30, length_cm=20, width_cm=20, height_cm=20)
        result = QuoteResult(status="quoted", message_to_customer="Test", quote_data={"total_vnd": 1000})
        # Should not raise
        await set_cached_quote(mock_redis, "nsh", input1, result)
