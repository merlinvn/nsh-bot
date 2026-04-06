"""Redis-backed session store and login rate limiter for admin users."""
import json
import secrets
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from app.api.config import admin_settings


class SessionStore:
    """Redis-backed session store for admin users."""

    KEY_PREFIX = "session:"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    async def create(
        self,
        user_id: str,
        username: str,
        csrf_token: str,
    ) -> str:
        """Create a new session. Returns the session_id."""
        session_id = secrets.token_hex(admin_settings.admin_session_id_bytes)
        data = {
            "user_id": user_id,
            "username": username,
            "csrf_token": csrf_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.redis.set(
            self._key(session_id),
            json.dumps(data),
            ex=admin_settings.admin_session_ttl_seconds,
        )
        return session_id

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Get session data, or None if not found/expired."""
        data = await self.redis.get(self._key(session_id))
        if data is None:
            return None
        return json.loads(data)

    async def delete(self, session_id: str) -> None:
        """Delete a session."""
        await self.redis.delete(self._key(session_id))

    async def delete_all_for_user(self, username: str) -> int:
        """Delete all sessions for a given username. Returns count deleted."""
        pattern = f"{self.KEY_PREFIX}*"
        count = 0
        async for key in self.redis.scan_iter(match=pattern):
            data = await self.redis.get(key)
            if data:
                session = json.loads(data)
                if session.get("username") == username:
                    await self.redis.delete(key)
                    count += 1
        return count

    async def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        """Validate that the CSRF token matches the session."""
        session = await self.get(session_id)
        if session is None:
            return False
        return session.get("csrf_token") == csrf_token


class LoginRateLimiter:
    """Rate limiter for login attempts using Redis sliding window."""

    KEY_PREFIX = "login_rate:"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def _key(self, ip: str) -> str:
        return f"{self.KEY_PREFIX}{ip}"

    async def is_allowed(self, ip: str) -> tuple[bool, int]:
        """
        Check if login attempt is allowed.
        Returns (allowed, current_count).
        """
        key = self._key(ip)
        count = await self.redis.get(key)
        if count is None:
            return True, 0
        return int(count) < admin_settings.admin_login_rate_limit_per_minute, int(count)

    async def record_attempt(self, ip: str) -> None:
        """Record a failed login attempt."""
        key = self._key(ip)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)  # 1 minute window
        await pipe.execute()
