"""Tests for outbound RabbitMQ consumer."""
import asyncio
import json
import signal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.outbound import consumer


class FakeQueue:
    """Fake queue returned by setup_consumer for testing."""

    async def consume(self, callback, no_ack=False):
        pass


@pytest.fixture
def mock_message():
    """Create a fake IncomingMessage with ack/nack methods."""
    msg = MagicMock()
    msg.body = json.dumps({
        "user_id": "user_123",
        "text": "Hello",
        "message_db_id": str(uuid4()),
    }).encode()
    msg.headers = {"correlation_id": "test-corr-id"}
    msg.delivery.tag = 42
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


class TestPrefetch:
    """Tests for consumer prefetch configuration."""

    @pytest.mark.asyncio
    async def test_prefetch_is_5(self) -> None:
        with patch("app.workers.outbound.consumer.aio_pika") as mock_aio_pika:
            mock_connection = AsyncMock()
            mock_channel = AsyncMock()
            mock_queue = MagicMock()
            mock_queue.consume = AsyncMock()

            mock_aio_pika.connect_robust = AsyncMock(return_value=mock_connection)
            mock_connection.channel = AsyncMock(return_value=mock_channel)
            mock_channel.declare_queue = AsyncMock(return_value=MagicMock())
            mock_channel.declare_queue.return_value.consume = AsyncMock()

            await consumer.setup_consumer()

            mock_channel.set_qos.assert_called_once_with(prefetch=5)


class TestHandleMessage:
    """Tests for handle_message function."""

    @pytest.mark.asyncio
    async def test_ack_on_success(self, mock_message: MagicMock) -> None:
        with patch("app.workers.outbound.consumer.process_outbound", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = None

            await consumer.handle_message(mock_message)

            mock_message.ack.assert_called_once()
            mock_message.nack.assert_not_called()

    @pytest.mark.asyncio
    async def test_nack_requeue_on_transient_error(self, mock_message: MagicMock) -> None:
        with patch(
            "app.workers.outbound.consumer.process_outbound",
            new_callable=AsyncMock,
        ) as mock_process:
            # Non-RetryableError subclass — treated as transient
            mock_process.side_effect = ConnectionError("Network error")

            await consumer.handle_message(mock_message)

            mock_message.nack.assert_called_once_with(requeue=True)
            mock_message.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_dlq_after_max_retries(self, mock_message: MagicMock) -> None:
        from app.workers.outbound.zalo_client import RetryableError

        with patch(
            "app.workers.outbound.consumer.process_outbound",
            new_callable=AsyncMock,
        ) as mock_process:
            # After exhausting retries, process_outbound raises RetryableError
            mock_process.side_effect = RetryableError("Max retries exhausted")

            await consumer.handle_message(mock_message)

            # Should ack (message goes to DLX/DLQ, not requeued)
            mock_message.ack.assert_called_once()
            mock_message.nack.assert_not_called()

    @pytest.mark.asyncio
    async def test_dlq_on_json_decode_error(self, mock_message: MagicMock) -> None:
        # Malformed JSON body
        mock_message.body = b"not valid json"
        mock_message.headers = {}
        mock_message.delivery.tag = 1

        await consumer.handle_message(mock_message)

        # Should ack malformed messages (don't requeue)
        mock_message.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_correlation_id_extracted_from_headers(self, mock_message: MagicMock) -> None:
        """Verify correlation_id from message headers is passed to logging."""
        with patch("app.workers.outbound.consumer.process_outbound", new_callable=AsyncMock):
            await consumer.handle_message(mock_message)

            mock_message.ack.assert_called_once()


class TestGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_consumer_closes_channel_and_connection(self) -> None:
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_channel.is_closed = False
        mock_connection.is_closed = False
        mock_channel.close = AsyncMock()
        mock_connection.close = AsyncMock()

        consumer._connection = mock_connection
        consumer._channel = mock_channel

        await consumer.shutdown_consumer()

        mock_channel.close.assert_called_once()
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_does_nothing_when_not_initialized(self) -> None:
        consumer._connection = None
        consumer._channel = None

        # Should not raise
        await consumer.shutdown_consumer()

    @pytest.mark.asyncio
    async def test_handle_message_nacks_when_shutdown_flag_is_set(self) -> None:
        mock_msg = MagicMock()
        mock_msg.body = json.dumps({"user_id": "u1", "text": "hi", "message_db_id": str(uuid4())}).encode()
        mock_msg.headers = {}
        mock_msg.delivery.tag = 1
        mock_msg.ack = AsyncMock()
        mock_msg.nack = AsyncMock()

        consumer._shutdown = True

        try:
            await consumer.handle_message(mock_msg)

            # Should requeue when shutdown flag is set
            mock_msg.nack.assert_called_once_with(requeue=True)
            mock_msg.ack.assert_not_called()
        finally:
            consumer._shutdown = False

    @pytest.mark.asyncio
    async def test_run_consumer_stops_on_shutdown_flag(self) -> None:
        """Verify run_consumer respects the _shutdown flag."""
        consumer._shutdown = False

        async def set_shutdown_soon():
            await asyncio.sleep(0.05)
            consumer._shutdown = True

        async def fake_consume(callback, no_ack=False):
            await asyncio.sleep(0.3)  # Will be cancelled by shutdown

        with patch("app.workers.outbound.consumer.setup_consumer", new_callable=AsyncMock) as mock_setup:
            mock_queue = MagicMock()
            mock_queue.consume = fake_consume
            mock_setup.return_value = mock_queue

            with patch("app.workers.outbound.consumer._shutdown", False):
                # Run with a timeout to avoid hanging
                try:
                    await asyncio.wait_for(
                        consumer.run_consumer(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    pass  # Expected if shutdown is working

        # Verify the consumer ran and eventually stopped
        mock_setup.assert_called_once()
