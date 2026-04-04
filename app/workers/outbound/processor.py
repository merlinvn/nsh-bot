"""Core outbound message processing with retry and backoff."""
import asyncio
from uuid import UUID

from sqlalchemy import insert

from app.core.config import get_settings
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
    message_db_id: UUID,
    attempt_no: int,
    status: str,
    response: dict | None = None,
    error: str | None = None,
) -> None:
    """Save a delivery attempt record to the database."""
    async with db_session() as session:
        stmt = insert(DeliveryAttempt).values(
            message_id=message_db_id,
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
        message: Dict with keys: user_id (str), text (str), message_db_id (UUID)

    Raises:
        RetryableError: If max retries exhausted (caller should send to DLQ)
    """
    user_id: str = message["user_id"]
    text: str = message["text"]
    message_db_id: UUID = UUID(message["message_db_id"])

    logger.info(
        "Processing outbound message",
        extra={"user_id": user_id, "message_db_id": str(message_db_id)},
    )

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
                message_db_id, attempt, "success", response=result
            )
            logger.info(
                "Outbound delivered",
                extra={
                    "user_id": user_id,
                    "message_db_id": str(message_db_id),
                    "attempt": attempt,
                },
            )
            return

        except RetryableError as e:
            last_error = str(e)
            await save_delivery_attempt(
                message_db_id, attempt, "failed", error=str(e)
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
                        "message_db_id": str(message_db_id),
                        "error": str(e),
                    },
                )
                raise RetryableError(f"Max retries exhausted: {e}") from e

        except NonRetryableError as e:
            last_error = str(e)
            await save_delivery_attempt(
                message_db_id, attempt, "failed", error=str(e)
            )
            logger.error(
                "Non-retryable error",
                extra={"user_id": user_id, "message_db_id": str(message_db_id), "error": str(e)},
            )
            return

    # Should not reach here, but safety fallback
    await save_delivery_attempt(message_db_id, MAX_RETRIES, "failed", error=last_error)
    raise RetryableError(f"Max retries exhausted: {last_error}")
