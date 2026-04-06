# Phase 2 Backend Architecture Design

**Date:** 2026-04-05
**Author:** Backend Architect
**Status:** Draft

---

## 1. Admin Auth Data Model

### 1.1 Design Decisions

- **Cookie-based session authentication** using Redis for session storage
- **No JWT tokens** — session ID stored in HttpOnly cookie, validated server-side via Redis lookup
- **Bcrypt hashing** for passwords (work factor 12)
- **Single admin user** — no role hierarchy in Phase 2

### 1.2 Session Design

Sessions are stored in Redis with the following structure:

```
Key: session:<session_id>
Value: JSON { "user_id": "uuid", "username": "admin", "created_at": "ISO8601" }
TTL: 24 hours (configurable)
```

The `session_id` is a cryptographically random 32-byte hex string (64 hex characters), generated using `secrets.token_hex(32)`.

Cookie settings:
- `HttpOnly`: true (prevents JavaScript access)
- `Secure`: true in production (HTTPS only)
- `SameSite`: Lax
- `Max-Age`: 86400 (24 hours)

### 1.3 New Table: `admin_users`

Stores the single admin account.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | User ID |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL | Login username |
| `password_hash` | VARCHAR(256) | NOT NULL | Bcrypt hash of password |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Account enabled/disabled |
| `last_login_at` | TIMESTAMPTZ | NULL | Last successful login |
| `failed_login_attempts` | INTEGER | NOT NULL, DEFAULT 0 | Consecutive failed attempts |
| `locked_until` | TIMESTAMPTZ | NULL | Account lockout expiry |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update time |

**Indexes:**
- `ix_admin_users_username` on `username`

**Note:** The `role` column exists in the schema for forward compatibility but no logic in Phase 2 depends on it.

### 1.4 Removed: `admin_refresh_tokens` Table

This table is **not created**. Refresh token logic does not apply to cookie-based sessions.

### 1.5 Security Considerations

- **Password policy:** Stored as bcrypt hash (work factor 12)
- **Account lockout:** After 5 consecutive failed logins, lock for 15 minutes
- **Session expiry:** 24 hours; user must re-login after expiry
- **Logout:** Invalidates session immediately by deleting from Redis
- **Rate limiting:** Login endpoint limited to 10 attempts per minute per IP

---

## 2. New API Endpoints Design

All admin endpoints live under `/admin/*` and use session cookie authentication.

### 2.1 Router Structure

```
/admin/
├── auth/           # Authentication (login, logout, me)
├── prompts/        # Prompt CRUD and version management
├── conversations/  # Conversation list, detail, replay
├── analytics/      # Metrics and dashboards
├── playground/     # LLM playground and benchmarking
├── zalo-tokens/    # Zalo OAuth token management
└── monitoring/    # Health checks, metrics
```

### 2.2 Admin Auth Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/auth/login` | Login with username/password | None |
| POST | `/admin/auth/logout` | Logout (invalidate session) | Session cookie |
| GET | `/admin/auth/me` | Get current user info | Session cookie |

**Login Request:**
```json
{
  "username": "admin",
  "password": "secret123"
}
```

**Login Response:**
```json
{
  "ok": true,
  "user": {
    "username": "admin"
  }
}
```

**Login sets cookie:**
```
Set-Cookie: session_id=<random-hex>; HttpOnly; Secure; SameSite=Lax; Max-Age=86400
```

### 2.3 Prompt Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/prompts` | List all prompts | Session |
| POST | `/admin/prompts` | Create new prompt | Session |
| GET | `/admin/prompts/{name}` | Get prompt detail | Session |
| PUT | `/admin/prompts/{name}` | Update prompt template | Session |
| DELETE | `/admin/prompts/{name}` | Delete prompt | Session |
| POST | `/admin/prompts/{name}/versions` | Create new version | Session |
| POST | `/admin/prompts/{name}/activate` | Activate a version | Session |
| GET | `/admin/prompts/{name}/versions` | List all versions | Session |

### 2.4 Conversation Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/conversations` | List conversations (paginated) | Session |
| GET | `/admin/conversations/{id}` | Get conversation detail | Session |
| POST | `/admin/conversations/{id}/replay` | Replay last message (dry-run) | Session |
| GET | `/admin/conversations/{id}/messages` | List messages in conversation | Session |
| GET | `/admin/conversations/stats` | Get conversation statistics | Session |

**Note on `/admin/conversations/{id}/replay`:** This is a **dry-run only** endpoint. It re-queues the conversation's last message for internal reprocessing through the conversation worker. It does NOT deliver any message to Zalo. The replayed message is processed as if it were a new inbound message, but any outbound response is logged only — not sent to the user.

