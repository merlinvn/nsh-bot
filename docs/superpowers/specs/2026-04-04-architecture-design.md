# Architecture Design - NeoChatPlatform Phase 1

## Overview

NeoChatPlatform Phase 1 delivers a production-ready Zalo chatbot agent using a queue-based, async-first architecture. The system decouples inbound webhook reception from LLM processing and outbound delivery, ensuring webhook responses under 200ms and reliable message delivery with retry semantics.

---

## RabbitMQ Topology

### Exchanges

#### `neochat.direct` (Exchange)
- **Type**: `direct`
- **Durable**: `true`
- **Purpose**: Primary routing exchange for all application messages

#### `neochat.dlx` (Dead Letter Exchange)
- **Type**: `direct`
- **Durable**: `true`
- **Purpose**: Catches messages from any queue that exceed retry limits or are rejected without requeue

### Queues

#### `conversation.process`
- **Durable**: `true`
- **Arguments**:
  - `x-dead-letter-exchange`: `neochat.dlx`
  - `x-dead-letter-routing-key`: `dead-letter`
  - `x-message-ttl`: `300000` (5 minutes — messages older than this are discarded)
  - `x-max-length`: `10000` (prevent unbounded growth)
- **Routing Key**: `conversation.process`
- **Consumer Prefetch**: `1` (process one conversation at a time per consumer; conversation processing is CPU/IO bound on LLM calls)
- **Purpose**: Inbound messages from Zalo, deduplicated and enriched with conversation context

#### `outbound.send`
- **Durable**: `true`
- **Arguments**:
  - `x-dead-letter-exchange`: `neochat.dlx`
  - `x-dead-letter-routing-key`: `dead-letter`
  - `x-message-ttl`: `600000` (10 minutes — outbound is less time-critical)
  - `x-max-length`: `50000`
- **Routing Key**: `outbound.send`
- **Consumer Prefetch**: `5` (outbound sends are I/O-bound network calls; batching improves throughput)
- **Purpose**: Agent responses ready to deliver to Zalo API

#### `dead-letter`
- **Durable**: `true`
- **Arguments**: none
- **Routing Key**: `dead-letter`
- **Purpose**: Terminal storage for messages that failed all retries. Operators can inspect and replay from this queue

### Routing Summary

| Exchange | Routing Key | Queue |
|---|---|---|
| `neochat.direct` | `conversation.process` | `conversation.process` |
| `neochat.direct` | `outbound.send` | `outbound.send` |
| `neochat.dlx` | `dead-letter` | `dead-letter` |

### Message Flow

```
Zalo → Webhook API
         ↓
    [Redis dedupe check]
         ↓
    Publish to neochat.direct (routing_key=conversation.process)
         ↓
    conversation.process queue
         ↓
    Conversation Worker (LLM + Tools)
         ↓
    Publish to neochat.direct (routing_key=outbound.send)
         ↓
    outbound.send queue
         ↓
    Outbound Worker (+ retry with exponential backoff, max 3)
         ↓
    Zalo API

    [on max retries exceeded]
         ↓
    neochat.dlx → dead-letter queue
```

### Retry Strategy

- **Max attempts**: 3
- **Backoff**: Exponential — 1s, 4s, 16s (base=2)
- **Retry trigger**: Non-2xx response from Zalo API, network timeout
- **Non-retryable**: 4xx responses (except 429 Too Many Requests which is retried with longer backoff)

---

## Project Structure

```
/app
  /api                    # FastAPI application
    __init__.py
    main.py               # FastAPI app entry point, includes lifespan
    /routers
      __init__.py
      webhooks.py         # POST /webhooks/zalo
      health.py           # GET /health/live, GET /health/ready
      internal.py         # Internal management endpoints
    /middleware
      __init__.py
      logging.py          # Request/response logging middleware
      request_id.py       # Request ID propagation (X-Request-ID)
    /schemas
      __init__.py
      webhook.py          # Pydantic schemas for Zalo webhook payloads
      conversation.py     # Conversation and message schemas
      prompt.py           # Prompt schemas
  /workers
    /conversation
      __init__.py
      main.py             # Worker entry point, connects to RabbitMQ
      processor.py         # Main processing pipeline (dedupe → LLM → tools → respond)
      /tools              # Tool implementations (whitelist only)
        __init__.py
        lookup_customer.py
        get_order_status.py
        create_support_ticket.py
        handoff_request.py
    /outbound
      __init__.py
      main.py             # Worker entry point
      sender.py           # Zalo API sending logic + retry wrapper
  /core
    __init__.py
    config.py             # Settings from environment variables (Pydantic BaseSettings)
    database.py           # PostgreSQL async connection (asyncpg / SQLAlchemy async)
    redis.py              # Redis client (redis-py)
    rabbitmq.py           # RabbitMQ connection + channel helpers (aio-pika)
    logging.py            # Structured logging setup (structlog or stdlib)
  /agent
    __init__.py
    llm.py                # Anthropic API client
    prompt_manager.py     # Prompt versioning and retrieval from DB
    tools.py              # Tool registry matching whitelist
/alembic
  /versions
  env.py
docker-compose.yml
.env.example
Dockerfile.api
Dockerfile.worker
```

