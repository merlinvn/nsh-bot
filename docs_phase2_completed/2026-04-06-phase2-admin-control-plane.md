# Phase 2 Admin Control Plane — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a production-ready admin control plane for NeoChatPlatform — a FastAPI `/admin/*` backend with cookie-session auth + a Next.js frontend, both extending the Phase 1 Zalo chatbot infrastructure.

**Architecture:** Backend is embedded in the existing FastAPI service (`/admin/*` routes). Frontend is a standalone Next.js 14 App Router project. Auth uses Redis-backed opaque session cookies (24h fixed TTL, bcrypt password hashing, account lockout, rate limiting). No JWT, no refresh tokens.

**Tech Stack:** FastAPI (Python), PostgreSQL + SQLAlchemy (async), Redis (sessions + rate limiting), RabbitMQ (unchanged), Next.js 14 (App Router), TypeScript, Tailwind + shadcn/ui, React Query, React Hook Form + Zod.

---

## Scope & Subsystem Split

This plan has two independent subsystems that can be built in parallel:

| Subsystem | Owner | Output |
|-----------|-------|--------|
| **Backend** | `backend-architect` | FastAPI `/admin/*` routes, DB models, Redis sessions |
| **Frontend** | `frontend-architect` | Next.js app with auth, all admin pages |

**Coordination:** The frontend references API shapes defined in the backend schemas. Backend tasks 1–10 (DB migrations, models, Redis sessions, auth) must be completed before frontend can run integration tests, but frontend scaffolding and page structure can start earlier.

---

## File Structure

### Backend files to create/modify

```
app/
├── api/
│   ├── routers/admin/
│   │   ├── __init__.py              # [CREATE]
│   │   ├── auth.py                  # [CREATE] login, logout, me, password
│   │   ├── prompts.py               # [CREATE] CRUD + versioning + activation
│   │   ├── conversations.py         # [CREATE] list/detail/replay/stats
│   │   ├── analytics.py             # [CREATE] overview/messages/latency/tools/fallbacks/tokens
│   │   ├── playground.py           # [CREATE] complete/benchmark/models
│   │   ├── zalo_tokens.py           # [CREATE] status/pkce/callback/refresh/revoke
│   │   └── monitoring.py           # [CREATE] health/metrics/workers/queues
│   ├── schemas/
│   │   ├── admin.py                 # [CREATE] Session user schemas, login/logout responses
│   │   ├── analytics.py             # [CREATE] Analytics response schemas
│   │   └── playground.py             # [CREATE] Playground/completion/benchmark schemas
│   ├── dependencies.py              # [MODIFY] Add get_current_admin_user dependency
│   ├── main.py                      # [MODIFY] Add admin_router to app
│   └── config.py                    # [MODIFY] Add admin_settings (session TTL, bcrypt rounds, lockout)
├── models/
│   ├── admin_user.py                # [CREATE] AdminUser SQLAlchemy model
│   ├── benchmark_result.py          # [CREATE] BenchmarkResult model
│   └── benchmark_item.py            # [CREATE] BenchmarkItem model
└── api/scripts/
    └── create_admin_user.py         # [CREATE] Bootstrap admin user script
```

### Frontend files to create

```
frontend/                              # [CREATE] New Next.js project
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── .env.local                        # NEXT_PUBLIC_API_URL=http://localhost:8000
└── src/
    ├── app/
    │   ├── (auth)/
    │   │   ├── login/
    │   │   │   └── page.tsx
    │   │   └── layout.tsx
    │   ├── (admin)/
    │   │   ├── layout.tsx            # Sidebar + header + auth guard
    │   │   ├── page.tsx              # Redirect to /admin/analytics
    │   │   ├── conversations/
    │   │   │   ├── page.tsx
    │   │   │   └── [id]/page.tsx
    │   │   ├── prompts/
    │   │   │   ├── page.tsx
    │   │   │   └── [name]/page.tsx
    │   │   ├── analytics/
    │   │   │   └── page.tsx
    │   │   ├── playground/
    │   │   │   └── page.tsx
    │   │   ├── tokens/
    │   │   │   └── page.tsx
    │   │   └── monitoring/
    │   │       └── page.tsx
    │   ├── layout.tsx
    │   └── globals.css
    ├── components/
    │   ├── ui/                       # shadcn/ui components
    │   ├── admin/
    │   │   ├── Sidebar.tsx
    │   │   ├── Header.tsx
    │   │   ├── DataTable.tsx
    │   │   ├── StatusBadge.tsx
    │   │   └── ConfirmDialog.tsx
    │   └── forms/
    │       ├── LoginForm.tsx
    │       └── PromptForm.tsx
    ├── context/
    │   └── AuthContext.tsx            # { user, login, logout, isLoading }
    ├── hooks/
    │   ├── useAuth.ts
    │   └── useApi.ts
    ├── lib/
    │   ├── api.ts                    # fetch with credentials: 'include'
    │   └── utils.ts
    └── types/
        └── api.ts                    # All API response types
```

### Database migrations

```bash
alembic revision --autogenerate -m "Add admin_user, benchmark_result, benchmark_item tables"
alembic revision --autogenerate -m "Add messages.error column and analytics indexes"
```

---

## BACKEND IMPLEMENTATION

### Task 1: Database Migrations

**Files:**
- Create: `alembic/versions/xxxx_add_admin_tables.py`
- Create: `alembic/versions/xxxx_add_messages_error_and_indexes.py`

- [ ] **Step 1: Generate migration for admin tables**

Run:
```bash
cd /Users/neo/Projects/AI/neo-chat-platform
alembic revision --autogenerate -m "Add admin_user benchmark_result benchmark_item tables"
```

Expected: New revision file created in `alembic/versions/`

- [ ] **Step 2: Review migration file — verify it creates correct tables**

The migration must include:
- `admin_users` table with all columns from spec §3.1 (id UUID PK, username UNIQUE NOT NULL, password_hash, is_active DEFAULT TRUE, last_login_at NULL, failed_login_attempts DEFAULT 0, locked_until NULL, created_at, updated_at)
- `benchmark_results` table (id UUID PK, name, status, iterations, error NULL, created_at, completed_at NULL)
- `benchmark_items` table (id UUID PK, benchmark_id FK, model_provider, model_name, avg_latency_ms NULL, p95_latency_ms NULL, avg_input_tokens NULL, avg_output_tokens NULL, total_cost NULL, raw_results JSONB NULL)
- Indexes: `ix_admin_users_username` on `admin_users(username)`

- [ ] **Step 3: Generate migration for messages error column and indexes**

Run:
```bash
alembic revision --autogenerate -m "Add messages error column and analytics indexes"
```

Expected: New revision file created in `alembic/versions/`

- [ ] **Step 4: Verify migration includes required indexes**

The migration must include:
- `ALTER TABLE messages ADD COLUMN error TEXT NULL`
- `CREATE INDEX ix_conversations_created_at ON conversations (created_at DESC)`
- `CREATE INDEX ix_messages_created_at ON messages (created_at DESC)`
- `CREATE INDEX ix_messages_direction_created ON messages (direction, created_at DESC)`

- [ ] **Step 5: Run migrations against database**

Run:
```bash
docker-compose exec api alembic upgrade head
```

