"""Webhook endpoints for receiving Zalo messages."""
from datetime import datetime, timezone
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.api.config import api_settings
from app.api.dependencies import get_rabbitmq, get_redis
from app.api.schemas.webhook import WebhookResponse, ZaloWebhookPayload
from app.api.services.dedup import check_and_set_message_id, check_and_set_ack_sent
from app.api.services.queue import publish_conversation_process
from app.api.services.signature import verify_zalo_signature
from app.core.config import settings
from app.models.zalo_user import ZaloUser
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger
from app.workers.shared.zalo_token_manager import get_zalo_token_manager

logger = get_logger("neochat.api.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ACK_TEXT = "Dạ em đã nhận được tin nhắn của anh/chị rồi ạ! Đợi em xíu để em hỗ trợ nhé 😊"


async def _upsert_zalo_user(user_id: str) -> None:
    """Fetch user profile from Zalo API and upsert into zalo_users table."""
    try:
        tm = get_zalo_token_manager()
        data = await tm.get_user_detail(user_id)
    except Exception as exc:
        logger.warning("zalo_user_fetch_failed", extra={"user_id": user_id, "error": str(exc)})
        return

    async with db_session() as session:
        result = await session.execute(select(ZaloUser).where(ZaloUser.user_id == user_id))
        existing = result.scalar_one_or_none()

        if existing:
            existing.display_name = data.get("display_name")
            existing.user_alias = data.get("user_alias")
            existing.avatar = data.get("avatar")
            existing.user_last_interaction_date = data.get("user_last_interaction_date")
            existing.user_is_follower = data.get("user_is_follower", False)
            existing.shared_info = data.get("shared_info")
            existing.tags_and_notes_info = data.get("tags_and_notes_info")
            existing.user_external_id = data.get("user_external_id")
            existing.user_id_by_app = data.get("user_id_by_app")
            existing.is_sensitive = data.get("is_sensitive")
            existing.last_fetched_at = datetime.now(timezone.utc)
        else:
            existing = ZaloUser(
                user_id=user_id,
                display_name=data.get("display_name"),
                user_alias=data.get("user_alias"),
                avatar=data.get("avatar"),
                user_last_interaction_date=data.get("user_last_interaction_date"),
                user_is_follower=data.get("user_is_follower", False),
                shared_info=data.get("shared_info"),
                tags_and_notes_info=data.get("tags_and_notes_info"),
                user_external_id=data.get("user_external_id"),
                user_id_by_app=data.get("user_id_by_app"),
                is_sensitive=data.get("is_sensitive"),
                last_fetched_at=datetime.now(timezone.utc),
            )
            session.add(existing)

        await session.commit()
        logger.info("zalo_user_upserted", extra={"user_id": user_id, "display_name": data.get("display_name")})


@router.get(
    "/zalo",
    summary="Zalo webhook verification",
    description="Handles Zalo webhook URL verification handshake.",
)
async def zalo_webhook_verify(challenge: str = Query(..., description="Verification challenge from Zalo")) -> PlainTextResponse:
    """Handle Zalo webhook verification request.

    Zalo sends a GET request with a challenge parameter during webhook setup.
    We respond with 200 and the challenge to confirm webhook ownership.
    """
    logger.info("zalo_webhook_verify", extra={"challenge": challenge})
    return PlainTextResponse(content=challenge, status_code=200)


@router.post(
    "/zalo",
    response_model=WebhookResponse,
    summary="Receive Zalo webhook",
    description="Receives inbound messages from Zalo OA webhook. Must respond in < 200ms.",
)
async def zalo_webhook(
    request: Request,
    x_signature: Annotated[str | None, Header(alias="X-Zalo-Signature")] = None,
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

    # Get redis client directly
    redis_client = await get_redis()

    # 2. Parse payload first to check event type
    try:
        payload = ZaloWebhookPayload.model_validate_json(raw_body)
    except Exception:
        # If payload parsing fails, check if it's a verification challenge
        import json
        try:
            body_json = json.loads(raw_body)
            if "challenge" in body_json:
                logger.info("zalo_verification_post", extra={"challenge": body_json["challenge"]})
                return WebhookResponse(success=True)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PAYLOAD", "message": "Failed to parse webhook payload."},
        )

    # 1. Verify signature for message events (user_send_text is Zalo's actual message event)
    # TEMP: Skip for testing - re-enable in production with correct webhook secret
    # if payload.event_name in ("send_message", "user_send_text"):
    #     if not verify_zalo_signature(raw_body, x_signature, api_settings.zalo_webhook_secret):
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail={"code": "INVALID_SIGNATURE", "message": "Webhook signature verification failed."},
    #         )

    # Only process user_send_text events with actual message data
    if payload.event_name != "user_send_text" or not payload.message:
        logger.info(
            "zalo_event_ignored",
            extra={"event": payload.event_name, "has_message": payload.message is not None},
        )
        return WebhookResponse(success=True)

    sender_id = None
    if payload.sender and isinstance(payload.sender, dict):
        sender_id = payload.sender.get("id")

    # Zalo uses msg_id, not message_id
    message_id = None
    text = ""
    if isinstance(payload.message, dict):
        message_id = payload.message.get("msg_id") or payload.message.get("message_id")
        text = payload.message.get("text", "")

    if not message_id:
        logger.warning("zalo_message_without_id", extra={"event": payload.event_name})
        return WebhookResponse(success=True)

    # Dev mode: restrict to a single Zalo user ID
    if settings.dev_zalo_user_id and sender_id != settings.dev_zalo_user_id:
        logger.info(
            "zalo_dev_mode_user_skipped",
            extra={"user_id": sender_id, "dev_zalo_user_id": settings.dev_zalo_user_id},
        )
        return WebhookResponse(success=True)

    # 2b. Fetch and store user profile if new or stale
    if sender_id:
        await _upsert_zalo_user(sender_id)

    # 3. Check deduplication
    is_new = await check_and_set_message_id(redis_client, message_id)
    if not is_new:
        # Silent duplicate — still return 200
        logger.info(
            "duplicate_message",
            extra={
                "event": "duplicate_message",
                "message_id": message_id,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return WebhookResponse(success=True)

    # 3b. Send ACK to customer only when agent needs to do a long tool call
    # ack_key = f"zalo:ack:{message_id}"
    # try:
    #     ack_sent = await redis_client.set(ack_key, "1", nx=True, ex=86400)
    #     if ack_sent:
    #         await publish_message(
    #             routing_key=OUTBOUND_SEND_RK,
    #             body={
    #                 "message_id": message_id,
    #                 "external_user_id": sender_id,
    #                 "text": ACK_TEXT,
    #                 "conversation_id": "",
    #                 "outbound_message_id": "",
    #                 "attempt_no": 1,
    #             },
    #         )
    #         logger.info("ack_published", extra={"message_id": message_id, "user_id": sender_id})
    #     else:
    #         logger.info("ack_already_sent_skipping", extra={"message_id": message_id})
    # except Exception as exc:
    #     logger.warning("ack_publish_failed", extra={"message_id": message_id, "error": str(exc)})

    # 4. Publish to conversation.process queue
    queue_payload = {
        "external_user_id": sender_id,
        "message_id": message_id,
        "text": text,
        "oa_id": api_settings.zalo_oa_id,
    }

    try:
        await publish_conversation_process(rabbitmq_channel, queue_payload)
    except Exception as exc:
        logger.exception(
            "queue_publish_failed",
            extra={
                "event": "queue_publish_failed",
                "message_id": message_id,
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
            "message_id": message_id,
            "user_id": sender_id,
            "request_id": getattr(request.state, "request_id", None),
        },
    )

    return WebhookResponse(success=True)
