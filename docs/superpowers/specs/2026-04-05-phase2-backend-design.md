# Phase 2 Backend Architecture Design

**Date:** 2026-04-05
**Author:** Backend Architect
**Status:** Draft

---

## 1. Admin Auth Data Model

### 1.1 Design Decisions

- **Stateless JWT authentication** with access tokens (15 min TTL) and refresh tokens (7 days TTL)
- **Bcrypt hashing** for passwords (work factor 12)
- **Refresh tokens stored in database** (not HttpOnly cookies, since API-only)
- **Single-role model** initially (admin vs super-admin), with extensibility for RBAC later

### 1.2 New Tables

#### `admin_users`

Stores admin user accounts. One row per admin user.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | User ID |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL | Login username |
| `password_hash` | VARCHAR(256) | NOT NULL | Bcrypt hash of password |
| `role` | VARCHAR(32) | NOT NULL, DEFAULT 'admin' | Role: 'admin' or 'super_admin' |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Account enabled/disabled |
| `last_login_at` | TIMESTAMPTZ | NULL | Last successful login |
| `failed_login_attempts` | INTEGER | NOT NULL, DEFAULT 0 | Consecutive failed attempts |
| `locked_until` | TIMESTAMPTZ | NULL | Account lockout expiry |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update time |

**Indexes:**
- `ix_admin_users_username` on `username`
- `ix_admin_users_role` on `role`

#### `admin_refresh_tokens`

Stores active refresh tokens for revocation support.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default uuid4 | Token ID |
| `user_id` | UUID | FK -> admin_users.id, NOT NULL | Owner |
| `token_hash` | VARCHAR(256) | UNIQUE, NOT NULL | SHA-256 hash of token |
| `expires_at` | TIMESTAMPTZ | NOT NULL | Expiration time |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation time |
| `revoked_at` | TIMESTAMPTZ | NULL | Revocation time (if revoked) |

**Indexes:**
- `ix_admin_refresh_tokens_user_id` on `user_id`
- `ix_admin_refresh_tokens_token_hash` on `token_hash`
- `ix_admin_refresh_tokens_expires_at` on `expires_at`

### 1.3 Security Considerations

- **Password policy:** Minimum 12 characters, stored as bcrypt hash (work factor 12)
- **Account lockout:** After 5 consecutive failed logins, lock for 15 minutes
- **Token revocation:** Refresh tokens can be individually revoked; all tokens revoked on password change
- **Audit logging:** All auth events logged (login success/failure, logout, token refresh)

---

## 2. New API Endpoints Design

All admin endpoints live under `/admin/*` and use JWT Bearer authentication.

### 2.1 Router Structure

```
/admin/
├── auth/          # Authentication (login, logout, refresh, me)
├── prompts/       # Prompt CRUD and version management
├── conversations/ # Conversation list, detail, replay
├── analytics/    # Metrics and dashboards
├── playground/    # LLM playground and benchmarking
├── zalo-tokens/   # Zalo OAuth token management
└── monitoring/   # Health checks, metrics
```

### 2.2 Admin Auth Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/auth/login` | Login with username/password | None |
| POST | `/admin/auth/logout` | Logout (revoke refresh token) | JWT |
| POST | `/admin/auth/refresh` | Refresh access token | Refresh token |
| GET | `/admin/auth/me` | Get current user info | JWT |
| POST | `/admin/auth/password` | Change own password | JWT |

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
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 2.3 Prompt Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/prompts` | List all prompts | JWT |
| POST | `/admin/prompts` | Create new prompt | JWT (super_admin) |
| GET | `/admin/prompts/{name}` | Get prompt detail | JWT |
| PUT | `/admin/prompts/{name}` | Update prompt template | JWT (super_admin) |
| DELETE | `/admin/prompts/{name}` | Delete prompt | JWT (super_admin) |
| POST | `/admin/prompts/{name}/versions` | Create new version | JWT (super_admin) |
| POST | `/admin/prompts/{name}/activate` | Activate a version | JWT |
| GET | `/admin/prompts/{name}/versions` | List all versions | JWT |

**Create Prompt Request:**
```json
{
  "name": "customer_support",
  "template": "You are a helpful...",
  "version": "v1.0",
  "created_by": "admin"
}
```

### 2.4 Conversation Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/conversations` | List conversations (paginated) | JWT |
| GET | `/admin/conversations/{id}` | Get conversation detail | JWT |
| POST | `/admin/conversations/{id}/replay` | Replay last message | JWT |
| GET | `/admin/conversations/{id}/messages` | List messages in conversation | JWT |
| GET | `/admin/conversations/stats` | Get conversation statistics | JWT |

