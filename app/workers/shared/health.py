"""Health check helpers for workers."""
import asyncio
import time
from dataclasses import dataclass
from enum import Enum


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: int | None = None


async def check_postgres() -> HealthCheckResult:
    from app.core.database import check_db_health

    start = time.monotonic()
    try:
        healthy = await check_db_health()
        latency_ms = int((time.monotonic() - start) * 1000)
        if healthy:
            return HealthCheckResult(name="postgres", status=HealthStatus.HEALTHY, latency_ms=latency_ms)
        return HealthCheckResult(
            name="postgres",
            status=HealthStatus.UNHEALTHY,
            message="DB health check returned False",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return HealthCheckResult(
            name="postgres",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
            latency_ms=latency_ms,
        )


async def check_redis() -> HealthCheckResult:
    from app.core.redis import check_redis_health

    start = time.monotonic()
    try:
        healthy = await check_redis_health()
        latency_ms = int((time.monotonic() - start) * 1000)
        if healthy:
            return HealthCheckResult(name="redis", status=HealthStatus.HEALTHY, latency_ms=latency_ms)
        return HealthCheckResult(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message="Redis health check returned False",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return HealthCheckResult(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
            latency_ms=latency_ms,
        )


async def check_rabbitmq() -> HealthCheckResult:
    from app.core.rabbitmq import check_rabbitmq_health

    start = time.monotonic()
    try:
        healthy = await check_rabbitmq_health()
        latency_ms = int((time.monotonic() - start) * 1000)
        if healthy:
            return HealthCheckResult(name="rabbitmq", status=HealthStatus.HEALTHY, latency_ms=latency_ms)
        return HealthCheckResult(
            name="rabbitmq",
            status=HealthStatus.UNHEALTHY,
            message="RabbitMQ health check returned False",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return HealthCheckResult(
            name="rabbitmq",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
            latency_ms=latency_ms,
        )


async def check_all() -> tuple[HealthStatus, list[HealthCheckResult]]:
    """Run all health checks and return combined status."""
    results = await asyncio.gather(
        check_postgres(),
        check_redis(),
        check_rabbitmq(),
    )

    statuses = [r.status for r in results]
    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall = HealthStatus.HEALTHY
    elif any(s == HealthStatus.UNHEALTHY for s in statuses):
        overall = HealthStatus.UNHEALTHY
    else:
        overall = HealthStatus.DEGRADED

    return overall, list(results)
