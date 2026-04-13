"""Admin conversations management router."""
import uuid as uuid_lib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.delivery_attempt import DeliveryAttempt
from app.models.tool_call import ToolCall
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.zalo_user import ZaloUser

router = APIRouter(prefix="/admin/conversations", tags=["admin:conversations"])


@router.get("")
async def list_conversations(
    user_id: str | None = None,
    status: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    sort: str = "created_at",
    order: str = "desc",
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """List conversations with pagination and filtering."""
    query = (
        select(Conversation, ZaloUser.display_name, ZaloUser.avatar)
        .outerjoin(ZaloUser, Conversation.external_user_id == ZaloUser.user_id)
    )
    if user_id:
        query = query.where(Conversation.external_user_id == user_id)
    if status:
        query = query.where(Conversation.status == status)
    if sort == "created_at":
        order_col = Conversation.created_at if order == "asc" else Conversation.created_at.desc()
    query = query.order_by(order_col)
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    rows = result.all()

    # Count total
    count_query = select(func.count(Conversation.id))
    if user_id:
        count_query = count_query.where(Conversation.external_user_id == user_id)
    if status:
        count_query = count_query.where(Conversation.status == status)
    total = await db.scalar(count_query)

    return {
        "items": [
            {
                "id": str(c.id),
                "external_user_id": c.external_user_id,
                "user_display_name": display_name,
                "user_avatar": avatar,
                "status": c.status,
                "created_at": c.created_at.isoformat(),
            }
            for c, display_name, avatar in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/stats")
async def conversation_stats(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get conversation statistics."""
    total = await db.scalar(select(func.count(Conversation.id)))
    active = await db.scalar(
        select(func.count(Conversation.id)).where(Conversation.status == "active")
    )
    return {"total": total or 0, "active": active or 0}


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 20,
    before: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get messages for a conversation with cursor-based pagination.

    Returns messages in DESC order (newest first). Use `before` to load older messages.
    """
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = select(Message).where(Message.conversation_id == conversation_id)

    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
            query = query.where(Message.created_at < before_dt)
        except ValueError:
            pass

    query = query.order_by(Message.created_at.desc()).limit(limit + 1)
    messages_result = await db.execute(query)
    messages = messages_result.scalars().all()

    # Check if there are more messages
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:-1]  # Remove the extra one

    if not messages:
        return {
            "messages": [],
            "has_more": False,
            "next_before": None,
        }

    # Last message in the list is the oldest (for next cursor)
    oldest = messages[-1]
    next_before = oldest.created_at.isoformat()

    message_ids = [str(m.id) for m in messages]

    tool_calls_result = await db.execute(
        select(ToolCall).where(ToolCall.message_id.in_(message_ids)).order_by(ToolCall.created_at)
    )
    tool_calls = tool_calls_result.scalars().all()

    delivery_result = await db.execute(
        select(DeliveryAttempt).where(DeliveryAttempt.message_id.in_(message_ids)).order_by(DeliveryAttempt.attempt_no)
    )
    delivery_attempts = delivery_result.scalars().all()

    tool_calls_by_msg: dict = {}
    for tc in tool_calls:
        tool_calls_by_msg.setdefault(str(tc.message_id), []).append({
            "id": str(tc.id),
            "tool_name": tc.tool_name,
            "input": tc.input,
            "output": tc.output,
            "success": tc.success,
            "error": tc.error,
            "latency_ms": tc.latency_ms,
            "created_at": tc.created_at.isoformat(),
        })

    delivery_by_msg: dict = {}
    for da in delivery_attempts:
        delivery_by_msg.setdefault(str(da.message_id), []).append({
            "id": str(da.id),
            "attempt_no": da.attempt_no,
            "status": da.status,
            "response": da.response,
            "error": da.error,
            "created_at": da.created_at.isoformat(),
        })

    return {
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "text": m.text,
                "error": m.error,
                "model": m.model,
                "latency_ms": m.latency_ms,
                "prompt_version": m.prompt_version,
                "token_usage": m.token_usage,
                "created_at": m.created_at.isoformat(),
                "tool_calls": tool_calls_by_msg.get(str(m.id), []),
                "delivery_attempts": delivery_by_msg.get(str(m.id), []),
            }
            for m in reversed(messages)  # oldest first for prepend
        ],
        "has_more": has_more,
        "next_before": next_before,
    }
@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get conversation with messages and tool calls."""
    conv_result = await db.execute(
        select(Conversation, ZaloUser.display_name, ZaloUser.avatar, ZaloUser.user_id_by_app)
        .outerjoin(ZaloUser, Conversation.external_user_id == ZaloUser.user_id)
        .where(Conversation.id == uuid_lib.UUID(conversation_id))
    )
    conv_row = conv_result.first()
    if not conv_row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv, user_display_name, user_avatar, user_id_by_app = conv_row

    messages_result = await db.execute(
        select(Message).where(Message.conversation_id == uuid_lib.UUID(conversation_id)).order_by(Message.created_at)
    )
    messages = messages_result.scalars().all()

    # Fetch tool_calls and delivery_attempts for all messages in one query
    message_ids = [str(m.id) for m in messages]

    tool_calls_result = await db.execute(
        select(ToolCall).where(ToolCall.message_id.in_(message_ids)).order_by(ToolCall.created_at)
    )
    tool_calls = tool_calls_result.scalars().all()

    delivery_result = await db.execute(
        select(DeliveryAttempt).where(DeliveryAttempt.message_id.in_(message_ids)).order_by(DeliveryAttempt.attempt_no)
    )
    delivery_attempts = delivery_result.scalars().all()

    # Index by message_id for fast lookup
    tool_calls_by_msg = {}
    for tc in tool_calls:
        tool_calls_by_msg.setdefault(str(tc.message_id), []).append({
            "id": str(tc.id),
            "tool_name": tc.tool_name,
            "input": tc.input,
            "output": tc.output,
            "success": tc.success,
            "error": tc.error,
            "latency_ms": tc.latency_ms,
            "created_at": tc.created_at.isoformat(),
        })

    delivery_by_msg = {}
    for da in delivery_attempts:
        delivery_by_msg.setdefault(str(da.message_id), []).append({
            "id": str(da.id),
            "attempt_no": da.attempt_no,
            "status": da.status,
            "response": da.response,
            "error": da.error,
            "created_at": da.created_at.isoformat(),
        })

    return {
        "id": str(conv.id),
        "external_user_id": conv.external_user_id,
        "user_display_name": user_display_name,
        "user_avatar": user_avatar,
        "user_id_by_app": user_id_by_app,
        "status": conv.status,
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "text": m.text,
                "error": m.error,
                "model": m.model,
                "latency_ms": m.latency_ms,
                "prompt_version": m.prompt_version,
                "token_usage": m.token_usage,
                "created_at": m.created_at.isoformat(),
                "tool_calls": tool_calls_by_msg.get(str(m.id), []),
                "delivery_attempts": delivery_by_msg.get(str(m.id), []),
            }
            for m in messages
        ],
    }


@router.post("/{conversation_id}/replay")
async def replay_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """
    Replay dry-run: re-processes last message through LLM agent pipeline.
    Result is stored in DB but NOT sent to Zalo.
    """
    # Get conversation and last message
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    last_msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction == "inbound")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    if not last_msg:
        raise HTTPException(status_code=400, detail="No inbound message to replay")

    # TODO: Call conversation worker pipeline (reuse existing llm.py logic)
    # This queues the message for processing but with a replay flag
    # The outbound worker suppresses delivery to Zalo
    return {"ok": True, "message": "Replay queued", "message_id": str(last_msg.id)}


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """List messages in a conversation."""
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "direction": m.direction,
            "text": m.text,
            "error": m.error,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
