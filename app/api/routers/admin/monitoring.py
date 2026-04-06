"""Admin monitoring router for system health and metrics."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.models.admin_user import AdminUser
from app.models.conversation import Conversation
from app.models.message import Message

router = APIRouter(prefix="/admin/monitoring", tags=["admin:monitoring"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Detailed health check: DB, Redis, RabbitMQ."""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = False
    try:
        from app.core.redis import get_redis_client

        r = await get_redis_client()
        await r.ping()
        redis_ok = True
    except Exception:
        pass

    rabbitmq_ok = False
    try:
        from app.core.rabbitmq import get_rabbitmq_channel

        ch = await get_rabbitmq_channel()
        rabbitmq_ok = ch.is_open
    except Exception:
        pass

    return {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "rabbitmq": "ok" if rabbitmq_ok else "error",
    }


@router.get("/metrics")
async def metrics(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """JSON metrics for UI dashboard (not Prometheus format)."""
    total_convs = await db.scalar(select(func.count(Conversation.id)))
    total_msgs = await db.scalar(select(func.count(Message.id)))
    avg_latency = await db.scalar(
        select(func.avg(Message.latency_ms)).where(Message.latency_ms.isnot(None))
    )

    return {
        "total_conversations": total_convs or 0,
        "total_messages": total_msgs or 0,
        "avg_latency_ms": float(avg_latency) if avg_latency else None,
    }


@router.get("/workers")
async def worker_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Worker status (up/down, last heartbeat)."""
    # TODO: Integrate with worker heartbeat mechanism (could use Redis keys)
    return {"workers": []}


@router.get("/queues")
async def queue_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Queue depths and message counts."""
    # TODO: Query RabbitMQ management API or use rabbitmqctl
    return {"queues": []}
