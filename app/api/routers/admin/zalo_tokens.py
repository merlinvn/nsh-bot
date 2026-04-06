"""Admin Zalo token management router."""
import secrets

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.models.admin_user import AdminUser
from app.models.zalo_token import ZaloToken

router = APIRouter(prefix="/admin/zalo-tokens", tags=["admin:zalo-tokens"])


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
    }


@router.post("/pkce")
async def generate_pkce(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Generate PKCE pair for Zalo OAuth."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = secrets.token_urlsafe(32)  # Simplified; real impl would use hash
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "oauth_url": "https://oauth.zaloapp.com/v4/permissions?...",
    }


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback from Zalo. Stores tokens."""
    # TODO: Exchange code for access token via Zalo API
    return {"ok": True}


@router.post("/refresh")
async def refresh_token(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Refresh Zalo access token."""
    # TODO: Call Zalo refresh endpoint
    return {"ok": True}


@router.delete("")
async def revoke_token(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Revoke Zalo tokens."""
    await db.execute(select(ZaloToken).delete())
    await db.commit()
    return {"ok": True}
