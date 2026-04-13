# NeoChat Platform — Deployment Guide

**Last Updated:** 2026-04-13

---

## Environments

| Environment | Compose File | Purpose |
|-------------|---------------|---------|
| Development | `docker-compose.dev.yml` | Local dev with debug ports |
| Production | `docker-compose.prod.yml` | Production deployment |

---

## Prerequisites

- Docker & Docker Compose
- Domain pointed to server (for HTTPS)
- `.env` file (copy from `.env.example`)

---

## Quick Start

### Development

```bash
# Start all services (debug ports enabled via override)
docker-compose -f docker-compose.dev.yml -f docker-compose.override.yml up -d

# Start without debug ports
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Run migrations
docker-compose -f docker-compose.dev.yml exec api uv run alembic upgrade head

# Create admin user
docker-compose -f docker-compose.dev.yml exec api uv run python app/api/scripts/create_admin_user.py --username admin --password 'YourPassword'
```

### Production

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec api uv run alembic upgrade head

# Create admin user
docker-compose -f docker-compose.prod.yml exec api uv run python app/api/scripts/create_admin_user.py --username admin --password 'YourPassword'
```

---

## Configuration

### Environment Variables

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://neochat:changeme@postgres:5432/neochat` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `RABBITMQ_URL` | RabbitMQ connection string | `amqp://guest:guest@rabbitmq:5672/` |
| `ZALO_APP_ID` | Zalo OA App ID | — |
| `ZALO_APP_SECRET` | Zalo OA App Secret | — |
| `ZALO_WEBHOOK_SECRET` | Zalo webhook verification secret | — |
| `ZALO_OA_ID` | Zalo Official Account ID | — |
| `ZALO_CALLBACK_URL` | Zalo OAuth callback URL | `https://yourdomain.com` |
| `LLM_PROVIDER` | `anthropic` or `openai-compat` | `anthropic` |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL | `http://localhost:11434/v1` |
| `OPENAI_API_KEY` | OpenAI API key | `ollama` |
| `OPENAI_MODEL` | OpenAI-compatible model name | `llama3.2` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `https://yourdomain.com` |
| `INTERNAL_API_KEY` | Key for internal API calls | — |

### Zalo OA Setup

1. Create a Zalo Official Account at https://oa.zalo.me
2. Get `ZALO_APP_ID`, `ZALO_APP_SECRET`, `ZALO_OA_ID` from Zalo developer portal
3. Set webhook URL: `https://yourdomain.com/webhooks/zalo`
4. Generate PKCE and authorize:
   ```bash
   docker-compose exec api uv run python app/api/scripts/generate_pkce.py
   ```
5. Update Zalo token:
   ```bash
   docker-compose exec -T api uv run python app/api/scripts/update_zalo_token.py --access-token "token"
   ```

---

## Caddy Reverse Proxy

The `Caddyfile` handles routing:

```
/api/*          → FastAPI (admin API)
/auth/zalo/callback → FastAPI (Zalo OAuth)
/webhooks/zalo  → FastAPI (Zalo webhooks)
/health         → FastAPI (health check)
/internal/*     → FastAPI (internal API, protected)
/*              → Next.js frontend (SPA)
```

### TLS

Caddy handles TLS automatically using Let's Encrypt. For Cloudflare-managed DNS:

1. Set Cloudflare API token in `Caddyfile` environment
2. Or use `tls internal` for self-signed (behind Cloudflare proxy)

---

## Docker Services

| Service | Description |
|---------|-------------|
| `postgres` | PostgreSQL 15 database |
| `redis` | Redis 7 for sessions, pub/sub, caching |
| `rabbitmq` | RabbitMQ 3.12 for message queues |
| `api` | FastAPI application server |
| `conversation-worker` | Processes incoming Zalo messages |
| `llm-worker` | Runs LLM inference |
| `outbound-worker` | Delivers outbound messages to Zalo |
| `frontend` | Next.js admin SPA |
| `caddy` | Reverse proxy and TLS |

---

## Database Migrations

Database schema managed via Alembic. Migrations live in `alembic/versions/`.

### Run Migrations