**Query Parameters for List:**
- `user_id` - Filter by external user ID
- `status` - Filter by status (active, closed)
- `created_after` - Filter by creation date
- `created_before` - Filter by creation date
- `page` - Page number (default 1)
- `size` - Page size (default 20, max 100)
- `sort` - Sort field (created_at, updated_at)
- `order` - Sort order (asc, desc)

### 2.5 Analytics Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/analytics/overview` | Dashboard overview metrics | JWT |
| GET | `/admin/analytics/messages` | Message volume over time | JWT |
| GET | `/admin/analytics/latency` | LLM latency percentiles | JWT |
| GET | `/admin/analytics/tools` | Tool usage breakdown | JWT |
| GET | `/admin/analytics/fallbacks` | Fallback rates | JWT |
| GET | `/admin/analytics/tokens` | Token usage summary | JWT |

**Overview Response:**
```json
{
  "period": {
    "start": "2026-04-01T00:00:00Z",
    "end": "2026-04-05T00:00:00Z"
  },
  "total_messages": 15234,
  "total_conversations": 2341,
  "unique_users": 1892,
  "avg_latency_ms": 1250,
  "p95_latency_ms": 3200,
  "p99_latency_ms": 5800,
  "tool_success_rate": 0.94,
  "fallback_rate": 0.06,
  "total_tokens_used": 4521000
}
```

### 2.6 LLM Playground Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/playground/complete` | Single completion test | JWT |
| POST | `/admin/playground/benchmark` | Run benchmark against models | JWT |
| GET | `/admin/playground/benchmark/{id}` | Get benchmark results | JWT |
| GET | `/admin/playground/benchmark/{id}/results` | Get benchmark detailed results | JWT |
| GET | `/admin/playground/models` | List available models | JWT |
| POST | `/admin/playground/models` | Add custom model endpoint | JWT (super_admin) |

**Complete Request:**
```json
{
  "model_provider": "anthropic",
  "model_name": "claude-sonnet-4-20250514",
  "system_prompt": "You are a helpful assistant.",
  "messages": [
    {"role": "user", "content": "Hello, who are you?"}
  ],
  "tools": []
}
```

**Benchmark Request:**
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

**Benchmark Result:**
```json
{
  "id": "uuid",
  "status": "completed",
  "results": [
    {
      "model": "claude-sonnet-4-20250514",
      "iterations": 3,
      "avg_latency_ms": 1150,
      "p95_latency_ms": 1800,
      "avg_input_tokens": 120,
      "avg_output_tokens": 85,
      "total_cost": 0.02,
      "responses": [
        {"iteration": 1, "latency_ms": 1100, "text": "...", "tokens": {...}},
        {"iteration": 2, "latency_ms": 1200, "text": "...", "tokens": {...}},
        {"iteration": 3, "latency_ms": 1150, "text": "...", "tokens": {...}}
      ]
    }
  ]
}
```

### 2.7 Zalo Token Management Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/zalo-tokens/status` | Get current token status | JWT |
| POST | `/admin/zalo-tokens/pkce` | Generate new PKCE pair | JWT |
| GET | `/admin/zalo-tokens/callback` | Handle OAuth callback | None (Zalo redirects) |
| POST | `/admin/zalo-tokens/refresh` | Refresh access token | JWT |
| DELETE | `/admin/zalo-tokens` | Revoke tokens | JWT (super_admin) |

### 2.8 Monitoring Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/monitoring/health` | Detailed health check | JWT |
| GET | `/admin/monitoring/metrics` | Prometheus metrics | JWT |
| GET | `/admin/monitoring/workers` | Worker status | JWT |
| GET | `/admin/monitoring/queues` | Queue depths | JWT |

---

## 3. Database Schema Changes

### 3.1 Summary of Changes

| Change | Type | Description |
|--------|------|-------------|
| `admin_users` | NEW TABLE | Admin user accounts |
| `admin_refresh_tokens` | NEW TABLE | Refresh token storage |
| `benchmark_results` | NEW TABLE | Playground benchmark results |
| `benchmark_items` | NEW TABLE | Individual benchmark test items |
| `conversations` | NEW INDEX | Index on `created_at` for time-range queries |
| `messages` | NEW INDEX | Index on `created_at` for time-range queries |
| `messages` | NEW COLUMN | `error` column for failed messages |