### 2.5 Analytics Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/analytics/overview` | Dashboard overview metrics | Session |
| GET | `/admin/analytics/messages` | Message volume over time | Session |
| GET | `/admin/analytics/latency` | LLM latency percentiles | Session |
| GET | `/admin/analytics/tools` | Tool usage breakdown | Session |
| GET | `/admin/analytics/fallbacks` | Fallback rates | Session |
| GET | `/admin/analytics/tokens` | Token usage summary | Session |

### 2.6 LLM Playground Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/playground/complete` | Single completion test | Session |
| POST | `/admin/playground/benchmark` | Run benchmark against models | Session |
| GET | `/admin/playground/benchmark/{id}` | Get benchmark results | Session |
| GET | `/admin/playground/benchmark/{id}/results` | Get benchmark detailed results | Session |
| GET | `/admin/playground/models` | List available models | Session |

**Note on API keys:** Custom model API key storage is **out of scope for Phase 2**. The playground accepts a model configuration at request time but does not persist API keys to the database. For OpenAI-compatible endpoints, the user provides any required credentials per-request.

### 2.7 Zalo Token Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/zalo-tokens/status` | Get current token status | Session |
| POST | `/admin/zalo-tokens/pkce` | Generate new PKCE pair | Session |
| GET | `/admin/zalo-tokens/callback` | Handle OAuth callback | None (Zalo redirects) |
| POST | `/admin/zalo-tokens/refresh` | Refresh access token | Session |
| DELETE | `/admin/zalo-tokens` | Revoke tokens | Session |

### 2.8 Monitoring Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/monitoring/health` | Detailed health check | Session |
| GET | `/admin/monitoring/metrics` | Metrics dashboard data (JSON) | Session |
| GET | `/admin/monitoring/workers` | Worker status | Session |
| GET | `/admin/monitoring/queues` | Queue depths | Session |

**Note on `/admin/monitoring/metrics`:** This endpoint returns **JSON-formatted metrics** for the monitoring dashboard UI. It is NOT a Prometheus scrape endpoint. If Prometheus integration is needed in the future, a separate `/metrics` endpoint with Prometheus text format would be added.

---

## 3. Database Schema Changes

### 3.1 Summary of Changes

| Change | Type | Description |
|--------|------|-------------|
| `admin_users` | NEW TABLE | Single admin account |
| `benchmark_results` | NEW TABLE | Playground benchmark results |
| `benchmark_items` | NEW TABLE | Individual benchmark test items |
| `conversations` | NEW INDEX | Index on `created_at` for time-range queries |
| `messages` | NEW INDEX | Index on `created_at` for time-range queries |
| `messages` | NEW COLUMN | `error` column for failed messages |

### 3.2 New Tables Detail

#### `admin_users`

```sql
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ NULL,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_admin_users_username ON admin_users (username);
```

#### `benchmark_results`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Result ID |
| `name` | VARCHAR(128) | NOT NULL | Benchmark name |
| `status` | VARCHAR(32) | NOT NULL | pending/running/completed/failed |
| `iterations` | INTEGER | NOT NULL | Number of iterations per model |
| `error` | TEXT | NULL | Error message if failed |
| `created_by` | UUID | FK -> admin_users.id | Who started it |
| `created_at` | TIMESTAMPTZ | NOT NULL | Start time |
| `completed_at` | TIMESTAMPTZ | NULL | Completion time |

#### `benchmark_items`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Item ID |
| `benchmark_id` | UUID | FK -> benchmark_results.id | Parent benchmark |
| `model_provider` | VARCHAR(32) | NOT NULL | anthropic/openai-compat |
| `model_name` | VARCHAR(128) | NOT NULL | Model identifier |
| `base_url` | VARCHAR(256) | NULL | Custom endpoint URL |
| `avg_latency_ms` | FLOAT | NULL | Average latency |
| `p95_latency_ms` | FLOAT | NULL | P95 latency |
| `avg_input_tokens` | INTEGER | NULL | Average input tokens |
| `avg_output_tokens` | INTEGER | NULL | Average output tokens |
| `total_cost` | FLOAT | NULL | Estimated cost |
| `raw_results` | JSONB | NULL | Full iteration results |

**Note:** `api_key` column is intentionally omitted. API keys are not stored in Phase 2.

### 3.3 Index Additions

```sql
CREATE INDEX ix_conversations_created_at ON conversations (created_at DESC);
CREATE INDEX ix_messages_created_at ON messages (created_at DESC);
CREATE INDEX ix_messages_direction_created ON messages (direction, created_at DESC);
```

### 3.4 Column Additions

```sql
ALTER TABLE messages ADD COLUMN error TEXT NULL;
```

---

## 4. Auth Flow

