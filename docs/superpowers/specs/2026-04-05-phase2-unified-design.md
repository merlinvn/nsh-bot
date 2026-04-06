# NeoChatPlatform Phase 2 — Admin Control Plane Design

**Date:** 2026-04-05
**Status:** Draft — Pending User Review
**Team:** backend-architect + frontend-architect

---

## 1. Overview

Phase 2 delivers an admin control plane for NeoChatPlatform: a web-based UI to manage conversations, prompts, analytics, LLM benchmarking, Zalo token lifecycle, and system monitoring.

**Key decisions:**
- **Frontend:** Next.js 14+ (App Router), separate from API, deployable independently
- **Backend:** Embedded in existing FastAPI service — extend with `/admin/*` routes, no new service
- **Auth:** JWT-based with short-lived access tokens (15m) + rotatable refresh tokens (7d), stored in DB
- **Frontend Auth:** Simple session with access token in memory, refresh via body rotation
- **Admin Model:** Single admin role — all authenticated users have full access. Security enhanced in future phases.
- **LLM Focus:** OpenAI-compatible model support for playground and benchmarking
- **Analytics:** Polling via React Query (30s interval) — no WebSocket complexity for Phase 2
- **CORS:** FastAPI CORS configured for frontend origin — no Next.js proxy needed

**Out of scope:** SSO, multi-tenant, mobile, A/B testing (Phase 5).

---

## 2. Architecture

### 2.1 System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Admin Browser (Next.js)                       │
│   /admin/auth, /admin/conversations, /admin/prompts, etc.          │
└─────────────────────────────────────────────────────────────────────┘
                                │ HTTPS + JWT (httpOnly cookie)
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
   (data + admin_users,    (session cache,        (queues unchanged)
    admin_refresh_tokens)    dedup)
