# Deployment Post-Mortem — 2026-04-17

## Summary

Prod deployment of `e9440ee` on `neo@10.10.50.230` took ~4 hours due to 4 avoidable issues.

---

## What Was Deployed

| Commit | Description |
|--------|-------------|
| `e9440ee` | update system prompt (off-topic refusal) |
| `a2a5977` | fix(prod): add nsh-mcp + MCP_SERVER_URLS |
| `d004307` | fix(alembic): resolve duplicate revision 007 conflict |
| `b1f4501` | (amend: down_revision was still wrong) |
| `34044ba` | (amend: down_revision still had wrong value) |
| `e87dfca` | (amend: fixed down_revision, added sa.Column import) |
| `de37990` | fix(frontend): pass NEXT_PUBLIC_API_URL as build arg |
| `6a71983` | docs: add gotchas section |

---

## Root Causes and Timeline

### 1. Prod compose missing `nsh-mcp` (30 min)

**Problem:** `docker-compose.prod.yml` had no `nsh-mcp` service and no `MCP_SERVER_URLS` env var.

**Fix:** Added both to `docker-compose.prod.yml`.

**Lesson:** Dev compose had it, prod did not. Should have been caught during the dev/prod diff before deployment.

### 2. Duplicate alembic revision 007 — took ~2.5 hours

**Problem:** Three migration files formed a branch point:
```
006
├── b7de17372549 (revision "007") → zalo_users table
├── 007_add_user_id_by_app (revision "007") → adds user_id_by_app col  ← CONFLICT
└── 007_add_evaluation_tables (revision "007") → eval tables            ← CONFLICT
```

Alembic requires a linear chain. Duplicate revision IDs at the same level cause `KeyError` on migration.

**Attempts:**
1. Tried sed on prod directly → conflicted with git pull
2. Renamed 007_add_evaluation_tables → 009, 008_add_judgment → 010
3. But left `down_revision = "007"` in 009_add_evaluation_tables (head vs code mismatch)
4. Result: still two heads (008 and 010)
5. Fixed `down_revision = "008"` in 009_add_evaluation_tables
6. Added `sa.Column` import to 007_add_user_id_by_app (had `op.Column` → AttributeError)

**Final chain:** `001 → 002 → 003 → 004 → 005 → 006 → b7de17372549(007) → 008 → 009 → 010`

**Lesson:** Don't touch production code directly. Fix locally, push, pull. Also: renaming files + editing revisions in separate steps caused confusion — should have verified chain with `alembic heads` after each change locally.

### 3. Tried to edit prod files directly — git pull conflicts (30 min)

**Problem:** Made sed changes directly on prod's `alembic/versions/`. When git pull arrived with the real fix, it refused to merge (`Your local changes to the following files would be overwritten by merge`).

**Attempted:** `git checkout -- <files>` to discard local changes, then `git pull`. Worked but added latency.

**Lesson:** Never modify prod source files directly. Always fix locally and deploy via git.

### 4. Migration `007_add_user_id_by_app` used `op.Column` instead of `sa.Column` (10 min)

**Problem:** Migration ran but failed at runtime with `AttributeError: module 'alembic.op' has no attribute 'Column'`.

**Fix:** Added `import sqlalchemy as sa` and changed `op.Column` → `sa.Column`.

**Lesson:** Test migrations locally before pushing. `uv run alembic upgrade head` locally would have caught this before the forced-push cycle.

### 5. Frontend `NEXT_PUBLIC_API_URL` baked in at build time (30 min)

**Problem:** Browser called `http://localhost:8000/api/auth/me` — frontend had `localhost:8000` baked in.

**Root cause:** `NEXT_PUBLIC_*` vars are baked during `npm run build`, not at container startup. Setting them in `environment:` in docker-compose only affects runtime, not the built JS bundle.

**Fix:** Added `ARG NEXT_PUBLIC_API_URL` + `ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL` to `Dockerfile.frontend`, and passed as build arg in `docker-compose.prod.yml`.

**Lesson:** This is a well-known Next.js quirk. Should have been documented proactively.

---

## What Went Right

- Prod containers were already defined in docker-compose.dev.yml — easy to compare
- `docker compose -f docker-compose.prod.yml exec -T api uv run alembic upgrade head` worked correctly to track progress
- Health checks on all containers confirmed successful startup after rebuilds
- Admin user seeding was trivial and worked first try

---

## Faster Path (what to do next time)

1. **Before deploying:** Diff dev vs prod compose. Check for missing services (`nsh-mcp`) and env vars (`MCP_SERVER_URLS`).
2. **Migrations:** Run `alembic upgrade head` locally first. Verify chain with `alembic heads` — must return exactly 1 head.
3. **Never edit prod files directly.** Fix locally → commit → push → pull → rebuild.
4. **If prod has local changes:** `git stash` or `git checkout -- <files>` before `git pull`.
5. **Frontend:** Add `ARG` for every `NEXT_PUBLIC_*` var in `Dockerfile.frontend` before deploying to prod.

---

## Files Changed

| File | Change |
|------|--------|
| `docker-compose.prod.yml` | +nsh-mcp service, +MCP_SERVER_URLS, +frontend build arg |
| `Dockerfile.frontend` | +ARG NEXT_PUBLIC_API_URL, +ENV |
| `alembic/versions/007_add_user_id_by_app_to_zalo_users.py` | revision "008", sa.Column import |
| `alembic/versions/009_add_evaluation_tables.py` | renamed from 007_add_evaluation_tables, revision "009", down_revision "008" |
| `alembic/versions/010_add_judgment_to_test_cases.py` | renamed from 008_add_judgment, revision "010", down_revision "009" |
| `docs/DEPLOYMENT.md` | +Important Gotchas section |