### 3.2 New Tables Detail

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
| `api_key` | VARCHAR(256) | NULL | API key (encrypted) |
| `avg_latency_ms` | FLOAT | NULL | Average latency |
| `p95_latency_ms` | FLOAT | NULL | P95 latency |
| `avg_input_tokens` | INTEGER | NULL | Average input tokens |
| `avg_output_tokens` | INTEGER | NULL | Average output tokens |
| `total_cost` | FLOAT | NULL | Estimated cost |
| `raw_results` | JSONB | NULL | Full iteration results |

### 3.3 Index Additions

**New index on `conversations`:**
```sql
CREATE INDEX ix_conversations_created_at ON conversations (created_at DESC);
```

**New index on `messages`:**
```sql
CREATE INDEX ix_messages_created_at ON messages (created_at DESC);
```

**New index on `messages` for analytics queries:**
```sql
CREATE INDEX ix_messages_direction_created ON messages (direction, created_at DESC);
```

### 3.4 Column Additions

**Add `error` column to `messages` table:**
```sql
ALTER TABLE messages ADD COLUMN error TEXT NULL;
```

### 3.5 Analytics Query Optimization

For heavy analytics queries (message volume over time, latency percentiles), consider adding:

**Materialized view or summary table (optional, for scale):**
```sql
CREATE TABLE message_stats_hourly (
    hour TIMESTAMPTZ NOT NULL,
    direction VARCHAR(16) NOT NULL,
    message_count INTEGER NOT NULL,
    avg_latency_ms FLOAT,
    total_tokens INTEGER,
    PRIMARY KEY (hour, direction)
);
```

Refresh hourly via background job.

---

## 4. Auth Flow

### 4.1 Login Flow

```
Client                                    API
  |                                        |
  |--- POST /admin/auth/login ------------>|
  |    {username, password}                |
  |                                        |
  |    1. Lookup admin_users by username   |
  |    2. Check is_active, locked_until   |
  |    3. Verify bcrypt password          |
  |    4. If failed: increment failed_    |
  |       login_attempts, lock if >= 5     |
  |    5. If success: reset failed_attempts|
  |    6. Generate JWT access token (15m)  |
  |    7. Generate refresh token, hash    |
  |       and store in admin_refresh_tokens|
  |    8. Log auth event                   |
  |                                        |
  |<-- 200 OK {access_token, refresh_token}|
  |                                        |
```

### 4.2 Authenticated Request Flow

```
Client                                    API
  |                                        |
  |--- GET /admin/prompts ---------------->|
  |    Authorization: Bearer <access_token>|
  |                                        |
  |    1. Extract JWT from header          |
  |    2. Verify signature, expiration      |
  |    3. Extract user_id from claims      |
  |    4. Check user still exists, active  |
  |    5. Check role permission for route |
  |                                        |
  |<-- 200 OK {prompts: [...]}            |
  |                                        |
```

### 4.3 Token Refresh Flow

```
Client                                    API
  |                                        |
  |--- POST /admin/auth/refresh ---------->|
  |    {refresh_token: "..."}              |
  |                                        |
  |    1. Lookup token_hash in DB          |
  |    2. Verify not expired, not revoked  |
  |    3. Get associated user              |
  |    4. Check user still active          |
  |    5. Generate new access token        |
  |    6. Optionally rotate refresh token  |
  |                                        |
  |<-- 200 OK {access_token, expires_in}  |
  |                                        |
```

### 4.4 Logout Flow

```
Client                                    API
  |                                        |
  |--- POST /admin/auth/logout ----------->|
  |    Authorization: Bearer <access_token>|
  |                                        |
  |    1. Extract refresh_token from body  |
  |    2. Hash and mark revoked in DB     |
  |    3. Log logout event                 |
  |                                        |
  |<-- 200 OK                              |
  |                                        |
```

### 4.5 JWT Token Structure

**Access Token Claims:**
```json
{
  "sub": "user-uuid",
  "username": "admin",
  "role": "admin",
  "type": "access",
  "iat": 1743844800,
  "exp": 1743845700
}
```

**Refresh Token Claims:**
```json
{
  "sub": "user-uuid",
  "type": "refresh",
  "jti": "token-uuid",
  "iat": 1743844800,
  "exp": 1744449600
}
```

### 4.6 Security Considerations

- **Short-lived access tokens:** 15 minutes to limit exposure if token is leaked
- **Refresh token rotation:** Each refresh issues a new refresh token (prevents replay)
- **Revocation on demand:** Logout invalidates refresh token immediately
- **Password change revokes all:** All refresh tokens for user invalidated on password change
- **Rate limiting:** Login endpoint limited to 10 attempts per minute per IP

