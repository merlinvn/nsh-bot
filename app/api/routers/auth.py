"""OAuth endpoints for Zalo authentication with PKCE.

Note: Zalo requires a different code_verifier for each OAuth request.
code_verifier and code_challenge are stored in zalo_tokens table.
"""
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.config import api_settings
from app.api.dependencies import get_db
from app.models.zalo_token import ZaloToken
from app.workers.shared.logging import get_logger

logger = get_logger("neochat.api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Zalo OAuth endpoints
ZALO_AUTH_URL = "https://oauth.zaloapp.com/v4/oa/permission"
ZALO_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"


def generate_code_verifier() -> str:
    """Generate a random code verifier for PKCE (43 characters)."""
    return secrets.token_urlsafe(43)[:43]


def generate_code_challenge(code_verifier: str) -> str:
    """Generate code challenge from code verifier using SHA-256 + Base64.

    code_challenge = Base64(SHA256(code_verifier)) without padding
    """
    sha256_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b"=").decode("ascii")


def _get_challenge_hash(code_challenge: str) -> str:
    """Create a lookup key from code_challenge."""
    return hashlib.sha256(code_challenge.encode()).hexdigest()[:32]


@router.get("/zalo/pkce")
async def zalo_pkce(db=Depends(get_db)):
    """Generate new PKCE pair and store in database.

    Returns the code_challenge to use in Zalo OAuth URL.
    Use this endpoint before initiating OAuth to get a fresh code_challenge.
    """
    # Generate new PKCE pair
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    # Store or update in zalo_tokens
    result = await db.execute(select(ZaloToken).limit(1))
    existing = result.scalar_one_or_none()

    if existing:
        await db.execute(
            update(ZaloToken)
            .where(ZaloToken.id == existing.id)
            .values(
                code_verifier=code_verifier,
                code_challenge=code_challenge,
            )
        )
    else:
        # Create placeholder token record with PKCE data only
        new_token = ZaloToken(
            id=uuid4(),
            access_token="pending",  # Will be replaced after OAuth
            code_verifier=code_verifier,
            code_challenge=code_challenge,
        )
        db.add(new_token)

    await db.commit()

    callback_url = f"{api_settings.zalo_callback_url}/auth/zalo/callback"

    # Build authorization URL
    auth_url = (
        f"{ZALO_AUTH_URL}"
        f"?app_id={api_settings.zalo_app_id}"
        f"&redirect_uri={callback_url}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state=hello"
    )

    logger.info("zalo_pkce_generated", extra={"code_challenge": code_challenge})

    return {
        "code_challenge": code_challenge,
        "code_verifier": code_verifier,  # Debug only - don't share
        "authorization_url": auth_url,
        "callback_url": callback_url,
    }


@router.get("/zalo/callback")
async def zalo_callback(
    code: str = Query(..., description="Authorization code from Zalo"),
    oa_id: str = Query(None, description="OA ID from Zalo"),
    db=Depends(get_db),
):
    """Handle Zalo OAuth callback with authorization code.

    Exchanges the authorization code for access token and refresh token,
    then stores them in the database.

    The code_verifier is retrieved from the zalo_tokens table.
    """
    logger.info("zalo_oauth_callback", extra={"oa_id": oa_id})

    # Get the pending token with code_verifier
    result = await db.execute(select(ZaloToken).limit(1))
    token_record = result.scalar_one_or_none()

    if not token_record or not token_record.code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CALLBACK", "message": "No pending PKCE found. Please call /auth/zalo/pkce first."},
        )

    code_verifier = token_record.code_verifier

    if not api_settings.zalo_app_id or not api_settings.zalo_app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CONFIG_MISSING", "message": "Zalo app credentials not configured"},
        )

    # Exchange authorization code for tokens
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "secret_key": api_settings.zalo_app_secret,
    }

    callback_url = f"{api_settings.zalo_callback_url}/auth/zalo/callback"

    payload = {
        "code": code,
        "app_id": api_settings.zalo_app_id,
        "grant_type": "authorization_code",
        "redirect_uri": callback_url,
        "code_verifier": code_verifier,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(ZALO_TOKEN_URL, data=payload, headers=headers)
    except httpx.RequestError as e:
        logger.error("zalo_token_request_failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "OAUTH_FAILED", "message": f"Failed to connect to Zalo: {str(e)}"},
        )

    if response.status_code != 200:
        error_text = response.text
        logger.error("zalo_token_exchange_failed", extra={"status": response.status_code, "error": error_text})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "OAUTH_FAILED", "message": f"Zalo token exchange failed: {error_text}"},
        )

    token_data = response.json()
    logger.info("zalo_token_exchange_success", extra={
        "has_access_token": "access_token" in token_data,
        "has_refresh_token": "refresh_token" in token_data,
    })

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "OAUTH_FAILED", "message": "No access token in Zalo response"},
        )

    # Calculate expiration time
    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Update token record with real tokens and clear PKCE data
    await db.execute(
        update(ZaloToken)
        .where(ZaloToken.id == token_record.id)
        .values(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            oa_id=oa_id,
            code_verifier=None,  # Clear after use
            code_challenge=None,
        )
    )
    await db.commit()

    logger.info("zalo_token_stored", extra={"expires_in": expires_in})

    return {
        "success": True,
        "message": "Zalo authentication successful. Access token stored.",
        "expires_in": expires_in,
    }


