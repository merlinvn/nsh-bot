# NeoChat Platform — System Specification

**Last Updated:** 2026-04-17
**Status:** Phase 2 (mostly complete)

---

## Architecture

```
                         ┌─────────────────────────────────────────────────────────────┐
                         │                    RabbitMQ                                       │
Zalo Webhook ──────────►│ conversation.process ──► ConversationWorker ──► llm.process ──┼──► LLMWorker ──► outbound.send ──► OutboundWorker ──► Zalo API
                         │                                                       ▲          │
                         └───────────────────────────────────────────────────────────┼──────────┘
                                                                               │
Admin Browser (Next.js) ──► Caddy (reverse proxy) ──► Admin API (FastAPI /api/*)
    │                                                          │                      │
    │  /* (Next.js SPA)                                        │                 PostgreSQL ◄────┘
    │                                                          │                      │
    └──────────────────────────────────────────────────────────│                Redis ◄────┘
                                                               │         (sessions, pub/sub, heartbeat)
                                                               │
                                                      ┌────────┴────────┐
                                                      │  LLM Workers   │
                                                      │  (llm.process) │
                                                      └────────────────┘
```

## Caddy Routing

All external traffic goes through Caddy (ports 80/443):

| Path | Destination | Purpose |
|------|-------------|---------|
| `/api/*` | `api:8000` | Admin API (FastAPI) |
| `/auth/zalo/callback` | `api:8000` | Zalo OAuth callback |
| `/webhooks/zalo` | `api:8000` | Zalo webhook receiver |
| `/health` | `api:8000` | Health check |
| `/internal/*` | `api:8000` | Internal API (protected) |
| `/*` | `frontend:3000` | Next.js SPA (admin UI) |

## Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| `api` | internal | FastAPI — webhook + admin endpoints |
| `conversation-worker` | internal | Consumes `conversation.process`, routes to `llm.process` |
| `llm-worker` | internal | Runs all LLM calls (Zalo, playground, evaluation) |
| `outbound-worker` | internal | Sends messages to Zalo API |
| `postgres` | internal | PostgreSQL 15 |
| `redis` | internal | Redis 7 — sessions, pub/sub, heartbeat |
| `rabbitmq` | 15672 (mgmt) | RabbitMQ 3.12 — message queues |
| `caddy` | 80, 443 | Reverse proxy (public) |
| `frontend` | internal | Next.js admin SPA |

**Dev-only ports** (via `docker-compose.override.yml`):
- `postgres:5432`, `redis:6379`, `api:8000`, `conversation-worker:8080`, `outbound-worker:8081`, `llm-worker:8082`, `frontend:3000`, `rabbitmq:5672`

**Worker health:** Each worker exposes `/health` on its metrics port (8080/8081/8082). Docker healthcheck returns `200 healthy` when the RabbitMQ consumer is running, `503 unhealthy` when the consumer has crashed. Workers auto-restart via `restart: unless-stopped` + healthcheck failures.

---

## Message Queues

| Queue | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `conversation.process` | API (webhook) | ConversationWorker | Zalo inbound messages |
| `llm.process` | ConversationWorker, API | LLMWorker | All LLM processing requests |
| `outbound.send` | ConversationWorker, LLMWorker | OutboundWorker | Outbound Zalo messages |
| `dead-letter` | RabbitMQ DLX | — | Failed messages |

---

## Workers

### ConversationWorker

- **Queue consumed:** `conversation.process` (prefetch=1)
- **Role:** Message routing — does NOT call LLM directly
- **Flow:**
  1. Receive Zalo message from `conversation.process`
  2. Save inbound `Message` to DB
  3. Create placeholder outbound `Message` in DB
  4. Publish to `llm.process` with `channel="zalo"`
  5. Wait for Redis response (`llm:response:{request_id}`)
  6. Update outbound `Message` with LLM text/latency/token_usage
  7. Publish to `outbound.send`
- **Heartbeat key:** `worker:heartbeat:conversation-worker`

### LLMWorker

- **Queue consumed:** `llm.process` (prefetch=5)
- **Role:** All LLM computation
- **Handles three channels:**

| Channel | Source | Processing | Response |
|---------|--------|------------|----------|
| `playground` | API (`/api/playground/chat`) | `AgentRunner` + tools | Redis pub/sub |
| `evaluation` | API (`/api/evaluations/{id}/run`) | `AgentRunner` + LLM judge | DB update + Redis pub/sub |
| `zalo` | ConversationWorker | `AgentRunner` + MCP tools | Redis pub/sub + DB update |

