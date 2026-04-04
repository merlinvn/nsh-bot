"""RabbitMQ connection helpers."""
import json
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange

from app.core.config import settings

_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None

DIRECT_EXCHANGE = "neochat.direct"
DLX_EXCHANGE = "neochat.dlx"

CONVERSATION_PROCESS_QUEUE = "conversation.process"
OUTBOUND_SEND_QUEUE = "outbound.send"
DEAD_LETTER_QUEUE = "dead-letter"

CONVERSATION_PROCESS_RK = "conversation.process"
OUTBOUND_SEND_RK = "outbound.send"
DEAD_LETTER_RK = "dead-letter"


async def get_rabbitmq_channel() -> AbstractChannel:
    """Return a shared RabbitMQ channel, creating exchanges/queues if needed."""
    global _connection, _channel
    if _channel is not None:
        return _channel

    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()

    direct_exchange = await _channel.declare_exchange(
        DIRECT_EXCHANGE, ExchangeType.DIRECT, durable=True
    )
    dlx_exchange = await _channel.declare_exchange(
        DLX_EXCHANGE, ExchangeType.DIRECT, durable=True
    )

    # Dead-letter queue
    dlq = await _channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
    await dlq.bind(dlx_exchange, DEAD_LETTER_RK)

    # conversation.process queue
    conv_queue = await _channel.declare_queue(
        CONVERSATION_PROCESS_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_EXCHANGE,
            "x-dead-letter-routing-key": DEAD_LETTER_RK,
            "x-message-ttl": 300000,
            "x-max-length": 10000,
        },
    )
    await conv_queue.bind(direct_exchange, CONVERSATION_PROCESS_RK)

    # outbound.send queue
    outbound_queue = await _channel.declare_queue(
        OUTBOUND_SEND_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_EXCHANGE,
            "x-dead-letter-routing-key": DEAD_LETTER_RK,
            "x-message-ttl": 600000,
            "x-max-length": 50000,
        },
    )
    await outbound_queue.bind(direct_exchange, OUTBOUND_SEND_RK)

    return _channel


async def close_rabbitmq() -> None:
    """Close the RabbitMQ connection."""
    global _connection, _channel
    if _channel is not None:
        await _channel.close()
        _channel = None
    if _connection is not None:
        await _connection.close()
        _connection = None


async def check_rabbitmq_health() -> bool:
    """Return True if RabbitMQ is reachable."""
    try:
        ch = await get_rabbitmq_channel()
        await ch.declare_queue("health_check_tmp", durable=False, auto_delete=True)
        return True
    except Exception:
        return False


async def publish_message(
    routing_key: str,
    body: dict[str, Any],
    headers: dict[str, Any] | None = None,
) -> None:
    """Publish a message to the direct exchange with the given routing key."""
    channel = await get_rabbitmq_channel()
    exchange = await channel.get_exchange(DIRECT_EXCHANGE)

    message = Message(
        body=json.dumps(body).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        headers=headers or {},
    )
    await exchange.publish(message, routing_key=routing_key)
