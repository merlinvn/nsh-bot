"""FastAPI dependencies for database, Redis, RabbitMQ, and auth."""
import redis.asyncio as redis
from fastapi import Header, HTTPException, status

from app.api.config import api_settings
from app.core.database import get_async_session
from app.core.rabbitmq import get_rabbitmq_channel
from app.core.redis import get_redis_client

# Database session dependency
get_db = get_async_session


async def get_redis() -> redis.Redis:
    """Redis client dependency."""
    client = await get_redis_client()
    return client


async def get_rabbitmq():
    """RabbitMQ channel dependency."""
    channel = await get_rabbitmq_channel()
    return channel


async def verify_internal_api_key(
    x_internal_api_key: str = Header(..., alias="X-Internal-Api-Key"),
) -> str:
    """Validate the internal API key header."""
    if x_internal_api_key != api_settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_API_KEY",
                "message": "Invalid or missing X-Internal-Api-Key header.",
            },
        )
    return x_internal_api_key
