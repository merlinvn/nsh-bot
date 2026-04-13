"""Internal admin API endpoints (require X-Internal-Api-Key header)."""
import logging
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db, get_rabbitmq, verify_internal_api_key
from app.api.schemas.conversation import (
    ConversationDetail,
    ConversationList,
    DeliveryAttemptResponse,
    MessageWithDetails,
    PaginatedConversationList,
    ToolCallResponse,
)
from app.api.schemas.prompt import PromptActivateRequest, PromptResponse, PromptVersion
from app.models.conversation import Conversation
from app.models.delivery_attempt import DeliveryAttempt
from app.models.message import Message
from app.models.prompt import Prompt
from app.models.tool_call import ToolCall

logger = logging.getLogger("neochat.api.internal")

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_api_key)])


# ---------- Conversations ----------


@router.get(
    "/conversations",
    response_model=PaginatedConversationList,
    summary="List conversations",
    description="Paginated list of conversations with optional filters.",
)
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Query(None, description="Filter by external user ID"),
    conversation_status: str | None = Query(None, alias="status", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
) -> PaginatedConversationList:
    """Return a paginated list of conversations, optionally filtered."""
    query = select(Conversation)
    count_query = select(func.count(Conversation.id))

    if user_id:
        query = query.where(Conversation.external_user_id == user_id)
        count_query = count_query.where(Conversation.external_user_id == user_id)
    if conversation_status:
        query = query.where(Conversation.status == conversation_status)
        count_query = count_query.where(Conversation.status == conversation_status)

    # Order by newest first
    query = query.order_by(Conversation.created_at.desc())

    # Pagination
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Execute
    result = await db.execute(query)
    count_result = await db.execute(count_query)

    conversations = result.scalars().all()
    total = count_result.scalar() or 0
    pages = math.ceil(total / size) if total > 0 else 1

    # Build response with message count
    items = []
    for conv in conversations:
        msg_count_result = await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
        msg_count = msg_count_result.scalar() or 0
        items.append(
            ConversationList(
                id=conv.id,
                external_user_id=conv.external_user_id,
                conversation_key=conv.conversation_key,
                status=conv.status,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=msg_count,
            )
        )

    return PaginatedConversationList(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get conversation detail",
    description="Full conversation with messages, tool calls, and delivery attempts.",
)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    """Return full conversation detail including messages and related records."""
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.tool_calls),
            selectinload(Conversation.messages)
            .selectinload(Message.delivery_attempts),
        )
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": f"Conversation {conversation_id} not found."},
        )

    messages = []
    for msg in conversation.messages:
        tool_calls = [
            ToolCallResponse(
                id=tc.id,
                tool_name=tc.tool_name,
                input=tc.input,
                output=tc.output,
                success=tc.success,
                error=tc.error,
                latency_ms=tc.latency_ms,
                created_at=tc.created_at,
            )
            for tc in msg.tool_calls
        ]
        delivery_attempts = [
            DeliveryAttemptResponse(
                id=da.id,
                attempt_no=da.attempt_no,
                status=da.status,
                response=da.response,
                error=da.error,
                created_at=da.created_at,
            )
            for da in msg.delivery_attempts
        ]
        messages.append(
            MessageWithDetails(
                id=msg.id,
                direction=msg.direction,
                text=msg.text,
                model=msg.model,
                latency_ms=msg.latency_ms,
                token_usage=msg.token_usage,
                message_id=msg.message_id,
                prompt_version=msg.prompt_version,
                created_at=msg.created_at,
                tool_calls=tool_calls,
                delivery_attempts=delivery_attempts,
            )
        )

    return ConversationDetail(
        id=conversation.id,
        external_user_id=conversation.external_user_id,
        conversation_key=conversation.conversation_key,
        status=conversation.status,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


# ---------- Replay ----------


@router.post(
    "/replay",
    summary="Replay a conversation",
    description="Re-queue a conversation's last message for reprocessing.",
)
async def replay_conversation(
    conversation_id: str = Query(..., description="Conversation ID to replay"),
    db: AsyncSession = Depends(get_db),
    rabbitmq_channel = Depends(get_rabbitmq),
) -> dict:
    """Re-queue the last inbound message of a conversation for reprocessing."""
    from app.api.services.queue import publish_conversation_process
    from app.core.rabbitmq import CONVERSATION_PROCESS_RK

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction == "inbound")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    message = result.scalar_one_or_none()

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": f"No inbound message found for conversation {conversation_id}."},
        )

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()

    queue_payload = {
        "external_user_id": conversation.external_user_id if conversation else "",
        "message_id": message.message_id,
        "text": message.text,
        "replay": True,
    }

    await publish_conversation_process(rabbitmq_channel, queue_payload)

    logger.info(
        "conversation_replayed",
        extra={
            "event": "conversation_replayed",
            "conversation_id": conversation_id,
            "message_id": message.message_id,
        },
    )

    return {"success": True, "conversation_id": conversation_id, "message_id": message.message_id}


# ---------- Prompts ----------


@router.get(
    "/prompts",
    response_model=list[PromptResponse],
    summary="List prompts",
    description="List all prompts with their versions.",
)
async def list_prompts(db: AsyncSession = Depends(get_db)) -> list[PromptResponse]:
    """Return all prompts with version information."""
    result = await db.execute(select(Prompt).order_by(Prompt.name))
    prompts = result.scalars().all()

    responses = []
    for prompt in prompts:
        versions = [
            PromptVersion(
                version=v.get("version", ""),
                template=v.get("template", ""),
                created_at=v.get("created_at", ""),
                active=v.get("active", False),
                created_by=v.get("created_by"),
            )
            for v in (prompt.versions or [])
        ]
        responses.append(
            PromptResponse(
                id=prompt.id,
                name=prompt.name,
                template=prompt.template,
                versions=versions,
                active_version=prompt.active_version,
                created_at=prompt.created_at,
                updated_at=prompt.updated_at,
            )
        )

    return responses


@router.post(
    "/prompts/activate",
    summary="Activate prompt version",
    description="Activate a specific version of a prompt by name.",
)
async def activate_prompt_version(
    request: PromptActivateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Activate a specific version of a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == request.name))
    prompt = result.scalar_one_or_none()

    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROMPT_NOT_FOUND", "message": f"Prompt '{request.name}' not found."},
        )

    # Find the version in versions list
    version_found = False
    for v in (prompt.versions or []):
        if v.get("version") == request.version:
            v["active"] = True
            version_found = True
        else:
            v["active"] = False

    if not version_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "VERSION_NOT_FOUND", "message": f"Version '{request.version}' not found in prompt '{request.name}'."},
        )

    prompt.active_version = str(request.version)
    await db.commit()

    logger.info(
        "prompt_version_activated",
        extra={
            "event": "prompt_version_activated",
            "prompt_name": request.name,
            "version": request.version,
        },
    )

    return {"success": True, "name": request.name, "active_version": request.version}
