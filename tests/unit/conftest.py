"""Pytest configuration for unit tests - no external dependencies."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def pytest_configure(config):
    """Configure logging to handle structlog-style calls before tests run."""
    # Override the Logger._log method to accept extra kwargs
    _original_log = logging.Logger._log

    def patched_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1, **kwargs):
        return _original_log(self, level, msg, args, exc_info=exc_info, extra=extra,
                           stack_info=stack_info, stacklevel=stacklevel)

    logging.Logger._log = patched_log


@pytest.fixture
def mock_db_session():
    """Provide a mock async database session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        yield session
    return _session


@pytest.fixture
def mock_queue_publisher():
    """Provide a mock RabbitMQ queue publisher."""
    publish_calls = []

    async def _publish(*args, **kwargs):
        publish_calls.append({"args": args, "kwargs": kwargs})

    mock_channel = AsyncMock()
    mock_channel.declare_exchange = AsyncMock()
    mock_exchange = AsyncMock()
    mock_exchange.publish = _publish
    mock_channel.declare_exchange.return_value = mock_exchange

    return mock_channel, mock_exchange, publish_calls


@pytest.fixture
def mock_llm_text_response():
    """Return a mock LLM response with text only."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockResponse:
        def __init__(self, text="Xin chào, tôi có thể giúp gì cho bạn?"):
            self.content = [MockBlock("text", text=text)]
            self.usage = MagicMock()
            self.usage.input_tokens = 100
            self.usage.output_tokens = 50

    return MockResponse


@pytest.fixture
def mock_llm_tool_call_response():
    """Return a mock LLM response with a tool call."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockResponse:
        def __init__(self, tool_name="lookup_customer", tool_input=None, text=""):
            self.content = []
            if text:
                self.content.append(MockBlock("text", text=text))
            self.content.append(
                MockBlock(
                    "tool_use",
                    id="tc_123",
                    name=tool_name,
                    input=tool_input or {},
                )
            )
            self.usage = MagicMock()
            self.usage.input_tokens = 100
            self.usage.output_tokens = 50

    return MockResponse
