"""Admin authentication router."""
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.config import admin_settings
from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.api.schemas.admin import LoginRequest, LoginResponse, MeResponse, PasswordChangeRequest
from app.core.session import LoginRateLimiter, SessionStore
from app.models.admin_user import AdminUser

router = APIRouter(prefix="/admin/auth", tags=["admin:auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db=Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """Login with username/password. Returns session cookie + CSRF token."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    rate_limiter = LoginRateLimiter(redis_client)
    allowed, count = await rate_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Too many login attempts. Try again later."},
        )

    # Find user
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == body.username)
    )
    user = result.scalar_one_or_none()

    # Check lockout
    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        await rate_limiter.record_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "ACCOUNT_LOCKED", "message": "Account locked. Try again later."},
        )

    # Verify credentials
    if user is None or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        # Record failed attempt
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= admin_settings.admin_max_login_attempts:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=admin_settings.admin_lockout_minutes
                )
            await db.commit()
        await rate_limiter.record_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."},
        )

    # Reset failed attempts on success
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Create session
    csrf_token = secrets.token_hex(32)
    session_store = SessionStore(redis_client)
    session_id = await session_store.create(
        user_id=str(user.id),
        username=user.username,
        csrf_token=csrf_token,
    )

    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=admin_settings.admin_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=False,  # Set True in production
        path="/",
    )

    return LoginResponse(
        ok=True,
        user={"username": user.username, "is_active": user.is_active},
        csrf_token=csrf_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    _: AdminUser = Depends(get_current_admin_user),
    redis_client: redis.Redis = Depends(get_redis),
):
    """Logout — delete session and clear cookie."""
    session_id = request.cookies.get("session_id")
    if session_id:
        session_store = SessionStore(redis_client)
        await session_store.delete(session_id)

    response.set_cookie(
        key="session_id",
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(current_user: AdminUser = Depends(get_current_admin_user)):
    """Get current authenticated admin user."""
    return MeResponse(username=current_user.username, is_active=current_user.is_active)


@router.post("/password")
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    response: Response,
    current_user: AdminUser = Depends(get_current_admin_user),
    db=Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """Change own password. Invalidates all sessions for this user."""
    # Verify current password
    if not bcrypt.checkpw(body.current_password.encode(), current_user.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_PASSWORD", "message": "Current password is incorrect."},
        )

    # Hash new password
    new_hash = bcrypt.hashpw(
        body.new_password.encode(), bcrypt.gensalt(rounds=admin_settings.admin_bcrypt_rounds)
    )

    # Delete ALL sessions for this user
    session_store = SessionStore(redis_client)
    await session_store.delete_all_for_user(current_user.username)

    # Update password
    current_user.password_hash = new_hash.decode()
    current_user.failed_login_attempts = 0
    current_user.locked_until = None
    await db.commit()

    # Clear the current session cookie (user must re-login)
    response.set_cookie(key="session_id", value="", max_age=0, httponly=True, samesite="lax", path="/")
    return {"ok": True}
