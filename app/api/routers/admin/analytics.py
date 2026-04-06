"""Admin analytics router."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.conversation import Conversation
from app.models.message import Message

router = APIRouter(prefix="/admin/analytics", tags=["admin:analytics"])


def _parse_date(date_str: str) -> datetime:
    """Parse ISO date string to datetime."""
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


@router.get("/overview")
async def analytics_overview(
    start: str = Query(..., description="ISO date string"),
    end: str = Query(..., description="ISO date string"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Dashboard overview for a time period."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)

    total_messages = await db.scalar(
        select(func.count(Message.id)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt)
        )
    )
    total_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(
            and_(Conversation.created_at >= start_dt, Conversation.created_at <= end_dt)
        )
    )
    # Avg latency (filter out NULLs)
    avg_latency = await db.scalar(
        select(func.avg(Message.latency_ms)).where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.latency_ms.isnot(None),
            )
        )
    )
    # P95 latency
    p95_result = await db.execute(
        select(Message.latency_ms)
        .where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.latency_ms.isnot(None),
            )
        )
        .order_by(Message.latency_ms)
    )
    p95_rows = p95_result.scalars().all()
    p95_row = p95_rows[int(len(p95_rows) * 95 // 100)] if p95_rows else None

    # Fallback rate: messages with error / total messages
    error_count = await db.scalar(
        select(func.count(Message.id)).where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.error.isnot(None),
            )
        )
    )
    fallback_rate = (error_count or 0) / (total_messages or 1)

    return {
        "period": {"start": start, "end": end},
        "total_messages": total_messages or 0,
        "total_conversations": total_conversations or 0,
        "avg_latency_ms": float(avg_latency) if avg_latency else None,
        "p95_latency_ms": float(p95_row) if p95_row else None,
        "fallback_rate": round(fallback_rate, 4),
    }


@router.get("/messages")
async def message_volume(
    start: str = Query(...),
    end: str = Query(...),
    interval: str = Query("day", description="hour|day"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Message volume over time grouped by interval."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    result = await db.execute(
        select(
            func.date_trunc("day", Message.created_at).label("bucket"),
            func.count(Message.id).label("count"),
        )
        .where(and_(Message.created_at >= start_dt, Message.created_at <= end_dt))
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = result.all()
    return {"buckets": [{"date": str(r.bucket.date()), "count": r.count} for r in rows]}


@router.get("/latency")
async def latency_percentiles(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """LLM latency percentiles (p50, p95, p99)."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    result = await db.execute(
        select(Message.latency_ms)
        .where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.latency_ms.isnot(None),
            )
        )
        .order_by(Message.latency_ms)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"p50": None, "p95": None, "p99": None}
    n = len(rows)
    return {
        "p50": float(rows[n * 50 // 100]),
        "p95": float(rows[n * 95 // 100]),
        "p99": float(rows[n * 99 // 100]) if n >= 100 else float(rows[-1]),
    }


@router.get("/tools")
async def tool_usage(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Tool usage breakdown."""
    from app.models.tool_call import ToolCall

    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    result = await db.execute(
        select(ToolCall.tool_name, func.count(ToolCall.id))
        .where(and_(ToolCall.created_at >= start_dt, ToolCall.created_at <= end_dt))
        .group_by(ToolCall.tool_name)
    )
    rows = result.all()
    return {"tools": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/fallbacks")
async def fallback_rates(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Fallback rates over time."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    total = await db.scalar(
        select(func.count(Message.id)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt)
        )
    )
    errors = await db.scalar(
        select(func.count(Message.id)).where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.error.isnot(None),
            )
        )
    )
    return {"total": total or 0, "errors": errors or 0, "rate": round((errors or 0) / (total or 1), 4)}


@router.get("/tokens")
async def token_usage(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Token usage summary from messages.token_usage JSON."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    result = await db.execute(
        select(Message.token_usage).where(
            and_(
                Message.created_at >= start_dt,
                Message.created_at <= end_dt,
                Message.token_usage.isnot(None),
            )
        )
    )
    token_usages = [r for r in result.scalars().all() if r]
    total_input = sum(t.get("input_tokens", 0) for t in token_usages)
    total_output = sum(t.get("output_tokens", 0) for t in token_usages)
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "message_count": len(token_usages),
    }
