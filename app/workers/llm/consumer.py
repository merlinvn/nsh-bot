"""RabbitMQ consumer for the llm.process queue."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.workers.llm.processor import LLMProcessor
from app.workers.shared.logging import get_logger

logger = get_logger("llm.consumer")

QUEUE_NAME = "llm.process"
QUEUE_ROUTING_KEY = "llm.process"
QUEUE_PREFETCH = 5


class LLMConsumer:
    def __init__(self) -> None:
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._queue: Optional[AbstractQueue] = None
        self._processor = LLMProcessor()
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

        logger.info("llm_consumer_started", extra={"queue": QUEUE_NAME, "prefetch": QUEUE_PREFETCH})
        await self._queue.consume(self._on_message)

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
                    "llm_message_received",
                    extra={"correlation_id": correlation_id, "queue": QUEUE_NAME},
                )
                await self._processor.process(payload)
                logger.info("llm_ack_sent", extra={"correlation_id": correlation_id})

            except json.JSONDecodeError as e:
                logger.error(
                    "llm_message_parse_error",
                    extra={"correlation_id": correlation_id, "error": str(e)},
                )

            except Exception as e:
                logger.exception(
                    "llm_message_processing_error",
                    extra={"correlation_id": correlation_id, "error": str(e)},
                )

    async def close(self) -> None:
        """Close connections gracefully."""
        self._running = False
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("llm_consumer_closed")