### Directory Responsibilities

| Path | Responsibility |
|---|---|
| `app/api/` | HTTP layer — webhook reception, health checks, internal management |
| `app/workers/conversation/` | Message consumption, LLM orchestration, tool execution |
| `app/workers/outbound/` | Zalo API delivery with retry semantics |
| `app/core/` | Shared infrastructure clients — DB, Redis, RabbitMQ, config, logging |
| `app/agent/` | LLM client, prompt management, tool registry |
| `alembic/` | Database migrations |
| `docker-compose.yml` | Full local stack definition |
| `Dockerfile.api` | Multi-stage build for FastAPI service |
| `Dockerfile.worker` | Multi-stage build for worker services |
| `.env.example` | Environment variable template |

### Key Design Decisions

- **`app/core/` is shared**: Both the API and workers import from `core`. At runtime, they each get their own client connections (no shared process state).
- **Workers are separate processes**: `conversation-worker` and `outbound-worker` each have their own `main.py`. This allows independent scaling and crash isolation.
- **No shared ORM session across queues**: Each message is processed in its own DB transaction scope.
- **Tools are explicitly whitelisted**: Only the four Phase 1 tools are wired into the tool registry. No dynamic tool loading.

---

## Docker Compose

```yaml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - RABBITMQ_URL=${RABBITMQ_URL}
      - ZALO_APP_ID=${ZALO_APP_ID}
      - ZALO_APP_SECRET=${ZALO_APP_SECRET}
      - ZALO_ACCESS_TOKEN=${ZALO_ACCESS_TOKEN}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  conversation-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    command: python -m workers.conversation.main
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - RABBITMQ_URL=${RABBITMQ_URL}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    restart: unless-stopped

  outbound-worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    command: python -m workers.outbound.main
    environment:
      - RABBITMQ_URL=${RABBITMQ_URL}
      - ZALO_APP_ID=${ZALO_APP_ID}
      - ZALO_APP_SECRET=${ZALO_APP_SECRET}
      - ZALO_ACCESS_TOKEN=${ZALO_ACCESS_TOKEN}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    depends_on:
      rabbitmq:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=${POSTGRES_DB:-neochat}
      - POSTGRES_USER=${POSTGRES_USER:-neochat}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-neochat}"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    environment:
      - RABBITMQ_DEFAULT_USER=${RABBITMQ_USER:-guest}
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PASSWORD:-guest}
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    ports:
      - "15672:15672"  # Management UI
      - "5672:5672"    # AMQP
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  rabbitmq_data:
```

### Service Dependencies

```
api → postgres (healthcheck)
api → redis (healthcheck)
api → rabbitmq (healthcheck)
conversation-worker → postgres (healthcheck)
conversation-worker → rabbitmq
outbound-worker → rabbitmq
```

### RabbitMQ Initialization

On first startup, the API service runs a startup hook (via FastAPI lifespan) to declare the exchange, queues, and bindings programmatically using `aio-pika`. This ensures the topology is always in sync with the application code.

---

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://neochat:password@postgres:5432/neochat
POSTGRES_DB=neochat
POSTGRES_USER=neochat
POSTGRES_PASSWORD=changeme

# Redis
REDIS_URL=redis://redis:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Zalo OA
ZALO_APP_ID=your_zalo_app_id
ZALO_APP_SECRET=your_zalo_app_secret
ZALO_ACCESS_TOKEN=your_zalo_access_token

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Logging
LOG_LEVEL=INFO
```

### Variable Descriptions

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg driver) |
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `REDIS_URL` | Yes | Redis connection URL |
| `RABBITMQ_URL` | Yes | RabbitMQ AMQP connection URL |
| `RABBITMQ_USER` | No | RabbitMQ management user (default: guest) |
| `RABBITMQ_PASSWORD` | No | RabbitMQ management password (default: guest) |
| `ZALO_APP_ID` | Yes | Zalo application ID |
| `ZALO_APP_SECRET` | Yes | Zalo application secret |
| `ZALO_ACCESS_TOKEN` | Yes | Zalo long-lived access token |
| `ANTHROPIC_API_KEY` | Yes (worker) | Anthropic API key for LLM calls |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

---

## Data Flow Summary

```
Zalo webhook POST
  → FastAPI /webhooks/zalo (parse, validate, dedupe via Redis)
  → Publish message to neochat.direct/conversation.process
  → Return 200 OK (< 200ms target)

conversation-worker consumes:
  → Load conversation history from PostgreSQL
  → Load active prompt from PostgreSQL
  → Call Anthropic API (with tool definitions)
  → Execute tools if needed (log to PostgreSQL)
  → Compose final response
  → Publish to neochat.direct/outbound.send

outbound-worker consumes:
  → Send to Zalo API
  → On failure: retry with exponential backoff (max 3)
  → On max retries: route to neochat.dlx → dead-letter queue
  → Log all delivery attempts to PostgreSQL
```
