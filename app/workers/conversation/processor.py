"""Core conversation processing pipeline."""

import json
import time
import uuid
from typing import Any, Optional

import aio_pika
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.workers.conversation.prompts import PromptManager
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger
from app.workers.shared.queue import get_channel

logger = get_logger("conversation-worker.processor")

OUTBOUND_QUEUE = "outbound.send"
FALLBACK_TEXT = "Xin lỗi, hệ thống đang bận. Quý khách vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ ngay nhé!"


class ConversationProcessor:
    def __init__(self) -> None:
        self._prompt_manager = PromptManager()

    async def process(self, payload: dict, correlation_id: str) -> None:
        """Main processing pipeline for a conversation message."""
        start_time = time.time()

        message_id = payload["message_id"]
        external_user_id = payload["external_user_id"]
        text = payload["text"]
        received_at = payload.get("received_at", "")
        zalo_message_id = payload.get("zalo_message_id", message_id)

        conversation: Optional[Conversation] = None
        inbound_msg: Optional[Message] = None
        outbound_text: Optional[str] = None
        outbound_message: Optional[Message] = None
        error: Optional[str] = None
        conversation_id_str: str = ""
        outbound_message_id_str: str = ""

        try:
            async with db_session() as db:
                # Step 1: Load or create conversation
                conversation = await self._load_or_create_conversation(db, external_user_id)
                conversation_id_str = str(conversation.id)
                logger.info(
                    "conversation_loaded",
                    extra={"correlation_id": correlation_id, "conversation_id": conversation_id_str},
                )

                # Step 2: Save inbound message to DB
                prompt_version = await self._prompt_manager.get_active_version()
                inbound_msg = Message(
                    conversation_id=conversation.id,
                    direction="inbound",
                    text=text,
                    message_id=zalo_message_id,
                    prompt_version=prompt_version,
                )
                db.add(inbound_msg)
                conversation.updated_at = func.now()
                await db.commit()
                await db.refresh(inbound_msg)

                logger.info(
                    "inbound_message_saved",
                    extra={"correlation_id": correlation_id, "inbound_message_id": str(inbound_msg.id)},
                )

                # Step 3: Build prompt and call LLM via llm.process queue
                system_prompt = await self._prompt_manager.get_system_prompt()
                conversation_history = await self._get_conversation_history(
                    db, conversation.id, limit=10
                )

                # Create placeholder outbound message (updated after LLM response)
                outbound_message = Message(
                    conversation_id=conversation.id,
                    direction="outbound",
                    text="",  # Will be updated with LLM response
                    message_id=f"{zalo_message_id}-out",
                    prompt_version=prompt_version,
                    model="",  # Will be updated with actual model
                    latency_ms=0,
                    token_usage=None,
                )
                db.add(outbound_message)
                await db.commit()
                await db.refresh(outbound_message)
                outbound_message_id_str = str(outbound_message.id)
                conversation_id_str = str(conversation.id)

                logger.info(
                    "outbound_placeholder_saved",
                    extra={"correlation_id": correlation_id, "outbound_message_id": outbound_message_id_str},
                )

        except Exception as e:
            error = str(e)
            logger.error(
                "processing_error",
                extra={"correlation_id": correlation_id, "error": error, "error_type": type(e).__name__, "processing_time_ms": int((time.time() - start_time) * 1000)},
            )
            outbound_text = FALLBACK_TEXT
            logger.info(
                "fallback_triggered",
                extra={"correlation_id": correlation_id, "reason": error},
            )

        # Step 4b: Fallback — save outbound message if LLM was never called
        if not outbound_message_id_str:
            try:
                async with db_session() as db:
                    from uuid import UUID
                    conv_id = UUID(conversation_id_str) if conversation_id_str else None
                    outbound_message = Message(
                        conversation_id=conv_id,
                        direction="outbound",
                        text=outbound_text or FALLBACK_TEXT,
                        message_id=f"{zalo_message_id}-out",
                        prompt_version=await self._prompt_manager.get_active_version(),
                        model="fallback",
                        latency_ms=0,
                        token_usage=None,
                    )
                    db.add(outbound_message)
                    await db.commit()
                    await db.refresh(outbound_message)
                    outbound_message_id_str = str(outbound_message.id)
                    logger.info(
                        "fallback_outbound_message_saved",
                        extra={"correlation_id": correlation_id, "outbound_message_id": outbound_message_id_str},
                    )
            except Exception as save_err:
                logger.error(
                    "fallback_outbound_save_error",
                    extra={"correlation_id": correlation_id, "error": str(save_err)},
                )

        # Step 5: Publish to llm.process and wait for Redis response
        try:
            from app.api.services.llm_queue import enqueue_llm_request_zalo

            llm_response = await enqueue_llm_request_zalo({
                "channel": "zalo",
                "correlation_id": correlation_id,
                "inbound_message_id": str(inbound_msg.id),
                "outbound_message_id": outbound_message_id_str,
                "external_user_id": external_user_id,
                "zalo_message_id": zalo_message_id,
                "system_prompt": system_prompt,
                "conversation_history": conversation_history,
                "inbound_text": text,
            })

            # Step 6: Update outbound message in DB with LLM response
            outbound_text = llm_response.get("text", FALLBACK_TEXT)
            latency_ms = llm_response.get("latency_ms", 0)
            token_usage = llm_response.get("token_usage", {})

            async with db_session() as db:
                from uuid import UUID
                result = await db.execute(
                    select(Message).where(Message.id == UUID(outbound_message_id_str))
                )
                saved_outbound = result.scalar_one_or_none()
                if saved_outbound:
                    saved_outbound.text = outbound_text
                    saved_outbound.latency_ms = latency_ms
                    saved_outbound.token_usage = token_usage
                    await db.commit()

            logger.info(
                "outbound_message_updated",
                extra={"correlation_id": correlation_id, "outbound_message_id": outbound_message_id_str, "latency_ms": latency_ms},
            )

        except Exception as e:
            logger.error(
                "llm_queue_error",
                extra={"correlation_id": correlation_id, "error": str(e)},
            )
            outbound_text = FALLBACK_TEXT
            # Outbound message already has placeholder text — update to fallback
            if outbound_message_id_str:
                try:
                    async with db_session() as db:
                        from uuid import UUID
                        result = await db.execute(
                            select(Message).where(Message.id == UUID(outbound_message_id_str))
                        )
                        saved_outbound = result.scalar_one_or_none()
                        if saved_outbound:
                            saved_outbound.text = FALLBACK_TEXT
                            await db.commit()
                except Exception:
                    pass

        # Step 7: Publish to outbound.send queue
        try:
            await self._publish_outbound(
                message_id=zalo_message_id,
                external_user_id=external_user_id,
                text=outbound_text or FALLBACK_TEXT,
                correlation_id=correlation_id,
                conversation_id=conversation_id_str,
                outbound_message_id=outbound_message_id_str,
            )

            logger.info(
                "response_published",
                extra={"correlation_id": correlation_id, "conversation_id": conversation_id_str or None, "processing_time_ms": int((time.time() - start_time) * 1000)},
            )
        except Exception as e:
            logger.error(
                "outbound_publish_error",
                extra={"correlation_id": correlation_id, "error": str(e), "error_type": type(e).__name__},
            )

    async def _load_or_create_conversation(
        self, db: AsyncSession, external_user_id: str
    ) -> Conversation:
        """Load existing conversation or create new one."""
        conversation_key = f"zalo:{external_user_id}"

        result = await db.execute(
            select(Conversation).where(Conversation.conversation_key == conversation_key)
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                external_user_id=external_user_id,
                conversation_key=conversation_key,
                status="active",
            )
            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)
            logger.info(
                "conversation_created",
                extra={"conversation_key": conversation_key},
            )

        return conversation

    async def _get_conversation_history(
        self, db: AsyncSession, conversation_id: uuid.UUID, limit: int = 10
    ) -> list[dict[str, str]]:
        """Get last N messages from conversation history for LLM context."""
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        # Return in chronological order (oldest first)
        messages = list(reversed(messages))

        history = []
        for msg in messages:
            role = "user" if msg.direction == "inbound" else "assistant"
            history.append({"role": role, "content": msg.text})

        return history


    async def _publish_outbound(
        self,
        message_id: str,
        external_user_id: str,
        text: str,
        correlation_id: str,
        conversation_id: str,
        outbound_message_id: str,
    ) -> None:
        """Publish response to outbound.send queue."""
        channel = await get_channel()
        exchange = await channel.declare_exchange(
            "neochat.direct",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        payload = {
            "message_id": message_id,
            "external_user_id": external_user_id,
            "text": text,
            "correlation_id": correlation_id,
            "conversation_id": conversation_id,
            "outbound_message_id": outbound_message_id,
            "attempt_no": 1,
        }

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                headers={"correlation_id": correlation_id},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=OUTBOUND_QUEUE,
        )

