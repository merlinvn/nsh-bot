"""RabbitMQ message publishing service."""
import json
from typing import Any

from aio_pika import Message
from aio_pika.abc import AbstractChannel

from app.core.rabbitmq import (
    CONVERSATION_PROCESS_QUEUE,
    CONVERSATION_PROCESS_RK,
    DIRECT_EXCHANGE,
)


async def publish_to_queue(
    channel: AbstractChannel,
    queue_name: str,
    message: dict[str, Any],
) -> None:
    """Publish a message to the named RabbitMQ queue via the direct exchange.

    Args:
        channel: An active RabbitMQ channel.
        queue_name: The queue name (used as routing key).
        message: The message body as a dictionary.

    Raises:
        aio_pika.exceptions.AMQPError: If publishing fails.
    """
    exchange = await channel.get_exchange(DIRECT_EXCHANGE)

    rabbitmq_message = Message(
        body=json.dumps(message).encode("utf-8"),
        content_type="application/json",
        delivery_mode=2,  # Persistent
    )

    await exchange.publish(rabbitmq_message, routing_key=queue_name)


async def publish_conversation_process(
    channel: AbstractChannel,
    message: dict[str, Any],
) -> None:
    """Publish a message to the conversation.process queue.

    Args:
        channel: An active RabbitMQ channel.
        message: The conversation processing payload.
    """
    await publish_to_queue(channel, CONVERSATION_PROCESS_RK, message)
