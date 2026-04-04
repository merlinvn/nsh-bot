"""Redis client factory."""
import redis.asyncio as redis

from app.core.config import settings

_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """Return a shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def check_redis_health() -> bool:
    """Return True if Redis is reachable."""
    try:
        client = await get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False
