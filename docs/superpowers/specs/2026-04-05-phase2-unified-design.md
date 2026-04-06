# NeoChatPlatform Phase 2 — Admin Control Plane Design

**Date:** 2026-04-05
**Last Updated:** 2026-04-06
**Status:** Draft — Pending User Review
**Team:** backend-architect + frontend-architect

---

## 1. Overview

Phase 2 delivers an admin control plane for NeoChatPlatform: a web-based UI to manage conversations, prompts, analytics, LLM benchmarking, Zalo token lifecycle, and system monitoring.

**Key decisions:**
- **Frontend:** Next.js 14+ (App Router), separate from API, deployable independently
- **Backend:** Embedded in existing FastAPI service — extend with `/admin/*` routes, no new service
- **Auth:** Single-admin username/password login with a secure httpOnly cookie-backed session. No JWT, no refresh tokens, no token storage in frontend.
- **Session storage:** Redis-backed sessions with opaque session ID cookie. TTL: 24h.
- **Admin Model:** Single admin user. No RBAC for Phase 2.
- **LLM Focus:** OpenAI-compatible model support for playground and benchmarking (no custom model API key storage)
- **Analytics:** Polling via React Query (30s interval) — no WebSocket complexity for Phase 2
- **CORS:** FastAPI CORS configured for frontend origin — no Next.js proxy needed

**Out of scope:** SSO, multi-tenant, mobile, A/B testing (Phase 5), role-based access, multiple admin accounts, refresh tokens, JWT, custom model endpoint storage.

---

## 2. Architecture