Expected: `Migration successful` — all new tables and columns created

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/
git commit -m "feat: add admin_user, benchmark_result, benchmark_item tables and analytics indexes"
```

---

### Task 2: Admin SQLAlchemy Models

**Files:**
- Create: `app/models/admin_user.py`
- Create: `app/models/benchmark_result.py`
- Create: `app/models/benchmark_item.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Write AdminUser model**

```python
# app/models/admin_user.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(time.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(time.utc),
        onupdate=lambda: datetime.now(time.utc)
    )
```

- [ ] **Step 2: Write BenchmarkResult model**

```python
# app/models/benchmark_result.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(time.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["BenchmarkItem"]] = relationship("BenchmarkItem", back_populates="benchmark")


class BenchmarkItem(Base):
    __tablename__ = "benchmark_items"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), SQLForeignKey("public.benchmark_results.id"), nullable=False
    )
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    benchmark: Mapped["BenchmarkResult"] = relationship("BenchmarkResult", back_populates="items")
```

- [ ] **Step 3: Update `app/models/__init__.py`**

Add exports:
```python
from app.models.admin_user import AdminUser
from app.models.benchmark_result import BenchmarkResult, BenchmarkItem
```

- [ ] **Step 4: Run unit tests to verify models**

Run:
```bash
uv run pytest tests/unit/ -v -k "test" --tb=short 2>&1 | head -50
```

Expected: Existing tests still pass. No import errors for new models.

- [ ] **Step 5: Commit**

```bash
git add app/models/admin_user.py app/models/benchmark_result.py app/models/benchmark_item.py app/models/__init__.py
git commit -m "feat: add AdminUser, BenchmarkResult, BenchmarkItem models"
```

---

### Task 3: Admin Config Settings

**Files:**
- Modify: `app/api/config.py`

- [ ] **Step 1: Read existing config.py**

```bash
cat app/api/config.py
```

- [ ] **Step 2: Add admin settings to config**

Add a new `AdminSettings` class:
```python
from pydantic_settings import BaseSettings


class AdminSettings(BaseSettings):
    # Session
    admin_session_ttl_seconds: int = 86400  # 24 hours
    admin_session_id_bytes: int = 32

    # Password
    admin_bcrypt_rounds: int = 12

    # Lockout
    admin_max_login_attempts: int = 5
    admin_lockout_minutes: int = 15

    # Rate limiting
    admin_login_rate_limit_per_minute: int = 10

    class Config:
        env_prefix = "ADMIN_"
```

And add `admin_settings = AdminSettings()` to the module.

- [ ] **Step 3: Commit**

```bash
git add app/api/config.py
git commit -m "feat: add AdminSettings (session TTL, bcrypt rounds, lockout, rate limit)"
```

---

### Task 4: Redis Session Management

**Files:**
- Create: `app/core/session.py`

- [ ] **Step 1: Create session management module**

```python
# app/core/session.py
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


# Rate limiter using Redis sliding window
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
```

- [ ] **Step 2: Commit**

```bash
git add app/core/session.py
git commit -m "feat: add Redis session store and login rate limiter"
```

---

### Task 5: Admin Auth Router

**Files:**
- Create: `app/api/routers/admin/auth.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/api/routers/admin/__init__.py`

- [ ] **Step 1: Create `get_current_admin_user` dependency**

```python
# In app/api/dependencies.py, add:

async def get_current_admin_user(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> AdminUser:
    """Validate session cookie and return the current admin user."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated."},
        )

    session_store = SessionStore(redis_client)
    session_data = await session_store.get(session_id)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_EXPIRED", "message": "Session expired."},
        )

    # Load admin user from DB
    db = await get_db()
    user = await db.get(AdminUser, uuid.UUID(session_data["user_id"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_INACTIVE", "message": "User inactive or not found."},
        )
    return user
```

- [ ] **Step 2: Create admin auth router**

```python
# app/api/routers/admin/auth.py
import bcrypt
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.config import admin_settings
from app.api.dependencies import get_current_admin_user, get_db, get_redis
from app.api.schemas.admin import LoginRequest, LoginResponse, MeResponse, PasswordChangeRequest
from app.core.session import LoginRateLimiter, SessionStore
from app.models.admin_user import AdminUser
import redis.asyncio as redis

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
    user = await db.execute(
        select(AdminUser).where(AdminUser.username == body.username)
    )
    user = user.scalar_one_or_none()

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
                from datetime import timedelta
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=admin_settings.admin_lockout_minutes)
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
    new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt(rounds=admin_settings.admin_bcrypt_rounds))

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
```

- [ ] **Step 3: Create admin schemas**

```python
# app/api/schemas/admin.py
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user: dict  # {"username": str, "is_active": bool}
    csrf_token: str


class MeResponse(BaseModel):
    username: str
    is_active: bool


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str  # Min 8 chars, validated server-side
```

- [ ] **Step 4: Create `app/api/routers/admin/__init__.py`**

```python
from app.api.routers.admin.auth import router as auth_router
from app.api.routers.admin.prompts import router as prompts_router
from app.api.routers.admin.conversations import router as conversations_router
from app.api.routers.admin.analytics import router as analytics_router
from app.api.routers.admin.playground import router as playground_router
from app.api.routers.admin.zalo_tokens import router as zalo_tokens_router
from app.api.routers.admin.monitoring import router as monitoring_router

__all__ = [
    "auth_router",
    "prompts_router",
    "conversations_router",
    "analytics_router",
    "playground_router",
    "zalo_tokens_router",
    "monitoring_router",
]
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routers/admin/ app/api/dependencies.py app/api/schemas/admin.py
git commit -m "feat: add admin auth router with session cookie, bcrypt, lockout, rate limiting"
```

---

### Task 6: Admin Prompts Router

**Files:**
- Create: `app/api/routers/admin/prompts.py`

- [ ] **Step 1: Read existing prompt model and router to understand patterns**

```bash
cat app/models/prompt.py
cat app/api/routers/internal.py  # if it has prompt endpoints
```

- [ ] **Step 2: Create prompts router**

```python
# app/api/routers/admin/prompts.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.api.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate, VersionCreate
from app.models.admin_user import AdminUser
from app.models.prompt import Prompt, PromptVersion

router = APIRouter(prefix="/admin/prompts", tags=["admin:prompts"])


@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_db)):
    """List all prompts."""
    result = await db.execute(select(Prompt).order_by(Prompt.name))
    prompts = result.scalars().all()
    return [{"name": p.name, "description": p.description, "active_version": p.active_version} for p in prompts]


@router.post("")
async def create_prompt(body: PromptCreate, db: AsyncSession = Depends(get_db)):
    """Create a new prompt."""
    existing = await db.execute(select(Prompt).where(Prompt.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Prompt already exists")
    prompt = Prompt(name=body.name, description=body.description, active_version=1)
    db.add(prompt)
    version = PromptVersion(prompt_id=prompt.id, version=1, template=body.template, created_by="admin")
    db.add(version)
    await db.commit()
    return {"name": prompt.name, "active_version": 1}


@router.get("/{name}")
async def get_prompt(name: str, db: AsyncSession = Depends(get_db)):
    """Get prompt detail."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": prompt.name, "description": prompt.description, "active_version": prompt.active_version}


@router.put("/{name}")
async def update_prompt(name: str, body: PromptUpdate, db: AsyncSession = Depends(get_db)):
    """Update prompt template (creates new version)."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    new_version = prompt.active_version + 1
    version = PromptVersion(prompt_id=prompt.id, version=new_version, template=body.template, created_by="admin")
    db.add(version)
    prompt.active_version = new_version
    if body.description:
        prompt.description = body.description
    await db.commit()
    return {"name": prompt.name, "active_version": new_version}


@router.delete("/{name}")
async def delete_prompt(name: str, db: AsyncSession = Depends(get_db)):
    """Delete a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await db.delete(prompt)
    await db.commit()
    return {"ok": True}


@router.post("/{name}/versions")
async def create_version(name: str, body: VersionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new version of a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    new_version = prompt.active_version + 1
    version = PromptVersion(prompt_id=prompt.id, version=new_version, template=body.template, created_by="admin")
    db.add(version)
    await db.commit()
    return {"version": new_version}


@router.post("/{name}/activate")
async def activate_version(name: str, body: VersionCreate, db: AsyncSession = Depends(get_db)):
    """Activate a specific version."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    version_result = await db.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id, PromptVersion.version == body.version)
    )
    if not version_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Version not found")
    prompt.active_version = body.version
    await db.commit()
    return {"name": name, "active_version": body.version}


@router.get("/{name}/versions")
async def list_versions(name: str, db: AsyncSession = Depends(get_db)):
    """List all versions of a prompt."""
    result = await db.execute(select(Prompt).where(Prompt.name == name))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    versions_result = await db.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id).order_by(PromptVersion.version.desc())
    )
    versions = versions_result.scalars().all()
    return [{"version": v.version, "created_at": v.created_at.isoformat()} for v in versions]
```

