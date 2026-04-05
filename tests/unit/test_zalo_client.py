"""Tests for ZaloClient."""
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
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


def _make_mock_response(status: int, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response with the given status and JSON body."""
    return httpx.Response(status, json=json_data or {})


def _make_mock_async_client(response: httpx.Response) -> MagicMock:
    """Create a mock AsyncClient that returns the given response from .post()."""
    mock = MagicMock()
    mock.post = AsyncMock(return_value=response)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_send_text_success(client: ZaloClient) -> None:
    response = _make_mock_response(200, {"error": 0, "message": "OK", "data": {"msg_id": "12345"}})
    mock_instance = _make_mock_async_client(response)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        result = await client.send_text("user_123", "Hello world")
        assert result["error"] == 0
        assert result["message"] == "OK"
        assert result["data"]["msg_id"] == "12345"


@pytest.mark.asyncio
async def test_send_text_http_429_raises_retryable(client: ZaloClient) -> None:
    response = _make_mock_response(429, {"error": 429, "message": "Rate limited"})
    mock_instance = _make_mock_async_client(response)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")
        assert "429" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_http_5xx_raises_retryable(client: ZaloClient) -> None:
    response = _make_mock_response(500, {"error": 500, "message": "Internal Server Error"})
    mock_instance = _make_mock_async_client(response)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")
        assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_http_4xx_raises_non_retryable(client: ZaloClient) -> None:
    response = _make_mock_response(400, {"error": 400, "message": "Bad Request"})
    mock_instance = _make_mock_async_client(response)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        with pytest.raises(NonRetryableError) as exc_info:
            await client.send_text("user_123", "Hello")
        assert "400" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_text_network_timeout_raises_retryable(client: ZaloClient) -> None:
    mock_instance = MagicMock()
    mock_instance.__aenter__ = AsyncMock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        with pytest.raises(RetryableError) as exc_info:
            await client.send_text("user_123", "Hello")
        assert "Network error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_correct_headers_and_body(client: ZaloClient) -> None:
    captured_post = AsyncMock(return_value=_make_mock_response(200, {"error": 0}))
    mock_instance = MagicMock()
    mock_instance.post = captured_post
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=mock_instance):
        await client.send_text("user_999", "Test message")

    captured_post.assert_called_once()
    call_args = captured_post.call_args

    # Verify URL
    assert call_args.args[0] == "https://openapi.zalo.me/v3.0/oa/message/cs"

    # Verify headers — client uses access_token (not Authorization: Bearer)
    headers = call_args.kwargs.get("headers", {})
    assert headers["access_token"] == "test_access_token"
    assert headers["Content-Type"] == "application/json"

    # Verify body
    body = call_args.kwargs.get("json", {})
    assert body["recipient"]["user_id"] == "user_999"
    assert body["message"]["text"] == "Test message"
