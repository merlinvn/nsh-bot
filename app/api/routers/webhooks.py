"""Webhook endpoints for receiving Zalo messages."""
import logging
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.config import api_settings
from app.api.dependencies import get_rabbitmq, get_redis
from app.api.schemas.webhook import WebhookResponse, ZaloWebhookPayload
from app.api.services.dedup import check_and_set_message_id
from app.api.services.queue import publish_conversation_process
from app.api.services.signature import verify_zalo_signature

logger = logging.getLogger("neochat.api.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/zalo",
    response_model=WebhookResponse,
    summary="Receive Zalo webhook",
    description="Receives inbound messages from Zalo OA webhook. Must respond in < 200ms.",
)
async def zalo_webhook(
    request: Request,
    x_signature: Annotated[str, Header(alias="X-Zalo-Signature")],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    rabbitmq_channel = Depends(get_rabbitmq),
) -> WebhookResponse:
    """Handle incoming Zalo webhook events.

    1. Verify HMAC-SHA256 signature
    2. Parse payload
    3. Deduplicate via Redis
    4. Publish to conversation.process queue
    5. Return immediately
    """
    # Read raw body for signature verification
    raw_body = await request.body()

    # 1. Verify signature
    if not verify_zalo_signature(raw_body, x_signature, api_settings.zalo_webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_SIGNATURE", "message": "Webhook signature verification failed."},
        )

    # 2. Parse payload
    payload = ZaloWebhookPayload.model_validate_json(raw_body)

    # 3. Check deduplication
    is_new = await check_and_set_message_id(redis_client, payload.message.message_id)
    if not is_new:
        # Silent duplicate — still return 200
        logger.info(
            "duplicate_message",
            extra={
                "event": "duplicate_message",
                "message_id": payload.message.message_id,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return WebhookResponse(success=True)

    # 4. Publish to conversation.process queue
    queue_payload = {
        "external_user_id": payload.sender.id,
        "message_id": payload.message.message_id,
        "text": payload.message.text,
        "oa_id": api_settings.zalo_oa_id,
    }

    try:
        await publish_conversation_process(rabbitmq_channel, queue_payload)
    except Exception as exc:
        logger.exception(
            "queue_publish_failed",
            extra={
                "event": "queue_publish_failed",
                "message_id": payload.message.message_id,
                "error": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "QUEUE_UNAVAILABLE", "message": "Failed to enqueue message."},
        )

    logger.info(
        "message_enqueued",
        extra={
            "event": "message_enqueued",
            "message_id": payload.message.message_id,
            "user_id": payload.sender.id,
            "request_id": getattr(request.state, "request_id", None),
        },
    )

    return WebhookResponse(success=True)
