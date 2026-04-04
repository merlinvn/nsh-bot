"""Tests for outbound message processor."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.outbound.processor import (
    MAX_RETRIES,
    BACKOFF_BASE,
    process_outbound,
    save_delivery_attempt,
)
from app.workers.outbound.zalo_client import (
    NonRetryableError,
    RetryableError,
    ZaloClient,
)


@pytest.fixture
def message_payload() -> dict:
    return {
        "user_id": "user_123",
        "text": "Hello world",
        "message_db_id": str(uuid4()),
    }


@pytest.fixture
def mock_db_session():
    """Mock db_session that commits without touching the real DB."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    patcher = patch(
        "app.workers.outbound.processor.db_session",
        return_value=mock_session,
    )
    mocked = patcher.start()
    mocked.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mocked.return_value.__aexit__ = AsyncMock(return_value=None)
    yield mock_session
    patcher.stop()


@pytest.fixture
def mock_zalo_client():
    with patch("app.workers.outbound.processor.ZaloClient") as MockClient:
        yield MockClient


@pytest.mark.asyncio
async def test_success_on_first_attempt(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    mock_instance.send_text = AsyncMock(return_value={"error": 0, "message": "OK"})
    mock_zalo_client.return_value = mock_instance

    await process_outbound(message_payload)

    # Should have called send_text once
    mock_instance.send_text.assert_called_once_with(
        message_payload["user_id"], message_payload["text"]
    )

    # Should have saved one delivery attempt with status=success
    assert mock_db_session.execute.call_count == 1
    call_args = mock_db_session.execute.call_args
    stmt = call_args.args[0]
    # Verify the insert values
    assert call_args.args[1]["status"] == "success"


@pytest.mark.asyncio
async def test_retry_on_429_then_succeeds(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    # First call raises 429, second succeeds
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )
    mock_zalo_client.return_value = mock_instance

    await process_outbound(message_payload)

    # Should have called send_text twice
    assert mock_instance.send_text.call_count == 2

    # Should have saved 2 delivery attempts
    assert mock_db_session.execute.call_count == 2

    # First attempt: failed (429)
    first_call_args = mock_db_session.execute.call_args_list[0]
    assert first_call_args.args[1]["status"] == "failed"
    assert first_call_args.args[1]["attempt_no"] == 1

    # Second attempt: success
    second_call_args = mock_db_session.execute.call_args_list[1]
    assert second_call_args.args[1]["status"] == "success"
    assert second_call_args.args[1]["attempt_no"] == 2


@pytest.mark.asyncio
async def test_retry_on_5xx_then_fails_after_max(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    # All 3 calls fail with 500
    mock_instance.send_text = AsyncMock(
        side_effect=RetryableError("Server error: 500")
    )
    mock_zalo_client.return_value = mock_instance

    with pytest.raises(RetryableError):
        await process_outbound(message_payload)

    # Should have exhausted all retries
    assert mock_instance.send_text.call_count == MAX_RETRIES

    # Should have saved 3 failed delivery attempts
    assert mock_db_session.execute.call_count == MAX_RETRIES

    for i in range(MAX_RETRIES):
        call_args = mock_db_session.execute.call_args_list[i]
        assert call_args.args[1]["status"] == "failed"
        assert call_args.args[1]["attempt_no"] == i + 1


@pytest.mark.asyncio
async def test_no_retry_on_non_retryable_error(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    # 400 raises NonRetryableError
    mock_instance.send_text = AsyncMock(
        side_effect=NonRetryableError("Client error: 400")
    )
    mock_zalo_client.return_value = mock_instance

    # Should return without raising (non-retryable, logs and returns)
    await process_outbound(message_payload)

    # Should have called send_text once
    mock_instance.send_text.assert_called_once()

    # Should have saved 1 failed delivery attempt
    assert mock_db_session.execute.call_count == 1
    call_args = mock_db_session.execute.call_args
    assert call_args.args[1]["status"] == "failed"


@pytest.mark.asyncio
async def test_exponential_backoff_timing(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    # 429 on first, success on second
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )
    mock_zalo_client.return_value = mock_instance

    start = time.monotonic()
    await process_outbound(message_payload)
    elapsed = time.monotonic() - start

    # Should have waited ~BACKOFF_BASE**1 = 2s between attempt 1 and 2
    assert elapsed >= BACKOFF_BASE**1 - 0.1, (
        f"Expected at least {BACKOFF_BASE**1}s backoff, got {elapsed:.2f}s"
    )
    assert elapsed < BACKOFF_BASE**1 + 1.0, (
        f"Backoff took too long: {elapsed:.2f}s (expected ~{BACKOFF_BASE**1}s)"
    )


@pytest.mark.asyncio
async def test_exponential_backoff_third_attempt(
    message_payload: dict,
    mock_db_session: MagicMock,
    mock_zalo_client: MagicMock,
) -> None:
    mock_instance = AsyncMock()
    # 429 on first two attempts, success on third
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )
    mock_zalo_client.return_value = mock_instance

    start = time.monotonic()
    await process_outbound(message_payload)
    elapsed = time.monotonic() - start

    # Should have waited: 2s (between 1→2) + 4s (between 2→3) = 6s total
    expected_backoff = BACKOFF_BASE**1 + BACKOFF_BASE**2
    assert elapsed >= expected_backoff - 0.1, (
        f"Expected at least {expected_backoff}s total backoff, got {elapsed:.2f}s"
    )
    assert elapsed < expected_backoff + 2.0, (
        f"Backoff took too long: {elapsed:.2f}s (expected ~{expected_backoff}s)"
    )
