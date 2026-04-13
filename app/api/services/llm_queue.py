"""LLM queue service — publish requests to llm.process and wait for Redis responses."""
import asyncio
import json
import uuid
from typing import Any

from app.core.redis import get_redis_client
from app.core.rabbitmq import LLM_PROCESS_RK, publish_message


async def enqueue_llm_request(
    payload: dict[str, Any],
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Publish an LLM request to llm.process queue and wait for the response.

    Args:
        payload: LLM request payload (must include 'channel' field)
        timeout: Maximum seconds to wait for response

    Returns:
        The LLM response dict from the worker
    """
    request_id = str(uuid.uuid4())
    redis_client = await get_redis_client()

    # Add request_id to payload
    full_payload = {**payload, "request_id": request_id}

    # Publish to llm.process queue
    await publish_message(
        routing_key=LLM_PROCESS_RK,
        body=full_payload,
        headers={"correlation_id": request_id},
    )

    # Wait for Redis response
    response_channel = f"llm:response:{request_id}"
    try:
        msg = await asyncio.wait_for(
            _wait_for_redis_response(redis_client, response_channel),
            timeout=timeout,
        )
        return json.loads(msg)
    except asyncio.TimeoutError:
        raise TimeoutError(f"LLM request timed out after {timeout}s (request_id={request_id})")


async def _wait_for_redis_response(redis_client, channel: str):
    """Wait for a message on a Redis pub/sub channel (skips subscribe confirmation)."""
    future: asyncio.Future = asyncio.get_running_loop().create_future()

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async def listen():
            async for msg in pubsub.listen():
                # Skip subscribe/unsubscribe confirmation messages
                if msg["type"] not in ("message", "pmessage"):
                    continue
                if not future.done():
                    future.set_result(msg["data"])
                break

        listen_task = asyncio.create_task(listen())
        try:
            result = await future
            return result
        finally:
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
