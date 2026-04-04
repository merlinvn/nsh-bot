"""Health check endpoints."""
import time

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.schemas.health import HealthResponse, HealthStatus
from app.core.database import check_db_health
from app.core.rabbitmq import check_rabbitmq_health
from app.core.redis import check_redis_health

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    summary="Liveness probe",
    description="Returns alive status with no dependency checks.",
)
async def health_live() -> dict:
    """Kubernetes liveness probe — always returns alive."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Checks PostgreSQL, Redis, and RabbitMQ connectivity.",
    responses={
        200: {"description": "All checks passed"},
        503: {"description": "One or more checks failed"},
    },
)
async def health_ready() -> JSONResponse:
    """Kubernetes readiness probe — verifies all dependencies."""
    checks: dict[str, HealthStatus] = {}
    all_healthy = True

    # Database check
    start = time.perf_counter()
    db_ok = await check_db_health()
    db_latency = (time.perf_counter() - start) * 1000
    checks["postgresql"] = HealthStatus(
        status="ok" if db_ok else "error",
        latency_ms=round(db_latency, 2),
        error=None if db_ok else "Connection failed",
    )
    if not db_ok:
        all_healthy = False

    # Redis check
    start = time.perf_counter()
    redis_ok = await check_redis_health()
    redis_latency = (time.perf_counter() - start) * 1000
    checks["redis"] = HealthStatus(
        status="ok" if redis_ok else "error",
        latency_ms=round(redis_latency, 2),
        error=None if redis_ok else "Connection failed",
    )
    if not redis_ok:
        all_healthy = False

    # RabbitMQ check
    start = time.perf_counter()
    rabbitmq_ok = await check_rabbitmq_health()
    rabbitmq_latency = (time.perf_counter() - start) * 1000
    checks["rabbitmq"] = HealthStatus(
        status="ok" if rabbitmq_ok else "error",
        latency_ms=round(rabbitmq_latency, 2),
        error=None if rabbitmq_ok else "Connection failed",
    )
    if not rabbitmq_ok:
        all_healthy = False

    overall_status = "ready" if all_healthy else "degraded"
    response = HealthResponse(status=overall_status, checks=checks)

    if not all_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )

    return JSONResponse(content=response.model_dump(mode="json"))
