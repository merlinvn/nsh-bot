"""Tests for webhook endpoints (POST /webhooks/zalo)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.main import app as main_app
from app.api.routers import webhooks


def create_test_app() -> FastAPI:
    """Create a FastAPI app for testing with correct exception handlers.

    Avoids the lifespan (no RabbitMQ/Redis init) but keeps custom exception handlers.
    """
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    from app.api.middleware import RequestIDMiddleware, StructuredLoggingMiddleware
    from app.api.routers import health_router, internal_router, webhooks_router

    test_app = FastAPI(
        title="NeoChatPlatform API (test)",
        version="1.0.0",
    )

    @test_app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "errors": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @test_app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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

    @test_app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        import pydantic_core
        # Handle HTTPException (including our 401/503 cases)
        if isinstance(exc, HTTPException):
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
        # Handle pydantic ValidationError (raised by model_validate_json inside endpoint body)
        if isinstance(exc, pydantic_core.ValidationError):
            return JSONResponse(
                status_code=422,
                content={
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "errors": exc.errors(),
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

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.add_middleware(StructuredLoggingMiddleware)
    test_app.add_middleware(RequestIDMiddleware)

    test_app.include_router(webhooks_router)
    test_app.include_router(health_router)
    test_app.include_router(internal_router)

    return test_app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient for a test app without lifespan."""
    return TestClient(create_test_app(), raise_server_exceptions=False)


@pytest.fixture
def valid_payload() -> dict:
    """Return a valid Zalo webhook payload."""
    return {
        "event_name": "send_text_message",
        "sender": {"id": "user_12345"},
        "message": {
            "message_id": "msg_abc123",
            "text": "Hello there",
        },
    }


@pytest.fixture
def valid_signature() -> str:
    """Return a valid HMAC-SHA256 signature (mocked as always valid)."""
    return "valid_signature_here"


def create_mock_rabbitmq_channel():
    """Create a mock RabbitMQ channel with mock exchange."""
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel = MagicMock()
    mock_channel.get_exchange = MagicMock(return_value=mock_exchange)
    return mock_channel, mock_exchange


class TestZaloWebhook:
    """Test cases for POST /webhooks/zalo."""

    def test_webhook_with_valid_signature(
        self,
        client: TestClient,
        valid_payload: dict,
        valid_signature: str,
    ) -> None:
        """Valid request with correct signature returns 200 and enqueues message."""
        body_bytes = json.dumps(valid_payload).encode()
        mock_channel, _ = create_mock_rabbitmq_channel()

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=True),
            patch.object(webhooks, "check_and_set_message_id", new_callable=AsyncMock, return_value=True),
            patch("app.api.services.queue.publish_to_queue", new_callable=AsyncMock),
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": valid_signature,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_webhook_with_invalid_signature(
        self,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Request with invalid signature returns 401."""
        body_bytes = json.dumps(valid_payload).encode()
        mock_channel, _ = create_mock_rabbitmq_channel()

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=False),
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": "invalid_signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 401
            data = response.json()
            assert data["code"] == "INVALID_SIGNATURE"

    def test_webhook_duplicate_message(
        self,
        client: TestClient,
        valid_payload: dict,
        valid_signature: str,
    ) -> None:
        """Duplicate message returns 200 but does NOT publish to queue."""
        body_bytes = json.dumps(valid_payload).encode()
        mock_channel, _ = create_mock_rabbitmq_channel()

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=True),
            patch.object(webhooks, "check_and_set_message_id", new_callable=AsyncMock, return_value=False),
            patch("app.api.services.queue.publish_to_queue", new_callable=AsyncMock) as mock_publish,
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": valid_signature,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            assert response.json()["success"] is True
            mock_publish.assert_not_called()

    def test_webhook_missing_sender_id(self, client: TestClient) -> None:
        """Payload missing sender.id returns 422 validation error."""
        invalid_payload = {
            "event_name": "send_text_message",
            # missing "sender"
            "message": {
                "message_id": "msg_abc123",
                "text": "Hello",
            },
        }
        body_bytes = json.dumps(invalid_payload).encode()
        mock_channel, _ = create_mock_rabbitmq_channel()

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=True),
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": "any_signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 422
            data = response.json()
            assert data["code"] == "VALIDATION_ERROR"

    def test_webhook_missing_message_id(self, client: TestClient) -> None:
        """Payload missing message.message_id returns 422 validation error."""
        invalid_payload = {
            "event_name": "send_text_message",
            "sender": {"id": "user_12345"},
            "message": {
                # missing "message_id"
                "text": "Hello",
            },
        }
        body_bytes = json.dumps(invalid_payload).encode()
        mock_channel, _ = create_mock_rabbitmq_channel()

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=True),
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": "any_signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 422
            data = response.json()
            assert data["code"] == "VALIDATION_ERROR"

    def test_webhook_queue_unavailable_returns_503(
        self,
        client: TestClient,
        valid_payload: dict,
        valid_signature: str,
    ) -> None:
        """When RabbitMQ publish fails, endpoint returns 503."""
        body_bytes = json.dumps(valid_payload).encode()
        mock_channel, mock_exchange = create_mock_rabbitmq_channel()
        mock_exchange.publish.side_effect = Exception("Connection refused")

        with (
            patch.object(webhooks, "verify_zalo_signature", return_value=True),
            patch.object(webhooks, "check_and_set_message_id", new_callable=AsyncMock, return_value=True),
            patch("app.api.dependencies.get_rabbitmq_channel", new_callable=AsyncMock, return_value=mock_channel),
        ):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": valid_signature,
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 503
            data = response.json()
            assert data["code"] == "QUEUE_UNAVAILABLE"