### 4.1 Login Flow

```
Browser                                     API
  |                                          |
  |--- POST /admin/auth/login -------------->|
  |     {username, password}                 |
  |                                          |
  |     1. Lookup admin_users by username    |
  |     2. Check is_active, locked_until     |
  |     3. Verify bcrypt password            |
  |     4. If failed: increment failed_     |
  |        login_attempts, lock if >= 5      |
  |     5. If success: reset failed_attempts|
  |        update last_login_at              |
  |     6. Generate session_id (secrets.     |
  |        token_hex(32))                   |
  |     7. Store in Redis: session:<id>    |
  |        -> {user_id, username, ts}        |
  |     8. Set HttpOnly cookie               |
  |     9. Log auth event                    |
  |                                          |
  |<-- 200 OK {ok: true, user: {...}}       |
  |     Set-Cookie: session_id=...           |
  |                                          |
```

### 4.2 Authenticated Request Flow

```
Browser                                     API
  |                                          |
  |--- GET /admin/prompts ----------------->|
  |     Cookie: session_id=<id>             |
  |                                          |
  |     1. Extract session_id from cookie   |
  |     2. Lookup Redis: session:<id>       |
  |     3. If not found: 401 Unauthorized   |
  |     4. If found: attach user to request |
  |                                          |
  |<-- 200 OK {prompts: [...]}              |
  |                                          |
```

### 4.3 Logout Flow

```
Browser                                     API
  |                                          |
  |--- POST /admin/auth/logout ------------>|
  |     Cookie: session_id=<id>             |
  |                                          |
  |     1. Extract session_id from cookie   |
  |     2. DELETE Redis: session:<id>      |
  |     3. Clear cookie (Max-Age=0)        |
  |     4. Log logout event                 |
  |                                          |
  |<-- 200 OK                               |
  |     Set-Cookie: session_id=; Max-Age=0   |
  |                                          |
```

### 4.4 Session Expiry

Sessions expire automatically after 24 hours via Redis TTL. The browser will receive a 401 on the next request after expiry, prompting re-login.

---

## 5. API Authentication

### 5.1 Authentication Methods Comparison

| Endpoint Type | Auth Method | Where Defined | Use Case |
|---------------|-------------|--------------|----------|
| `/webhooks/*` | Signature verification | Zalo webhook secret | Zalo inbound messages |
| `/internal/*` | X-Internal-Api-Key header | Shared secret in config | Internal service-to-service |
| `/admin/*` | Session cookie (HttpOnly) | Redis session store | Admin UI browser client |

### 5.2 Dependency Injection

**Session-based auth dependency:**
```python
# app/api/dependencies.py

async def get_current_admin_user(
    session_id: str | None = Cookie(None, alias="session_id"),
    redis: Redis = Depends(get_redis),
) -> AdminUser:
    """Validate session cookie and return current admin user."""
    if not session_id:
        raise HTTPException(401, {"code": "NOT_AUTHENTICATED", "message": "Login required"})

    session_data = await redis.get(f"session:{session_id}")
    if not session_data:
        raise HTTPException(401, {"code": "SESSION_EXPIRED", "message": "Session expired, please re-login"})

    # session_data = {"user_id": "...", "username": "admin"}
    # Lookup user, check is_active, return
```

### 5.3 Endpoint Protection

All `/admin/*` endpoints require a valid session cookie. No role-based access control in Phase 2 — the single admin has full access to all endpoints.

### 5.4 Migration Strategy

Existing internal endpoints (`/internal/*`) remain unchanged — they continue to use `X-Internal-Api-Key`. This means:
- Existing internal clients (workers, scripts) don't need changes
- Admin UI uses new session-cookie-based `/admin/*` endpoints
- No breaking changes to Phase 1 functionality

---

## 6. Frontend Auth State

### 6.1 Login Form

The login form posts username/password to `POST /admin/auth/login`. On success, the backend sets the session cookie automatically. The frontend does not store any tokens.

### 6.2 Auth State Management

The frontend uses React Context to track:
- `user: { username: string } | null` — current user info from `/admin/auth/me`
- `isAuthenticated: boolean` — whether a session exists

On app load, call `GET /admin/auth/me` to restore auth state from the session cookie.

### 6.3 No Token Storage

- **No Bearer tokens** stored in memory or localStorage
- **No JWT decode** in frontend
- **No token refresh** logic
- Session cookie is HttpOnly — inaccessible to JavaScript
- All subsequent requests send the cookie automatically via browser

### 6.4 Logout

On logout, call `POST /admin/auth/logout` which clears the cookie server-side. Frontend clears its auth context state.

---

## 7. LLM Playground Backend

### 7.1 Architecture

