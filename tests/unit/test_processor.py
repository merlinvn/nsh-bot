"""Tests for outbound message processor."""
import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.outbound.processor import (
    MAX_RETRIES,
    BACKOFF_BASE,
    process_outbound,
)
from app.workers.outbound.zalo_client import NonRetryableError, RetryableError


@pytest.fixture
def message_payload() -> dict:
    return {
        "user_id": "user_123",
        "text": "Hello world",
        "message_db_id": str(uuid4()),
    }


@pytest.fixture
def mock_db_session():
    """Mock db_session context manager, yielding the mock session."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    @asynccontextmanager
    async def _db_cm():
        yield mock_session

    patcher = patch("app.workers.outbound.processor.db_session", _db_cm)
    patcher.start()
    yield mock_session
    patcher.stop()


@pytest.mark.asyncio
async def test_success_on_first_attempt(message_payload: dict, mock_db_session: AsyncMock) -> None:
    """When send_text succeeds on first try, one delivery attempt is saved."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(return_value={"error": 0, "message": "OK"})

    with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
        await process_outbound(message_payload)

    mock_instance.send_text.assert_called_once_with(
        message_payload["user_id"], message_payload["text"]
    )
    assert mock_db_session.execute.call_count == 1
    stmt = mock_db_session.execute.call_args.args[0]
    # Extract values from the insert statement
    values = {col.key: val.value if hasattr(val, "value") else val
               for col, val in stmt._values.items()}
    assert values["status"] == "success"
    assert values["attempt_no"] == 1


@pytest.mark.asyncio
async def test_retry_on_429_then_succeeds(
    message_payload: dict,
    mock_db_session: AsyncMock,
) -> None:
    """On 429, processor retries and succeeds on second attempt."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )

    with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
        await process_outbound(message_payload)

    assert mock_instance.send_text.call_count == 2
    assert mock_db_session.execute.call_count == 2

    # First attempt: failed
    stmt1 = mock_db_session.execute.call_args_list[0].args[0]
    vals1 = {col.key: val.value if hasattr(val, "value") else val
             for col, val in stmt1._values.items()}
    assert vals1["status"] == "failed"
    assert vals1["attempt_no"] == 1

    # Second attempt: success
    stmt2 = mock_db_session.execute.call_args_list[1].args[0]
    vals2 = {col.key: val.value if hasattr(val, "value") else val
             for col, val in stmt2._values.items()}
    assert vals2["status"] == "success"
    assert vals2["attempt_no"] == 2


@pytest.mark.asyncio
async def test_retry_on_5xx_then_fails_after_max(
    message_payload: dict,
    mock_db_session: AsyncMock,
) -> None:
    """On 5xx, processor retries MAX_RETRIES times then raises RetryableError."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(
        side_effect=RetryableError("Server error: 500")
    )

    with pytest.raises(RetryableError):
        with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
            await process_outbound(message_payload)

    assert mock_instance.send_text.call_count == MAX_RETRIES
    assert mock_db_session.execute.call_count == MAX_RETRIES

    for i in range(MAX_RETRIES):
        stmt = mock_db_session.execute.call_args_list[i].args[0]
        vals = {col.key: val.value if hasattr(val, "value") else val
                for col, val in stmt._values.items()}
        assert vals["status"] == "failed"
        assert vals["attempt_no"] == i + 1


@pytest.mark.asyncio
async def test_no_retry_on_non_retryable_error(
    message_payload: dict,
    mock_db_session: AsyncMock,
) -> None:
    """On NonRetryableError (4xx), no retry occurs and function returns."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(
        side_effect=NonRetryableError("Client error: 400")
    )

    with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
        await process_outbound(message_payload)

    mock_instance.send_text.assert_called_once()
    assert mock_db_session.execute.call_count == 1
    stmt = mock_db_session.execute.call_args.args[0]
    vals = {col.key: val.value if hasattr(val, "value") else val
             for col, val in stmt._values.items()}
    assert vals["status"] == "failed"


@pytest.mark.asyncio
async def test_exponential_backoff_timing(
    message_payload: dict,
    mock_db_session: AsyncMock,
) -> None:
    """After 429, processor waits ~2s before retry."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )

    with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
        start = time.monotonic()
        await process_outbound(message_payload)
        elapsed = time.monotonic() - start

    expected = BACKOFF_BASE**1
    assert elapsed >= expected - 0.1, (
        f"Expected ~{expected}s backoff, got {elapsed:.2f}s"
    )
    assert elapsed < expected + 1.0, (
        f"Backoff took too long: {elapsed:.2f}s"
    )


@pytest.mark.asyncio
async def test_exponential_backoff_third_attempt(
    message_payload: dict,
    mock_db_session: AsyncMock,
) -> None:
    """With two failures then success, waits 2s + 4s = 6s total."""
    mock_instance = MagicMock()
    mock_instance.send_text = AsyncMock(
        side_effect=[
            RetryableError("Rate limited (429)"),
            RetryableError("Rate limited (429)"),
            {"error": 0, "message": "OK"},
        ]
    )

    with patch("app.workers.outbound.processor.ZaloClient", return_value=mock_instance):
        start = time.monotonic()
        await process_outbound(message_payload)
        elapsed = time.monotonic() - start

    expected = BACKOFF_BASE**1 + BACKOFF_BASE**2
    assert elapsed >= expected - 0.1, (
        f"Expected ~{expected}s total backoff, got {elapsed:.2f}s"
    )
    assert elapsed < expected + 2.0, (
        f"Backoff took too long: {elapsed:.2f}s"
    )