- [ ] **Step 3: Create prompt schemas**

```python
# app/api/schemas/prompt.py
from pydantic import BaseModel


class PromptCreate(BaseModel):
    name: str
    description: str | None = None
    template: str


class PromptUpdate(BaseModel):
    template: str
    description: str | None = None


class PromptResponse(BaseModel):
    name: str
    description: str | None
    active_version: int


class VersionCreate(BaseModel):
    version: int
    template: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git add app/api/routers/admin/prompts.py app/api/schemas/prompt.py
git commit -m "feat: add admin prompts router (CRUD + versioning + activation)"
```

---

### Task 7: Admin Conversations Router

**Files:**
- Create: `app/api/routers/admin/conversations.py`

- [ ] **Step 1: Create conversations router**

```python
# app/api/routers/admin/conversations.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.conversation import Conversation
from app.models.message import Message

router = APIRouter(prefix="/admin/conversations", tags=["admin:conversations"])


@router.get("")
async def list_conversations(
    user_id: str | None = None,
    status: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    sort: str = "created_at",
    order: str = "desc",
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """List conversations with pagination and filtering."""
    query = select(Conversation)
    if user_id:
        query = query.where(Conversation.external_user_id == user_id)
    if status:
        query = query.where(Conversation.status == status)
    if sort == "created_at":
        order_col = Conversation.created_at if order == "asc" else Conversation.created_at.desc()
    query = query.order_by(order_col)
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    convs = result.scalars().all()

    # Count total
    count_query = select(func.count(Conversation.id))
    if user_id:
        count_query = count_query.where(Conversation.external_user_id == user_id)
    if status:
        count_query = count_query.where(Conversation.status == status)
    total = await db.scalar(count_query)

    return {
        "items": [{"id": str(c.id), "external_user_id": c.external_user_id, "status": c.status, "created_at": c.created_at.isoformat()} for c in convs],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/stats")
async def conversation_stats(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get conversation statistics."""
    total = await db.scalar(select(func.count(Conversation.id)))
    active = await db.scalar(select(func.count(Conversation.id)).where(Conversation.status == "active"))
    return {"total": total or 0, "active": active or 0}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get conversation with messages and tool calls."""
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    messages = messages_result.scalars().all()

    return {
        "id": str(conv.id),
        "external_user_id": conv.external_user_id,
        "status": conv.status,
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "text": m.text,
                "error": m.error,
                "model": m.model,
                "latency_ms": m.latency_ms,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.post("/{conversation_id}/replay")
async def replay_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """
    Replay dry-run: re-processes last message through LLM agent pipeline.
    Result is stored in DB but NOT sent to Zalo.
    """
    # Get conversation and last message
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    last_msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction == "inbound")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    if not last_msg:
        raise HTTPException(status_code=400, detail="No inbound message to replay")

    # TODO: Call conversation worker pipeline (reuse existing llm.py logic)
    # This queues the message for processing but with a replay flag
    # The outbound worker suppresses delivery to Zalo
    return {"ok": True, "message": "Replay queued", "message_id": str(last_msg.id)}


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """List messages in a conversation."""
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "direction": m.direction,
            "text": m.text,
            "error": m.error,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
```

- [ ] **Step 2: Verify Message model has `error` column (add if missing)**

Check `app/models/message.py` for the `error` field. If not present, add it:

```python
error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 3: Commit**

```bash
git add app/api/routers/admin/conversations.py
git commit -m "feat: add admin conversations router (list/detail/replay/stats)"
```

---

### Task 8: Admin Analytics Router

**Files:**
- Create: `app/api/routers/admin/analytics.py`
- Create: `app/api/schemas/analytics.py`

- [ ] **Step 1: Create analytics router**

```python
# app/api/routers/admin/analytics.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser
from app.models.conversation import Conversation
from app.models.message import Message

router = APIRouter(prefix="/admin/analytics", tags=["admin:analytics"])


@router.get("/overview")
async def analytics_overview(
    start: str = Query(..., description="ISO date string"),
    end: str = Query(..., description="ISO date string"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Dashboard overview for a time period."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)

    total_messages = await db.scalar(
        select(func.count(Message.id)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt)
        )
    )
    total_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(
            and_(Conversation.created_at >= start_dt, Conversation.created_at <= end_dt)
        )
    )
    # Avg latency (filter out NULLs)
    avg_latency = await db.scalar(
        select(func.avg(Message.latency_ms)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.latency_ms.isnot(None))
        )
    )
    # P95 latency
    p95_result = await db.execute(
        select(Message.latency_ms)
        .where(and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.latency_ms.isnot(None)))
        .order_by(Message.latency_ms)
        .limit(1)
        .offset(int((await db.scalar(
            select(func.count(Message.id)).where(
                and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.latency_ms.isnot(None))
            )
        ) or 1) * 95 // 100)
    )
    p95_row = p95_result.scalar_one_or_none()

    # Fallback rate: messages with error / total messages
    error_count = await db.scalar(
        select(func.count(Message.id)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.error.isnot(None))
        )
    )
    fallback_rate = (error_count or 0) / (total_messages or 1)

    return {
        "period": {"start": start, "end": end},
        "total_messages": total_messages or 0,
        "total_conversations": total_conversations or 0,
        "avg_latency_ms": float(avg_latency) if avg_latency else None,
        "p95_latency_ms": float(p95_row) if p95_row else None,
        "fallback_rate": round(fallback_rate, 4),
    }