- **Heartbeat key:** `worker:heartbeat:llm-worker`

### OutboundWorker

- **Queue consumed:** `outbound.send` (prefetch=5)
- **Role:** Delivers messages to Zalo API with retry
- **Retry logic:** Exponential backoff, max 3 attempts
- **Heartbeat key:** `worker:heartbeat:outbound-worker`

---

## LLM Queue — Channel Routing

All LLM calls go through `llm.process` with a `channel` field that determines response routing.

### Request Payload (all channels)

```json
{
  "request_id": "uuid",
  "channel": "playground" | "evaluation" | "zalo",
  "response_channel": "llm:response:{request_id}"
}
```

### `playground` Channel

- **API endpoint:** `POST /api/playground/chat`
- **Payload:** `system_prompt`, `messages` (history), `new_message`
- **Worker:** `LLMProcessor._process_playground()` — runs `AgentRunner`, publishes to Redis `llm:response:{request_id}`
- **Response:** `{text, tool_calls, token_usage, latency_ms, error}`

### `evaluation` Channel

- **API endpoint:** `POST /api/evaluations/{id}/run`
- **Payload:** `evaluation_id`, `tc_id`, `question`, `expected_answer`, `prompt_name`
- **Worker:** `LLMProcessor._process_evaluation()` — runs `AgentRunner` + LLM judge, updates DB, publishes to Redis
- **Response:** `{text, passed, judgment, latency_ms, error}`

### `zalo` Channel

- **Source:** ConversationWorker (not API)
- **Payload:** `channel`, `correlation_id`, `inbound_message_id`, `outbound_message_id`, `external_user_id`, `zalo_message_id`, `system_prompt`, `conversation_history`, `inbound_text`
- **Worker:** `LLMProcessor._process_zalo()` — runs `AgentRunner` with MCP tools (`calculate_shipping_quote`), records ToolCalls in DB, publishes to Redis
- **Response:** `{text, token_usage, latency_ms}`
- **Note:** ConversationWorker handles `outbound.send` publish after receiving Redis response

---

## Admin API Endpoints

All `/api/*` routes require session cookie authentication (except login).

### Auth

| Route | Method | Description |
|-------|--------|-------------|
| `/api/auth/login` | POST | Login with username/password |
| `/api/auth/logout` | POST | Logout (clear session) |
| `/api/auth/me` | GET | Get current user info |
| `/api/auth/password` | POST | Change own password |

### Prompts

| Route | Method | Description |
|-------|--------|-------------|
| `/api/prompts` | GET | List all prompts |
| `/api/prompts` | POST | Create new prompt |
| `/api/prompts/{name}` | GET | Get prompt detail |
| `/api/prompts/{name}` | PUT | Update prompt (new version) |
| `/api/prompts/{name}` | DELETE | Delete prompt |
| `/api/prompts/{name}/versions` | POST | Create new version |
| `/api/prompts/{name}/activate` | POST | Activate a version |
| `/api/prompts/{name}/versions` | GET | List all versions |

### Conversations

| Route | Method | Description |
|-------|--------|-------------|
| `/api/conversations` | GET | List conversations (paginated) |
| `/api/conversations/{id}` | GET | Get conversation + messages |
| `/api/conversations/{id}/replay` | POST | Dry-run replay (no Zalo delivery) |
| `/api/conversations/stats` | GET | Conversation statistics |
| `/api/conversations/{id}/messages` | GET | List messages in conversation |

### Analytics

| Route | Method | Description |
|-------|--------|-------------|
| `/api/analytics/overview` | GET | Dashboard overview |
| `/api/analytics/messages` | GET | Message volume over time |
| `/api/analytics/latency` | GET | LLM latency percentiles |
| `/api/analytics/tools` | GET | Tool usage breakdown |
| `/api/analytics/fallbacks` | GET | Fallback rates |
| `/api/analytics/tokens` | GET | Token usage summary |

### Playground

| Route | Method | Description |
|-------|--------|-------------|
| `/api/playground/chat` | POST | Chat via llm.process queue |
| `/api/playground/complete` | POST | Single completion test |
| `/api/playground/benchmark` | POST | Run benchmark |
| `/api/playground/benchmark/{id}` | GET | Get benchmark result |
| `/api/playground/benchmark/{id}/results` | GET | Get benchmark detailed results |
| `/api/playground/models` | GET | List available models |

### Evaluations

