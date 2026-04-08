"""Admin Zalo token management router - OAuth token exchange."""
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import api_settings
from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.zalo_token import ZaloToken
from app.workers.shared.zalo_token_manager import get_zalo_token_manager

router = APIRouter(prefix="/admin/zalo-tokens", tags=["admin:zalo-tokens"])


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
    return f"https://oauth.zaloapp.com/v4/oa/permission?{params}"


@router.get("/status")
async def token_status(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Current Zalo token status."""
    manager = get_zalo_token_manager()
    return await manager.get_status()


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
    _: AdminUser = Depends(get_current_admin_user),
):
    """Refresh Zalo access token using the stored refresh token.

    Uses ZaloTokenManager which handles refresh + DB persistence.
    """
    manager = get_zalo_token_manager()
    try:
        await manager.get_access_token(force_refresh=True)
        return {"ok": True, "message": "Token refreshed successfully"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.delete("")
async def revoke_token(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Revoke Zalo tokens."""
    manager = get_zalo_token_manager()
    await manager.revoke()
    return {"ok": True}
