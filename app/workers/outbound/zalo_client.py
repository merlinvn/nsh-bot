"""Zalo API client for sending outbound messages."""
import asyncio
from typing import Any

import httpx

from app.workers.shared.logging import get_logger

logger = get_logger("zalo_client")


class RetryableError(Exception):
    """Error that should be retried: HTTP 429, 5xx, network timeout."""

    pass


class NonRetryableError(Exception):
    """Error that should NOT be retried: HTTP 4xx (except 429)."""

    pass


class ZaloClient:
    """Client for sending messages via the Zalo Official Account API."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        access_token: str,
        oa_id: str,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = access_token
        self.oa_id = oa_id
        self.base_url = "https://openapi.zalo.me"

    async def send_text(self, user_id: str, text: str) -> dict[str, Any]:
        """
        Send a text message to a Zalo user.

        Args:
            user_id: Zalo user ID
            text: Message text

        Returns:
            Zalo API response dict

        Raises:
            RetryableError: On HTTP 429, 5xx, or network timeout
            NonRetryableError: On HTTP 4xx (except 429)
        """
        url = f"{self.base_url}/v3.0/oa/message/text"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "recipient": {"user_id": user_id},
            "message": {"text": text},
        }

        logger.debug("Sending Zalo message", extra={"user_id": user_id, "text": text[:50]})

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, OSError) as e:
            logger.warning("Zalo API network error", extra={"error": str(e)})
            raise RetryableError(f"Network error: {e}") from e

        status = response.status_code

        if status == 200:
            result = response.json()
            logger.info("Zalo message sent", extra={"user_id": user_id})
            return result

        if status == 429:
            logger.warning("Zalo rate limited", extra={"user_id": user_id})
            raise RetryableError(f"Rate limited (429)")

        if 500 <= status < 600:
            logger.warning(
                "Zalo server error",
                extra={"user_id": user_id, "status": status},
            )
            raise RetryableError(f"Server error: {status}")

        # 4xx except 429 — non-retryable
        logger.error(
            "Zalo API client error",
            extra={"user_id": user_id, "status": status, "body": response.text[:200]},
        )
        raise NonRetryableError(f"Client error: {status} — {response.text[:200]}")
