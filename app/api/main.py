"""FastAPI application entry point for NeoChatPlatform API."""
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware as FastAPICORSMiddleware
from fastapi.responses import JSONResponse

from app.api.config import admin_settings, api_settings
from app.api.middleware import PIIMaskingFilter, RequestIDMiddleware, StructuredLoggingMiddleware
from app.api.routers import auth_router, health_router, internal_router, webhooks_router
from app.api.routers.admin import (
    analytics_router,
    auth_router as admin_auth_router,
    conversations_router,
    evaluations_router,
    monitoring_router,
    playground_router,
    prompts_router,
    zalo_tokens_router,
    zalo_users_router,
)
from app.core.rabbitmq import close_rabbitmq, get_rabbitmq_channel
from app.core.redis import close_redis_client

# Configure root logger
logging.basicConfig(
    level=getattr(logging, api_settings.log_level.upper(), logging.INFO),
    format="%(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("neochat.api")

# Add PII masking filter to root logger
for handler in _logger.handlers:
    handler.addFilter(PIIMaskingFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager — startup and shutdown."""
    # Startup: warm up connections
    _logger.info("startup", extra={"event": "startup", "service": "api"})
    try:
        await get_rabbitmq_channel()
        _logger.info("rabbitmq_connected", extra={"event": "rabbitmq_connected"})
    except Exception as exc:
        _logger.warning("rabbitmq_startup_failed", extra={"event": "rabbitmq_startup_failed", "error": str(exc)})

    yield

    # Shutdown: close connections gracefully
    _logger.info("shutdown", extra={"event": "shutdown", "service": "api"})
    await close_rabbitmq()
    await close_redis_client()
    _logger.info("shutdown_complete", extra={"event": "shutdown_complete"})


# Build CORS origins list
cors_origins = [o.strip() for o in api_settings.cors_origins.split(",") if o.strip()]
# Add admin CORS origins
admin_cors_origins = [o.strip() for o in admin_settings.admin_cors_origins.split(",") if o.strip()]
all_cors_origins = list(set(cors_origins + admin_cors_origins))

app = FastAPI(
    title="NeoChatPlatform API",
    description="FastAPI webhook and admin API for NeoChatPlatform Phase 1 — Zalo chatbot agent.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware stack (applied in reverse order of declaration)
app.add_middleware(
    FastAPICORSMiddleware,
    allow_origins=all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(webhooks_router)
app.include_router(health_router)
app.include_router(internal_router)
app.include_router(auth_router)

# Include admin routers
app.include_router(admin_auth_router)
app.include_router(prompts_router)
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(evaluations_router)
app.include_router(playground_router)
app.include_router(zalo_tokens_router)
app.include_router(zalo_users_router)
app.include_router(monitoring_router)


# ---------- Exception handlers ----------


# CORS headers — used by exception handlers to ensure error responses
# always include CORS headers even when the middleware doesn't intercept.
ALLOWED_ORIGINS = list(
    set(
        [
            o.strip()
            for o in (api_settings.cors_origins.split(",") + admin_settings.admin_cors_origins.split(","))
            if o.strip()
        ]
    )
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Create a JSON error response with explicit CORS headers."""
    content = {"code": code, "message": message, "request_id": request_id}
    if extra:
        content.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={
            "Access-Control-Allow-Origin": ", ".join(ALLOWED_ORIGINS),
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    return _error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        request_id=getattr(request.state, "request_id", None),
        extra={"errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions — forward the existing detail."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = detail.get("code", "HTTP_ERROR")
    message = detail.get("message", str(exc.detail))

    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request_id=getattr(request.state, "request_id", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any unhandled exceptions."""
    _logger.exception(
        "unhandled_exception",
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return _error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
        request_id=getattr(request.state, "request_id", None),
    )


# Root endpoint
@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint — basic info about the API."""
    return {
        "service": "NeoChatPlatform API",
        "version": "1.0.0",
        "status": "running",
    }
