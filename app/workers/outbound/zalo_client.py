"""Zalo API client for sending outbound messages."""
import asyncio
import re
from typing import Any

import httpx

from app.workers.shared.logging import get_logger

logger = get_logger("zalo_client")


def strip_markdown(text: str) -> str:
    """Convert markdown formatting to plain text for Zalo send_text API.

    Zalo's send_text only sends plain text — markdown like **bold** or *italic*
    shows as literal characters. This strips common markdown patterns.
    """
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Italic: *text* or _text_ (but not inside words)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'\1', text)
    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # Inline code: `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # HTML underline: <u>text</u>
    text = re.sub(r'<u>(.+?)</u>', r'\1', text)
    return text


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
        url = f"{self.base_url}/v3.0/oa/message/cs"
        headers = {
            "access_token": self.access_token,
            "Content-Type": "application/json",
        }
        payload = {
            "recipient": {"user_id": user_id},
            "message": {"text": strip_markdown(text)},
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
            # Zalo returns {"error": 0, "message": "Success"} on success
            # or {"error": <code>, "message": "<error_message>"} on failure
            error_code = result.get("error")
            if error_code == 0:
                logger.info("Zalo message sent", extra={"user_id": user_id})
                return result
            elif error_code is not None:
                error_msg = result.get("message", "Unknown error")
                logger.error(
                    "Zalo API error",
                    extra={"user_id": user_id, "error_code": error_code, "error_msg": error_msg},
                )
                # Error codes that mean we should retry
                if error_code in (-216, -1002):  # Token invalid/expired, rate limit
                    raise RetryableError(f"Token invalid ({error_code})")
                raise NonRetryableError(f"Zalo error {error_code}: {error_msg}")
            else:
                # Unexpected response format - treat as success
                logger.info("Zalo message sent", extra={"user_id": user_id, "result": str(result)[:100]})
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

        # 401 Unauthorized — token expired, should refresh and retry
        if status == 401:
            logger.warning("Zalo API token expired", extra={"user_id": user_id})
            raise RetryableError(f"Token expired (401)")

        # Other 4xx except 429 — non-retryable
        logger.error(
            "Zalo API client error",
            extra={"user_id": user_id, "status": status, "body": response.text[:200]},
        )
        raise NonRetryableError(f"Client error: {status} — {response.text[:200]}")
