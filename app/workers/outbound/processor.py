"""Core outbound message processing with retry and backoff."""
import asyncio
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import insert

from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.models.delivery_attempt import DeliveryAttempt
from app.workers.outbound.zalo_client import (
    NonRetryableError,
    RetryableError,
    ZaloClient,
)
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger
from app.workers.shared.zalo_token_manager import get_zalo_token_manager

settings = get_settings()
logger = get_logger("processor")

MAX_RETRIES = 3
BACKOFF_BASE = 2.0


async def save_delivery_attempt(
    message_db_id: str,
    attempt_no: int,
    status: str,
    response: dict | None = None,
    error: str | None = None,
) -> None:
    """Save a delivery attempt record to the database."""
    if not message_db_id:
        logger.debug("Skipping delivery attempt save — no message_db_id")
        return
    async with db_session() as session:
        stmt = insert(DeliveryAttempt).values(
            message_id=UUID(message_db_id),
            attempt_no=attempt_no,
            status=status,
            response=response,
            error=error,
        )
        await session.execute(stmt)
        logger.debug(
            "Saved delivery attempt",
            extra={
                "message_db_id": str(message_db_id),
                "attempt_no": attempt_no,
                "status": status,
            },
        )


async def process_outbound(message: dict) -> None:
    """
    Process an outbound message with retry logic.

    Args:
        message: Dict with keys: external_user_id (str), text (str), message_id (str), outbound_message_id (str), etc.

    Raises:
        RetryableError: If max retries exhausted (caller should send to DLQ)
    """
    user_id: str = message["external_user_id"]
    text: str = message["text"]
    message_id: str = message["message_id"]
    outbound_message_id: str = message.get("outbound_message_id", "")

    logger.info(
        "Processing outbound message",
        extra={"user_id": user_id, "message_id": message_id, "outbound_message_id": outbound_message_id},
    )

    # Idempotency check: prevent double-send if same message_id is processed twice
    redis_client = await get_redis_client()
    sent_key = f"outbound:sent:{message_id}"
    was_sent = await redis_client.set(sent_key, "1", nx=True, ex=86400)
    if was_sent is None:
        logger.info("Outbound already processed, skipping", extra={"message_id": message_id, "user_id": user_id})
        return

    # Get fresh access token (auto-refreshes if expired)
    token_manager = get_zalo_token_manager()
    access_token = await token_manager.get_access_token()

    zalo_client = ZaloClient(
        app_id=settings.zalo_app_id,
        app_secret=settings.zalo_app_secret,
        access_token=access_token,
        oa_id=settings.zalo_oa_id,
    )

    attempt = 1
    last_error: str | None = None

    while attempt <= MAX_RETRIES:
        try:
            result = await zalo_client.send_text(user_id, text)
            await save_delivery_attempt(
                outbound_message_id, attempt, "success", response=result
            )
            logger.info(
                "Outbound delivered",
                extra={
                    "user_id": user_id,
                    "outbound_message_id": outbound_message_id,
                    "attempt": attempt,
                },
            )
            return

        except RetryableError as e:
            last_error = str(e)
            await save_delivery_attempt(
                outbound_message_id, attempt, "failed", error=str(e)
            )

            # Check if token expired (401) - refresh and retry
            if "Token expired (401)" in str(e) and attempt < MAX_RETRIES:
                logger.info("Refreshing expired token and retrying", extra={"user_id": user_id})
                access_token = await token_manager.get_access_token(force_refresh=True)
                zalo_client = ZaloClient(
                    app_id=settings.zalo_app_id,
                    app_secret=settings.zalo_app_secret,
                    access_token=access_token,
                    oa_id=settings.zalo_oa_id,
                )
                attempt += 1
                continue

            if attempt < MAX_RETRIES:
                wait_time = BACKOFF_BASE**attempt
                logger.warning(
                    "Retryable error, backing off",
                    extra={
                        "user_id": user_id,
                        "attempt": attempt,
                        "wait_seconds": wait_time,
                        "error": str(e),
                    },
                )
                await asyncio.sleep(wait_time)
                attempt += 1
            else:
                logger.error(
                    "Max retries exhausted, sending to DLQ",
                    extra={
                        "user_id": user_id,
                        "outbound_message_id": outbound_message_id,
                        "error": str(e),
                    },
                )
                raise RetryableError(f"Max retries exhausted: {e}") from e

        except NonRetryableError as e:
            last_error = str(e)
            await save_delivery_attempt(
                outbound_message_id, attempt, "failed", error=str(e)
            )
            logger.error(
                "Non-retryable error",
                extra={"user_id": user_id, "outbound_message_id": outbound_message_id, "error": str(e)},
            )
            return

    # Should not reach here, but safety fallback
    await save_delivery_attempt(outbound_message_id, MAX_RETRIES, "failed", error=last_error)
    raise RetryableError(f"Max retries exhausted: {last_error}")
