"""RabbitMQ channel factory and consumer utilities."""
import asyncio
from typing import Any, Callable, Coroutine

import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

"""RabbitMQ channel factory and consumer utilities."""
import asyncio
import json
from typing import Any, Callable, Coroutine

import aio_pika
from aio_pika import IncomingMessage, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

from app.core.config import settings
from app.workers.shared.logging import get_logger

logger = get_logger("queue")

_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None


async def get_connection() -> AbstractConnection:
    """Get or create the shared RabbitMQ connection."""
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    return _connection


async def get_channel() -> AbstractChannel:
    """Get or create the shared RabbitMQ channel."""
    global _channel
    if _channel is None or _channel.is_closed:
        conn = await get_connection()
        _channel = await conn.channel()
    return _channel


async def get_queue(name: str, prefetch: int = 5) -> AbstractQueue:
    """Declare and return a queue, setting prefetch on the channel."""
    channel = await get_channel()
    await channel.set_qos(prefetch_count=prefetch)
    queue = await channel.declare_queue(name, durable=True)
    return queue


async def publish_to_queue(
    routing_key: str,
    message: dict[str, Any],
    headers: dict[str, Any] | None = None,
) -> None:
    """Publish a message to a RabbitMQ queue."""
    channel = await get_channel()
    body = Message(
        body=json.dumps(message, default=str).encode(),
        headers=headers or {},
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    await channel.default_exchange.publish(body, routing_key=routing_key)


async def consume_queue(
    queue_name: str,
    callback: Callable[[IncomingMessage], Coroutine[Any, Any, None]],
    prefetch: int = 5,
    auto_ack: bool = False,
) -> None:
    """Start consuming messages from a queue."""
    queue = await get_queue(queue_name, prefetch=prefetch)
    await queue.consume(callback, no_ack=auto_ack)
    logger.info("Started consuming queue", extra={"queue": queue_name})


async def close_connection() -> None:
    """Close the shared RabbitMQ connection."""
    global _connection, _channel
    if _channel and not _channel.is_closed:
        await _channel.close()
        _channel = None
    if _connection and not _connection.is_closed:
        await _connection.close()
        _connection = None
