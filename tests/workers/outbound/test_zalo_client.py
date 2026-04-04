"""Tests for ZaloClient."""
from aioresponses import aioresponses
import pytest

from app.workers.outbound.zalo_client import (
    NonRetryableError,
    RetryableError,
    ZaloClient,
)


@pytest.fixture
def client() -> ZaloClient:
    return ZaloClient(
        app_id="test_app_id",
        app_secret="test_app_secret",
        access_token="test_access_token",
        oa_id="test_oa_id",
    )


@pytest.mark.asyncio
async def test_send_text_success(client: ZaloClient) -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=200,
            payload={"error": 0, "message": "OK", "data": {"msg_id": "12345"}},
        )

        result = await client.send_text("user_123", "Hello world")

        assert result["error"] == 0
        assert result["message"] == "OK"
        assert result["data"]["msg_id"] == "12345"


@pytest.mark.asyncio
async def test_send_text_http_429_raises_retryable(client: ZaloClient) -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=429,
            payload={"error": 429, "message": "Rate limited"},
        )

        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")

        assert "429" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_http_5xx_raises_retryable(client: ZaloClient) -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=500,
            payload={"error": 500, "message": "Internal Server Error"},
        )

        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")

        assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_http_4xx_raises_non_retryable(client: ZaloClient) -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=400,
            payload={"error": 400, "message": "Bad Request"},
        )

        with pytest.raises(NonRetryableError) as exc_info:
            await client.send_text("user_123", "Hello")

        assert "400" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_network_timeout_raises_retryable(client: ZaloClient) -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            exception=TimeoutError("Connection timed out"),
        )

        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")

        assert "Network error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_correct_headers_and_body(client: ZaloClient) -> None:
    captured_request: dict = {}

    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=200,
            payload={"error": 0, "message": "OK"},
            callback=lambda *args, **kwargs: captured_request.update({
                "headers": dict(args[1].headers) if len(args) > 1 else {},
                "body": args[2] if len(args) > 2 else {},
            }) or (200, {}, {"error": 0, "message": "OK"}),
        )

        # Use a callback that captures the request details properly
        async def request_callback(url, method, **kwargs):
            captured_request["headers"] = dict(kwargs.get("headers", {}))
            captured_request["body"] = kwargs.get("json", {})
            return 200, {}, {"error": 0, "message": "OK"}

        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=200,
            payload={"error": 0, "message": "OK"},
        )
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=200,
            payload={"error": 0, "message": "OK"},
            headers={"Authorization": "Bearer test_access_token"},
            json={"recipient": {"user_id": "user_999"}, "message": {"text": "Test message"}},
        )

    # Re-do with proper assertion using aioresponses' built-in assertion
    with aioresponses() as mocked:
        mocked.post(
            "https://openapi.zalo.me/v3.0/oa/message/text",
            status=200,
            payload={"error": 0, "message": "OK"},
        )

        await client.send_text("user_999", "Test message")

        # Verify the request was made with correct URL
        assert mocked.requests
        req_key = list(mocked.requests.keys())[0]
        req = mocked.requests[req_key][0]

        # Check Authorization header
        assert "Authorization" in req.kwargs.headers
        assert req.kwargs.headers["Authorization"] == "Bearer test_access_token"

        # Check body
        assert req.kwargs.json["recipient"]["user_id"] == "user_999"
        assert req.kwargs.json["message"]["text"] == "Test message"
