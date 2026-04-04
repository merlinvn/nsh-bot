"""Zalo OAuth token management with persistent storage."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.zalo_token import ZaloToken
from app.workers.shared.db import db_session
from app.workers.shared.logging import get_logger

logger = get_logger("zalo_token_manager")

settings = get_settings()


class ZaloTokenManager:
    """Manages Zalo OAuth tokens with automatic refresh."""

    def __init__(self):
        self.app_id = settings.zalo_app_id
        self.app_secret = settings.zalo_app_secret
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None

    async def _get_or_create_token(self, session: AsyncSession) -> ZaloToken:
        """Get existing token or create initial record.

        Note: Tokens should be obtained via OAuth flow (/auth/zalo/login).
        This method will return None if no token exists in the database.
        """
        result = await session.execute(select(ZaloToken).limit(1))
        token_record = result.scalar_one_or_none()

        if token_record is None:
            logger.warning("No Zalo token found in database. Please authenticate via /auth/zalo/login")

        return token_record

    async def _save_token(
        self,
        session: AsyncSession,
        token_record: ZaloToken,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> None:
        """Save updated token to database."""
        token_record.access_token = access_token
        if refresh_token:
            token_record.refresh_token = refresh_token
        if expires_in_seconds:
            token_record.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        else:
            token_record.expires_at = None

        await session.execute(
            update(ZaloToken).where(ZaloToken.id == token_record.id).values(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=token_record.expires_at,
            )
        )
        await session.commit()
        logger.info("Saved updated Zalo token to database")

    async def _refresh_access_token(self, refresh_token: str) -> dict:
        """Call Zalo API to refresh access token."""
        url = "https://oauth.zaloapp.com/v4/oa/access_token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": self.app_secret,
        }
        payload = {
            "refresh_token": refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")

        return response.json()

    def _is_token_expired(self) -> bool:
        """Check if current token is expired or about to expire (within 5 minutes)."""
        if self._expires_at is None:
            return False
        # Consider expired if less than 5 minutes remaining
        expiry_threshold = datetime.now(timezone.utc) + timedelta(minutes=5)
        return self._expires_at < expiry_threshold

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Args:
            force_refresh: If True, always refresh the token even if not expired.

        Returns:
            Valid Zalo access token string
        """
        async with db_session() as session:
            token_record = await self._get_or_create_token(session)

            self._access_token = token_record.access_token
            self._refresh_token = token_record.refresh_token
            self._expires_at = token_record.expires_at

            # Check if token needs refresh
            if self._refresh_token and (force_refresh or self._is_token_expired()):
                logger.info("Zalo token expired or expiring soon, refreshing...")
                try:
                    token_data = await self._refresh_access_token(self._refresh_token)

                    await self._save_token(
                        session,
                        token_record,
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token", self._refresh_token),
                        expires_in_seconds=int(token_data.get("expires_in", 0)),
                    )

                    self._access_token = token_data["access_token"]
                    if "refresh_token" in token_data:
                        self._refresh_token = token_data["refresh_token"]

                except Exception as e:
                    logger.error(f"Failed to refresh Zalo token: {e}")
                    # Return existing token even if expired - let API call fail naturally
                    # This prevents complete outage if refresh fails

        if not self._access_token:
            raise Exception("No Zalo access token available")

        return self._access_token

    async def initialize_from_static_token(self) -> None:
        """
        Initialize token storage from static ZALO_ACCESS_TOKEN and ZALO_REFRESH_TOKEN env vars.
        Call this once during worker startup to seed the database.
        """
        if not settings.zalo_access_token:
            logger.warning("No static ZALO_ACCESS_TOKEN configured")
            return

        async with db_session() as session:
            result = await session.execute(select(ZaloToken).limit(1))
            existing = result.scalar_one_or_none()

            if existing is None:
                token_record = ZaloToken(
                    id=uuid4(),
                    access_token=settings.zalo_access_token,
                    refresh_token=settings.zalo_refresh_token or None,
                    expires_at=None,
                )
                session.add(token_record)
                await session.commit()
                logger.info("Initialized Zalo token storage from environment variable")
            else:
                logger.info("Zalo token storage already initialized")

# Singleton instance
_token_manager: ZaloTokenManager | None = None


def get_zalo_token_manager() -> ZaloTokenManager:
    """Get or create the singleton token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = ZaloTokenManager()
    return _token_manager