The playground runs within the API process, reusing the existing LLM client infrastructure from `app.workers.conversation.llm`.

```
Admin UI Browser
      |
      | HTTPS + Session Cookie
      v
FastAPI /admin/playground/*
      |
      +-- Single Completion: Direct LLM call, return response
      |
      +-- Benchmark: Async task, store results in DB
```

### 7.2 API Key Handling

**Phase 2 does not store API keys.** For OpenAI-compatible model benchmarks:
- The user provides credentials (base_url, api_key) in the benchmark request
- These are used for the duration of the benchmark only
- No credentials are persisted to the database

### 7.3 Benchmark Request Example

```json
{
  "test_prompts": [
    {
      "name": "greeting",
      "messages": [{"role": "user", "content": "Say hello in 5 words or less"}]
    }
  ],
  "models": [
    {"provider": "anthropic", "name": "claude-sonnet-4-20250514"},
    {"provider": "openai-compat", "name": "llama3.2", "base_url": "http://localhost:11434/v1", "api_key": "ollama"}
  ],
  "iterations": 3
}
```

---

## 8. Implementation Priority

### Phase 2A (Admin Core)
1. `admin_users` table + seed script
2. Redis session infrastructure
3. `/admin/auth/*` endpoints (login, logout, me)
4. `/admin/monitoring/health`

### Phase 2B (Conversation Management)
1. Extend existing `/internal/conversations` to `/admin/conversations`
2. Replay endpoint (dry-run only)

### Phase 2C (Prompt Management)
1. Prompt CRUD endpoints
2. Version management
3. Activation endpoint

### Phase 2D (Analytics)
1. Analytics query endpoints
2. Dashboard overview endpoint

### Phase 2E (LLM Playground)
1. Single completion endpoint
2. Benchmark infrastructure
3. Results storage and retrieval

### Phase 2F (Zalo Token Management)
1. Expose existing Zalo OAuth flow via admin endpoints
2. Token status and refresh endpoints

---

## 9. File Structure Changes

```
app/
├── api/
│   ├── routers/
│   │   ├── __init__.py           # Add admin_router
│   │   ├── admin/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py           # Login, logout, me
│   │   │   ├── prompts.py        # Prompt CRUD
│   │   │   ├── conversations.py  # Conversation management
│   │   │   ├── analytics.py      # Analytics endpoints
│   │   │   ├── playground.py    # LLM playground
│   │   │   ├── zalo_tokens.py    # Zalo token management
│   │   │   └── monitoring.py     # Health, metrics
│   │   ├── internal.py          # Unchanged
│   │   └── webhooks.py           # Unchanged
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── admin.py              # Shared admin schemas
│   │   ├── analytics.py          # Analytics response models
│   │   └── playground.py         # Playground request/response models
│   ├── dependencies.py           # Add session auth dependencies
│   └── main.py                   # Add admin_router
├── models/
│   ├── __init__.py
│   ├── admin_user.py             # NEW
│   ├── benchmark_result.py      # NEW
│   └── benchmark_item.py        # NEW
└── workers/
    └── conversation/
        └── llm.py               # Unchanged, reused

docs/superpowers/specs/
└── 2026-04-05-phase2-unified-design.md  # This file
```

---

## 10. Migration Notes

### Database Migration

```sql
-- Run via Alembic
alembic revision --autogenerate -m "Add admin tables"

-- SQL for initial setup:
CREATE TABLE admin_users (...);
CREATE TABLE benchmark_results (...);
CREATE TABLE benchmark_items (...);

-- Add column to existing table
ALTER TABLE messages ADD COLUMN error TEXT NULL;

-- Add indexes
CREATE INDEX ix_conversations_created_at ON conversations (created_at DESC);
CREATE INDEX ix_messages_created_at ON messages (created_at DESC);
CREATE INDEX ix_messages_direction_created ON messages (direction, created_at DESC);
```

### Seed Script

```python
# app/api/scripts/create_admin_user.py
# Creates initial admin user for first-time setup
# Usage: uv run python app/api/scripts/create_admin_user.py --username admin --password secret123
```

### Environment Variables

```env
# Admin session settings
ADMIN_SESSION_TTL_SECONDS=86400

# Existing settings used
DATABASE_URL=<existing>
REDIS_URL=<existing>
```

---

## 11. Open Questions

1. **Analytics caching:** Should analytics endpoints use Redis caching? 1-minute TTL for dashboard overview to reduce DB load?

2. **Conversation replay confirmation:** Should replay require a confirmation step (e.g., "Are you sure you want to replay? This will process N messages internally")?

3. **Audit logging:** Log all admin actions (who did what, when)? Consider adding `admin_audit_log` table.