---

## 5. API Authentication

### 5.1 Authentication Methods Comparison

| Endpoint Type | Auth Method | Where Defined | Use Case |
|---------------|-------------|--------------|----------|
| `/webhooks/*` | Signature verification | Zalo webhook secret | Zalo inbound messages |
| `/internal/*` | X-Internal-Api-Key header | Shared secret in config | Internal service-to-service |
| `/admin/*` | JWT Bearer token | Database-backed users | Admin UI frontend |
| `/auth/*` | None or token in body | OAuth flows | Auth endpoints themselves |

### 5.2 Dependency Injection

**New dependency for admin auth:**
```python
# app/api/dependencies.py

async def get_current_admin_user(
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Validate JWT and return current admin user."""
    # Extract and validate Bearer token
    # Check user exists and is active
    # Return user object
```

**New dependency for role checking:**
```python
def require_role(required_role: str):
    """Dependency factory for role-based access."""
    async def check_role(user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
        if user.role != required_role and user.role != "super_admin":
            raise HTTPException(403, "Insufficient permissions")
        return user
    return check_role
```

### 5.3 Endpoint Protection Matrix

| Endpoint Pattern | Access | Required Role |
|-----------------|--------|--------------|
| `/admin/auth/*` | authenticated | any |
| `/admin/monitoring/health` | authenticated | any |
| `/admin/prompts GET` | authenticated | any |
| `/admin/prompts POST/PUT/DELETE` | authenticated | super_admin |
| `/admin/conversations/*` | authenticated | any |
| `/admin/analytics/*` | authenticated | any |
| `/admin/playground GET` | authenticated | any |
| `/admin/playground POST` | authenticated | super_admin |
| `/admin/zalo-tokens GET` | authenticated | any |
| `/admin/zalo-tokens DELETE` | authenticated | super_admin |

### 5.4 Migration Strategy

Existing internal endpoints (`/internal/*`) remain unchanged - they continue to use `X-Internal-Api-Key`. This means:
- Existing internal clients (workers, scripts) don't need changes
- Admin UI uses new JWT-based `/admin/*` endpoints
- No breaking changes to Phase 1 functionality

---

## 6. LLM Playground Backend

### 6.1 Architecture

The playground service runs within the API process, using the existing LLM client infrastructure from `app.workers.conversation.llm`.

```
Admin UI Browser
      |
      | HTTPS + JWT Auth
      v
FastAPI /admin/playground/*
      |
      +-- Single Completion: Direct LLM call, return response
      |
      +-- Benchmark: Async task, store results in DB
```

### 6.2 Single Completion Flow