### 2.1 System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Admin Browser (Next.js)                       │
│   /admin/auth, /admin/conversations, /admin/prompts, etc.          │
└─────────────────────────────────────────────────────────────────────┘
                                │ HTTPS + httpOnly session cookie
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI (port 8000)                                │
│                                                                      │
│   Existing (Phase 1):          New (Phase 2):                       │
│   ├── /webhooks/*               └── /admin/*                        │
│   ├── /health/*                    ├── /admin/auth/*                │
│   └── /internal/*                   ├── /admin/prompts/*            │
│                                        ├── /admin/conversations/*    │
│                                        ├── /admin/analytics/*        │
│                                        ├── /admin/playground/*       │
│                                        ├── /admin/zalo-tokens/*       │
│                                        └── /admin/monitoring/*       │
└─────────────────────────────────────────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   PostgreSQL              Redis                  RabbitMQ
   (admin_users,           (sessions,             (queues unchanged)
    benchmark_results,      dedup)
    benchmark_items)
```

### 2.2 Session Flow

```
Browser                              FastAPI
   |                                     |
   |-- POST /admin/auth/login ---------->|
   |   {username, password}              |
   |                                     | Verify bcrypt
   |                                     | Create session ID (random 32 bytes hex)
   |                                     | Store in Redis: key="session:<id>", TTL=24h
   |                                     | Set-Cookie: session_id=<id>; HttpOnly; SameSite=Lax; Max-Age=86400
   |<-- 200 {ok: true, user: {...}} ------|
   |   [Browser stores cookie automatically]
   |                                     |
   |-- GET /admin/conversations -------->|
   |   Cookie: session_id=<id>           |
   |                                     | Lookup Redis "session:<id>"
   |                                     | Validate session, get user
   |<-- 200 {conversations: [...]} -------|
   |                                     |
   |-- POST /admin/auth/logout --------->|
   |   Cookie: session_id=<id>            |
   |                                     | Delete Redis "session:<id>"
   |                                     | Set-Cookie: session_id=; Max-Age=0
   |<-- 200 {ok: true} -------------------|
```

### 2.3 Backend Integration Points

| Concern | Phase 1 | Phase 2 Extension |
|---------|---------|-------------------|
| Router | `app/api/routers/` | New `app/api/routers/admin/` |
| Models | `app/models/` | New `admin_user`, `benchmark_result`, `benchmark_item` |
| Schemas | `app/api/schemas/` | New `admin.py`, `analytics.py`, `playground.py` |
| Dependencies | `app/api/dependencies.py` | Add `get_current_admin_user` (session-based) |
| Main | `app/api/main.py` | Add `admin_router` with `/admin/*` prefix |
| Redis | existing | New key prefix `session:` for admin sessions |

### 2.4 Frontend Integration Points

| Concern | Value |
|---------|-------|
| API Base | `NEXT_PUBLIC_API_URL` env var (default: `http://localhost:8000`) |
| Auth | Browser cookie (httpOnly) — no token storage in React state |
| Session check | `GET /admin/auth/me` returns `{username, is_active}` |
| CORS | FastAPI configured with frontend origin — same-machine deploy uses Docker network |
| Dev CORS | Backend allows `http://localhost:3000` for Next.js dev server |

---

## 3. Data Model

### 3.1 New Tables

#### `admin_users`
Stores the single admin account. username/password only — no roles for Phase 2.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL |
| `password_hash` | VARCHAR(256) | NOT NULL (bcrypt, work factor 12) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE |
| `last_login_at` | TIMESTAMPTZ | NULL |
| `failed_login_attempts` | INTEGER | NOT NULL, DEFAULT 0 |
| `locked_until` | TIMESTAMPTZ | NULL (account lockout after 5 failed attempts, 15 min) |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

**Indexes:** `ix_admin_users_username`

> **Note:** `role` column is reserved for future use. No logic in Phase 2 depends on it.

#### `benchmark_results`
Stores playground benchmark runs.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `name` | VARCHAR(128) | NOT NULL |
| `status` | VARCHAR(32) | NOT NULL — `pending`, `running`, `completed`, `failed` |
| `iterations` | INTEGER | NOT NULL |
| `error` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `completed_at` | TIMESTAMPTZ | NULL |

#### `benchmark_items`
Stores per-model results within a benchmark.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `benchmark_id` | UUID | FK → `benchmark_results.id` |
| `model_provider` | VARCHAR(32) | NOT NULL (`anthropic`, `openai-compat`) |
| `model_name` | VARCHAR(128) | NOT NULL |
| `avg_latency_ms` | FLOAT | NULL |
| `p95_latency_ms` | FLOAT | NULL |
| `avg_input_tokens` | INTEGER | NULL |
| `avg_output_tokens` | INTEGER | NULL |
| `total_cost` | FLOAT | NULL |
| `raw_results` | JSONB | NULL (full iteration details) |

> **Note:** `api_key` and `base_url` columns are intentionally omitted. Phase 2 playground uses only pre-configured providers (Anthropic API key from env, OpenAI-compatible from env). No custom model endpoint storage.

### 3.2 Schema Additions to Existing Tables

**`messages` — add `error` column:**
```sql
ALTER TABLE messages ADD COLUMN error TEXT NULL;
```

**New indexes for analytics queries:**
```sql
CREATE INDEX ix_conversations_created_at ON conversations (created_at DESC);
CREATE INDEX ix_messages_created_at ON messages (created_at DESC);
CREATE INDEX ix_messages_direction_created ON messages (direction, created_at DESC);
```

### 3.3 Session Storage (Redis)

```
Key:   session:<session_id>
Value: JSON { "user_id": "...", "username": "admin", "created_at": "..." }
TTL:   86400 (24 hours)
```

Session ID: 32 random bytes, hex-encoded (64 hex chars). Generated with `secrets.token_hex(32)`.

### 3.4 Removed Tables

- **`admin_refresh_tokens`** — not needed. Cookie-session with Redis replaces the JWT + refresh token model entirely.

---

## 4. API Design

All admin endpoints use session cookie authentication (except login and OAuth callback). The session cookie is sent automatically by the browser — no `Authorization: Bearer` header.

### 4.1 Router Structure

```
/admin/
├── auth/              # Login, logout, me, password change
├── prompts/           # CRUD + versioning + activation
├── conversations/     # List, detail, replay (dry-run), message history
├── analytics/         # Overview, message volume, latency, tools, fallbacks, tokens
├── playground/        # Single completion, benchmark, models
├── zalo-tokens/       # Status, PKCE OAuth, refresh, revoke
└── monitoring/        # Health, metrics, workers, queues
```

### 4.2 Auth Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/auth/login` | Login with username/password | None |
| POST | `/admin/auth/logout` | Logout (clear session) | Session cookie |
| GET | `/admin/auth/me` | Get current user info | Session cookie |
| POST | `/admin/auth/password` | Change own password | Session cookie |

**Login Request:**
```json
{
  "username": "admin",
  "password": "..."
}
```

**Login Response (200 OK):**
```json
{
  "ok": true,
  "user": {
    "username": "admin",
    "is_active": true
  }
}
```
*Sets `Set-Cookie: session_id=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400`*

**Me Response (200 OK):**
```json
{
  "username": "admin",
  "is_active": true
}
```

**Logout Response (200 OK):**
```json
{
  "ok": true
}
```
*Sets `Set-Cookie: session_id=; Max-Age=0` to clear the cookie.*

**Error Responses:**
- `401 Unauthorized` — invalid credentials or expired session
- `429 Too Many Requests` — rate limited (10 attempts/min per IP)

### 4.3 Session Cookie Configuration

| Attribute | Value |
|-----------|-------|
| `HttpOnly` | Always |
| `Secure` | `true` in production, `false` in development |
| `SameSite` | `Lax` |
| `Max-Age` | 86400 (24 hours) |
| `Path` | `/` |

### 4.4 Prompt Endpoints

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

### 4.5 Conversation Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/conversations` | List (paginated, filterable) | Session |
| GET | `/admin/conversations/{id}` | Get conversation + messages + tool calls | Session |
| POST | `/admin/conversations/{id}/replay` | Replay last message (dry-run only) | Session |
| GET | `/admin/conversations/{id}/messages` | List messages in conversation | Session |
| GET | `/admin/conversations/stats` | Get conversation statistics | Session |

**Query params for list:** `user_id`, `status`, `created_after`, `created_before`, `page`, `size`, `sort`, `order`

> **Conversation Replay:** `/admin/conversations/{id}/replay` re-queues the last inbound message through the conversation worker pipeline. It is a **dry-run** — the replay processes through the LLM and tools but the resulting outbound message is **NOT delivered to Zalo**. It is logged and stored in DB for debugging/review only. This allows testing prompt changes against real conversation history without sending anything to the end user.

### 4.6 Analytics Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/analytics/overview` | Dashboard overview | Session |
| GET | `/admin/analytics/messages` | Message volume over time | Session |
| GET | `/admin/analytics/latency` | LLM latency percentiles | Session |
| GET | `/admin/analytics/tools` | Tool usage breakdown | Session |
| GET | `/admin/analytics/fallbacks` | Fallback rates | Session |
| GET | `/admin/analytics/tokens` | Token usage summary | Session |

**Overview Response:**
```json
{
  "period": { "start": "2026-04-01T00:00:00Z", "end": "2026-04-06T00:00:00Z" },
  "total_messages": 15234,
  "total_conversations": 2341,
  "avg_latency_ms": 1250,
  "p95_latency_ms": 3200,
  "fallback_rate": 0.06
}
```

### 4.7 Playground Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/playground/complete` | Single completion test | Session |
| POST | `/admin/playground/benchmark` | Run benchmark | Session |
| GET | `/admin/playground/benchmark/{id}` | Get benchmark result | Session |
| GET | `/admin/playground/benchmark/{id}/results` | Get benchmark detailed results | Session |
| GET | `/admin/playground/models` | List available models | Session |

> **Custom model endpoints** are out of scope for Phase 2. The playground only supports: (1) Anthropic models via `ANTHROPIC_API_KEY` from env, (2) OpenAI-compatible models via the configured `OPENAI_BASE_URL` + `OPENAI_API_KEY`. No custom endpoint or API key storage.

**Complete Request:**
```json
{
  "model_provider": "openai-compat",
  "model_name": "llama3.2",
  "system_prompt": "You are a helpful...",
  "messages": [
    {"role": "user", "content": "Hello, who are you?"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

**Benchmark Request:**
```json
{
  "name": "Model comparison test",
  "test_prompts": [
    {
      "name": "greeting",
      "messages": [{"role": "user", "content": "Say hello in 5 words or less"}]
    }
  ],
  "models": [
    {"provider": "openai-compat", "name": "llama3.2"},
    {"provider": "anthropic", "name": "claude-sonnet-4-20250514"}
  ],
  "iterations": 3
}
```

### 4.8 Zalo Token Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/zalo-tokens/status` | Current token status | Session |
| POST | `/admin/zalo-tokens/pkce` | Generate PKCE pair | Session |
| GET | `/admin/zalo-tokens/callback` | OAuth callback (Zalo redirects) | None (Zalo redirect) |
| POST | `/admin/zalo-tokens/refresh` | Refresh access token | Session |
| DELETE | `/admin/zalo-tokens` | Revoke tokens | Session |

### 4.9 Monitoring Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/monitoring/health` | Detailed health check (DB, Redis, RabbitMQ) | Session |
| GET | `/admin/monitoring/metrics` | JSON metrics for UI dashboard (not Prometheus) | Session |
| GET | `/admin/monitoring/workers` | Worker status (up/down, last heartbeat) | Session |
| GET | `/admin/monitoring/queues` | Queue depths and message counts | Session |

> **On `/admin/monitoring/metrics`:** This endpoint returns JSON formatted for the admin UI monitoring dashboard (charts, gauges). It is **not** a Prometheus-compatible scrape endpoint. Prometheus integration would be a separate future endpoint (e.g., `/metrics/prometheus`).

### 4.10 Auth Flow Summary

```
Login:
  POST /admin/auth/login {username, password}
  → 200 {ok: true, user: {username, is_active}}
  → Set-Cookie: session_id=<opaque>; HttpOnly; SameSite=Lax; Max-Age=86400

Authenticated requests:
  Cookie: session_id=<opaque>
  → Backend: Redis lookup "session:<id>"
  → Valid? → process request
  → Invalid/expired? → 401 Unauthorized

Logout:
  POST /admin/auth/logout
  → Delete Redis session key
  → Set-Cookie: session_id=; Max-Age=0
  → 200 {ok: true}

Me:
  GET /admin/auth/me
  → Returns {username, is_active} from session
```

---

## 5. Frontend Architecture

### 5.1 Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | Next.js 14+ (App Router) | SSR for analytics, file-based routing, deploy flexibility |
| Language | TypeScript (strict) | Type safety |
| Styling | Tailwind CSS + shadcn/ui | Consistent, accessible components |
| State | React Query (server state) + React Context (auth user info) | Simple, sufficient for 6 pages |
| Forms | React Hook Form + Zod | Validation |
| Charts | Recharts | Simple, composable |
| Auth | Direct cookie session — no auth library | Browser handles cookie, backend validates |

**Removed:** NextAuth.js, Zustand, Bearer tokens, auth proxy complexity.

### 5.2 Auth Implementation

**Frontend auth is simple:**
1. `POST /admin/auth/login` with form data
2. On success: response includes user info; browser has already stored the session cookie automatically
3. Session state in React Context: `{ username: string | null, isActive: boolean }`
4. `GET /admin/auth/me` on app load to confirm active session
5. `POST /admin/auth/logout` clears cookie server-side, clears React Context

**No:**
- Bearer tokens in headers
- Tokens in localStorage or memory
- Refresh token logic
- NextAuth.js or similar

### 5.3 Folder Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── (auth)/              # Auth layout group
│   │   │   ├── login/
│   │   │   └── layout.tsx
│   │   ├── (admin)/             # Protected admin layout group
│   │   │   ├── layout.tsx       # Sidebar + header + content
│   │   │   ├── page.tsx         # Dashboard (redirect to /admin/analytics)
│   │   │   ├── conversations/
│   │   │   ├── prompts/
│   │   │   ├── analytics/
│   │   │   ├── playground/
│   │   │   ├── tokens/
│   │   │   └── monitoring/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── ui/                  # shadcn/ui base components
│   │   ├── admin/               # Sidebar, Header, DataTable, StatusBadge, ConfirmDialog
│   │   └── forms/
│   ├── lib/
│   │   ├── api.ts               # Typed API client (fetch with cookie credentials)
│   │   └── utils.ts
│   ├── hooks/
│   │   ├── useAuth.ts           # React Context consumer
│   │   └── useApi.ts
│   ├── context/
│   │   └── AuthContext.tsx      # { user, login, logout, isLoading }
│   └── types/
│       └── api.ts
└── .env.local                   # NEXT_PUBLIC_API_URL
```

### 5.4 API Client (lib/api.ts)

```typescript
// All requests include credentials (cookies) automatically
const apiRequest = async <T>(endpoint: string, options?: RequestInit): Promise<T> => {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    credentials: 'include',  // Required: sends session cookie
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
};

// No Authorization headers needed — session cookie handled by browser
```

### 5.5 Navigation

```
Sidebar (fixed left, collapsible to icon-only):
├── Dashboard      → /admin/analytics (analytics overview)
├── Conversations  → /admin/conversations
├── Prompts        → /admin/prompts
├── Playground     → /admin/playground
├── Tokens         → /admin/tokens
└── Monitoring     → /admin/monitoring
```

### 5.6 Build Priority

| Phase | Duration | Deliverables |
|-------|----------|---------------|
| **Phase 1 (MVP)** | 2 weeks | Auth + Shell, Conversation list/detail |
| **Phase 2** | 3 weeks | Prompt management, Analytics dashboard |
| **Phase 3** | 2 weeks | LLM Playground (chat, streaming), Token management |
| **Phase 4** | 1 week | Monitoring dashboard, Polish |

---

## 6. Key Design Decisions

### 6.1 Auth: Simple cookie-backed session (Phase 2)
- Single admin username/password — no multiple accounts, no roles
- Opaque session ID generated server-side, stored in Redis with 24h TTL
- httpOnly, SameSite=Lax cookie — browser JS cannot access the session ID
- No JWT, no access tokens, no refresh tokens
- Account lockout after 5 failed login attempts (15 min lockout)
- Login rate limiting: 10 attempts/min per IP (via Redis sliding window)

### 6.2 Conversation replay is a dry-run
- Replay re-processes the last message through the LLM agent pipeline
- The resulting response is stored in DB but **NOT sent to Zalo**
- This allows testing prompt changes against real conversation context safely

### 6.3 Playground uses only configured providers
- Phase 2: No custom model endpoint storage in DB
- Anthropic: uses `ANTHROPIC_API_KEY` from env
- OpenAI-compatible: uses `OPENAI_BASE_URL` + `OPENAI_API_KEY` from env

### 6.4 Monitoring metrics is a UI endpoint
- Returns JSON for charts/gauges in the admin UI
- Not Prometheus format — separate endpoint if Prometheus needed later

### 6.5 Backend embedded, not separate
- `/admin/*` routes added to existing FastAPI app
- Same PostgreSQL, Redis, RabbitMQ as Phase 1
- No new service to operate
- Existing `/internal/*` endpoints unchanged — Phase 1 keeps working

---

## 7. Security Considerations

- **Session ID:** 32 random bytes hex, unguessable, stored in Redis only
- **Password hashing:** bcrypt work factor 12
- **Session cookie:** `HttpOnly` (no XSS access), `SameSite=Lax`, `Secure` in production
- **Session TTL:** 24 hours in Redis — automatic expiry
- **Account lockout:** 5 failed attempts → 15 min lockout
- **Login rate limiting:** 10 attempts/min per IP (Redis sliding window)
- **CORS:** Only `http://localhost:3000` for dev; proper origins in production
- **Audit logging:** All auth events (login success/failure, logout) written to structured logs
- **No sensitive data in logs:** Session IDs, tokens, passwords never logged

---

## 8. File Changes Summary

### Backend (Phase 2 additions)

```
app/
├── api/
│   ├── routers/admin/
│   │   ├── __init__.py
│   │   ├── auth.py           # login, logout, me, password — session-based
│   │   ├── prompts.py
│   │   ├── conversations.py   # + replay (dry-run)
│   │   ├── analytics.py
│   │   ├── playground.py     # completion + benchmark (no custom endpoint storage)
│   │   ├── zalo_tokens.py
│   │   └── monitoring.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── admin.py          # Session user schemas
│   │   ├── analytics.py
│   │   └── playground.py
│   ├── dependencies.py       # + get_current_admin_user (session-based)
│   └── main.py               # + admin_router
├── models/
│   ├── admin_user.py
│   ├── benchmark_result.py
│   └── benchmark_item.py     # No api_key/base_url columns
└── workers/conversation/llm.py  # Unchanged — reused by playground
```

### Frontend (new)

```
frontend/                    # New Next.js project, separate repo/dir
├── src/
│   ├── app/(auth)/login/
│   ├── app/(admin)/          # Dashboard, conversations, prompts, playground, tokens, monitoring
│   ├── components/admin/     # Sidebar, Header, DataTable, etc.
│   ├── context/AuthContext.tsx  # { user, login, logout }
│   ├── lib/api.ts            # fetch with credentials: 'include'
│   └── hooks/useAuth.ts
```

### Database migrations

```bash
alembic revision --autogenerate -m "Add admin_user, benchmark_result, benchmark_item tables"
```

---

## 9. Future Expansion

When Phase 2 is stable, future phases can evolve:

- **Multi-admin accounts:** Add more `admin_users` rows, session-per-user
- **RBAC:** Add `role` column, protect endpoints with role checks
- **SSO/OIDC:** Replace password login with OIDC provider
- **Custom model endpoints:** Re-add `base_url` + encrypted `api_key` to `benchmark_items`
- **Prometheus metrics:** Separate `/metrics/prometheus` endpoint with Prometheus format
- **Audit log table:** `admin_audit_log` for tamper-evident action history

---

**Document version:** 2.0 (auth redesign — cookie-session, single admin)
**Review status:** Awaiting user review