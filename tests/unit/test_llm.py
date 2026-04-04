"""Tests for the Anthropic LLM client wrapper."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.conversation.llm import AnthropicLLM, LLMResponse, ToolCallResult


@pytest.mark.asyncio
async def test_llm_returns_text_only():
    """Mock Anthropic messages.create to return text response."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_response = MagicMock()
    mock_response.content = [MockBlock("text", text="Chào bạn, tôi có thể giúp gì?")]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 25

    with patch("app.workers.conversation.llm.anthropic.AsyncAnthropic") as MockAnthropic:
        mock_client_instance = AsyncMock()
        MockAnthropic.return_value = mock_client_instance
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)

        llm = AnthropicLLM(api_key="test-key", model="claude-sonnet-4-20250514")
        result = await llm.complete(
            system_prompt="Bạn là CSKH",
            messages=[{"role": "user", "content": "Xin chào"}],
            tools=[],
        )

        assert result.text == "Chào bạn, tôi có thể giúp gì?"
        assert result.tool_calls == []
        assert result.token_usage == {"input_tokens": 50, "output_tokens": 25}
        mock_client_instance.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_llm_returns_tool_call():
    """Mock Anthropic to return content_block with input_json."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_response = MagicMock()
    mock_response.content = [
        MockBlock(
            "tool_use",
            id="tc_abc123",
            name="lookup_customer",
            input={"query": "0912345678"},
        )
    ]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 80
    mock_response.usage.output_tokens = 40

    with patch("app.workers.conversation.llm.anthropic.AsyncAnthropic") as MockAnthropic:
        mock_client_instance = AsyncMock()
        MockAnthropic.return_value = mock_client_instance
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)

        llm = AnthropicLLM(api_key="test-key", model="claude-sonnet-4-20250514")
        result = await llm.complete(
            system_prompt="Bạn là CSKH",
            messages=[{"role": "user", "content": "Tra cứu khách hàng"}],
            tools=[],
        )

        assert result.text == ""
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "lookup_customer"
        assert result.tool_calls[0].input == {"query": "0912345678"}
        assert result.tool_calls[0].id == "tc_abc123"


@pytest.mark.asyncio
async def test_llm_timeout_enforced():
    """Mock Anthropic to sleep longer than 15s then timeout."""
    async def slow_create(*args, **kwargs):
        await asyncio.sleep(20)  # Exceeds 15s timeout
        return MagicMock(content=[], usage=None)

    mock_logger = MagicMock()

    with (
        patch("app.workers.conversation.llm.anthropic.AsyncAnthropic") as MockAnthropic,
        patch("app.workers.conversation.llm.logger", mock_logger),
    ):
        mock_client_instance = AsyncMock()
        MockAnthropic.return_value = mock_client_instance
        mock_client_instance.messages.create = slow_create

        llm = AnthropicLLM(api_key="test-key", model="claude-sonnet-4-20250514", timeout=15)

        with pytest.raises(TimeoutError, match="timed out"):
            await llm.complete(
                system_prompt="Bạn là CSKH",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )


@pytest.mark.asyncio
async def test_llm_max_tokens_respected():
    """Verify messages.create called with max_tokens=1024."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_response = MagicMock()
    mock_response.content = [MockBlock("text", text="Response text")]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    with patch("app.workers.conversation.llm.anthropic.AsyncAnthropic") as MockAnthropic:
        mock_client_instance = AsyncMock()
        MockAnthropic.return_value = mock_client_instance
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)

        llm = AnthropicLLM(api_key="test-key", model="claude-sonnet-4-20250514")
        await llm.complete(
            system_prompt="Bạn là CSKH",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
        )

        call_kwargs = mock_client_instance.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