1. Receive completion request with model config and messages
2. Validate model config (check it's a supported provider)
3. Create appropriate LLM client (AnthropicLLM or OpenAICompatLLM)
4. Call the LLM with timing
5. Capture response text, latency, token usage
6. Return results

**Note:** Single completions are synchronous (timeout ~60s). Long-running requests should use the benchmark endpoint.

### 6.3 Benchmark Flow

1. Receive benchmark request with test prompts and models
2. Create `benchmark_result` record in DB (status=pending)
3. For each model:
   - For each iteration:
     - Call LLM with test prompt
     - Store response, latency, tokens
   - Compute aggregate stats (avg latency, p95, etc.)
4. Update `benchmark_result` status=completed
5. Return benchmark ID for polling

**Async execution:** Benchmarks run in background tasks to avoid timeout. Client polls for completion.

### 6.4 Supported Model Configurations

```python
class PlaygroundModel(BaseModel):
    """Configuration for a playground model."""
    provider: Literal["anthropic", "openai-compat"]
    name: str  # Model name (e.g., "claude-sonnet-4-20250514")
    base_url: str | None = None  # Required for openai-compat if not default
    api_key: str | None = None  # Required for openai-compat
```

### 6.5 Token Usage and Cost Estimation

**Token counting:** Use LLM provider's returned token counts.

**Cost estimation:**
- Anthropic: $3.75/M input tokens, $18.75/M output tokens (Sonnet 4)
- OpenAI-compatible: User-provided rates or default $0

Store cost in `benchmark_items.total_cost`.

### 6.6 LLM Client Integration

Reuse `app.workers.conversation.llm`:

```python
from app.workers.conversation.llm import create_llm_client, AnthropicLLM, OpenAICompatLLM

# For playground, we create clients ad-hoc
if provider == "anthropic":
    client = AnthropicLLM(
        api_key=model_config.api_key or api_settings.anthropic_api_key,
        model=model_config.name,
        timeout=60  # Longer timeout for playground
    )
else:
    client = OpenAICompatLLM(
        base_url=model_config.base_url,
        api_key=model_config.api_key,
        model=model_config.name,
        timeout=60
    )

response = await client.complete(
    system_prompt=system_prompt,
    messages=messages,
    tools=tools
)
```

### 6.7 Benchmark Result Storage

```json
{
  "id": "uuid",
  "benchmark_id": "uuid",
  "model_provider": "anthropic",
  "model_name": "claude-sonnet-4-20250514",
  "iterations": [
    {
      "iteration": 1,
      "latency_ms": 1100,
      "input_tokens": 120,
      "output_tokens": 85,
      "text": "Hello! I am a helpful AI...",
      "error": null
    },
    {
      "iteration": 2,
      "latency_ms": 1200,
      "input_tokens": 120,
      "output_tokens": 92,
      "text": "Hi there! I'm ready to help...",
      "error": null
    }
  ],
  "stats": {
    "avg_latency_ms": 1150,
    "p95_latency_ms": 1200,
    "avg_input_tokens": 120,
    "avg_output_tokens": 88.5,
    "total_cost": 0.012
  }
}
```

---

## 7. Implementation Priority

### Phase 2A (MVP - Admin Core)
1. `admin_users` table + seed script
2. JWT auth infrastructure
3. `/admin/auth/*` endpoints
4. `/admin/monitoring/health`
5. Extend existing `/internal/conversations` to `/admin/conversations`

### Phase 2B (Prompt Management)
1. Prompt CRUD endpoints
2. Version management
3. Activation endpoint (can reuse/extend internal)

### Phase 2C (Analytics)
1. Analytics query endpoints
2. Dashboard overview endpoint

### Phase 2D (LLM Playground)
1. Single completion endpoint
2. Benchmark infrastructure
3. Results storage and retrieval

### Phase 2E (Zalo Token UI Integration)
1. Expose existing Zalo OAuth flow via admin endpoints
2. Token status and refresh endpoints

---

## 8. File Structure Changes

```
app/
├── api/
│   ├── routers/
│   │   ├── __init__.py           # Add admin_router
│   │   ├── admin/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py           # Login, logout, refresh, me
│   │   │   ├── prompts.py        # Prompt CRUD
│   │   │   ├── conversations.py  # Conversation management
│   │   │   ├── analytics.py      # Analytics endpoints
│   │   │   ├── playground.py     # LLM playground
│   │   │   ├── zalo_tokens.py    # Zalo token management
│   │   │   └── monitoring.py     # Health, metrics
│   │   ├── internal.py          # Unchanged
│   │   └── webhooks.py           # Unchanged
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── admin.py              # Shared admin schemas
│   │   ├── analytics.py          # Analytics response models
│   │   └── playground.py         # Playground request/response models
│   ├── dependencies.py           # Add admin auth dependencies
│   └── main.py                   # Add admin_router
├── models/
│   ├── __init__.py
│   ├── admin_user.py             # NEW
│   ├── admin_refresh_token.py    # NEW
│   ├── benchmark_result.py       # NEW
│   └── benchmark_item.py         # NEW
└── workers/
    └── conversation/
        └── llm.py                # Unchanged, reused

docs/superpowers/specs/
└── 2026-04-05-phase2-backend-design.md  # This file
```

---

## 9. Migration Notes

### Database Migration

```sql
-- Run via Alembic
alembic revision --autogenerate -m "Add admin tables"

-- Or raw SQL for initial setup:
CREATE TABLE admin_users (...);
CREATE TABLE admin_refresh_tokens (...);
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
# New admin settings
ADMIN_JWT_SECRET=<generate-with-openssl-rand-base64-32>
ADMIN_JWT_ACCESS_TOKEN_TTL_MINUTES=15
ADMIN_JWT_REFRESH_TOKEN_TTL_DAYS=7

# Existing settings used
DATABASE_URL=<existing>
REDIS_URL=<existing>
```

---

## 10. Open Questions

1. **Rate limiting for analytics:** Should analytics endpoints be cached? Redis caching with 1-minute TTL for dashboard overview?

2. **LLM Playground API key security:** Should custom model API keys be encrypted at rest? Currently stored as-is.

3. **Token expiration on password change:** Should we invalidate ALL refresh tokens or just the current one? (Recommend: all for security)

4. **Super admin creation:** How is the first super_admin created? Seed script only? (Yes)

5. **Audit logging:** Log all admin actions (who did what, when)? Consider adding `admin_audit_log` table.