@router.get("/messages")
async def message_volume(
    start: str = Query(...),
    end: str = Query(...),
    interval: str = Query("day", description="hour|day"),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Message volume over time grouped by interval."""
    # Simple implementation: group by date
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    result = await db.execute(
        select(
            func.date_trunc('day', Message.created_at).label('bucket'),
            func.count(Message.id).label('count'),
        )
        .where(and_(Message.created_at >= start_dt, Message.created_at <= end_dt))
        .group_by('bucket')
        .order_by('bucket')
    )
    rows = result.all()
    return {"buckets": [{"date": str(r.bucket.date()), "count": r.count} for r in rows]}


@router.get("/latency")
async def latency_percentiles(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """LLM latency percentiles (p50, p95, p99)."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    result = await db.execute(
        select(Message.latency_ms)
        .where(and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.latency_ms.isnot(None)))
        .order_by(Message.latency_ms)
    )
    rows = result.scalars().all()
    if not rows:
        return {"p50": None, "p95": None, "p99": None}
    n = len(rows)
    return {
        "p50": float(rows[n * 50 // 100]),
        "p95": float(rows[n * 95 // 100]),
        "p99": float(rows[n * 99 // 100]) if n >= 100 else float(rows[-1]),
    }


@router.get("/tools")
async def tool_usage(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Tool usage breakdown."""
    # Assumes tool_calls table has tool_name and created_at
    from app.models.tool_call import ToolCall
    result = await db.execute(
        select(ToolCall.tool_name, func.count(ToolCall.id))
        .where(and_(ToolCall.created_at >= datetime.fromisoformat(start), ToolCall.created_at <= datetime.fromisoformat(end)))
        .group_by(ToolCall.tool_name)
    )
    rows = result.all()
    return {"tools": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/fallbacks")
async def fallback_rates(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Fallback rates over time."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    total = await db.scalar(
        select(func.count(Message.id)).where(and_(Message.created_at >= start_dt, Message.created_at <= end_dt))
    )
    errors = await db.scalar(
        select(func.count(Message.id)).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.error.isnot(None))
        )
    )
    return {"total": total or 0, "errors": errors or 0, "rate": round((errors or 0) / (total or 1), 4)}


@router.get("/tokens")
async def token_usage(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Token usage summary from messages.token_usage JSON."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    result = await db.execute(
        select(Message.token_usage).where(
            and_(Message.created_at >= start_dt, Message.created_at <= end_dt, Message.token_usage.isnot(None))
        )
    )
    token_usages = [r for r in result.scalars().all() if r]
    total_input = sum(t.get("input_tokens", 0) for t in token_usages)
    total_output = sum(t.get("output_tokens", 0) for t in token_usages)
    return {"total_input_tokens": total_input, "total_output_tokens": total_output, "message_count": len(token_usages)}
```

- [ ] **Step 2: Create analytics schemas**

```python
# app/api/schemas/analytics.py
from pydantic import BaseModel


class AnalyticsOverview(BaseModel):
    period: dict
    total_messages: int
    total_conversations: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    fallback_rate: float
```

- [ ] **Step 3: Commit**

```bash
git add app/api/routers/admin/analytics.py app/api/schemas/analytics.py
git commit -m "feat: add admin analytics router (overview, messages, latency, tools, fallbacks, tokens)"
```

---

### Task 9: Admin Playground Router

**Files:**
- Create: `app/api/routers/admin/playground.py`
- Create: `app/api/schemas/playground.py`

- [ ] **Step 1: Create playground schemas**

```python
# app/api/schemas/playground.py
from pydantic import BaseModel


class CompletionRequest(BaseModel):
    model_provider: str  # "anthropic" or "openai-compat"
    model_name: str
    system_prompt: str
    messages: list[dict]  # [{"role": str, "content": str}]
    temperature: float | None = 0.7
    max_tokens: int | None = 1024


class BenchmarkRequest(BaseModel):
    name: str
    test_prompts: list[dict]  # [{"name": str, "messages": [...]}]
    models: list[dict]  # [{"provider": str, "name": str}]
    iterations: int
```

- [ ] **Step 2: Create playground router**

```python
# app/api/routers/admin/playground.py
import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.config import api_settings
from app.api.dependencies import get_current_admin_user, get_db
from app.api.schemas.playground import BenchmarkRequest, CompletionRequest
from app.models.admin_user import AdminUser
from app.models.benchmark_result import BenchmarkItem, BenchmarkResult

router = APIRouter(prefix="/admin/playground", tags=["admin:playground"])


@router.post("/complete")
async def single_completion(
    body: CompletionRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Single completion test using configured provider."""
    # Use existing LLM client from app.workers.conversation.llm
    # Provider "anthropic" uses ANTHROPIC_API_KEY
    # Provider "openai-compat" uses OPENAI_BASE_URL + OPENAI_API_KEY
    from app.workers.conversation.llm import LLMClient
    client = LLMClient(provider=body.model_provider, model=body.model_name)
    response = await client.complete(
        system_prompt=body.system_prompt,
        messages=body.messages,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )
    return {"content": response["content"], "usage": response.get("usage"), "latency_ms": response.get("latency_ms")}


@router.post("/benchmark")
async def run_benchmark(
    body: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Start a benchmark run."""
    from app.workers.conversation.llm import LLMClient
    benchmark = BenchmarkResult(
        id=uuid.uuid4(),
        name=body.name,
        status="pending",
        iterations=body.iterations,
    )
    db.add(benchmark)
    await db.commit()

    # Background task to run benchmark
    async def run():
        benchmark.status = "running"
        await db.commit()
        try:
            for model_cfg in body.models:
                client = LLMClient(provider=model_cfg["provider"], model=model_cfg["name"])
                latencies = []
                input_tokens_list = []
                output_tokens_list = []
                raw_results = []
                for i in range(body.iterations):
                    for prompt_cfg in body.test_prompts:
                        result = await client.complete(
                            system_prompt="",
                            messages=prompt_cfg["messages"],
                        )
                        latencies.append(result.get("latency_ms", 0))
                        if result.get("usage"):
                            input_tokens_list.append(result["usage"].get("input_tokens", 0))
                            output_tokens_list.append(result["usage"].get("output_tokens", 0))
                        raw_results.append({"iteration": i, "prompt": prompt_cfg["name"], **result})
                import statistics
                item = BenchmarkItem(
                    id=uuid.uuid4(),
                    benchmark_id=benchmark.id,
                    model_provider=model_cfg["provider"],
                    model_name=model_cfg["name"],
                    avg_latency_ms=statistics.mean(latencies) if latencies else None,
                    p95_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0] if latencies else None,
                    avg_input_tokens=int(statistics.mean(input_tokens_list)) if input_tokens_list else None,
                    avg_output_tokens=int(statistics.mean(output_tokens_list)) if output_tokens_list else None,
                    raw_results=raw_results,
                )
                db.add(item)
            benchmark.status = "completed"
            benchmark.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            benchmark.status = "failed"
            benchmark.error = str(exc)
        await db.commit()

    asyncio.create_task(run())
    return {"id": str(benchmark.id), "status": "pending"}


@router.get("/benchmark/{benchmark_id}")
async def get_benchmark(benchmark_id: str, db: AsyncSession = Depends(get_db), _: AdminUser = Depends(get_current_admin_user)):
    result = await db.execute(select(BenchmarkResult).where(BenchmarkResult.id == benchmark_id))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return {"id": str(b.id), "name": b.name, "status": b.status, "error": b.error, "created_at": b.created_at.isoformat()}


@router.get("/benchmark/{benchmark_id}/results")
async def get_benchmark_results(benchmark_id: str, db: AsyncSession = Depends(get_db), _: AdminUser = Depends(get_current_admin_user)):
    result = await db.execute(select(BenchmarkItem).where(BenchmarkItem.benchmark_id == benchmark_id))
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "model_provider": i.model_provider,
            "model_name": i.model_name,
            "avg_latency_ms": i.avg_latency_ms,
            "p95_latency_ms": i.p95_latency_ms,
            "avg_input_tokens": i.avg_input_tokens,
            "avg_output_tokens": i.avg_output_tokens,
        }
        for i in items
    ]


@router.get("/models")
async def list_models(
    _: AdminUser = Depends(get_current_admin_user),
):
    """List available models (from configured providers)."""
    return {
        "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
        "openai-compat": ["llama3.2", "gpt-4o-mini"],
    }
```

- [ ] **Step 3: Commit**

```bash
git add app/api/routers/admin/playground.py app/api/schemas/playground.py
git commit -m "feat: add admin playground router (completion + benchmark)"
```

---

### Task 10: Admin Zalo Tokens & Monitoring Routers

**Files:**
- Create: `app/api/routers/admin/zalo_tokens.py`
- Create: `app/api/routers/admin/monitoring.py`

- [ ] **Step 1: Create zalo_tokens router**

```python
# app/api/routers/admin/zalo_tokens.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_admin_user, get_db
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
    import secrets
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = secrets.token_urlsafe(32)  # Simplified; real impl would use hash
    return {"code_verifier": code_verifier, "code_challenge": code_challenge, "oauth_url": f"https://oauth.zaloapp.com/v4/permissions?..."}


@router.get("/callback")
async def oauth_callback(
    code: str,
    state: str,
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
```

- [ ] **Step 2: Create monitoring router**

```python
# app/api/routers/admin/monitoring.py
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_admin_user, get_db
from app.models.admin_user import AdminUser

router = APIRouter(prefix="/admin/monitoring", tags=["admin:monitoring"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Detailed health check: DB, Redis, RabbitMQ."""
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = False
    try:
        from app.core.redis import get_redis_client
        r = await get_redis_client()
        await r.ping()
        redis_ok = True
    except Exception:
        pass

    rabbitmq_ok = False
    try:
        from app.core.rabbitmq import get_rabbitmq_channel
        ch = await get_rabbitmq_channel()
        rabbitmq_ok = ch.is_open
    except Exception:
        pass

    return {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "rabbitmq": "ok" if rabbitmq_ok else "error",
    }


@router.get("/metrics")
async def metrics(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """JSON metrics for UI dashboard (not Prometheus format)."""
    from app.models.conversation import Conversation
    from app.models.message import Message
    from sqlalchemy import func

    total_convs = await db.scalar(select(func.count(Conversation.id)))
    total_msgs = await db.scalar(select(func.count(Message.id)))
    avg_latency = await db.scalar(select(func.avg(Message.latency_ms)).where(Message.latency_ms.isnot(None)))

    return {
        "total_conversations": total_convs or 0,
        "total_messages": total_msgs or 0,
        "avg_latency_ms": float(avg_latency) if avg_latency else None,
    }


@router.get("/workers")
async def worker_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Worker status (up/down, last heartbeat)."""
    # TODO: Integrate with worker heartbeat mechanism (could use Redis keys)
    return {"workers": []}


@router.get("/queues")
async def queue_status(
    _: AdminUser = Depends(get_current_admin_user),
):
    """Queue depths and message counts."""
    # TODO: Query RabbitMQ management API or use rabbitmqctl
    return {"queues": []}
```

- [ ] **Step 3: Commit**

```bash
git add app/api/routers/admin/zalo_tokens.py app/api/routers/admin/monitoring.py
git commit -m "feat: add admin zalo-tokens and monitoring routers"
```

---

### Task 11: Main App Integration & CORS

**Files:**
- Modify: `app/api/main.py`
- Modify: `app/api/config.py`

- [ ] **Step 1: Update main.py to include admin router**

In `main.py`, add:
```python
from app.api.routers.admin import auth_router, prompts_router, conversations_router, analytics_router, playground_router, zalo_tokens_router, monitoring_router
```

And add to the router inclusion section:
```python
app.include_router(auth_router)
app.include_router(prompts_router)
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(playground_router)
app.include_router(zalo_tokens_router)
app.include_router(monitoring_router)
```

- [ ] **Step 2: Verify CORS configuration covers frontend origin**

The existing CORS configuration in `main.py` uses `api_settings.cors_origins`. Ensure `ADMIN_CORS_ORIGINS` or similar is configured in `AdminSettings`. Update CORS to include frontend origin:
```python
# In config.py AdminSettings:
admin_cors_origins: str = "http://localhost:3000"
```

- [ ] **Step 3: Run integration tests to verify routes**

```bash
uv run pytest tests/integration/ -v -k "test_webhook" --tb=short 2>&1 | head -30
```
Expected: Existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add app/api/main.py app/api/config.py
git commit -m "feat: include admin routers in FastAPI app"
```

---

### Task 12: Bootstrap Admin User Script

**Files:**
- Create: `app/api/scripts/create_admin_user.py`

- [ ] **Step 1: Create bootstrap script**

```python
#!/usr/bin/env python
"""Bootstrap script to create the initial admin user."""
import argparse
import bcrypt
import sys
import uuid
from datetime import datetime, timezone

from app.core.database import async_session_maker
from app.models.admin_user import AdminUser


async def create_admin(username: str, password: str):
    async with async_session_maker() as db:
        # Check if any admin exists
        from sqlalchemy import select
        result = await db.execute(select(AdminUser))
        existing = result.scalars().first()
        if existing:
            print("ERROR: Admin user already exists. Bootstrap aborted.", file=sys.stderr)
            sys.exit(1)

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        admin = AdminUser(
            id=uuid.uuid4(),
            username=username,
            password_hash=password_hash,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        await db.commit()
        print(f"Admin user '{username}' created successfully.")


if __name__ == "__main__":
    import asyncio
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()
    asyncio.run(create_admin(args.username, args.password))
```

- [ ] **Step 2: Test the script**

```bash
docker-compose exec api /bin/sh -c "echo 'TestAdmin123!' | uv run python app/api/scripts/create_admin_user.py --username admin --password 'TestAdmin123!'"
```

Expected: "Admin user 'admin' created successfully."

- [ ] **Step 3: Commit**

```bash
git add app/api/scripts/create_admin_user.py
git commit -m "feat: add bootstrap admin user script"
```

---

## FRONTEND IMPLEMENTATION

### Task 13: Next.js Project Scaffold

**Files:**
- Create: `frontend/` (entire directory structure)

- [ ] **Step 1: Initialize Next.js 14 project**

Run:
```bash
cd /Users/neo/Projects/AI/neo-chat-platform
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --no-import-alias \
  --turbopack \
  2>&1
```

When prompted:
- TypeScript: Yes
- Tailwind: Yes
- ESLint: Yes
- App Router: Yes
- SrcDir: Yes
- Turbopack: Yes

Expected: `frontend/` directory created with Next.js 14.

- [ ] **Step 2: Install additional dependencies**

Run:
```bash
cd frontend
npm install @tanstack/react-query react-hook-form @hookform/resolvers zod recharts date-fns clsx tailwind-merge lucide-react
npm install -D @types/node
```

- [ ] **Step 3: Install shadcn/ui**

Run:
```bash
cd frontend
npx shadcn@latest init -d 2>&1
```

Accept defaults (style: default, base color: slate, CSS variables: yes).

Then install components:
```bash
npx shadcn@latest add button input label card dialog table tabs form select badge toast -y 2>&1
```

- [ ] **Step 4: Create `.env.local`**

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 5: Commit (frontend scaffolding)**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Next.js 14 project with shadcn/ui, React Query, Zod"
```

---

### Task 14: API Client & Auth Context

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/context/AuthContext.tsx`
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/hooks/useApi.ts`
- Create: `frontend/src/types/api.ts`

- [ ] **Step 1: Create `lib/api.ts`**

```typescript
// frontend/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return res.json();
}

export const api = {
  get: <T>(endpoint: string) => apiRequest<T>(endpoint),
  post: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(endpoint: string) => apiRequest<T>(endpoint, { method: "DELETE" }),
};
```

- [ ] **Step 2: Create `lib/utils.ts`**

```typescript
// frontend/src/lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Create `types/api.ts`**

```typescript
// frontend/src/types/api.ts
export interface AdminUser {
  username: string;
  is_active: boolean;
}

export interface LoginResponse {
  ok: boolean;
  user: AdminUser;
  csrf_token: string;
}

export interface Conversation {
  id: string;
  external_user_id: string;
  status: string;
  created_at: string;
}

export interface Message {
  id: string;
  direction: "inbound" | "outbound";
  text: string;
  error: string | null;
  model: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface AnalyticsOverview {
  period: { start: string; end: string };
  total_messages: number;
  total_conversations: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  fallback_rate: number;
}
```

- [ ] **Step 4: Create `context/AuthContext.tsx`**

```typescript
// frontend/src/context/AuthContext.tsx
"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AdminUser } from "@/types/api";

interface AuthContextValue {
  user: AdminUser | null;
  csrfToken: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api.get<AdminUser>("/admin/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const res = await api.post<{ ok: boolean; user: AdminUser; csrf_token: string }>(
      "/admin/auth/login",
      { username, password }
    );
    setUser(res.user);
    setCsrfToken(res.csrf_token);
  };

  const logout = async () => {
    await api.post("/admin/auth/logout");
    setUser(null);
    setCsrfToken(null);
  };

  return (
    <AuthContext.Provider value={{ user, csrfToken, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
```

- [ ] **Step 5: Create `hooks/useApi.ts`**

```typescript
// frontend/src/hooks/useApi.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Conversation, AnalyticsOverview } from "@/types/api";

export function useConversations(params?: Record<string, string>) {
  const queryStr = params ? "?" + new URLSearchParams(params).toString() : "";
  return useQuery<{ items: Conversation[]; total: number; page: number }>({
    queryKey: ["conversations", params],
    queryFn: () => api.get("/admin/conversations" + queryStr),
    refetchInterval: 30000,
  });
}

export function useConversation(id: string) {
  return useQuery<Conversation & { messages: Message[] }>({
    queryKey: ["conversation", id],
    queryFn: () => api.get(`/admin/conversations/${id}`),
    enabled: !!id,
  });
}

export function useAnalyticsOverview(start: string, end: string) {
  return useQuery<AnalyticsOverview>({
    queryKey: ["analytics", "overview", start, end],
    queryFn: () => api.get(`/admin/analytics/overview?start=${start}&end=${end}`),
    refetchInterval: 30000,
  });
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/utils.ts frontend/src/context/AuthContext.tsx frontend/src/hooks/useAuth.ts frontend/src/hooks/useApi.ts frontend/src/types/api.ts
git commit -m "feat(frontend): add API client, auth context, and React Query hooks"
```

---

### Task 15: Login Page

**Files:**
- Create: `frontend/src/app/(auth)/login/page.tsx`
- Create: `frontend/src/app/(auth)/layout.tsx`
- Create: `frontend/src/components/forms/LoginForm.tsx`

- [ ] **Step 1: Create login page**

```typescript
// frontend/src/app/(auth)/login/page.tsx
"use client";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LoginForm } from "@/components/forms/LoginForm";

export default function LoginPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/admin");
    }
  }, [user, isLoading, router]);

  if (isLoading) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold">NeoChat Admin</h1>
          <p className="text-gray-500">Sign in to your admin account</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create login form component**

```typescript
// frontend/src/components/forms/LoginForm.tsx
"use client";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await login(username, password);
      router.push("/admin");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign In</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
            />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? "Signing in..." : "Sign In"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Create auth layout**

```typescript
// frontend/src/app/(auth)/layout.tsx
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(auth\)/login/page.tsx frontend/src/app/\(auth\)/layout.tsx frontend/src/components/forms/LoginForm.tsx
git commit -m "feat(frontend): add login page and form"
```

---

### Task 16: Admin Layout & Sidebar

**Files:**
- Create: `frontend/src/app/(admin)/layout.tsx`
- Create: `frontend/src/components/admin/Sidebar.tsx`
- Create: `frontend/src/components/admin/Header.tsx`

- [ ] **Step 1: Create admin layout with auth guard**

```typescript
// frontend/src/app/(admin)/layout.tsx
"use client";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/components/admin/Sidebar";
import { Header } from "@/components/admin/Header";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create Sidebar component**

```typescript
// frontend/src/components/admin/Sidebar.tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Play,
  Key,
  Activity,
} from "lucide-react";

const navItems = [
  { href: "/admin/analytics", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/conversations", label: "Conversations", icon: MessageSquare },
  { href: "/admin/prompts", label: "Prompts", icon: FileText },
  { href: "/admin/playground", label: "Playground", icon: Play },
  { href: "/admin/tokens", label: "Tokens", icon: Key },
  { href: "/admin/monitoring", label: "Monitoring", icon: Activity },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-64 flex-col border-r bg-white">
      <div className="border-b p-4">
        <h1 className="text-lg font-bold">NeoChat Admin</h1>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:bg-gray-50"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3: Create Header component**

```typescript
// frontend/src/components/admin/Header.tsx
"use client";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";

export function Header() {
  const { user, logout } = useAuth();
  return (
    <header className="flex h-14 items-center justify-between border-b bg-white px-6">
      <div className="text-sm text-gray-500">Welcome, {user?.username}</div>
      <Button variant="ghost" size="sm" onClick={logout}>
        <LogOut className="mr-2 h-4 w-4" />
        Logout
      </Button>
    </header>
  );
}
```

- [ ] **Step 4: Create admin root redirect page**

```typescript
// frontend/src/app/(admin)/page.tsx
import { redirect } from "next/navigation";

export default function AdminRootPage() {
  redirect("/admin/analytics");
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(admin\)/layout.tsx frontend/src/app/\(admin\)/page.tsx frontend/src/components/admin/Sidebar.tsx frontend/src/components/admin/Header.tsx
git commit -m "feat(frontend): add admin layout with auth guard, sidebar, and header"
```

---

### Task 17: Analytics Dashboard Page

**Files:**
- Create: `frontend/src/app/(admin)/analytics/page.tsx`

- [ ] **Step 1: Create analytics page**

```typescript
// frontend/src/app/(admin)/analytics/page.tsx
"use client";
import { useAnalyticsOverview } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function AnalyticsPage() {
  const end = new Date().toISOString();
  const start = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const { data, isLoading } = useAnalyticsOverview(start, end);

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Total Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data?.total_messages.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Total Conversations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data?.total_conversations.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Avg Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {data?.avg_latency_ms ? `${Math.round(data.avg_latency_ms)}ms` : "N/A"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Fallback Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {data ? `${(data.fallback_rate * 100).toFixed(2)}%` : "N/A"}
            </div>
            <Badge variant={data && data.fallback_rate > 0.1 ? "destructive" : "default"}>
              {data && data.fallback_rate > 0.1 ? "High" : "Normal"}
            </Badge>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/\(admin\)/analytics/page.tsx
git commit -m "feat(frontend): add analytics dashboard page"
```

---

### Task 18: Conversations List & Detail Pages

**Files:**
- Create: `frontend/src/app/(admin)/conversations/page.tsx`
- Create: `frontend/src/app/(admin)/conversations/[id]/page.tsx`

- [ ] **Step 1: Create conversations list page**

```typescript
// frontend/src/app/(admin)/conversations/page.tsx
"use client";
import { useConversations } from "@/hooks/useApi";
import { DataTable } from "@/components/admin/DataTable";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export default function ConversationsPage() {
  const { data, isLoading } = useConversations();

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Conversations</h1>
      <DataTable
        data={data?.items || []}
        columns={[
          { header: "ID", accessor: (row) => <Link href={`/admin/conversations/${row.id}`} className="font-mono text-sm">{row.id.slice(0, 8)}</Link> },
          { header: "User ID", accessor: (row) => row.external_user_id },
          { header: "Status", accessor: (row) => <Badge>{row.status}</Badge> },
          { header: "Created", accessor: (row) => new Date(row.created_at).toLocaleString() },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create conversations detail page**

```typescript
// frontend/src/app/(admin)/conversations/[id]/page.tsx
"use client";
import { useConversation } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ConversationDetailPage({ params }: { params: { id: string } }) {
  const { data, isLoading } = useConversation(params.id);

  if (isLoading) return <div>Loading...</div>;
  if (!data) return <div>Conversation not found</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversation {data.id.slice(0, 8)}</h1>
        <Badge>{data.status}</Badge>
      </div>
      <div className="space-y-4">
        {data.messages.map((msg) => (
          <Card key={msg.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Badge variant={msg.direction === "inbound" ? "default" : "secondary"}>
                  {msg.direction}
                </Badge>
                {msg.model && <span className="text-gray-400 text-xs">{msg.model}</span>}
                {msg.latency_ms && <span className="text-gray-400 text-xs">{Math.round(msg.latency_ms)}ms</span>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap">{msg.text}</p>
              {msg.error && <p className="mt-2 text-sm text-red-500">Error: {msg.error}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create DataTable component**

```typescript
// frontend/src/components/admin/DataTable.tsx
import { Card, CardContent } from "@/components/ui/card";

interface Column<T> {
  header: string;
  accessor: (row: T) => React.ReactNode;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
}

export function DataTable<T>({ data, columns }: DataTableProps<T>) {
  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-gray-50 text-left">
              {columns.map((col) => (
                <th key={col.header} className="px-4 py-3 text-sm font-medium text-gray-500">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                {columns.map((col) => (
                  <td key={col.header} className="px-4 py-3 text-sm">
                    {col.accessor(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length === 0 && <div className="p-8 text-center text-gray-400">No data</div>}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(admin\)/conversations/page.tsx frontend/src/app/\(admin\)/conversations/\[id\]/page.tsx frontend/src/components/admin/DataTable.tsx
git commit -m "feat(frontend): add conversations list and detail pages"
```

---

### Task 19: Prompts Management Page

**Files:**
- Create: `frontend/src/app/(admin)/prompts/page.tsx`
- Create: `frontend/src/app/(admin)/prompts/[name]/page.tsx`
- Create: `frontend/src/components/forms/PromptForm.tsx`

- [ ] **Step 1: Create prompts list page**

```typescript
// frontend/src/app/(admin)/prompts/page.tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function PromptsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: () => api.get<{ name: string; description: string | null; active_version: number }[]>("/admin/prompts"),
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Prompts</h1>
      </div>
      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-gray-50 text-left">
                <th className="px-4 py-3 text-sm font-medium text-gray-500">Name</th>
                <th className="px-4 py-3 text-sm font-medium text-gray-500">Description</th>
                <th className="px-4 py-3 text-sm font-medium text-gray-500">Active Version</th>
                <th className="px-4 py-3 text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((prompt) => (
                <tr key={prompt.name} className="border-b hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link href={`/admin/prompts/${prompt.name}`} className="font-medium hover:underline">
                      {prompt.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">{prompt.description || "—"}</td>
                  <td className="px-4 py-3 text-sm">v{prompt.active_version}</td>
                  <td className="px-4 py-3">
                    <Link href={`/admin/prompts/${prompt.name}`}>
                      <Button variant="ghost" size="sm">Edit</Button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!data || data.length === 0) && <div className="p-8 text-center text-gray-400">No prompts</div>}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create prompt detail/edit page**

```typescript
// frontend/src/app/(admin)/prompts/[name]/page.tsx
"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PromptForm } from "@/components/forms/PromptForm";

export default function PromptDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const queryClient = useQueryClient();
  const [newTemplate, setNewTemplate] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["prompt", name],
    queryFn: () => api.get<{ name: string; description: string | null; active_version: number }>(`/admin/prompts/${name}`),
  });

  const updateMutation = useMutation({
    mutationFn: (template: string) => api.put(`/admin/prompts/${name}`, { template }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
    },
  });

  const activateMutation = useMutation({
    mutationFn: (version: number) => api.post(`/admin/prompts/${name}/activate`, { version }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prompts"] });
      queryClient.invalidateQueries({ queryKey: ["prompt", name] });
    },
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Prompt: {name}</h1>
      <PromptForm onSubmit={(template) => updateMutation.mutate(template)} />
    </div>
  );
}
```

- [ ] **Step 3: Create PromptForm component**

```typescript
// frontend/src/components/forms/PromptForm.tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

interface PromptFormProps {
  onSubmit: (template: string) => void;
  initialValue?: string;
  isLoading?: boolean;
}

export function PromptForm({ onSubmit, initialValue = "", isLoading }: PromptFormProps) {
  const [template, setTemplate] = useState(initialValue);

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="template">Prompt Template</Label>
        <Textarea
          id="template"
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          rows={10}
          className="font-mono text-sm"
        />
      </div>
      <Button onClick={() => onSubmit(template)} disabled={isLoading}>
        {isLoading ? "Saving..." : "Save New Version"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(admin\)/prompts/page.tsx frontend/src/app/\(admin\)/prompts/\[name\]/page.tsx frontend/src/components/forms/PromptForm.tsx
git commit -m "feat(frontend): add prompts management pages"
```

---

### Task 20: Playground Page

**Files:**
- Create: `frontend/src/app/(admin)/playground/page.tsx`

- [ ] **Step 1: Create playground page**

```typescript
// frontend/src/app/(admin)/playground/page.tsx
"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function PlaygroundPage() {
  const [provider, setProvider] = useState("openai-compat");
  const [model, setModel] = useState("llama3.2");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [messages, setMessages] = useState("");
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const completeMutation = useMutation({
    mutationFn: () =>
      api.post<{ content: string }>("/admin/playground/complete", {
        model_provider: provider,
        model_name: model,
        system_prompt: systemPrompt,
        messages: [{ role: "user", content: messages }],
      }),
    onSuccess: (data) => setResponse(data.content),
    onError: (err: any) => setResponse(`Error: ${err.message}`),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    completeMutation.mutate();
    setIsLoading(false);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">LLM Playground</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Complete</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Provider</Label>
                  <Select value={provider} onValueChange={setProvider}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openai-compat">OpenAI Compatible</SelectItem>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Model</Label>
                  <Input value={model} onChange={(e) => setModel(e.target.value)} />
                </div>
              </div>
              <div>
                <Label>System Prompt</Label>
                <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={3} />
              </div>
              <div>
                <Label>User Message</Label>
                <Textarea value={messages} onChange={(e) => setMessages(e.target.value)} rows={4} placeholder="Say hello in 5 words or less" />
              </div>
              <Button type="submit" disabled={isLoading}>
                {isLoading ? "Generating..." : "Generate"}
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Response</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm">{response || "Response will appear here"}</pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/\(admin\)/playground/page.tsx
git commit -m "feat(frontend): add LLM playground page"
```

---

### Task 21: Tokens & Monitoring Pages

**Files:**
- Create: `frontend/src/app/(admin)/tokens/page.tsx`
- Create: `frontend/src/app/(admin)/monitoring/page.tsx`

- [ ] **Step 1: Create tokens page**

```typescript
// frontend/src/app/(admin)/tokens/page.tsx
"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function TokensPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["zalo-token-status"],
    queryFn: () => api.get<{ has_token: boolean; expires_at: string | null }>("/admin/zalo-tokens/status"),
    refetchInterval: 30000,
  });

  const refreshMutation = useMutation({
    mutationFn: () => api.post("/admin/zalo-tokens/refresh"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zalo-token-status"] }),
  });

  const revokeMutation = useMutation({
    mutationFn: () => api.delete("/admin/zalo-tokens"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zalo-token-status"] }),
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Zalo Token Management</h1>
      <Card>
        <CardHeader>
          <CardTitle>Current Token Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Badge variant={data?.has_token ? "default" : "destructive"}>
              {data?.has_token ? "Token Active" : "No Token"}
            </Badge>
            {data?.expires_at && (
              <span className="text-sm text-gray-500">
                Expires: {new Date(data.expires_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button onClick={() => refreshMutation.mutate()} disabled={refreshMutation.isPending}>
              Refresh Token
            </Button>
            <Button variant="destructive" onClick={() => revokeMutation.mutate()} disabled={revokeMutation.isPending}>
              Revoke Token
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create monitoring page**

```typescript
// frontend/src/app/(admin)/monitoring/page.tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function MonitoringPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["monitoring-health"],
    queryFn: () => api.get<{ database: string; redis: string; rabbitmq: string }>("/admin/monitoring/health"),
    refetchInterval: 10000,
  });

  const { data: metrics } = useQuery({
    queryKey: ["monitoring-metrics"],
    queryFn: () => api.get<{ total_conversations: number; total_messages: number; avg_latency_ms: number | null }>("/admin/monitoring/metrics"),
    refetchInterval: 30000,
  });

  if (healthLoading) return <div>Loading...</div>;

  const statusBadge = (status: string) => (
    <Badge variant={status === "ok" ? "default" : "destructive"}>{status}</Badge>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System Monitoring</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Database</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.database) : "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Redis</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.redis) : "—"}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">RabbitMQ</CardTitle>
          </CardHeader>
          <CardContent>{health ? statusBadge(health.rabbitmq) : "—"}</CardContent>
        </Card>
      </div>
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>Total Conversations: {metrics.total_conversations.toLocaleString()}</p>
            <p>Total Messages: {metrics.total_messages.toLocaleString()}</p>
            <p>Avg Latency: {metrics.avg_latency_ms ? `${Math.round(metrics.avg_latency_ms)}ms` : "N/A"}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(admin\)/tokens/page.tsx frontend/src/app/\(admin\)/monitoring/page.tsx
git commit -m "feat(frontend): add tokens and monitoring pages"
```

---

## Self-Review Checklist

**Spec coverage — can you point to a task for each requirement?**

- [x] Session cookie auth (Redis-backed, 24h TTL) → Task 4 (SessionStore), Task 5 (auth router)
- [x] Login/logout/me/password change → Task 5 (auth router)
- [x] CSRF token in login response → Task 5 (auth router returns csrf_token)
- [x] Account lockout (5 failed attempts, 15 min) → Task 5 (auth router)
- [x] Login rate limiting (10/min per IP) → Task 4 (LoginRateLimiter), Task 5 (auth router)
- [x] Prompt CRUD + versioning + activation → Task 6 (prompts router)
- [x] Conversation list/detail/replay/stats → Task 7 (conversations router)
- [x] Replay is dry-run (no Zalo delivery) → Task 7 (replay endpoint)
- [x] Analytics (overview/messages/latency/tools/fallbacks/tokens) → Task 8 (analytics router)
- [x] Playground (completion + benchmark + models) → Task 9 (playground router)
- [x] Zalo token management (status/pkce/callback/refresh/revoke) → Task 10 (zalo_tokens router)
- [x] Monitoring (health/metrics/workers/queues) → Task 10 (monitoring router)
- [x] AdminUsers, BenchmarkResult, BenchmarkItem models → Task 2 (models)
- [x] DB migrations → Task 1 (migrations)
- [x] Bootstrap admin script → Task 12 (create_admin_user.py)
- [x] FastAPI CORS configured for frontend origin → Task 11 (main.py integration)
- [x] Frontend Next.js app scaffold → Task 13 (Next.js project)
- [x] Frontend auth (cookie session, React Context) → Task 14 (AuthContext)
- [x] Admin layout with sidebar/header → Task 16 (admin layout)
- [x] Analytics dashboard page → Task 17
- [x] Conversations list + detail pages → Task 18
- [x] Prompts management pages → Task 19
- [x] Playground page → Task 20
- [x] Tokens + Monitoring pages → Task 21

**Placeholder scan — any "TBD", "TODO", "implement later"?**

The `replay_conversation` in Task 7 has a TODO for the actual LLM pipeline call (leverages existing `llm.py`). The Zalo OAuth callback in Task 10 is a stub. These are intentional per the spec's dry-run design and Zalo OAuth complexity being deferred.

**Type consistency — do method signatures match across tasks?**

- `LoginResponse` schema: Task 5 defines `ok`, `user`, `csrf_token` — frontend `AuthContext.tsx` matches
- `MeResponse`: `username`, `is_active` — frontend `AdminUser` type matches
- `Conversation`: `id`, `external_user_id`, `status`, `created_at` — frontend type matches
- `AnalyticsOverview`: all field names match between backend response and frontend type

---

## Coordination Notes for Team

**Backend first milestones (unblock frontend integration):**
1. Tasks 1–5 (DB migrations, models, session store, auth router) must be done before the frontend login page can be tested end-to-end
2. Tasks 6–10 (remaining admin routers) can proceed in parallel once auth is working

**Frontend build order:**
1. Task 13 (scaffold) can start immediately — no backend dependency
2. Task 14 (API client + auth context) needs backend auth endpoints
3. Tasks 15–21 (pages) can be built in any order once Task 14 is done

**CI/test strategy:**
- Backend: `uv run pytest tests/unit/` must pass after each task
- Frontend: `cd frontend && npm run build` must succeed before commit
- Integration: Manual end-to-end test after backend Tasks 1–5 + frontend Tasks 13–15

**Plan saved at:** `docs/superpowers/plans/2026-04-06-phase2-admin-control-plane.md`
