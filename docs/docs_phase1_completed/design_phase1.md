# NeoChatPlatform Phase 1 — Design Specification

> **Supersedes** all files in `docs/superpowers/specs/`.

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Data Model](#3-data-model)
4. [API Specification](#4-api-specification)
5. [Queue Topology](#5-queue-topology)
6. [Worker Design](#6-worker-design)
7. [Agent Design](#7-agent-design)
8. [Prompt System](#8-prompt-system)
9. [Configuration](#9-configuration)
10. [Project Structure](#10-project-structure)
11. [Acceptance Criteria](#11-acceptance-criteria)

---

## 1. Overview

NeoChatPlatform Phase 1 delivers a production-ready Zalo chatbot agent using a queue-based, async-first architecture. The system decouples inbound webhook reception from LLM processing and outbound delivery, ensuring webhook responses under 200ms and reliable message delivery with retry semantics.

**Goal:** A chatbot that receives Zalo messages via webhook, processes them through an LLM agent with tool-calling capabilities, and delivers responses back through Zalo's API — all with full logging, retry semantics, and operational observability.

### Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Webhook response latency | < 200ms |
| Conversation processing | < 15s total (LLM timeout enforced) |
| Daily conversations | 100–1,000 |
| Message loss | Zero — durable queues, acknowledges only on success |
| Retry | Max 3 attempts, exponential backoff |

---

## 2. Architecture

### 2.1 System Flow

```
Zalo
  ↓
FastAPI Webhook (POST /webhooks/zalo)
  ↓ [Redis dedupe check]
RabbitMQ: conversation.process queue
  ↓ [prefetch=1]
Conversation Worker (LLM + Tools)
  ↓
RabbitMQ: outbound.send queue
  ↓ [prefetch=5]
Outbound Worker (Zalo API)
  ↓
Zalo API

[on max retries exceeded]
  ↓
RabbitMQ: dead-letter queue
```

### 2.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **FastAPI API** | Receive webhooks, health checks, internal admin API |
| **Conversation Worker** | Consume conversation.process, run LLM agent + tools, publish outbound |
| **Outbound Worker** | Consume outbound.send, call Zalo API, retry with backoff |
| **PostgreSQL** | Persistent storage for all business data |
| **Redis** | Message deduplication, caching |
| **RabbitMQ** | Durable message queues with dead-letter support |

### 2.3 LLM Provider Support

The system supports two LLM providers (configured via `LLM_PROVIDER` env var):

| Provider | Description |
|----------|-------------|
| `anthropic` (default) | Anthropic Claude API. Uses `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` |
| `openai-compat` | OpenAI-compatible API (Ollama, LM Studio, LocalAI, Azure OpenAI). Uses `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` |

Tool format is automatically adapted per provider:
- **Anthropic**: `{"type": "function", "function": {...}}` (OpenAI-compatible format sent to Anthropic's API)
- **OpenAI-compatible**: Standard OpenAI tool format

---

## 3. Data Model

### 3.1 ER Overview

```
Conversations (1)───(∞) Messages (1)───(∞) ToolCalls
                              │
                              └───(∞) DeliveryAttempts

Prompts (standalone, referenced by Messages.prompt_version)
ZaloTokens (standalone, for OAuth token storage)
```

### 3.2 Table Specifications

#### `conversations`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| external_user_id | VARCHAR(128) | NOT NULL |
| conversation_key | VARCHAR(256) | UNIQUE, NOT NULL |
| status | VARCHAR(16) | DEFAULT 'active' |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

Status values: `active`, `closed`

#### `messages`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| conversation_id | UUID | FK → conversations.id, ON DELETE CASCADE |
| direction | VARCHAR(16) | NOT NULL |
| text | TEXT | NOT NULL |
| model | VARCHAR(64) | NULLABLE |
| latency_ms | INTEGER | NULLABLE |
| token_usage | JSONB | NULLABLE |
| message_id | VARCHAR(128) | NOT NULL (Zalo's message_id for dedup) |
| prompt_version | VARCHAR(32) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

Direction values: `inbound`, `outbound`

#### `tool_calls`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| message_id | UUID | FK → messages.id, ON DELETE CASCADE |
| tool_name | VARCHAR(64) | NOT NULL |
| input | JSONB | NOT NULL |
| output | JSONB | NOT NULL |
| success | BOOLEAN | NOT NULL |
| error | TEXT | NULLABLE |
| latency_ms | INTEGER | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

#### `delivery_attempts`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| message_id | UUID | FK → messages.id, ON DELETE CASCADE |
| attempt_no | INTEGER | NOT NULL |
| status | VARCHAR(16) | NOT NULL |
| response | JSONB | NULLABLE |
| error | TEXT | NULLABLE |
| created_at | TIMESTAMPTZ | NOT NULL |

Status values: `pending`, `success`, `failed`

#### `prompts`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| name | VARCHAR(64) | UNIQUE, NOT NULL |
| template | TEXT | NOT NULL |
| versions | JSONB | NOT NULL, DEFAULT '[]' |
| active_version | VARCHAR(32) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

`versions` JSONB entry structure:
```json
{
  "version": "v1.0",
  "template": "You are a helpful...",
  "created_at": "2026-04-01T00:00:00Z",
  "active": true,
  "created_by": "admin"
}
```

#### `zalo_tokens` (Phase 1 addition)

Stores Zalo OAuth tokens for long-lived API access.

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| refresh_token | TEXT | NOT NULL |
| access_token | TEXT | NOT NULL |
| expires_at | TIMESTAMPTZ | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |

### 3.3 Indexes

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| conversations | ix_conversations_external_user_id | external_user_id, created_at DESC | User's conversations, newest first |
| conversations | ix_conversations_conversation_key | conversation_key | Unique dedup lookup |
| conversations | ix_conversations_status | status | Filter active/closed |
| messages | ix_messages_conversation_created | conversation_id, created_at | Conversation history in order |
| messages | ix_messages_message_id | message_id | Deduplication check |
| tool_calls | ix_tool_calls_message_id | message_id | Tool calls per message |
| delivery_attempts | ix_delivery_attempts_message_id | message_id | Delivery attempts per message |
| delivery_attempts | ix_delivery_attempts_status | status | Stuck messages polling |
| prompts | ix_prompts_name | name | Prompt lookup |

---

## 4. API Specification

### 4.1 Public Endpoints

#### `POST /webhooks/zalo`

Receives inbound Zalo messages. Must respond < 200ms.

**Headers:**
- `X-Zalo-Signature` (required): HMAC-SHA256 signature
- `Content-Type: application/json`

**Behavior:**
1. Verify HMAC-SHA256 signature against raw body
2. Parse body → extract `sender.id`, `message.message_id`, `message.text`
3. Check Redis for `message_id` (TTL 24h) → dedupe; if duplicate, return `{"success": true}` immediately
4. Store `message_id` in Redis with 24h TTL
5. Create or load conversation
6. Save inbound message to DB
7. Publish to `conversation.process` queue
8. Return `{"success": true}` immediately

**Response:**
- `200 OK` — `{"success": true}`
- `400 Bad Request` — invalid payload
- `401 Unauthorized` — invalid signature
- `429 Too Many Requests` — rate limited

---

#### `GET /health/live`

Liveness probe — no dependency checks.

**Response:** `{"status": "alive"}`

---

#### `GET /health/ready`

Readiness probe — verifies PostgreSQL, Redis, RabbitMQ connections.

**Response:**
- `200 OK` — `{"status": "ready", "checks": {"database": "ok", "redis": "ok", "rabbitmq": "ok"}}`
- `503 Service Unavailable` — one or more checks fail

---

### 4.2 Internal Endpoints

All internal endpoints require `X-Internal-Api-Key` header. Rate limited to 100 req/min per IP.

| Endpoint | Description |
|----------|-------------|
| `GET /internal/conversations` | Paginated list with filters (`user_id`, `status`) |
| `GET /internal/conversations/{id}` | Full conversation with messages, tool_calls, delivery_attempts |
| `POST /internal/replay?conversation_id={uuid}` | Re-queue conversation for reprocessing |
| `GET /internal/prompts` | List all prompts with versions |
| `POST /internal/prompts/activate` | Activate a specific prompt version |

### 4.3 Error Handling

| Exception | Status | Code |
|-----------|--------|------|
| Invalid signature | 401 | INVALID_SIGNATURE |
| Duplicate message | 200 | (silent) |
| Conversation not found | 404 | CONVERSATION_NOT_FOUND |
| Prompt not found | 404 | PROMPT_NOT_FOUND |
| Queue unavailable | 503 | QUEUE_UNAVAILABLE |
| Rate limit exceeded | 429 | RATE_LIMIT_EXCEEDED |

---

## 5. Queue Topology

### 5.1 RabbitMQ Exchanges & Queues

| Exchange | Type | Durable |
|----------|------|---------|
| `neochat.direct` | direct | true |
| `neochat.dlx` | direct | true |

| Queue | Routing Key | TTL | Max Length | Prefetch | DLX |
|-------|-------------|-----|-------------|----------|-----|
| conversation.process | conversation.process | 5 min | 10,000 | 1 | neochat.dlx |
| outbound.send | outbound.send | 10 min | 50,000 | 5 | neochat.dlx |
| dead-letter | dead-letter | — | — | — | — |

### 5.2 Retry Strategy

- **Max attempts:** 3
- **Backoff:** Exponential — 1s, 2s, 4s (base=2)
- **Retry triggers:** HTTP 429, 5xx, network timeout
- **Non-retryable:** HTTP 4xx (except 429), invalid/expired token (flagged for admin)
- **Exhausted retries:** Message routed to dead-letter queue

---

## 6. Worker Design

### 6.1 Conversation Worker

**Pipeline:**
1. Consume from `conversation.process` (auto_ack=False)
2. Load or create conversation from DB
3. Save inbound message to DB
4. Build prompt: active system prompt + last N messages (N = context_window_size, default 10)
5. Call LLM API (timeout 15s)
6. Parse response:
   - Text only → use as final response
   - Tool calls → execute up to 2, re-call LLM with results
7. Save outbound message to DB (with model, latency, token_usage)
8. Publish to `outbound.send` queue
9. Ack on success; nack + requeue on transient errors

**Fallback:** On non-transient error, publish fallback text:
> "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."

### 6.2 Outbound Worker

**Pipeline:**
1. Consume from `outbound.send` (auto_ack=False)
2. Get Zalo access token (from config or via refresh)
3. Call Zalo API to send text
4. On success: save delivery_attempt (status=success), ack
5. On failure: retry with exponential backoff (max 3)
6. After max retries: save delivery_attempt (status=failed), ack, message → dead-letter

### 6.3 Shared Worker Concerns

- **Graceful shutdown:** SIGTERM/SIGINT handler, finish in-flight work within 30s
- **Structured JSON logging:** correlation_id propagated everywhere, no tokens/PII logged
- **Health endpoints:** `/health/live` and `/health/ready` per worker
- **Prometheus metrics:** messages processed, LLM latency, tool calls, retries, DLQ depth

---

## 7. Agent Design

### 7.1 LLM Configuration

| Setting | Value |
|---------|-------|
| Default model | `claude-sonnet-4-20250514` |
| Max tokens | 1024 |
| Timeout | 15s total |
| System prompt | Fetched from DB at startup, cached, refreshed every 5 minutes |

### 7.2 Tool Calling

| Tool | Purpose | Timeout |
|------|---------|---------|
| `lookup_customer` | Find customer by phone/name | 5s |
| `get_order_status` | Query order by order_id | 5s |
| `create_support_ticket` | Open a support ticket | 5s |
| `handoff_request` | Flag for human handoff | 3s |

### 7.3 Constraints

- Max 2 tool calls per request
- Max 3 LLM steps total (initial call + tool results + final response)
- Timeout total: 15s

---

## 8. Prompt System

### 8.1 Prompt Types

| Name | Purpose |
|------|---------|
| `system` | Main agent system prompt (CSKH role, brevity, no hallucination) |
| `tool_policy` | When and how to call tools |
| `fallback` | Response when intent is unclear |

### 8.2 Versioning

- Prompts stored in `prompts` table with `versions` JSONB array
- `active_version` field tracks current active version
- Switching versions: `POST /internal/prompts/activate`
- All prompt changes logged with version stamp on each message

---

## 9. Configuration

### 9.1 Environment Variables

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

# Zalo OA
ZALO_APP_ID=your_zalo_app_id
ZALO_APP_SECRET=your_zalo_app_secret
ZALO_ACCESS_TOKEN=your_zalo_access_token
ZALO_WEBHOOK_SECRET=your_webhook_secret
ZALO_OA_ID=your_oa_id

# LLM Provider: "anthropic" or "openai-compat"
LLM_PROVIDER=anthropic

# Anthropic (llm_provider = "anthropic")
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# OpenAI-Compatible (llm_provider = "openai-compat")
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3.2

# API
INTERNAL_API_KEY=your_internal_api_key
CORS_ORIGINS=*
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=100

# Worker
CONTEXT_WINDOW_SIZE=10
MAX_TOOL_CALLS=2
LLM_TIMEOUT_SECONDS=15
```

### 9.2 Docker Compose Services

| Service | Image | Ports | Dependencies |
|---------|-------|-------|-------------|
| api | Dockerfile.api | 8000 | postgres, redis, rabbitmq (all healthy) |
| conversation-worker | Dockerfile.worker | 8080 (metrics) | postgres, rabbitmq |
| outbound-worker | Dockerfile.worker | 8081 (metrics) | rabbitmq |
| postgres | postgres:15-alpine | 5432 | — |
| redis | redis:7-alpine | 6379 | — |
| rabbitmq | rabbitmq:3.12-management-alpine | 5672, 15672 | — |

> Note: `docker-compose.yml` is split into `docker-compose.base.yml` (shared infra), `docker-compose.dev.yml`, and `docker-compose.prod.yml`.

RabbitMQ management UI: http://localhost:15672 (guest/guest)

---

## 10. Project Structure

```
/app
  /api
    __init__.py
    main.py               # FastAPI app entry point, lifespan, exception handlers
    config.py             # Pydantic BaseSettings from env
    dependencies.py       # DB, Redis, RabbitMQ, auth dependencies
    middleware.py         # Request ID, structured logging, PII masking
    /routers
      webhooks.py         # POST /webhooks/zalo
      health.py           # GET /health/live, GET /health/ready
      internal.py         # /internal/* endpoints
      auth.py             # Zalo OAuth token management
    /schemas
      webhook.py          # Zalo payload/response schemas
      health.py           # Health check schemas
      conversation.py     # Conversation list/detail schemas
      prompt.py           # Prompt schemas
      errors.py           # Error schemas
    /services
      signature.py        # HMAC-SHA256 webhook verification
      dedup.py            # Redis dedup service
      queue.py            # RabbitMQ publisher
    /scripts
      update_zalo_token.py
      generate_pkce.py
  /workers
    /conversation
      __init__.py
      main.py             # Worker entry, signal handling, health/metrics servers
      consumer.py         # RabbitMQ consumer loop
      processor.py        # Core processing pipeline (LLM + tools)
      llm.py              # LLM client wrapper (Anthropic + OpenAI-compatible)
      tools.py            # Tool registry + executors
      prompts.py          # Prompt loading and caching
      types.py            # Type definitions for worker
    /outbound
      __init__.py
      main.py             # Worker entry point
      consumer.py         # RabbitMQ consumer loop
      processor.py        # Zalo sending + retry logic
      zalo_client.py      # Zalo API client
      zalo_token_manager.py  # OAuth token refresh logic
    /shared
      __init__.py
      logging.py          # Structured JSON logger setup
      db.py               # SQLAlchemy async session
      queue.py            # RabbitMQ channel factory
      health.py           # Health check helpers
      metrics.py          # Prometheus metrics registry
  /core
    __init__.py
    config.py             # Shared settings
    database.py           # PostgreSQL async connection
    redis.py              # Redis client
    rabbitmq.py           # RabbitMQ connection helpers
  /models                 # SQLAlchemy ORM models
    __init__.py
    base.py               # Base, TimestampMixin, UUIDMixin
    conversation.py
    message.py
    tool_call.py
    delivery_attempt.py
    prompt.py
    zalo_token.py
/alembic
  /versions
    001_initial_schema.py
    002_add_zalo_tokens.py
    003_add_pkce_to_zalo_tokens.py
docker-compose.base.yml
docker-compose.dev.yml
docker-compose.prod.yml
.env.example
Dockerfile.api
Dockerfile.worker
```

---

## 11. Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|---------------|
| 1 | Webhook responds < 200ms | Load test with curl timing |
| 2 | No message loss under load | Pause rabbitmq, verify no unacked messages |
| 3 | Deduplication works | Send same message_id twice, only one outbound |
| 4 | Agent responds correctly | Send test message, verify LLM response |
| 5 | Tool calls execute | Trigger lookup_customer, verify DB tool_call record |
| 6 | Outbound delivers | Check Zalo received message |
| 7 | Retry works | Mock Zalo failure, verify 3 retries + DLQ |
| 8 | Fallback on error | Kill LLM, verify fallback message delivered |
| 9 | Logs are complete | Grep for correlation_id, verify all events present |
| 10 | Prompt versioning | Activate new version, verify new messages use it |
| 11 | Docker Compose works | `docker-compose up -d`, all services healthy |
| 12 | Graceful shutdown | SIGTERM worker, verify in-flight completes |
| 13 | Token refresh | Token expires → auto-refresh → retry succeeds |
