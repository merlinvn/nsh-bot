"""RabbitMQ consumer for the outbound.send queue."""
import asyncio
import json

import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

from app.core.config import get_settings
from app.workers.outbound.processor import process_outbound
from app.workers.outbound.zalo_client import RetryableError
from app.workers.shared.logging import get_logger

settings = get_settings()
logger = get_logger("consumer")

OUTBOUND_QUEUE = "outbound.send"
OUTBOUND_PREFETCH = 5

_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None
_queue: AbstractQueue | None = None
_shutdown = False


async def setup_consumer() -> AbstractQueue:
    """Create connection, channel, and declare queue with prefetch."""
    global _connection, _channel, _queue
    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch=OUTBOUND_PREFETCH)
    _queue = await _channel.declare_queue(OUTBOUND_QUEUE, durable=True)
    return _queue


async def handle_message(message: IncomingMessage) -> None:
    """Process a single message from the outbound.send queue."""
    global _shutdown

    if _shutdown:
        await message.nack(requeue=True)
        return

    correlation_id = message.headers.get("correlation_id") if message.headers else None
    delivery_tag = message.delivery.tag

    logger.info(
        "Received outbound message",
        extra={
            "correlation_id": correlation_id,
            "delivery_tag": delivery_tag,
        },
    )

    try:
        payload = json.loads(message.body.decode())
        await process_outbound(payload)
        await message.ack()
        logger.info(
            "Message acknowledged",
            extra={"correlation_id": correlation_id, "delivery_tag": delivery_tag},
        )

    except RetryableError:
        # Max retries exhausted internally — ack and let DLX handle it
        logger.warning(
            "Max retries exhausted, sending to DLQ",
            extra={"correlation_id": correlation_id, "delivery_tag": delivery_tag},
        )
        await message.ack()

    except json.JSONDecodeError as e:
        logger.error(
            "Invalid JSON in message, dropping",
            extra={"correlation_id": correlation_id, "error": str(e)},
        )
        # Don't requeue malformed messages
        await message.ack()

    except Exception as e:
        logger.error(
            "Unexpected error processing message",
            extra={"correlation_id": correlation_id, "error": str(e)},
        )
        # Requeue transient errors
        await message.nack(requeue=True)


async def run_consumer() -> None:
    """Start the outbound message consumer."""
    global _shutdown

    queue = await setup_consumer()
    logger.info(
        "Outbound consumer started",
        extra={"queue": OUTBOUND_QUEUE, "prefetch": OUTBOUND_PREFETCH},
    )

    await queue.consume(handle_message, no_ack=False)

    # Keep running until shutdown
    while not _shutdown:
        await asyncio.sleep(1.0)


async def shutdown_consumer() -> None:
    """Gracefully close the RabbitMQ connection."""
    global _connection, _channel
    if _channel and not _channel.is_closed:
        await _channel.close()
    if _connection and not _connection.is_closed:
        await _connection.close()
    logger.info("Outbound consumer shut down")
