"""Redis-based message deduplication service."""
import redis.asyncio as redis


async def check_and_set_message_id(
    redis_client: redis.Redis,
    message_id: str,
    ttl: int = 86400,
) -> bool:
    """Check if a message_id has been seen before, and if not, mark it as seen.

    This uses Redis SET with NX (only set if not exists) and an expiration TTL.

    Args:
        redis_client: An async Redis client.
        message_id: The Zalo message_id to check.
        ttl: Time-to-live in seconds (default 24h = 86400).

    Returns:
        True if the message_id is new (not a duplicate).
        False if the message_id already exists (duplicate).
    """
    key = f"zalo:dedup:{message_id}"
    # SET key value NX EX ttl
    # Returns True if the key was set (new), None if it already existed
    result = await redis_client.set(key, "1", nx=True, ex=ttl)
    return result is not None


async def check_and_set_ack_sent(
    redis_client: redis.Redis,
    message_id: str,
    ttl: int = 86400,
) -> bool:
    """Check if an ACK has already been sent for this message_id.

    Uses Redis SET with NX to ensure only one ACK is ever sent per message_id.
    This prevents ACK flooding when webhooks are called multiple times or
    when queues republish messages.

    Args:
        redis_client: An async Redis client.
        message_id: The Zalo message_id to check.
        ttl: Time-to-live in seconds (default 24h = 86400).

    Returns:
        True if ACK was sent (key was set — this is the first time).
        False if ACK was already sent previously (duplicate).
    """
    key = f"zalo:ack:{message_id}"
    result = await redis_client.set(key, "1", nx=True, ex=ttl)
    return result is not None
