"""Tests for webhook endpoints (POST /webhooks/zalo)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routers import webhooks


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


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


def make_webhook_headers(signature: str, body: bytes) -> dict:
    """Build request headers for the webhook endpoint."""
    return {"X-Zalo-Signature": signature, "Content-Type": "application/json"}


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

        # Mock signature verification to return True
        with patch.object(webhooks, "verify_zalo_signature", return_value=True):
            # Mock Redis dedup check — message is new (not duplicate)
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value="OK")  # new message

            # Mock RabbitMQ channel
            mock_channel = AsyncMock()
            mock_channel.get_exchange = AsyncMock(
                return_value=AsyncMock(publish=AsyncMock())
            )

            # Override dependencies
            app.dependency_overrides[webhooks.get_redis] = lambda: mock_redis
            app.dependency_overrides[webhooks.get_rabbitmq] = lambda: mock_channel

            try:
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
            finally:
                app.dependency_overrides.clear()

    def test_webhook_with_invalid_signature(
        self,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Request with invalid signature returns 401."""
        body_bytes = json.dumps(valid_payload).encode()

        # Mock signature verification to return False
        with patch.object(webhooks, "verify_zalo_signature", return_value=False):
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

        with patch.object(webhooks, "verify_zalo_signature", return_value=True):
            # Mock Redis dedup — message already exists (is duplicate)
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value=None)  # None = already exists

            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            mock_exchange.publish = AsyncMock()
            mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

            app.dependency_overrides[webhooks.get_redis] = lambda: mock_redis
            app.dependency_overrides[webhooks.get_rabbitmq] = lambda: mock_channel

            try:
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
                # Queue publish should NOT have been called
                mock_exchange.publish.assert_not_called()
            finally:
                app.dependency_overrides.clear()

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

        with patch.object(webhooks, "verify_zalo_signature", return_value=True):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": "any_signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 422

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

        with patch.object(webhooks, "verify_zalo_signature", return_value=True):
            response = client.post(
                "/webhooks/zalo",
                content=body_bytes,
                headers={
                    "X-Zalo-Signature": "any_signature",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 422

    def test_webhook_queue_unavailable_returns_503(
        self,
        client: TestClient,
        valid_payload: dict,
        valid_signature: str,
    ) -> None:
        """When RabbitMQ publish fails, endpoint returns 503."""
        body_bytes = json.dumps(valid_payload).encode()

        with patch.object(webhooks, "verify_zalo_signature", return_value=True):
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value="OK")

            # Mock RabbitMQ publish to raise an exception
            mock_channel = AsyncMock()
            mock_exchange = AsyncMock()
            mock_exchange.publish = AsyncMock(side_effect=Exception("Connection refused"))
            mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

            app.dependency_overrides[webhooks.get_redis] = lambda: mock_redis
            app.dependency_overrides[webhooks.get_rabbitmq] = lambda: mock_channel

            try:
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
            finally:
                app.dependency_overrides.clear()