```bash
# Run all pending migrations (upgrade to latest)
docker-compose exec api uv run alembic upgrade head

# Upgrade one step at a time
docker-compose exec api uv run alembic upgrade +1

# Check current version
docker-compose exec api uv run alembic current

# Show migration history
docker-compose exec api uv run alembic history
```

### Rollback

```bash
# Rollback one migration
docker-compose exec api uv run alembic downgrade -1

# Rollback to a specific revision
docker-compose exec api uv run alembic downgrade <revision_id>

# Rollback all migrations (nuke schema)
docker-compose exec api uv run alembic downgrade base
```

### Create Migration

When changing models in `app/models/`:

```bash
# Auto-generate migration from model changes
docker-compose exec api uv run alembic revision --autogenerate -m "describe change"

# Create empty migration (manual SQL)
docker-compose exec api uv run alembic revision -m "describe change"
```

Then edit the generated file in `alembic/versions/` to review/customize before applying.

### Reset Database (Development Only)

⚠️ **This destroys all data. Never do this in production.**

```bash
# Drop all tables and recreate from scratch
docker-compose exec api uv run alembic downgrade base
docker-compose exec api uv run alembic upgrade head

# Recreate admin user after reset
docker-compose exec api uv run python app/api/scripts/create_admin_user.py \
  --username admin --password 'YourPassword'
```

### Verify Schema

```bash
# Check if schema matches models (no pending migrations)
docker-compose exec api uv run alembic upgrade head --check

# Show SQL that would run without executing
docker-compose exec api uv run alembic upgrade head --sql
```

---

## Admin User Management

### Create Admin User

```bash
docker-compose exec api uv run python app/api/scripts/create_admin_user.py \
  --username admin --password 'YourPassword'
```

### Change Admin Password

```bash
# Via CLI
docker-compose exec api uv run python app/api/scripts/create_admin_user.py \
  --username admin --password 'NewPassword'

# Or via API (while logged in)
curl -X POST https://yourdomain.com/api/auth/password \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <your_csrf_token>" \
  -b <session_cookie> \
  -d '{"current_password":"OldPassword","new_password":"NewPassword"}'
```

### Reset Admin Password (Forgot)

If you lost admin access, reset via database:

```bash
# Get into postgres
docker-compose exec postgres psql -U neochat -d neochat

# In psql, update password hash (requires bcrypt hash of new password)
# Generate hash locally: python -c "import bcrypt; print(bcrypt.hashpw(b'NewPass', bcrypt.gensalt()).decode())"
UPDATE admin_users SET password_hash = '<bcrypt_hash>' WHERE username = 'admin';
\q
```

Or delete and recreate:

```bash
docker-compose exec api uv run python app/api/scripts/create_admin_user.py \
  --username admin --password 'NewPassword' --force
```

---

## Troubleshooting

### Services not starting

```bash
# Check service health
docker-compose ps

# View logs for specific service
docker-compose logs -f api
docker-compose logs -f postgres

# Check dependencies
docker-compose exec api python -c "from app.api.main import app; print('API OK')"
```

### Zalo webhook not receiving messages

1. Verify webhook URL is publicly accessible
2. Check Zalo OA webhook configuration
3. Test manually:
   ```bash
   curl -X POST https://yourdomain.com/webhooks/zalo \
     -H "Content-Type: application/json" \
     -d '{"event_name":"test"}'
   ```

### Frontend shows 404

1. Clear browser cache (Cmd+Shift+R)
2. Purge Cloudflare cache if using CDN
3. Verify `NEXT_PUBLIC_API_URL` is set to `https://yourdomain.com`

### LLM not responding

1. Check LLM worker logs: `docker-compose logs -f llm-worker`
2. Verify LLM provider credentials
3. Check queue depth: `/api/monitoring/queues`

---

## Monitoring

- **Health:** `GET /health`
- **Admin UI:** `https://yourdomain.com/admin`
- **RabbitMQ Management:** Port 15672 (dev only)

---

## Security Checklist

- [ ] Change all default passwords
- [ ] Set `INTERNAL_API_KEY` for internal endpoints
- [ ] Configure `CORS_ORIGINS` to your domain only
- [ ] Enable Zalo webhook verification
- [ ] Use HTTPS (Caddy handles this)
- [ ] Set `ADMIN_BCRYPT_ROUNDS` to 12+ in production
