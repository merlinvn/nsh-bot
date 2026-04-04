"""RabbitMQ consumer for the conversation.process queue."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.workers.conversation.processor import ConversationProcessor
from app.workers.shared.logging import get_logger

logger = get_logger("conversation-worker.consumer")

QUEUE_NAME = "conversation.process"
QUEUE_ROUTING_KEY = "conversation.process"
QUEUE_PREFETCH = 1


class ConversationConsumer:
    def __init__(self) -> None:
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._queue: Optional[AbstractQueue] = None
        self._processor = ConversationProcessor()
        self._running = False

    async def run(self) -> None:
        """Connect to RabbitMQ and start consuming messages."""
        self._running = True
        self._connection = await aio_pika.connect_robust(
            self._get_rabbitmq_url(),
            timeout=10.0,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=QUEUE_PREFETCH)

        # Declare queue (should already exist from API setup, but idempotent)
        self._queue = await self._channel.declare_queue(
            QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "neochat.dlx",
                "x-dead-letter-routing-key": "dead-letter",
                "x-message-ttl": 300000,
                "x-max-length": 10000,
            },
        )

        logger.info("consumer_started", queue=QUEUE_NAME, prefetch=QUEUE_PREFETCH)

        await self._queue.consume(self._on_message)

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    def _get_rabbitmq_url(self) -> str:
        from app.core.config import settings
        return settings.rabbitmq_url

    async def _on_message(self, message: IncomingMessage) -> None:
        """Process a single message from the queue."""
        correlation_id = message.headers.get("correlation_id", "unknown") if message.headers else "unknown"

        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body.decode())
                logger.info(
                    "message_received",
                    correlation_id=correlation_id,
                    queue=QUEUE_NAME,
                )

                await self._processor.process(payload, correlation_id)

                logger.info(
                    "ack_sent",
                    correlation_id=correlation_id,
                )

            except json.JSONDecodeError as e:
                logger.error(
                    "message_parse_error",
                    correlation_id=correlation_id,
                    error=str(e),
                    error_type="JSONDecodeError",
                )
                # Permanent error: ack to send to DLQ
                logger.info("ack_sent_dlq", correlation_id=correlation_id)

            except Exception as e:
                error_type = type(e).__name__
                is_transient = _is_transient_error(e)

                logger.error(
                    "message_processing_error",
                    correlation_id=correlation_id,
                    error=str(e),
                    error_type=error_type,
                    transient=is_transient,
                )

                if is_transient:
                    # Requeue for transient errors
                    await message.nack(requeue=True)
                    logger.info("nack_sent_requeue", correlation_id=correlation_id)
                else:
                    # Permanent error: ack (will go to DLQ)
                    logger.info("ack_sent_dlq", correlation_id=correlation_id)

    async def close(self) -> None:
        """Close connections gracefully."""
        self._running = False
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("consumer_closed")


def _is_transient_error(error: Exception) -> bool:
    """Classify errors as transient or permanent.

    Transient errors should be retried (nack + requeue).
    Permanent errors should go to DLQ (ack).
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Network/timeout errors are transient
    if isinstance(error, (asyncio.TimeoutError, OSError, ConnectionError)):
        return True

    # LLM errors
    if "timeout" in error_str or "timed out" in error_str:
        return True
    if "rate limit" in error_str or "429" in error_str:
        return True
    if "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str:
        return True

    # DB errors are transient
    if error_type in ("DBAPIError", "OperationalError", "InterfaceError"):
        return True

    # Bad request / auth errors are permanent
    if "400" in error_str or "401" in error_str or "403" in error_str or "invalid" in error_str:
        return False

    # Unknown errors: default to transient for safety
    return True
