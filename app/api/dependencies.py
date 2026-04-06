"""FastAPI dependencies for database, Redis, RabbitMQ, and auth."""
import uuid

import redis.asyncio as redis
from fastapi import Depends, Header, HTTPException, Request, status

from app.api.config import api_settings
from app.core.database import get_async_session
from app.core.rabbitmq import get_rabbitmq_channel
from app.core.redis import get_redis_client
from app.core.session import SessionStore

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


async def get_current_admin_user(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> "AdminUser":
    """Validate session cookie and return the current admin user."""
    from app.models.admin_user import AdminUser

    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated."},
        )

    session_store = SessionStore(redis_client)
    session_data = await session_store.get(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_EXPIRED", "message": "Session expired."},
        )

    # Load admin user from DB
    db = await get_async_session()
    async with db:
        user = await db.get(AdminUser, uuid.UUID(session_data["user_id"]))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_INACTIVE", "message": "User inactive or not found."},
            )
        return user
