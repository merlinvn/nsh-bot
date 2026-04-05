"""Core conversation processing pipeline."""

import asyncio
import json
import time
import uuid
from typing import Any, Optional

import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.tool_call import ToolCall
from app.workers.conversation.llm import BaseLLM, create_llm_client
from app.workers.conversation.types import LLMResponse, ToolCallResult
from app.workers.conversation.prompts import PromptManager
from app.workers.conversation.registry import get_registry, LocalToolBackend, MAIN_AGENT_TOOLS
from app.workers.conversation.tools import ToolExecutor, ToolResult
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger
from app.workers.shared.queue import get_channel

logger = get_logger("conversation-worker.processor")

OUTBOUND_QUEUE = "outbound.send"
MAX_LLM_STEPS = 3
MAX_TOOL_CALLS_PER_STEP = 2
LLM_TIMEOUT_SECONDS = 15
FALLBACK_TEXT = "Xin lỗi, hệ thống đang bận. Quý khách vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ ngay nhé!"


class ConversationProcessor:
    def __init__(self) -> None:
        self._llm: Optional[BaseLLM] = None
        self._prompt_manager = PromptManager()
        registry = get_registry()
        backend = LocalToolBackend(registry)
        self._tool_executor = ToolExecutor(backend)
        self._registry = registry

    def _get_llm(self) -> BaseLLM:
        if self._llm is None:
            from app.core.config import settings
            self._llm = create_llm_client(
                provider=settings.llm_provider,
                anthropic_api_key=settings.anthropic_api_key,
                anthropic_model=settings.anthropic_model,
                openai_base_url=settings.openai_base_url,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
                timeout=LLM_TIMEOUT_SECONDS,
            )
        return self._llm

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
                logger.info(
                    "conversation_loaded",
                    extra={"correlation_id": correlation_id, "conversation_id": str(conversation.id)},
                )

                # Step 2: Save inbound message to DB
                prompt_version = self._prompt_manager.get_active_version()
                inbound_msg = Message(
                    conversation_id=conversation.id,
                    direction="inbound",
                    text=text,
                    message_id=zalo_message_id,
                    prompt_version=prompt_version,
                )
                db.add(inbound_msg)
                await db.commit()
                await db.refresh(inbound_msg)

                logger.info(
                    "inbound_message_saved",
                    extra={"correlation_id": correlation_id, "inbound_message_id": str(inbound_msg.id)},
                )

                # Step 3: Build prompt and call LLM
                system_prompt = self._prompt_manager.get_system_prompt()
                conversation_history = await self._get_conversation_history(
                    db, conversation.id, limit=10
                )

                llm_response = await self._call_llm_with_tools(
                    system_prompt=system_prompt,
                    conversation_history=conversation_history,
                    inbound_text=text,
                    correlation_id=correlation_id,
                    inbound_message_id=inbound_msg.id,
                    db=db,
                )

                outbound_text = llm_response.text
                latency_ms = llm_response.latency_ms
                token_usage = llm_response.token_usage

                # Step 4: Save outbound message to DB
                outbound_message = Message(
                    conversation_id=conversation.id,
                    direction="outbound",
                    text=outbound_text,
                    message_id=f"{zalo_message_id}-out",
                    prompt_version=prompt_version,
                    model=self._get_llm().model,
                    latency_ms=latency_ms,
                    token_usage=token_usage,
                )
                db.add(outbound_message)
                await db.commit()
                await db.refresh(outbound_message)

                # Extract IDs before session closes
                conversation_id_str = str(conversation.id)
                outbound_message_id_str = str(outbound_message.id)
                logger.info(
                    "outbound_message_saved",
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

        # Step 4b: Save outbound message to DB (even on fallback)
        # This ensures we have a valid outbound_message_id for delivery tracking
        if not outbound_message_id_str:
            try:
                async with db_session() as db:
                    # Use conversation_id_str if available, otherwise None
                    from uuid import UUID
                    conv_id = UUID(conversation_id_str) if conversation_id_str else None
                    outbound_message = Message(
                        conversation_id=conv_id,
                        direction="outbound",
                        text=outbound_text or FALLBACK_TEXT,
                        message_id=f"{zalo_message_id}-out",
                        prompt_version=self._prompt_manager.get_active_version(),
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

        # Step 5: Publish to outbound.send queue
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
            # Don't fail the processing — message was already saved to DB
            # and will need manual intervention

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

    async def _call_llm_with_tools(
        self,
        system_prompt: str,
        conversation_history: list[dict[str, str]],
        inbound_text: str,
        correlation_id: str,
        inbound_message_id: uuid.UUID,
        db: AsyncSession,
    ) -> "LLMResponse":
        """Call LLM with tools, handling tool execution and re-calling."""
        llm = self._get_llm()

        # Build messages list with current inbound message appended
        messages = conversation_history + [{"role": "user", "content": inbound_text}]

        for step in range(MAX_LLM_STEPS):
            logger.info(
                "llm_call_start",
                extra={"correlation_id": correlation_id, "step": step + 1, "max_steps": MAX_LLM_STEPS},
            )

            response = await llm.complete(
                system_prompt=system_prompt,
                messages=messages,
                tools=self._registry.definitions(allowed_names=MAIN_AGENT_TOOLS),
            )

            logger.info(
                "llm_call_end",
                extra={"correlation_id": correlation_id, "step": step + 1, "latency_ms": response.latency_ms, "has_tool_calls": len(response.tool_calls) > 0},
            )

            # Add assistant response to messages
            assistant_content: list[dict] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })

            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})

            if not response.tool_calls:
                # No tool calls — this is the final response
                return response

            # Execute tool calls (max 2 per step)
            tool_calls_to_execute = response.tool_calls[:MAX_TOOL_CALLS_PER_STEP]

            for tc in tool_calls_to_execute:
                tool_start = time.time()
                logger.info(
                    "tool_call_start",
                    extra={"correlation_id": correlation_id, "tool_name": tc.name, "tool_input": tc.input},
                )

                try:
                    result = await self._tool_executor.execute(tc.name, tc.input)

                    # Save tool call to DB
                    tool_call_record = ToolCall(
                        message_id=inbound_message_id,
                        tool_name=tc.name,
                        input=tc.input,
                        output=result.output,
                        success=True,
                        latency_ms=int((time.time() - tool_start) * 1000),
                    )
                    db.add(tool_call_record)
                    await db.commit()

                    tool_latency = int((time.time() - tool_start) * 1000)
                    logger.info(
                        "tool_call_end",
                        extra={"correlation_id": correlation_id, "tool_name": tc.name, "success": True, "latency_ms": tool_latency},
                    )

                    # Append tool result to messages for next LLM call
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps(result.output),
                        }],
                    })

                except Exception as e:
                    tool_latency = int((time.time() - tool_start) * 1000)
                    logger.error(
                        "tool_call_error",
                        extra={"correlation_id": correlation_id, "tool_name": tc.name, "error": str(e), "error_type": type(e).__name__, "latency_ms": tool_latency},
                    )

                    # Save failed tool call to DB
                    tool_call_record = ToolCall(
                        message_id=inbound_message_id,
                        tool_name=tc.name,
                        input=tc.input,
                        output={"error": str(e)},
                        success=False,
                        error=str(e),
                        latency_ms=tool_latency,
                    )
                    db.add(tool_call_record)
                    await db.commit()

                    # Return error to LLM and continue
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps({"error": str(e)}),
                        }],
                    })

        # Max steps reached — return what we have
        return response

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
