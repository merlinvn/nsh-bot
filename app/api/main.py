"""FastAPI application entry point for NeoChatPlatform API."""
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.config import api_settings
from app.api.middleware import PIIMaskingFilter, RequestIDMiddleware, StructuredLoggingMiddleware
from app.api.routers import health_router, internal_router, webhooks_router
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
    CORSMiddleware,
    allow_origins=cors_origins,
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


# ---------- Exception handlers ----------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "errors": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions — forward the existing detail."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = detail.get("code", "HTTP_ERROR")
    message = detail.get("message", str(exc.detail))

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        },
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
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "request_id": getattr(request.state, "request_id", None),
        },
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