| Route | Method | Description |
|-------|--------|-------------|
| `/api/evaluations` | GET | List all evaluations |
| `/api/evaluations` | POST | Create new evaluation |
| `/api/evaluations/{id}` | GET | Get evaluation with test cases |
| `/api/evaluations/{id}` | DELETE | Delete evaluation |
| `/api/evaluations/{id}/test-cases` | POST | Add test case |
| `/api/evaluations/{id}/test-cases/{tc_id}` | DELETE | Delete test case |
| `/api/evaluations/{id}/run` | POST | Run evaluation (via llm.process queue) |

### Zalo Tokens

| Route | Method | Description |
|-------|--------|-------------|
| `/api/zalo-tokens/status` | GET | Current token status |
| `/api/zalo-tokens/pkce` | POST | Generate PKCE pair |
| `/api/zalo-tokens/refresh` | POST | Refresh access token |
| `/api/zalo-tokens` | DELETE | Revoke tokens |

### Monitoring

| Route | Method | Description |
|-------|--------|-------------|
| `/api/monitoring/health` | GET | Detailed health check |
| `/api/monitoring/health-detail` | GET | Per-service health with latency |
| `/api/monitoring/metrics` | GET | JSON metrics for UI |
| `/api/monitoring/metrics-trend` | GET | Current + previous metrics for trend |
| `/api/monitoring/workers` | GET | Worker status (alive/stale/dead) |
| `/api/monitoring/queues` | GET | Queue depths, rates, oldest message age |
| `/api/monitoring/queues/{vhost}/{queue_name}/messages` | GET | Peek messages in queue (without consuming) |

---

## Data Models (PostgreSQL)

### Core

- **Conversations**: `id`, `external_user_id`, `conversation_key`, `status`, `created_at`, `updated_at`
- **Messages**: `id`, `conversation_id`, `direction` (inbound/outbound), `text`, `message_id`, `model`, `latency_ms`, `token_usage` (JSON), `error`, `prompt_version`, `created_at`
- **ToolCalls**: `id`, `message_id`, `tool_name`, `input` (JSON), `output` (JSON), `success`, `latency_ms`, `created_at`
- **DeliveryAttempts**: `id`, `message_id`, `status`, `attempt_no`, `response`, `error`, `created_at`
- **Prompts**: `id`, `name`, `template`, `created_at`, `updated_at`, `active_version`, `versions` (JSON array — no separate table)
- **AdminUsers**: `id`, `username`, `password_hash`, `is_active`, `last_login_at`, `failed_login_attempts`, `locked_until`, `created_at`

### Benchmark

- **BenchmarkResults**: `id`, `name`, `status`, `iterations`, `error`, `created_at`, `completed_at`
- **BenchmarkItems**: `id`, `benchmark_id`, `model_provider`, `model_name`, `avg_latency_ms`, `p95_latency_ms`, `avg_input_tokens`, `avg_output_tokens`, `total_cost`, `raw_results` (JSON)

### Evaluation

- **PromptEvaluations**: `id`, `name`, `prompt_name`, `status` (pending/running/completed/failed), `total`, `passed`, `failed`, `error`, `created_at`, `completed_at`
- **EvaluationTestCases**: `id`, `evaluation_id`, `question`, `expected_answer`, `actual_answer`, `passed`, `judgment`, `latency_ms`, `error`, `created_at`

---

## Agent System

### AgentRunner (`app/workers/conversation/agent.py`)

Shared LLM loop used by LLMWorker for all channels.

- **Max steps:** 3
- **Max tool calls per step:** 2
- **Tool backend:** `MCPToolBackend` — routes all 5 tools across 3 MCP domains
- **Tool call recording:** Persisted to `tool_calls` table via `on_tool_call` callback

### MCP Tools (5 tools — standalone HTTP MCP server)

The MCP server runs as a separate Docker service (`nsh-mcp`). Workers call it via HTTP JSON-RPC at `http://nsh-mcp:8080/rpc`.

| Domain | Tool | Handler |
|--------|------|---------|
| Shipping | `calculate_shipping_quote` | `nsh-mcp/src/nsh_mcp/engine.py` |
| Customer | `lookup_customer` | `nsh-mcp/src/nsh_mcp/customer.py` |
| Customer | `get_order_status` | `nsh-mcp/src/nsh_mcp/customer.py` |
| Support | `create_support_ticket` | `nsh-mcp/src/nsh_mcp/support.py` |
| Support | `handoff_request` | `nsh-mcp/src/nsh_mcp/support.py` |

`MCPToolBackend` (`app/workers/mcp_client.py`) is the async tool execution entry point used by workers.
`list_tools()` in the same file fetches tool definitions from the MCP server at startup (cached in-process).

