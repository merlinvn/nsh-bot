"""Admin Zalo token management router - OAuth token exchange."""
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import api_settings
from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.models.admin_user import AdminUser
from app.models.zalo_token import ZaloToken

router = APIRouter(prefix="/admin/zalo-tokens", tags=["admin:zalo-tokens"])

ZALO_AUTH_URL = "https://oauth.zaloapp.com/v4/oa/permission"
ZALO_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
ZALO_REFRESH_URL = "https://oauth.zaloapp.com/v4/oa/refresh"


def _generate_code_verifier() -> str:
    """Generate a random code verifier for PKCE (43 characters)."""
    return secrets.token_urlsafe(43)[:43]


def _generate_code_challenge(code_verifier: str) -> str:
    """Generate code challenge from code verifier using SHA-256 + Base64.

    code_challenge = Base64URL(SHA256(code_verifier)) without padding.
    This is the S256 method.
    """
    sha256_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b"=").decode("ascii")


def _build_auth_url(code_verifier: str, callback_url: str) -> str:
    """Build the Zalo OAuth authorization URL with S256 PKCE."""
    code_challenge = _generate_code_challenge(code_verifier)
    params = urlencode({
        "app_id": api_settings.zalo_app_id,
        "redirect_uri": callback_url,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{ZALO_AUTH_URL}?{params}"


async def _refresh_access_token(refresh_token: str) -> dict:
    """Refresh access token via Zalo API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ZALO_REFRESH_URL,
            data={
                "refresh_token": refresh_token,
                "app_id": api_settings.zalo_app_id,
                "grant_type": "refresh_token",
            },
            headers={"secret_key": api_settings.zalo_app_secret},
        )
        resp.raise_for_status()
        return resp.json()


@router.get("/status")
async def token_status(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Current Zalo token status."""
    result = await db.execute(select(ZaloToken).order_by(ZaloToken.created_at.desc()).limit(1))
    token = result.scalar_one_or_none()
    if not token:
        return {"has_token": False}
    return {
        "has_token": True,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "refreshed_at": token.updated_at.isoformat(),
        "oa_id": token.oa_id,
    }


@router.post("/pkce")
async def generate_pkce(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Generate PKCE pair and authorization URL for Zalo OAuth.

    Stores code_verifier and code_challenge in the most recent ZaloToken record
    (matching the pattern used by /auth/zalo/callback). Returns the auth URL.
    """
    if not api_settings.zalo_app_id:
        return {"error": "zalo_app_id not configured", "oauth_url": None}
    if not api_settings.zalo_callback_url:
        return {"error": "zalo_callback_url not configured", "oauth_url": None}

    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    callback_url = f"{api_settings.zalo_callback_url}/auth/zalo/callback"

    # Store in DB — same pattern as /auth/zalo/pkce
    result = await db.execute(select(ZaloToken).limit(1))
    existing = result.scalar_one_or_none()

    if existing:
        await db.execute(
            update(ZaloToken)
            .where(ZaloToken.id == existing.id)
            .values(code_verifier=code_verifier, code_challenge=code_challenge)
        )
    else:
        db.add(ZaloToken(
            id=uuid.uuid4(),
            access_token="pending",
            code_verifier=code_verifier,
            code_challenge=code_challenge,
        ))

    await db.commit()

    oauth_url = _build_auth_url(code_verifier, callback_url)

    return {
        "oauth_url": oauth_url,
        "callback_url": callback_url,
    }


@router.post("/refresh")
async def refresh_token(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Refresh Zalo access token using the stored refresh token."""
    result = await db.execute(select(ZaloToken).order_by(ZaloToken.created_at.desc()).limit(1))
    token = result.scalar_one_or_none()

    if not token or not token.refresh_token:
        return {"ok": False, "error": "No refresh token available"}

    try:
        token_data = await _refresh_access_token(token.refresh_token)
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"Zalo API error: {exc.response.text}"}
    except Exception as exc:
        return {"ok": False, "error": f"Failed to refresh token: {str(exc)}"}

    access_token = token_data.get("access_token")
    refresh_token_new = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    token.access_token = access_token
    if refresh_token_new:
        token.refresh_token = refresh_token_new
    token.expires_at = expires_at
    await db.commit()

    return {
        "ok": True,
        "message": "Token refreshed successfully",
        "expires_in": expires_in,
    }


@router.delete("")
async def revoke_token(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Revoke Zalo tokens."""
    await db.execute(select(ZaloToken).delete())
    await db.commit()
    return {"ok": True}
