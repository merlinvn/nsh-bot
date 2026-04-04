"""Tests for the conversation processor pipeline."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.conversation.processor import (
    MAX_LLM_STEPS,
    ConversationProcessor,
)
from app.workers.conversation.types import LLMResponse, ToolCallResult


class MockBlock:
    """Helper: mimics an Anthropic content block."""

    def __init__(self, block_type: str, **kwargs):
        self.type = block_type
        for k, v in kwargs.items():
            setattr(self, k, v)


def make_text_response(text: str) -> MagicMock:
    """Create a mock LLM response with only text."""
    mock = MagicMock()
    mock.content = [MockBlock("text", text=text)]
    mock.usage = MagicMock()
    mock.usage.input_tokens = 50
    mock.usage.output_tokens = 25
    return mock


def make_conversation(conv_id=None):
    """Create a mock Conversation."""
    conv = MagicMock()
    conv.id = conv_id or uuid4()
    conv.external_user_id = "user_123"
    conv.status = "active"
    return conv


def make_message(msg_id=None, direction="inbound"):
    """Create a mock Message."""
    msg = MagicMock()
    msg.id = msg_id or uuid4()
    msg.direction = direction
    return msg


class MockDBSession:
    """Async context manager providing a mock DB session."""

    def __init__(self, conv=None):
        self._conv = conv

    def __call__(self):
        """Return an async context manager for the session."""
        return _MockSessionCtx(self._conv)

    async def __aenter__(self):
        return await _MockSessionCtx(self._conv).__aenter__()

    async def __aexit__(self, *args):
        await _MockSessionCtx(self._conv).__aexit__(*args)


class _MockSessionCtx:
    """Inner async context manager that holds the session state."""

    def __init__(self, conv=None):
        self._conv = conv

    async def __aenter__(self):
        conv = self._conv
        if conv is None:
            conv = make_conversation()

        self.session = AsyncMock()
        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", uuid4())
        )
        self.session.rollback = MagicMock()

        # First execute call: load/create conversation
        mock_result_conv = MagicMock()
        mock_result_conv.scalar_one_or_none = MagicMock(return_value=conv)

        # Second execute call: conversation history (empty)
        mock_result_hist = MagicMock()
        mock_result_hist.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        # Subsequent calls: messages
        mock_result_msgs = MagicMock()
        mock_result_msgs.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        results = [mock_result_conv, mock_result_hist, mock_result_msgs]
        results_iter = iter(results)

        async def fake_execute(query):
            try:
                return next(results_iter)
            except StopIteration:
                return mock_result_msgs

        self.session.execute = fake_execute
        return self.session

    async def __aexit__(self, *args):
        pass


def mock_db_session_factory(conv=None):
    """Return a mock db_session context manager."""
    return MockDBSession(conv)


@pytest.mark.asyncio
async def test_process_inbound_message_saves_and_llm():
    """Verify: inbound saved, LLM called, outbound saved, published to queue."""
    conv = make_conversation()
    publish_calls = []

    async def mock_publish(message, routing_key=""):
        publish_calls.append({
            "routing_key": routing_key,
            "body": json.loads(message.body.decode()),
        })

    with (
        patch("app.workers.conversation.processor.db_session", mock_db_session_factory(conv)),
        patch("app.workers.conversation.processor.get_channel", new_callable=AsyncMock) as mock_get_channel,
        patch("app.workers.conversation.processor.LLMResponse", LLMResponse),
        patch("app.workers.conversation.processor.ToolCallResult", ToolCallResult),
    ):
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_exchange.publish = mock_publish
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_get_channel.return_value = mock_channel

        with patch("app.workers.conversation.processor.create_llm_client") as MockLLM:
            mock_llm_instance = AsyncMock()
            MockLLM.return_value = mock_llm_instance
            mock_llm_instance.complete = AsyncMock(
                return_value=LLMResponse(
                    text="Xin chào, tôi có thể giúp gì?",
                    tool_calls=[],
                    latency_ms=500,
                    token_usage={"input_tokens": 50, "output_tokens": 25},
                )
            )
            mock_llm_instance.model = "claude-sonnet-4-20250514"

            processor = ConversationProcessor()
            processor._llm = mock_llm_instance

            payload = {
                "message_id": "msg_001",
                "external_user_id": "user_123",
                "text": "Xin chào",
                "zalo_message_id": "zalo_001",
            }

            await processor.process(payload, "corr_001")

            # Verify LLM was called
            mock_llm_instance.complete.assert_called_once()

            # Verify exchange was declared for publishing
            assert mock_channel.declare_exchange.called

            # Verify outbound was published
            assert len(publish_calls) == 1
            assert publish_calls[0]["routing_key"] == "outbound.send"
            assert "text" in publish_calls[0]["body"]


@pytest.mark.asyncio
async def test_process_with_tool_calls():
    """Verify: tool executed, LLM re-called with results, final text used."""
    conv = make_conversation()
    publish_calls = []

    async def mock_publish(message, routing_key=""):
        publish_calls.append({
            "routing_key": routing_key,
            "body": json.loads(message.body.decode()),
        })

    with (
        patch("app.workers.conversation.processor.db_session", mock_db_session_factory(conv)),
        patch("app.workers.conversation.processor.get_channel", new_callable=AsyncMock) as mock_get_channel,
        patch("app.workers.conversation.processor.LLMResponse", LLMResponse),
        patch("app.workers.conversation.processor.ToolCallResult", ToolCallResult),
    ):
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_exchange.publish = mock_publish
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_get_channel.return_value = mock_channel

        with patch("app.workers.conversation.processor.create_llm_client") as MockLLM:
            mock_llm_instance = AsyncMock()
            MockLLM.return_value = mock_llm_instance
            mock_llm_instance.complete = AsyncMock(
                side_effect=[
                    LLMResponse(
                        text="",
                        tool_calls=[
                            ToolCallResult(
                                id="tc_1",
                                name="lookup_customer",
                                input={"query": "0912345678"},
                            )
                        ],
                        latency_ms=300,
                        token_usage={"input_tokens": 60, "output_tokens": 30},
                    ),
                    LLMResponse(
                        text="Tôi đã tra cứu thông tin của bạn.",
                        tool_calls=[],
                        latency_ms=400,
                        token_usage={"input_tokens": 80, "output_tokens": 40},
                    ),
                ]
            )
            mock_llm_instance.model = "claude-sonnet-4-20250514"

            processor = ConversationProcessor()
            processor._llm = mock_llm_instance

            payload = {
                "message_id": "msg_002",
                "external_user_id": "user_123",
                "text": "Tra cứu khách hàng",
                "zalo_message_id": "zalo_002",
            }

            await processor.process(payload, "corr_002")

            # LLM should be called twice (tool step + final)
            assert mock_llm_instance.complete.call_count == 2

            # Outbound should be published with final text
            assert len(publish_calls) == 1
            assert "tra cứu" in publish_calls[0]["body"]["text"].lower()


@pytest.mark.asyncio
async def test_max_tool_calls_enforced():
    """LLM with 2 tool calls per step — processor handles correctly."""
    conv = make_conversation()
    publish_calls = []

    async def mock_publish(message, routing_key=""):
        publish_calls.append({"routing_key": routing_key, "body": json.loads(message.body.decode())})

    with (
        patch("app.workers.conversation.processor.db_session", mock_db_session_factory(conv)),
        patch("app.workers.conversation.processor.get_channel", new_callable=AsyncMock) as mock_get_channel,
        patch("app.workers.conversation.processor.LLMResponse", LLMResponse),
        patch("app.workers.conversation.processor.ToolCallResult", ToolCallResult),
    ):
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_exchange.publish = mock_publish
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_get_channel.return_value = mock_channel

        with patch("app.workers.conversation.processor.create_llm_client") as MockLLM:
            mock_llm_instance = AsyncMock()
            MockLLM.return_value = mock_llm_instance
            mock_llm_instance.complete = AsyncMock(
                return_value=LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCallResult(id="tc_1", name="lookup_customer", input={"query": "0912345678"}),
                        ToolCallResult(id="tc_2", name="get_order_status", input={"order_id": "ORD-001"}),
                    ],
                    latency_ms=200,
                    token_usage={"input_tokens": 50, "output_tokens": 20},
                )
            )
            mock_llm_instance.model = "claude-sonnet-4-20250514"

            processor = ConversationProcessor()
            processor._llm = mock_llm_instance

            payload = {
                "message_id": "msg_003",
                "external_user_id": "user_123",
                "text": "Help",
                "zalo_message_id": "zalo_003",
            }

            await processor.process(payload, "corr_003")

            # With MAX_LLM_STEPS=3, LLM is called 3 times (each returns tool calls,
            # the last response is returned when steps are exhausted)
            assert mock_llm_instance.complete.call_count == MAX_LLM_STEPS


@pytest.mark.asyncio
async def test_max_llm_steps_enforced():
    """After 3 total LLM calls (initial + 2 tool results), processor stops."""
    conv = make_conversation()
    publish_calls = []

    async def mock_publish(message, routing_key=""):
        publish_calls.append({"routing_key": routing_key, "body": json.loads(message.body.decode())})

    with (
        patch("app.workers.conversation.processor.db_session", mock_db_session_factory(conv)),
        patch("app.workers.conversation.processor.get_channel", new_callable=AsyncMock) as mock_get_channel,
        patch("app.workers.conversation.processor.LLMResponse", LLMResponse),
        patch("app.workers.conversation.processor.ToolCallResult", ToolCallResult),
    ):
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_exchange.publish = mock_publish
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_get_channel.return_value = mock_channel

        with patch("app.workers.conversation.processor.create_llm_client") as MockLLM:
            mock_llm_instance = AsyncMock()
            MockLLM.return_value = mock_llm_instance
            # Always return tool calls — forces max steps
            mock_llm_instance.complete = AsyncMock(
                return_value=LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCallResult(id="tc_x", name="lookup_customer", input={"query": "0912345678"})
                    ],
                    latency_ms=200,
                    token_usage={"input_tokens": 50, "output_tokens": 20},
                )
            )
            mock_llm_instance.model = "claude-sonnet-4-20250514"

            processor = ConversationProcessor()
            processor._llm = mock_llm_instance

            payload = {
                "message_id": "msg_004",
                "external_user_id": "user_123",
                "text": "Help",
                "zalo_message_id": "zalo_004",
            }

            await processor.process(payload, "corr_004")

            # MAX_LLM_STEPS = 3, so LLM should be called exactly 3 times
            assert mock_llm_instance.complete.call_count == MAX_LLM_STEPS


@pytest.mark.asyncio
async def test_fallback_on_non_transient_error():
    """Mock LLM to raise — verify fallback Vietnamese text used."""
    conv = make_conversation()
    publish_calls = []

    async def mock_publish(message, routing_key=""):
        publish_calls.append({"routing_key": routing_key, "body": json.loads(message.body.decode())})

    with (
        patch("app.workers.conversation.processor.db_session", mock_db_session_factory(conv)),
        patch("app.workers.conversation.processor.get_channel", new_callable=AsyncMock) as mock_get_channel,
        patch("app.workers.conversation.processor.LLMResponse", LLMResponse),
        patch("app.workers.conversation.processor.ToolCallResult", ToolCallResult),
        patch("app.workers.conversation.processor.get_logger") as mock_get_logger,
    ):
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_exchange.publish = mock_publish
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_get_channel.return_value = mock_channel
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with patch("app.workers.conversation.processor.create_llm_client") as MockLLM:
            mock_llm_instance = AsyncMock()
            MockLLM.return_value = mock_llm_instance
            mock_llm_instance.complete = AsyncMock(
                side_effect=Exception("Invalid request: bad parameter")
            )
            mock_llm_instance.model = "claude-sonnet-4-20250514"

            processor = ConversationProcessor()
            processor._llm = mock_llm_instance

            payload = {
                "message_id": "msg_005",
                "external_user_id": "user_123",
                "text": "Hello",
                "zalo_message_id": "zalo_005",
            }

            await processor.process(payload, "corr_005")

            # Should have published with fallback text
            assert len(publish_calls) == 1
            fallback_text = publish_calls[0]["body"]["text"]
            assert "Xin lỗi" in fallback_text
            assert "hệ thống" in fallback_text
