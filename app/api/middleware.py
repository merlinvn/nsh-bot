"""Middleware for the FastAPI application."""
import logging
import re
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("neochat.api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID header to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class PIIMaskingFilter(logging.Filter):
    """Masks phone numbers and tokens in log records."""

    PHONE_RE = re.compile(r"\b\d{8,15}\b")
    TOKEN_RE = re.compile(r"(?i)(bearer|token|secret|key)[\s:=]+[\w\-\.]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._mask(record.msg)
        if record.args:
            record.args = tuple(
                self._mask(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True

    def _mask(self, text: str) -> str:
        text = self.TOKEN_RE.sub(r"\1[REDACTED]", text)
        # Mask sequences of 8+ digits (phone numbers)
        text = self.PHONE_RE.sub(lambda m: "*" * len(m.group()), text)
        return text


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request/response details in structured JSON format with correlation_id."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        start_time = time.perf_counter()

        logger.info(
            "request_start",
            extra={
                "event": "request_start",
                "method": request.method,
                "path": request.url.path,
                "request_id": request_id,
                "client_ip": request.client.host if request.client else None,
            },
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "request_complete",
                extra={
                    "event": "request_complete",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                },
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "request_error",
                extra={
                    "event": "request_error",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                    "error": str(exc),
                },
            )
            raise
