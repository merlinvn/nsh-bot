# NeoChat Platform — Project Post-Mortem

**Last Updated:** 2026-04-17
**Period Covered:** Project inception → 2026-04-17
**Total Commits:** ~90 | **Fix Commits:** 50 (56%)

---

## Executive Summary

56% of all commits are bug fixes, refactors, or deployment corrections. The system has been rebuilt in 3 phases with significant architectural churn. Most recurring issues stem from 5 systemic patterns that, if addressed proactively, would have saved an estimated 20+ hours of rework.

---

## Recurring Issues by Frequency

| Issue Category | Sessions | Severity | Root Cause |
|---------------|----------|----------|------------|
| Zalo token expiry/refresh | 29x keyword | High | Zalo OAuth tokens expire; no auto-refresh was wired initially |
| Port/internal mismatch | 27x keyword | High | Dev uses localhost ports; prod uses internal Docker DNS |
| Worker consumer crashes | 19x keyword | High | Workers had no health checks reflecting actual RabbitMQ consumer state |
| Prompt management | 24x keyword | Medium | No auto-population; deletion = data loss without recovery |
| CORS errors (localhost fetch) | 12x keyword | High | Frontend calling `localhost:8000` instead of actual API URL |
| Auth redirect loops | 18x keyword | High | Cookie session vs redirect flow miswired |
| RabbitMQ queue depth/DLQ | 17x keyword | Medium | Messages landing in DLQ with no alerting |
| Database migrations | 14x keyword | High | Duplicate revision IDs; migration conflicts |
| Alembic migration conflicts | 11x keyword | High | Multiple migrations claiming same revision number |
| MCP tool call failures | 10x keyword | Medium | MCP server URL wrong; tools unregistered |

---

## Top 5 Most Impactful Issues

### 1. Zalo OAuth Token Management (29x)

**Symptom:** Zalo API returns `-216 Access token is invalid` or `401`.

**Root cause:** Tokens expire and were not being refreshed. Token state was stored in memory only.

**Fixes applied:**
- `ZaloTokenManager` (`app/workers/shared/zalo_token_manager.py`) — singleton with auto-refresh on 401
- Token persisted to PostgreSQL `zalo_tokens` table
- Admin UI to view/refresh/revoke tokens
- CLI script to update token: `update_zalo_token.py --access-token`

**If done earlier:** Would have saved ~6 hours of investigating silent message delivery failures.

---

### 2. Worker Consumer Health Not Reflecting Actual State (19x)

**Symptom:** Worker container reports `healthy` but RabbitMQ consumer has crashed.

**Root cause:** Health endpoint just returned `200 OK` — didn't check if the RabbitMQ consumer was actually running.

**Fix applied:** `app/workers/shared/health.py` — health check verifies consumer is connected to RabbitMQ. Returns `503 unhealthy` if consumer is down. Docker healthcheck depends on this.

**Prevention:** Every worker health endpoint must verify its queue consumer is alive, not just that the process is running.

---

### 3. CORS — Frontend Calling `localhost:8000` (12x)

**Symptom:** Browser console: `Access to fetch at 'http://localhost:8000/api/auth/me' from origin 'http://localhost:3000'`.

**Root cause:** `NEXT_PUBLIC_API_URL` baked at build time, not runtime. Setting it in `environment:` in docker-compose only affects server-side, not the Next.js client bundle.

**Fix applied:** `ARG NEXT_PUBLIC_API_URL` + `ENV` in `Dockerfile.frontend`, passed as Docker build arg.

**Prevention:** Document and enforce: `NEXT_PUBLIC_*` vars must be build args, never runtime environment.

---

### 4. Alembic Duplicate Revision Conflict

**Symptom:** `alembic upgrade head` fails with `KeyError: 'b7de17372549'` or `Multiple head revisions`.

**Root cause:** Multiple migration files claimed `revision = "007"`. Alembic requires a linear, unique chain.

**Fix applied:** Renumbered conflicting migrations to sequential unique IDs: `007_add_user_id_by_app` → `008`, `007_add_evaluation_tables` → `009`, `008_add_judgment` → `010`.

**Prevention:**
1. Never reuse a revision number
2. Always verify chain with `alembic heads` (must return exactly 1 head) before pushing
3. Run `alembic upgrade head` locally before deploying

---

### 5. Worker-MCP Communication (10x)

**Symptom:** Tool calls silently fail; quote tool returns no results.

**Root cause:** `MCP_SERVER_URLS` not set in prod compose. Workers couldn't reach `nsh-mcp` service.

