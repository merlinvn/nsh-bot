"""Admin monitoring router for system health and metrics."""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import api_settings
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
    """Worker status from Redis heartbeat keys."""
    import redis.asyncio as redis
    from app.core.redis import get_redis_client

    r = await get_redis_client()
    workers = []
    async for key in r.scan_iter(match="worker:heartbeat:*"):
        data = await r.get(key)
        if data:
            import json
            info = json.loads(data)
            workers.append({
                "name": key.decode().replace("worker:heartbeat:", ""),
                "status": info.get("status", "unknown"),
                "last_seen": info.get("timestamp"),
            })
    return {"workers": workers}


@router.get("/queues")
async def queue_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Queue depths and message counts via RabbitMQ management API."""
    mgmt_url = api_settings.rabbitmq_management_url
    queues = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{mgmt_url}/api/queues")
            if resp.status_code == 200:
                all_queues = resp.json()
                # Filter to only neochat queues
                for q in all_queues:
                    name = q.get("name", "")
                    if "neochat" in name or name in ("conversation.process", "outbound.send"):
                        queues.append({
                            "name": name,
                            "messages": q.get("messages", 0),
                            "consumers": q.get("consumers", 0),
                            "state": q.get("state", "unknown"),
                        })
    except Exception:
        pass

    return {"queues": queues}
