"""Shared Redis heartbeat for worker liveness monitoring."""

import asyncio
import json
import time

HEARTBEAT_KEY_PREFIX = "worker:heartbeat:"
HEARTBEAT_INTERVAL_SEC = 10


async def publish_heartbeat(name: str, status: str = "running") -> None:
    """Publish a heartbeat to Redis for the given worker name."""
    from app.core.redis import get_redis_client

    key = f"{HEARTBEAT_KEY_PREFIX}{name}"
    data = json.dumps({
        "status": status,
        "timestamp": time.time(),
    })
    r = await get_redis_client()
    # No TTL — stale heartbeats are detected by age, not expiry
    await r.set(key, data)


async def start_heartbeat_loop(worker_name: str, status: str = "running") -> asyncio.Task:
    """Start a background heartbeat loop. Returns the task."""
    async def loop():
        while True:
            try:
                await publish_heartbeat(worker_name, status)
            except Exception:
                pass
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)

    return asyncio.create_task(loop())