@router.post("/zalo/refresh")
async def zalo_refresh_token(db=Depends(get_db)):
    """Manually refresh the Zalo access token using the stored refresh token."""
    result = await db.execute(select(ZaloToken).limit(1))
    token_record = result.scalar_one_or_none()

    if not token_record or not token_record.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_TOKEN", "message": "No refresh token available. Please re-authorize via /auth/zalo/pkce"},
        )

    if not api_settings.zalo_app_id or not api_settings.zalo_app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CONFIG_MISSING", "message": "Zalo app credentials not configured"},
        )

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "secret_key": api_settings.zalo_app_secret,
    }

    payload = {
        "refresh_token": token_record.refresh_token,
        "app_id": api_settings.zalo_app_id,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(ZALO_TOKEN_URL, data=payload, headers=headers)
    except httpx.RequestError as e:
        logger.error("zalo_refresh_request_failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "REFRESH_FAILED", "message": f"Failed to connect to Zalo: {str(e)}"},
        )

    if response.status_code != 200:
        error_text = response.text
        logger.error("zalo_refresh_failed", extra={"status": response.status_code, "error": error_text})
        await db.execute(
            update(ZaloToken)
            .where(ZaloToken.id == token_record.id)
            .values(refresh_token=None)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "REFRESH_FAILED", "message": f"Token refresh failed. Please re-authorize via /auth/zalo/pkce"},
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    new_refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "REFRESH_FAILED", "message": "No access token in Zalo refresh response"},
        )

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    await db.execute(
        update(ZaloToken)
        .where(ZaloToken.id == token_record.id)
        .values(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at,
        )
    )
    await db.commit()

    logger.info("zalo_token_refreshed", extra={"expires_in": expires_in})

    return {
        "success": True,
        "message": "Token refreshed successfully.",
        "expires_in": expires_in,
    }


@router.get("/zalo/status")
async def zalo_token_status(db=Depends(get_db)):
    """Check the current status of Zalo OAuth tokens."""
    result = await db.execute(select(ZaloToken).limit(1))
    token_record = result.scalar_one_or_none()

    if not token_record:
        return {
            "authenticated": False,
            "message": "No Zalo tokens found. Please authorize via /auth/zalo/pkce",
        }

    has_pending_pkce = token_record.code_verifier is not None
    now = datetime.now(timezone.utc)
    is_expired = token_record.expires_at and token_record.expires_at < now

    return {
        "authenticated": token_record.access_token != "pending",
        "has_pending_pkce": has_pending_pkce,
        "has_refresh_token": token_record.refresh_token is not None,
        "expires_at": token_record.expires_at.isoformat() if token_record.expires_at else None,
        "is_expired": is_expired,
        "message": "Token is valid and can be used." if not is_expired else "Token is expired. Use /auth/zalo/refresh to refresh or /auth/zalo/pkce to re-authorize.",
    }
