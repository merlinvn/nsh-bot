"""LLM processor — handles playground, evaluation, and zalo LLM calls."""
import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any

import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rabbitmq import OUTBOUND_SEND_QUEUE as OUTBOUND_QUEUE
from app.models.evaluation import EvaluationTestCase, PromptEvaluation
from app.models.prompt import Prompt
from app.workers.conversation.agent import AgentRunner
from app.workers.conversation.llm import create_llm_client
from app.workers.mcp_client import MCPToolBackend, list_tools

MAX_LLM_STEPS = 3
MAX_TOOL_CALLS_PER_STEP = 2

from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger
from app.workers.shared.queue import get_channel

logger = get_logger("llm.processor")


# ---------------------------------------------------------------------------
# LLMProcessor
# ---------------------------------------------------------------------------


class LLMProcessor:
    """Processes LLM requests from the llm.process queue.

    Routes responses based on channel:
    - zalo    → publish to outbound.send queue
    - playground → publish to Redis response channel
    - evaluation → update DB records directly
    """

    def __init__(self) -> None:
        self._llm = None
        self._mcp_backend = MCPToolBackend()

    def _get_llm(self):
        if self._llm is None:
            self._llm = create_llm_client(
                provider=settings.llm_provider,
                anthropic_api_key=settings.anthropic_api_key,
                anthropic_model=settings.anthropic_model,
                openai_base_url=settings.openai_base_url,
                openai_api_key=settings.openai_api_key,
                openai_model=settings.openai_model,
            )
        return self._llm

    async def process(self, payload: dict[str, Any]) -> None:
        """Main entry point — called by the queue consumer."""
        request_id = payload.get("request_id", str(uuid.uuid4()))
        channel = payload.get("channel", "playground")
        logger.info("llm_request_received", extra={"request_id": request_id, "channel": channel})

        try:
            if channel == "zalo":
                await self._process_zalo(payload, request_id)
            elif channel == "playground":
                await self._process_playground(payload, request_id)
            elif channel == "evaluation":
                await self._process_evaluation(payload, request_id)
            else:
                logger.error("unknown_channel", extra={"request_id": request_id, "channel": channel})
        except Exception as exc:
            logger.exception("llm_process_error", extra={"request_id": request_id, "channel": channel, "error": str(exc)})
            # Publish error response for playground/evaluation
            if channel != "zalo":
                await self._publish_redis_response(request_id, channel, {"error": str(exc)})

    # ---------------------------------------------------------------------------
    # Channel-specific processing
    # ---------------------------------------------------------------------------

    async def _process_zalo(self, payload: dict[str, Any], request_id: str) -> None:
        """Process a Zalo LLM call routed from conversation.process via llm.process.

        Runs AgentRunner with full tool call recording (own db_session),
        handles quote subagent delegation, updates outbound Message in DB,
        and publishes response to Redis for ConversationProcessor.
        """
        request_id = payload.get("request_id", request_id)
        response_channel = payload.get("response_channel", f"llm:response:{request_id}")

        inbound_message_id = payload.get("inbound_message_id", "")
        outbound_message_id = payload.get("outbound_message_id", "")
        correlation_id = payload.get("correlation_id", "")

        # system_prompt may be passed directly or resolved via prompt_name
        system_prompt = payload.get("system_prompt", "")
        if not system_prompt and payload.get("prompt_name"):
            async with db_session() as db:
                result = await db.execute(select(Prompt).where(Prompt.name == payload["prompt_name"]))
                prompt_record = result.scalar_one_or_none()
                system_prompt = prompt_record.template if prompt_record else ""

        conversation_history = payload.get("conversation_history", [])
        inbound_text = payload.get("inbound_text", "")

        runner = AgentRunner(
            llm=self._get_llm(),
            tool_executor=self._mcp_backend,
            system_prompt=system_prompt,
            tool_definitions=list_tools(),
            max_steps=MAX_LLM_STEPS,
            max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
        )

        async def on_tool_call(
            tool_name: str,
            tool_input: dict,
            tool_output: dict,
            success: bool,
            latency_ms: int,
        ) -> None:
            # Record ToolCall in DB
            async with db_session() as db:
                from app.models.tool_call import ToolCall
                msg_uuid = uuid.UUID(inbound_message_id) if inbound_message_id else None
                record = ToolCall(
                    message_id=msg_uuid,
                    tool_name=tool_name,
                    input=tool_input,
                    output=tool_output,
                    success=success,
                    latency_ms=latency_ms,
                )
                db.add(record)
                await db.commit()

        result = await runner.run(conversation_history, inbound_text, on_tool_call=on_tool_call)

        # Update outbound Message in DB with LLM response
        if outbound_message_id:
            async with db_session() as db:
                from app.models.message import Message
                msg_result = await db.execute(
                    select(Message).where(Message.id == uuid.UUID(outbound_message_id))
                )
                outbound_msg = msg_result.scalar_one_or_none()
                if outbound_msg:
                    outbound_msg.text = result.text
                    outbound_msg.latency_ms = result.latency_ms
                    outbound_msg.token_usage = result.token_usage
                    await db.commit()

        # Publish response to Redis for ConversationProcessor
        await self._publish_redis_response(request_id, "zalo", {
            "text": result.text,
            "token_usage": result.token_usage,
            "latency_ms": result.latency_ms,
        })

    async def _process_playground(self, payload: dict[str, Any], request_id: str) -> None:
        """Process a playground chat LLM call."""
        system_prompt = payload.get("system_prompt", "")
        messages = payload.get("messages", [])
        new_message = payload.get("new_message", "")

        conversation_history = messages + [{"role": "user", "content": new_message}]

        runner = AgentRunner(
            llm=self._get_llm(),
            tool_executor=self._mcp_backend,
            system_prompt=system_prompt,
            tool_definitions=list_tools(),
            max_steps=MAX_LLM_STEPS,
            max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
        )

        result = await runner.run(messages, new_message)

        response = {
            "text": result.text,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                    "output": tc.output,
                    "success": tc.success,
                    "latency_ms": tc.latency_ms,
                }
                for tc in result.tool_calls
            ],
            "token_usage": result.token_usage,
            "latency_ms": result.latency_ms,
            "error": None,
        }

        await self._publish_redis_response(request_id, "playground", response)

    async def _process_evaluation(self, payload: dict[str, Any], request_id: str) -> None:
        """Process an evaluation test case LLM call."""
        evaluation_id = payload.get("evaluation_id", "")
        tc_id = payload.get("tc_id", "")
        question = payload.get("question", "")
        expected_answer = payload.get("expected_answer", "")
        prompt_name = payload.get("prompt_name", "")

        # Resolve system prompt from DB
        system_prompt = ""
        if prompt_name:
            async with db_session() as db:
                result = await db.execute(select(Prompt).where(Prompt.name == prompt_name))
                prompt_record = result.scalar_one_or_none()
                system_prompt = prompt_record.template if prompt_record else ""

        runner = AgentRunner(
            llm=self._get_llm(),
            tool_executor=self._mcp_backend,
            system_prompt=system_prompt,
            tool_definitions=list_tools(),
            max_steps=MAX_LLM_STEPS,
            max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
        )

        result = await runner.run([], question)

        actual = result.text.strip()
        latency_ms = result.latency_ms

        # LLM judge
        is_passed = None
        judgment = None
        error = None

        try:
            judge_prompt = f"""Bạn là người đánh giá câu trả lời của AI.

Câu hỏi: {question}

Câu trả lời kỳ vọng: {expected_answer}

Câu trả lời thực tế: {actual}

Hãy đánh giá câu trả lời thực tế có đúng ý và đầy đủ so với kỳ vọng không.
Trả lời CHÍNH XÁC một trong hai format:
PASS — nếu câu trả lời đúng ý, đầy đủ
FAIL — nếu câu trả lời sai hoặc thiếu thông tin quan trọng

Kèm theo giải thích ngắn gọn (1-2 câu) sau PASS/FAIL."""

            judge_response = await self._get_llm().complete(
                system_prompt=judge_prompt,
                messages=[{"role": "user", "content": "Đánh giá câu trả lời này."}],
                tools=[],
            )

            judge_text = judge_response.text.strip()
            is_passed = judge_text.lower().startswith("pass")
            lines = judge_text.split("\n")
            reasoning_lines = [
                l for l in lines
                if not l.lower().startswith("pass") and not l.lower().startswith("fail") and l.strip()
            ]
            judgment = "PASS" if is_passed else "FAIL"
            if reasoning_lines:
                judgment = f"{judgment}: {' '.join(reasoning_lines[:2])}"

        except Exception as exc:
            error = str(exc)

        # Update DB directly
        async with db_session() as db:
            # Update test case
            tc_result = await db.execute(
                select(EvaluationTestCase).where(EvaluationTestCase.id == uuid.UUID(tc_id))
            )
            tc = tc_result.scalar_one_or_none()
            if tc:
                tc.actual_answer = actual
                tc.passed = is_passed
                tc.judgment = judgment
                tc.latency_ms = latency_ms
                tc.error = error

            # Update evaluation summary
            eval_result = await db.execute(
                select(PromptEvaluation).where(PromptEvaluation.id == uuid.UUID(evaluation_id))
            )
            evaluation = eval_result.scalar_one_or_none()
            if evaluation:
                all_tc_result = await db.execute(
                    select(EvaluationTestCase).where(EvaluationTestCase.evaluation_id == uuid.UUID(evaluation_id))
                )
                all_tcs = all_tc_result.scalars().all()
                passed = sum(1 for t in all_tcs if t.passed is True)
                failed = sum(1 for t in all_tcs if t.passed is False and t.passed is not None)
                from datetime import datetime, timezone
                evaluation.status = "completed"
                evaluation.completed_at = datetime.now(timezone.utc)
                evaluation.total = len(all_tcs)
                evaluation.passed = passed
                evaluation.failed = failed

            await db.commit()

        # Publish Redis response so API knows we're done
        response = {
            "text": actual,
            "passed": is_passed,
            "judgment": judgment,
            "latency_ms": latency_ms,
            "error": error,
        }
        await self._publish_redis_response(request_id, "evaluation", response)

    # ---------------------------------------------------------------------------
    # Response delivery helpers
    # ---------------------------------------------------------------------------

    async def _publish_outbound(self, payload: dict[str, Any], text: str) -> None:
        """Publish Zalo response to outbound.send queue."""
        channel = await get_channel()
        exchange = await channel.declare_exchange(
            "neochat.direct",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        msg_payload = {
            "message_id": payload.get("message_id", ""),
            "external_user_id": payload.get("external_user_id", ""),
            "text": text,
            "correlation_id": payload.get("correlation_id", ""),
            "conversation_id": payload.get("conversation_id", ""),
            "outbound_message_id": payload.get("outbound_message_id", ""),
            "attempt_no": 1,
        }

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(msg_payload).encode(),
                headers={"correlation_id": payload.get("correlation_id", "")},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=OUTBOUND_QUEUE,
        )

    async def _publish_redis_response(self, request_id: str, channel: str, response: dict[str, Any]) -> None:
        """Publish LLM response to Redis pub/sub channel."""
        from app.core.redis import get_redis_client

        redis_client = await get_redis_client()
        full_response = {
            "request_id": request_id,
            "channel": channel,
            **response,
        }
        await redis_client.publish(f"llm:response:{request_id}", json.dumps(full_response, default=str))