### Pricing Engine

`nsh-mcp/src/nsh_mcp/pricing/pricing.py` — pure `QuoteInput → QuoteResult`, no I/O.
`nsh-mcp/src/nsh_mcp/pricing/config.py` — tenant config loaded from JSON files, cached in-process dict (`_config_cache`), 900s TTL per tenant, fail-open.

### Prompt Management

`PromptManager` (`app/workers/conversation/prompts.py`) loads and caches prompts from the `prompts` table.

- **Cache TTL:** 5 minutes (in-memory, not Redis)
- **Default prompts:** `system`, `tool_policy`, `fallback`
- **Auto-population (upsert):** If any of the 3 defaults are absent from DB, `_load_from_db()` inserts the hardcoded default as version 1 and commits it. On next cache refresh (after TTL or deletion), the default is re-inserted if missing — i.e., deleting from the frontend causes automatic re-population on next access.
- **Startup:** Lazy — no automatic load at startup; prompts load on first request.
- **Versioning:** Versions start at 1.

---

## Redis Usage

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `session:{session_id}` | Admin session data | 24h fixed |
| `zalo:dedup:{message_id}` | Zalo inbound message deduplication | 24h |
| `zalo:ack:{message_id}` | Zalo webhook ACK idempotency | 24h |
| `outbound:sent:{outbound_message_id}` | Outbound message idempotency (prevent double-send) | 24h |
| `worker:heartbeat:{name}` | Worker alive signal | none (detected by age) |
| `llm:response:{request_id}` | LLM response pub/sub channel | none |
| `monitoring:metrics:prev` | Previous metrics for trend | 60s |

---

## Security

- **Admin sessions:** Redis-backed, 24h fixed TTL, httpOnly + SameSite=Lax cookie
- **CSRF:** Token returned in login response body, sent as `X-CSRF-Token` header on state-changing requests
- **Rate limiting:** Login attempts limited by Redis (locked_until field)
- **Logging:** Access tokens never logged; PII masked
- **Webhook:** All input validated; deduplicated by `message_id`

---

## Admin Bootstrap

After first DB setup:
```bash
docker-compose exec api uv run python app/api/scripts/create_admin_user.py \
  --username admin --password 'your-password'
```

---

## LLM Configuration

| Setting | Env Var | Default |
|---------|---------|---------|
| Provider | `LLM_PROVIDER` | `anthropic` |
| Anthropic API Key | `ANTHROPIC_API_KEY` | — |
| Anthropic Model | `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` |
| OpenAI Base URL | `OPENAI_BASE_URL` | `http://localhost:11434/v1` |
| OpenAI API Key | `OPENAI_API_KEY` | `ollama` |
| OpenAI Model | `OPENAI_MODEL` | `llama3.2` |
| LLM Timeout | `LLM_TIMEOUT_SECONDS` | 15 |

**Note:** OpenAI-compatible format uses `{"type": "function", "function": {...}}` NOT Anthropic's `{"name": ..., "input_schema": ...}`. Handled by `OpenAICompatLLM._convert_tools()`.

---

## Phase Roadmap

1. **Phase 1** ✅: Zalo Chat Agent MVP
2. **Phase 2** ✅ (mostly): Admin Control Plane — auth, analytics, prompt management, LLM playground, token management, monitoring, prompt evaluation with LLM judge
3. **Phase 3**: Multi-channel (Telegram, Facebook Messenger)
4. **Phase 4**: RAG/knowledge base
5. **Phase 5**: Multi-tenant, Kubernetes, A/B testing

---

## Important Notes

- **Zalo Token:** All token operations delegated to `ZaloTokenManager` in `app/workers/shared/zalo_token_manager.py`. If Zalo returns `-216 Access token is invalid`, token was revoked server-side. Update via:
  ```bash
  docker-compose exec -T api uv run python app/api/scripts/update_zalo_token.py \
    --access-token "token"
  ```

- **LLM Judge (Evaluation):** Each test case judged by second LLM call asking if actual answer semantically matches expected. Returns Vietnamese PASS/FAIL with reasoning.

- **MCP Architecture:** `nsh-mcp/` — standalone MCP HTTP server (separate Docker service). `app/workers/mcp_client.py` — worker-side MCP client. `MCPToolBackend` executes tools via HTTP JSON-RPC. `list_tools()` aggregates tool definitions. Tenant pricing in `nsh-mcp/data/{tenant_id}/pricing_rules.json`. Config cached in-process (900s TTL), fail-open.
