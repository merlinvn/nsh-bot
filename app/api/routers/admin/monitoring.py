"""Admin monitoring router for system health and metrics."""
import httpx
import json
import time
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import api_settings
from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.conversation import Conversation
from app.models.message import Message
from app.workers.shared.health import HealthStatus, check_all

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
        from app.core.rabbitmq import check_rabbitmq_health

        rabbitmq_ok = await check_rabbitmq_health()
    except Exception:
        pass

    return {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "rabbitmq": "ok" if rabbitmq_ok else "error",
    }


@router.get("/health-detail")
async def health_detail(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Per-service health with latency in ms (uses check_all())."""
    _, results = await check_all()
    services = []
    for r in results:
        if r.status == HealthStatus.HEALTHY:
            status = "ok"
        elif r.status == HealthStatus.UNHEALTHY:
            status = "error"
        else:
            status = "degraded"
        services.append({
            "name": r.name,
            "status": status,
            "latency_ms": r.latency_ms,
        })
    return {"services": services}


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


METRICS_PREV_KEY = "monitoring:metrics:prev"
METRICS_PREV_TTL = 60


@router.get("/metrics-trend")
async def metrics_trend(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Current metrics + previous values from Redis for trend comparison."""
    from app.core.redis import get_redis_client

    total_convs = await db.scalar(select(func.count(Conversation.id)))
    total_msgs = await db.scalar(select(func.count(Message.id)))
    avg_latency = await db.scalar(
        select(func.avg(Message.latency_ms)).where(Message.latency_ms.isnot(None))
    )

    current = {
        "total_conversations": total_convs or 0,
        "total_messages": total_msgs or 0,
        "avg_latency_ms": float(avg_latency) if avg_latency else None,
    }

    r = await get_redis_client()
    prev_raw = await r.get(METRICS_PREV_KEY)
    previous = json.loads(prev_raw) if prev_raw else current

    # Update previous for next refresh
    await r.set(METRICS_PREV_KEY, json.dumps(current), ex=METRICS_PREV_TTL)

    return {"current": current, "previous": previous}


@router.get("/workers")
async def worker_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Worker status from Redis heartbeat keys with age and alive/stale/dead status."""
    from app.core.redis import get_redis_client

    r = await get_redis_client()
    workers = []
    now = time.time()
    async for key in r.scan_iter(match="worker:heartbeat:*"):
        data = await r.get(key)
        if data:
            info = json.loads(data)
            name = key.replace("worker:heartbeat:", "")
            last_seen = info.get("timestamp")
            age_seconds = int(now - last_seen) if last_seen else None
            if age_seconds is not None:
                if age_seconds < 60:
                    status = "alive"
                elif age_seconds < 300:
                    status = "stale"
                else:
                    status = "dead"
            else:
                status = "dead"
            workers.append({
                "name": name,
                "status": status,
                "last_seen": last_seen,
                "age_seconds": age_seconds,
            })
    return {"workers": workers}


@router.get("/queues")
async def queue_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Queue depths, message age, and rates via RabbitMQ management API."""
    mgmt_url = api_settings.rabbitmq_management_url
    queues = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{mgmt_url}/api/queues")
            if resp.status_code == 200:
                all_queues = resp.json()
                for q in all_queues:
                    name = q.get("name", "")
                    if "neochat" in name or name in ("conversation.process", "outbound.send"):
                        msgs = q.get("messages", 0)
                        # message_stats contains rate info
                        stats = q.get("message_stats", {}) or {}
                        # messages_details has age distribution: [min, 25pct, median, 75pct, max] in ms
                        age_detail = q.get("messages_details", []) or []
                        oldest_ms = age_detail[4] if len(age_detail) >= 5 else None

                        queues.append({
                            "name": name,
                            "messages": msgs,
                            "consumers": q.get("consumers", 0),
                            "state": q.get("state", "unknown"),
                            # Rate: messages published per second (total, not rate per sec from stats)
                            "publish_rate": stats.get("publish", 0),
                            "deliver_rate": stats.get("deliver", 0),
                            # Oldest message age in ms (None if queue is empty)
                            "oldest_message_age_ms": oldest_ms if msgs > 0 else None,
                        })
    except Exception:
        pass

    return {"queues": queues}


@router.get("/queues/{vhost}/{queue_name}/messages")
async def queue_peek_messages(
    vhost: str,
    queue_name: str,
    count: int = 10,
    _: AdminUser = Depends(get_current_admin_user),
):
    """Peek at messages in a queue without consuming them.

    Returns up to `count` messages (default 10, max 100).
    Uses RabbitMQ's /api/queues/{vhost}/{name}/get endpoint with ack_requeue_false
    (messages are discarded after being read — this is a peek, not a consume).
    """
    mgmt_url = api_settings.rabbitmq_management_url
    import urllib.parse
    vhost_encoded = urllib.parse.quote(vhost, safe="")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{mgmt_url}/api/queues/{vhost_encoded}/{queue_name}/get",
                json={
                    "count": min(count, 100),
                    "ackmode": "ack_requeue_false",
                    "encoding": "auto",
                },
            )
            if resp.status_code == 404:
                return {"messages": [], "error": "Queue not found"}
            if resp.status_code != 200:
                return {"messages": [], "error": f"RabbitMQ error: {resp.status_code}"}
            raw_messages = resp.json()
            messages = []
            for m in raw_messages:
                payload = m.get("payload", "")
                try:
                    import json as _json
                    parsed = _json.loads(payload)
                except Exception:
                    parsed = {"raw": payload[:500]}
                messages.append({
                    "routing_key": m.get("routing_key", ""),
                    "message_id": m.get("message_id", ""),
                    "timestamp": m.get("timestamp"),
                    "payload": parsed,
                })
            return {"messages": messages}
    except Exception as e:
        return {"messages": [], "error": str(e)}