**Fix applied:** Added `MCP_SERVER_URLS` to `x-common-env` anchor in `docker-compose.prod.yml`; added `nsh-mcp` service definition.

**Prevention:** Prod compose must be diffed against dev compose before each deployment.

---

## Anti-Patterns That Caused the Most Rework

### 1. Prod/dev compose divergence
Dev had `nsh-mcp`, `MCP_SERVER_URLS`, correct ports. Prod didn't. Every missing item required a deployment cycle to discover.

**Rule:** `diff docker-compose.dev.yml docker-compose.prod.yml` must return clean before deployment.

### 2. Editing code on production directly
When alembic fix was attempted via `sed` directly on prod, it conflicted with `git pull`, requiring recovery.

**Rule:** Never modify prod source files. Always fix locally → commit → push → pull → rebuild.

### 3. Not running migrations locally first
The `op.Column` vs `sa.Column` bug in a migration would have been caught by running `alembic upgrade head` locally.

**Rule:** `uv run alembic upgrade head` locally on every migration change before pushing.

### 4. Next.js `NEXT_PUBLIC_*` runtime vs build time confusion
Setting `environment: { NEXT_PUBLIC_API_URL: ... }` felt like it should work — it doesn't.

**Rule:** Add `ARG` + `ENV` in Dockerfile; pass as `build.args` in compose.

---

## Architecture Decisions That Caused Recurring Work

### MCP extraction (`app/workers/mcp` → `nsh-mcp/` standalone)

Extracted MCP server mid-development, then had to fix all references. The standalone `nsh-mcp/` directory is now the correct path, but old references (`app/workers/mcp/backend.py`) persisted in docs.

**Current correct paths:**
- MCP server: `nsh-mcp/src/nsh_mcp/server.py`
- MCP client: `app/workers/mcp_client.py` (not `app/workers/mcp/backend.py`)
- Pricing: `nsh-mcp/src/nsh_mcp/pricing/pricing.py`
- Pricing config: `nsh-mcp/src/nsh_mcp/pricing/config.py`

### Tool count discrepancy

SPEC originally said 6 tools. Code has 5. `explain_quote_breakdown` never existed.

### Redis key prefix inconsistency

Some keys use `zalo:dedup:`, others documented as `dedup:zalo:`. Actual: `zalo:dedup:{message_id}`.

---

## What Was Built Correctly

- **Queue architecture**: `conversation.process` → `llm.process` → `outbound.send` — clean separation, no direct LLM calls from webhooks
- **Channel routing**: `playground`, `evaluation`, `zalo` channels are cleanly separated in processor
- **PromptManager**: In-memory cache with 5-min TTL, lazy loading — overall good design
- **Docker healthchecks**: All services have proper health checks with `service_healthy` dependencies
- **Idempotency**: `outbound:sent:{id}` Redis key prevents double-send

---

## Checklist: Pre-Deployment Verification

- [ ] `diff docker-compose.dev.yml docker-compose.prod.yml` — no missing services or env vars
- [ ] `uv run alembic upgrade head` locally — migrations apply cleanly
- [ ] `alembic heads` returns exactly 1 head
- [ ] `MCP_SERVER_URLS` present in prod compose `x-common-env`
- [ ] `nsh-mcp` service present in prod compose
- [ ] `NEXT_PUBLIC_API_URL` passed as Docker build arg for frontend
- [ ] `docker compose -f docker-compose.prod.yml up -d --build` completes without error
- [ ] All containers `healthy` in `docker compose ps`
- [ ] `docker compose exec api alembic upgrade head` runs cleanly on prod
- [ ] Admin user seeded or verified working

---

## Files Changed Most Frequently (fix commits)

| File | Fix Count |
|------|----------|
| `docker-compose.prod.yml` | 5 |
| `docker-compose.dev.yml` | 4 |
| `alembic/` migrations | 6 |
| `app/workers/conversation/prompts.py` | 4 |
| `app/workers/shared/health.py` | 2 |
| `Dockerfile.frontend` | 3 |
| `app/api/routers/admin/auth.py` | 3 |
| `app/workers/mcp_client.py` | 2 |
| `nsh-mcp/` (various) | 8 |

---

## Related Documents

- `SPEC.md` — Current system architecture (updated 2026-04-17)
- `DEPLOYMENT.md` — Deployment guide with gotchas section
- `POSTMORTEM-2026-04-17.md` — Detailed timeline of today's deployment
