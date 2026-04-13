"""Core conversation processing pipeline."""

import asyncio
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.tool_call import ToolCall
from app.workers.conversation.agent import AgentRunner
from app.workers.conversation.llm import BaseLLM, create_llm_client
from app.workers.conversation.types import LLMResponse, ToolCallResult
from app.workers.conversation.prompts import PromptManager
from app.workers.conversation.registry import get_registry, LocalToolBackend, MAIN_AGENT_TOOLS, QUOTE_AGENT_TOOLS
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


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    """Configuration for an agent (main or subagent)."""
    name: str
    system_prompt: str
    tool_definitions: list[dict[str, Any]]
    max_steps: int = MAX_LLM_STEPS


async def _build_main_agent_config(prompt_manager: PromptManager, registry) -> AgentConfig:
    """Build the main agent configuration."""
    return AgentConfig(
        name="main",
        system_prompt=await prompt_manager.get_system_prompt(),
        tool_definitions=registry.definitions(allowed_names=MAIN_AGENT_TOOLS),
    )


def _build_quote_agent_config(prompt_manager: PromptManager, registry) -> AgentConfig:
    """Build the quote subagent configuration."""
    return AgentConfig(
        name="quote",
        system_prompt=prompt_manager.get_quote_system_prompt(),
        tool_definitions=registry.definitions(allowed_names=QUOTE_AGENT_TOOLS),
    )


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
                await db.commit()
                await db.refresh(inbound_msg)

                logger.info(
                    "inbound_message_saved",
                    extra={"correlation_id": correlation_id, "inbound_message_id": str(inbound_msg.id)},
                )

                # Step 3: Build prompt and call LLM
                system_prompt = await self._prompt_manager.get_system_prompt()
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
        """Call LLM with tools (main agent path) using AgentRunner."""
        main_agent = await _build_main_agent_config(self._prompt_manager, self._registry)
        runner = AgentRunner(
            llm=self._get_llm(),
            tool_executor=self._tool_executor,
            system_prompt=main_agent.system_prompt,
            tool_definitions=main_agent.tool_definitions,
            max_steps=main_agent.max_steps,
            max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
        )

        # Capture inbound_message_id for quote subagent (closure)
        _inbound_id = inbound_message_id

        async def on_tool_call(
            tool_name: str,
            tool_input: dict,
            tool_output: dict,
            success: bool,
            latency_ms: int,
        ) -> None:
            # Intercept delegate_to_quote_agent — run quote subagent and replace output
            if tool_name == "delegate_to_quote_agent" and success and tool_output.get("delegated"):
                result = await self._run_quote_subagent(
                    customer_message=tool_output["customer_message"],
                    known_context=tool_output.get("known_context", {}),
                    correlation_id=correlation_id,
                    inbound_message_id=_inbound_id,
                    db=db,
                )
                tool_output.clear()
                tool_output.update(result)
                success = result.get("status") != "error"

            # Persist tool call record to DB
            record = ToolCall(
                message_id=_inbound_id,
                tool_name=tool_name,
                input=tool_input,
                output=tool_output,
                success=success,
                latency_ms=latency_ms,
            )
            db.add(record)
            db.commit()

        result = await runner.run(conversation_history, inbound_text, on_tool_call=on_tool_call)

        # Convert AgentRunResult back to LLMResponse for existing process() caller
        return LLMResponse(
            text=result.text,
            tool_calls=[ToolCallResult(id=tc.id, name=tc.name, input=tc.input) for tc in result.tool_calls],
            latency_ms=result.latency_ms,
            token_usage=result.token_usage,
        )

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

    # ---------------------------------------------------------------------------
    # Quote subagent runner
    # ---------------------------------------------------------------------------

    async def _run_quote_subagent(
        self,
        customer_message: str,
        known_context: dict,
        correlation_id: str,
        inbound_message_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        """Run the quote subagent loop and return the structured result.

        The quote subagent runs in its own LLM loop with its own prompt and
        only the calculate_shipping_quote tool. It returns structured JSON
        with status field.
        """
        quote_agent = _build_quote_agent_config(self._prompt_manager, self._registry)

        # Build subagent input from customer message and known context
        subagent_input_parts = [f"Khách hàng hỏi: {customer_message}"]
        if known_context:
            ctx_lines = [f"Thông tin đã biết: {known_context}"]
            subagent_input_parts.extend(ctx_lines)
        subagent_input = "\n".join(subagent_input_parts)

        runner = AgentRunner(
            llm=self._get_llm(),
            tool_executor=self._tool_executor,
            system_prompt=quote_agent.system_prompt,
            tool_definitions=quote_agent.tool_definitions,
            max_steps=quote_agent.max_steps,
            max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
        )

        # Quote agent has no sub-agents, so no interception needed — just save to DB
        async def on_quote_tool_call(
            tool_name: str,
            tool_input: dict,
            tool_output: dict,
            success: bool,
            latency_ms: int,
        ) -> None:
            record = ToolCall(
                message_id=inbound_message_id,
                tool_name=tool_name,
                input=tool_input,
                output=tool_output,
                success=success,
                latency_ms=latency_ms,
            )
            db.add(record)
            db.commit()

        try:
            result = await runner.run([], subagent_input, on_tool_call=on_quote_tool_call)

            # Parse JSON from subagent response
            raw_text = (result.text or "").strip()
            try:
                parsed = json.loads(raw_text)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "quote_subagent_invalid_json",
                    extra={"correlation_id": correlation_id, "raw_text": raw_text[:200]},
                )
                parsed = {
                    "status": "manual_review",
                    "message_to_customer": "Em cần kiểm tra thêm để báo giá chính xác. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
                    "reason": "quote_subagent_invalid_json",
                    "raw_text": raw_text[:200],
                }

            return parsed

        except Exception as e:
            logger.exception(
                "quote_subagent_error",
                extra={"correlation_id": correlation_id, "error": str(e)},
            )
            return {
                "status": "manual_review",
                "message_to_customer": "Em cần kiểm tra thêm để báo giá chính xác. Anh/chị vui lòng liên hệ Zalo 098.2128.029 để được hỗ trợ.",
                "reason": f"quote_subagent_error: {str(e)[:100]}",
            }
