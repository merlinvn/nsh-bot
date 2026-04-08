"""Admin Zalo token management router."""
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import api_settings
from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.models.admin_user import AdminUser
from app.models.zalo_token import ZaloToken

router = APIRouter(prefix="/admin/zalo-tokens", tags=["admin:zalo-tokens"])

ZALO_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
ZALO_REFRESH_URL = "https://oauth.zaloapp.com/v4/oa/refresh"
PKCE_TTL_SECONDS = 600  # 10 minutes


def _build_auth_url(code_verifier: str, state: str) -> str:
    """Build the Zalo OAuth authorization URL."""
    callback_url = f"{api_settings.zalo_callback_url}/admin/zalo-tokens/callback"
    params = urlencode({
        "app_id": api_settings.zalo_app_id,
        "redirect_uri": callback_url,
        "code_challenge": code_verifier,  # Zalo uses plain challenge
        "state": state,
    })
    return f"https://oauth.zaloapp.com/v4/oa/permission?{params}"


async def _store_pkce_state(redis_client: redis.Redis, state: str, code_verifier: str) -> None:
    """Store PKCE state in Redis with 10-minute TTL."""
    key = f"zalo:pkce:{state}"
    await redis_client.set(key, json.dumps({"code_verifier": code_verifier}), ex=PKCE_TTL_SECONDS)


async def _get_pkce_state(redis_client: redis.Redis, state: str) -> str | None:
    """Retrieve and delete PKCE state from Redis."""
    key = f"zalo:pkce:{state}"
    data = await redis_client.get(key)
    if data:
        await redis_client.delete(key)
        return json.loads(data).get("code_verifier")
    return None


async def _exchange_code_for_token(code: str, code_verifier: str) -> dict:
    """Exchange authorization code for access token via Zalo API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ZALO_TOKEN_URL,
            data={
                "code": code,
                "app_id": api_settings.zalo_app_id,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            headers={"secret_key": api_settings.zalo_app_secret},
        )
        resp.raise_for_status()
        return resp.json()


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
    redis_client: redis.Redis = Depends(get_redis),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Generate PKCE pair and authorization URL for Zalo OAuth."""
    if not api_settings.zalo_app_id:
        return {
            "code_verifier": None,
            "oauth_url": None,
            "error": "zalo_app_id not configured",
        }
    if not api_settings.zalo_callback_url:
        return {
            "code_verifier": None,
            "oauth_url": None,
            "error": "zalo_callback_url not configured",
        }

    code_verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)

    # Store state -> code_verifier mapping in Redis
    await _store_pkce_state(redis_client, state, code_verifier)

    oauth_url = _build_auth_url(code_verifier, state)

    return {
        "code_verifier": code_verifier,
        "state": state,
        "oauth_url": oauth_url,
    }


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    oa_id: str = Query(...),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """OAuth callback from Zalo. Exchanges code for access token, stores in DB, redirects to frontend."""
    from fastapi.responses import RedirectResponse

    # Default redirect to tokens page
    redirect_url = f"{api_settings.zalo_callback_url}/admin/tokens"

    # Look up code_verifier from Redis using state
    code_verifier = None
    if state:
        code_verifier = await _get_pkce_state(redis_client, state)

    if not code_verifier:
        return RedirectResponse(
            url=f"{redirect_url}?error=invalid_state",
            status_code=302,
        )

    try:
        token_data = await _exchange_code_for_token(code, code_verifier)
    except httpx.HTTPStatusError as exc:
        error_msg = exc.response.text[:200]
        return RedirectResponse(
            url=f"{redirect_url}?error=exchange_failed&detail={error_msg}",
            status_code=302,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"{redirect_url}?error=exchange_failed&detail={str(exc)[:100]}",
            status_code=302,
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Upsert token — delete old and insert new
    await db.execute(select(ZaloToken).delete())
    new_token = ZaloToken(
        id=uuid.uuid4(),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        oa_id=oa_id,
    )
    db.add(new_token)
    await db.commit()

    return RedirectResponse(
        url=f"{redirect_url}?success=1&expires_in={expires_in or ''}",
        status_code=302,
    )


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
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    token.access_token = access_token
    if refresh_token:
        token.refresh_token = refresh_token
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