```

### 2.2 Backend Integration Points

| Concern | Phase 1 | Phase 2 Extension |
|---------|---------|-------------------|
| Router | `app/api/routers/` | New `app/api/routers/admin/` |
| Models | `app/models/` | New `admin_user`, `admin_refresh_token`, `benchmark_result`, `benchmark_item` |
| Schemas | `app/api/schemas/` | New `admin.py`, `analytics.py`, `playground.py` |
| Dependencies | `app/api/dependencies.py` | Add `get_current_admin_user`, `require_role` |
| Main | `app/api/main.py` | Add `admin_router` with `/admin/*` prefix |

### 2.3 Frontend Integration Points

| Concern | Value |
|---------|-------|
| API Base | `NEXT_PUBLIC_API_URL` env var (default: `http://localhost:8000`) |
| Auth | Tokens in React Context (memory only) — never localStorage |
| CORS | FastAPI configured with frontend origin — same-machine deploy uses Docker network |
| Dev CORS | Backend allows `http://localhost:3000` for Next.js dev server |

---

## 3. Data Model

### 3.1 New Tables

#### `admin_users`
Stores admin accounts for panel access.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `username` | VARCHAR(64) | UNIQUE, NOT NULL |
| `password_hash` | VARCHAR(256) | NOT NULL (bcrypt, work factor 12) |
| `role` | VARCHAR(32) | NOT NULL, DEFAULT `'admin'` — only `'admin'` for Phase 2 |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE |
| `last_login_at` | TIMESTAMPTZ | NULL |
| `failed_login_attempts` | INTEGER | NOT NULL, DEFAULT 0 |
| `locked_until` | TIMESTAMPTZ | NULL (account lockout after 5 failed attempts, 15 min) |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

**Indexes:** `ix_admin_users_username`, `ix_admin_users_role`

#### `admin_refresh_tokens`
Stores active refresh tokens for revocation support.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `admin_users.id` |
| `token_hash` | VARCHAR(256) | UNIQUE, NOT NULL (SHA-256 of token value) |
| `expires_at` | TIMESTAMPTZ | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `revoked_at` | TIMESTAMPTZ | NULL |

**Indexes:** `ix_admin_refresh_tokens_user_id`, `ix_admin_refresh_tokens_token_hash`, `ix_admin_refresh_tokens_expires_at`

#### `benchmark_results`
Stores playground benchmark runs.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `name` | VARCHAR(128) | NOT NULL |
| `status` | VARCHAR(32) | NOT NULL — `pending`, `running`, `completed`, `failed` |
| `iterations` | INTEGER | NOT NULL |
| `error` | TEXT | NULL |
| `created_by` | UUID | FK → `admin_users.id` |
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
| `base_url` | VARCHAR(256) | NULL (custom endpoint for openai-compat) |
| `api_key` | VARCHAR(256) | NULL (encrypted or masked) |
| `avg_latency_ms` | FLOAT | NULL |
| `p95_latency_ms` | FLOAT | NULL |
| `avg_input_tokens` | INTEGER | NULL |
| `avg_output_tokens` | INTEGER | NULL |
| `total_cost` | FLOAT | NULL |
| `raw_results` | JSONB | NULL (full iteration details) |

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

---

## 4. API Design

All admin endpoints use JWT Bearer authentication (except login and OAuth callback).

### 4.1 Router Structure

```
/admin/
├── auth/              # Login, logout, refresh, me, password change
├── prompts/           # CRUD + versioning + activation
├── conversations/     # List, detail, replay, message history
├── analytics/         # Overview, message volume, latency, tools, fallbacks, tokens
├── playground/        # Single completion, benchmark, models
├── zalo-tokens/       # Status, PKCE OAuth, refresh, revoke
└── monitoring/        # Health, metrics, workers, queues
```

### 4.2 Auth Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/auth/login` | Login with username/password | None |
| POST | `/admin/auth/logout` | Logout (revoke refresh token) | JWT |
| POST | `/admin/auth/refresh` | Refresh access token | Refresh token (body) |
| GET | `/admin/auth/me` | Get current user info | JWT |
| POST | `/admin/auth/password` | Change own password | JWT |

**Login response:**
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 4.3 Prompt Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/prompts` | List all prompts | JWT |
| POST | `/admin/prompts` | Create new prompt | JWT |
| GET | `/admin/prompts/{name}` | Get prompt detail | JWT |
| PUT | `/admin/prompts/{name}` | Update prompt template | JWT |
| DELETE | `/admin/prompts/{name}` | Delete prompt | JWT |
| POST | `/admin/prompts/{name}/versions` | Create new version | JWT |
| POST | `/admin/prompts/{name}/activate` | Activate a version | JWT |
| GET | `/admin/prompts/{name}/versions` | List all versions | JWT |

### 4.4 Conversation Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/conversations` | List (paginated, filterable) | JWT |
| GET | `/admin/conversations/{id}` | Get conversation + messages + tool calls | JWT |
| POST | `/admin/conversations/{id}/replay` | Replay last message | JWT |
| GET | `/admin/conversations/stats` | Get conversation statistics | JWT |

**Query params for list:** `user_id`, `status`, `created_after`, `created_before`, `page`, `size`, `sort`, `order`

### 4.5 Analytics Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/analytics/overview` | Dashboard overview | JWT |
| GET | `/admin/analytics/messages` | Message volume over time | JWT |
| GET | `/admin/analytics/latency` | LLM latency percentiles | JWT |
| GET | `/admin/analytics/tools` | Tool usage breakdown | JWT |
| GET | `/admin/analytics/fallbacks` | Fallback rates | JWT |
| GET | `/admin/analytics/tokens` | Token usage summary | JWT |

### 4.6 Playground Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/admin/playground/complete` | Single completion test | JWT |
| POST | `/admin/playground/benchmark` | Run benchmark | JWT |
| GET | `/admin/playground/benchmark/{id}` | Get benchmark result | JWT |
| GET | `/admin/playground/models` | List available models | JWT |
| POST | `/admin/playground/models` | Add custom model | JWT |

### 4.7 Zalo Token Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/zalo-tokens/status` | Current token status | JWT |
| POST | `/admin/zalo-tokens/pkce` | Generate PKCE pair | JWT |
| GET | `/admin/zalo-tokens/callback` | OAuth callback (Zalo redirects) | None |
| POST | `/admin/zalo-tokens/refresh` | Refresh access token | JWT |
| DELETE | `/admin/zalo-tokens` | Revoke tokens | JWT |

### 4.8 Monitoring Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/admin/monitoring/health` | Detailed health check | JWT |
| GET | `/admin/monitoring/metrics` | Prometheus metrics | JWT |
| GET | `/admin/monitoring/workers` | Worker status | JWT |
| GET | `/admin/monitoring/queues` | Queue depths | JWT |

### 4.9 Auth Flow Summary

```
Login:
  POST /admin/auth/login {username, password}
  → 200 {access_token, refresh_token, expires_in}
  → Tokens stored in React Context (memory only, never localStorage)

Authenticated requests:
  Authorization: Bearer <access_token>

Token refresh:
  POST /admin/auth/refresh {refresh_token}
  → 200 {access_token, expires_in, new_refresh_token} (rotated)
  → Client updates both tokens in memory

Logout:
  POST /admin/auth/logout {refresh_token}
  → Revokes refresh token in DB
  → Clears tokens from React Context
```

---

## 5. Frontend Architecture

### 5.1 Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | Next.js 14+ (App Router) | SSR for analytics, file-based routing, API route proxy, deploy flexibility |
| Language | TypeScript (strict) | Type safety |
| Styling | Tailwind CSS + shadcn/ui | Consistent, accessible components |
| State | React Query (server) + React Context (auth) | One less library to maintain, sufficient for 6 pages |
| Forms | React Hook Form + Zod | Validation |
| Charts | Recharts | Simple, composable |
| Auth | NextAuth.js Credentials provider | Handles sessions, protected routes, httpOnly cookies |

### 5.2 Folder Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── (auth)/              # Auth layout group
│   │   │   ├── login/
│   │   │   └── layout.tsx
│   │   ├── (admin)/             # Protected admin layout group
│   │   │   ├── layout.tsx       # Sidebar + header + content
│   │   │   ├── page.tsx         # Dashboard (redirect)
│   │   │   ├── conversations/
│   │   │   ├── prompts/
│   │   │   ├── analytics/
│   │   │   ├── playground/
│   │   │   ├── tokens/
│   │   │   └── monitoring/
│   │   ├── api/                 # Optional proxy routes
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── ui/                  # shadcn/ui base
│   │   ├── admin/               # Sidebar, Header, DataTable, StatusBadge, ConfirmDialog
│   │   └── forms/
│   ├── lib/
│   │   ├── api.ts               # Typed API client
│   │   ├── auth.ts              # Auth utilities
│   │   └── utils.ts
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   └── useApi.ts
│   ├── stores/
│   │   └── authStore.ts
│   └── types/
│       └── api.ts
└── .env.local                   # NEXT_PUBLIC_API_URL
```

### 5.3 Navigation

```
Sidebar (fixed left, collapsible to icon-only):
├── Dashboard      → /admin (analytics overview)
├── Conversations  → /admin/conversations
├── Prompts        → /admin/prompts
├── Playground     → /admin/playground
├── Tokens         → /admin/tokens
└── Monitoring     → /admin/monitoring
```

### 5.4 Build Priority

| Phase | Duration | Deliverables |
|-------|----------|---------------|
| **Phase 1 (MVP)** | 2 weeks | Auth + Shell, Conversation list/detail |
| **Phase 2** | 3 weeks | Prompt management, Analytics dashboard |
| **Phase 3** | 2 weeks | LLM Playground (chat, streaming), Token management |
| **Phase 4** | 1 week | Monitoring dashboard, Polish |

---

## 6. Key Design Decisions

### 6.1 Auth: Simple JWT with body rotation
- Access token (15m TTL) stored in React Context/memory, sent via `Authorization: Bearer` header
- Refresh token (7d TTL) stored in React Context/memory, sent in request body for rotation
- Refresh token rotation: each refresh issues a new refresh token
- All tokens revoked on password change, individual token revocation on logout
- Account lockout after 5 failed attempts (15 min)
- **Phase 2:** Single admin role — no endpoint-level role guards
- **Phase 3+:** Add role-based access (admin vs super_admin) when needed

### 6.2 Backend embedded, not separate
- `/admin/*` routes added to existing FastAPI app
- Same PostgreSQL, Redis, RabbitMQ as Phase 1
- No new service to operate
- Existing `/internal/*` endpoints unchanged — Phase 1 keeps working

### 6.3 Playground reuses existing LLM clients
- `app.workers.conversation.llm.AnthropicLLM` and `OpenAICompatLLM` imported directly
- Benchmarks run as async background tasks, results stored in DB, polled via GET
- Single completions are synchronous (60s timeout)

### 6.4 Zalo PKCE OAuth UI
- Current: `update_zalo_token.py` script
- Phase 2: Admin UI with "Connect Zalo" button → redirect to Zalo OAuth → callback stores tokens
- Endpoint `GET /admin/zalo-tokens/callback` handles OAuth redirect from Zalo

---

## 7. Security Considerations

- **JWT secret:** Generated with `openssl rand -base64 32`, stored in env
- **Password hashing:** bcrypt work factor 12
- **Refresh token storage:** SHA-256 hash in DB (not plaintext)
- **API key storage:** Custom model API keys stored as-is (no encryption in Phase 2 — consider for Phase 3)
- **CORS:** Only `http://localhost:3000` for dev; production uses Next.js API proxy
- **Rate limiting:** Login endpoint — 10 attempts/min per IP
- **Audit logging:** All auth events logged (success, failure, logout, token refresh)

---

## 8. Open Questions

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Analytics caching? | Redis cache, 1-min TTL for dashboard overview |
| 2 | Custom model API key encryption? | Not in Phase 2 — plaintext OK for MVP |
| 3 | First super_admin creation? | Seed script only (`create_admin_user.py`) |
| 4 | Audit log table (`admin_audit_log`)? | Defer to Phase 3 — log to existing structured logs for now |
| 5 | Real-time monitoring (WebSocket)? | Defer — polling `/admin/monitoring/metrics` sufficient for Phase 2 |

---

## 9. File Changes Summary

### Backend (Phase 2 additions)

```
app/
├── api/
│   ├── routers/admin/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── prompts.py
│   │   ├── conversations.py
│   │   ├── analytics.py
│   │   ├── playground.py
│   │   ├── zalo_tokens.py
│   │   └── monitoring.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── analytics.py
│   │   └── playground.py
│   ├── dependencies.py         # + get_current_admin_user, require_role
│   └── main.py                 # + admin_router mount
├── models/
│   ├── admin_user.py
│   ├── admin_refresh_token.py
│   ├── benchmark_result.py
│   └── benchmark_item.py
└── workers/conversation/llm.py  # Unchanged — reused by playground
```

### Frontend (new)

```
frontend/                    # New Next.js project, separate repo/dir
├── src/app/(auth)/login/
├── src/app/(admin)/         # Dashboard, conversations, prompts, playground, tokens, monitoring
├── src/components/admin/
├── src/lib/api.ts
├── src/hooks/useAuth.ts
└── ...
```

### Database migrations

```bash
alembic revision --autogenerate -m "Add admin tables and benchmark tables"
```

---

**Document version:** 1.0
**Review status:** Awaiting user review