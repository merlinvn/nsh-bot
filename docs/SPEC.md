# NeoChat Platform — System Specification

**Last Updated:** 2026-04-13
**Status:** Phase 2 (mostly complete)

---

## Overview

NeoChatPlatform is a multi-phase AI conversation platform starting with Zalo OA (Vietnamese messaging platform).

## Architecture

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    RabbitMQ                                       │
Zalo Webhook ─────►│ conversation.process ──► ConversationWorker ──► llm.process ──┼──► LLMWorker ──► outbound.send ──► OutboundWorker ──► Zalo API
                    │                                                       ▲          │
                    └───────────────────────────────────────────────────────────┼──────────┘
                                                                              │
Admin Browser (Next.js) ──► Admin API (FastAPI /admin/*) ──► PostgreSQL ◄────┘
                                       │                      │
                                       │                 Redis ◄────┘
                                       │            (sessions, pub/sub, heartbeat)
                                       │
                              ┌────────┴────────┐
                              │  LLM Workers   │
                              │  (llm.process) │
                              └────────────────┘
```

## Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| `api` | 8000 | FastAPI — webhook + admin endpoints |
| `conversation-worker` | 8080 | Consumes `conversation.process`, routes to `llm.process` |
| `llm-worker` | 8082 | Runs all LLM calls (Zalo, playground, evaluation) |
| `outbound-worker` | 8081 | Sends messages to Zalo API |
| `postgres` | 5432 | PostgreSQL 15 |
| `redis` | 6379 | Redis 7 — sessions, pub/sub, heartbeat |
| `rabbitmq` | 5672, 15672 | RabbitMQ 3.12 — message queues |

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

### ConversationWorker (port 8080)

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

### LLMWorker (port 8082)

- **Queue consumed:** `llm.process` (prefetch=5)
- **Role:** All LLM computation
- **Handles three channels:**

| Channel | Source | Processing | Response |
|---------|--------|------------|----------|
| `playground` | API (`/admin/playground/chat`) | `AgentRunner` + tools | Redis pub/sub |
| `evaluation` | API (`/admin/evaluations/{id}/run`) | `AgentRunner` + LLM judge | DB update + Redis pub/sub |
| `zalo` | ConversationWorker | `AgentRunner` + tools + quote subagent | Redis pub/sub + DB update |

- **For `zalo` channel specifically:**
  - Runs `AgentRunner` with full tool call recording (own `db_session`)
  - Intercepts `delegate_to_quote_agent` — runs quote subagent
  - Updates outbound `Message` in DB with text/latency/token_usage
  - Publishes response to Redis for ConversationWorker
- **Heartbeat key:** `worker:heartbeat:llm-worker`

### OutboundWorker (port 8081)

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

- **API endpoint:** `POST /admin/playground/chat`
- **Payload:** `system_prompt`, `messages` (history), `new_message`
- **Worker:** `LLMProcessor._process_playground()` — runs `AgentRunner`, publishes to Redis `llm:response:{request_id}`
- **Response:** `{text, tool_calls, token_usage, latency_ms, error}`

### `evaluation` Channel

- **API endpoint:** `POST /admin/evaluations/{id}/run`
- **Payload:** `evaluation_id`, `tc_id`, `question`, `expected_answer`, `prompt_name`
- **Worker:** `LLMProcessor._process_evaluation()` — runs `AgentRunner` + LLM judge, updates DB, publishes to Redis
- **Response:** `{text, passed, judgment, latency_ms, error}`

### `zalo` Channel

- **Source:** ConversationWorker (not API)
- **Payload:** `inbound_message_id`, `outbound_message_id`, `system_prompt`, `conversation_history`, `inbound_text`
- **Worker:** `LLMProcessor._process_zalo()` — runs `AgentRunner` with tool call recording + quote subagent, updates outbound `Message` in DB, publishes to Redis
- **Response:** `{text, token_usage, latency_ms}`
- **Note:** ConversationWorker handles `outbound.send` publish after receiving Redis response

---

## Admin API Endpoints

All `/admin/*` routes require session cookie authentication (except login).

### Auth

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/auth/login` | POST | Login with username/password |
| `/admin/auth/logout` | POST | Logout (clear session) |
| `/admin/auth/me` | GET | Get current user info |
| `/admin/auth/password` | POST | Change own password |

### Prompts

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/prompts` | GET | List all prompts |
| `/admin/prompts` | POST | Create new prompt |
| `/admin/prompts/{name}` | GET | Get prompt detail |
| `/admin/prompts/{name}` | PUT | Update prompt (new version) |
| `/admin/prompts/{name}` | DELETE | Delete prompt |
| `/admin/prompts/{name}/versions` | POST | Create new version |
| `/admin/prompts/{name}/activate` | POST | Activate a version |
| `/admin/prompts/{name}/versions` | GET | List all versions |

### Conversations

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/conversations` | GET | List conversations (paginated) |
| `/admin/conversations/{id}` | GET | Get conversation + messages |
| `/admin/conversations/{id}/replay` | POST | Dry-run replay (no Zalo delivery) |
| `/admin/conversations/stats` | GET | Conversation statistics |
| `/admin/conversations/{id}/messages` | GET | List messages in conversation |

### Analytics

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/analytics/overview` | GET | Dashboard overview |
| `/admin/analytics/messages` | GET | Message volume over time |
| `/admin/analytics/latency` | GET | LLM latency percentiles |
| `/admin/analytics/tools` | GET | Tool usage breakdown |
| `/admin/analytics/fallbacks` | GET | Fallback rates |
| `/admin/analytics/tokens` | GET | Token usage summary |

### Playground

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/playground/chat` | POST | Chat via llm.process queue |
| `/admin/playground/complete` | POST | Single completion test |
| `/admin/playground/benchmark` | POST | Run benchmark |
| `/admin/playground/benchmark/{id}` | GET | Get benchmark result |
| `/admin/playground/benchmark/{id}/results` | GET | Get benchmark detailed results |
| `/admin/playground/models` | GET | List available models |

### Evaluations

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/evaluations` | GET | List all evaluations |
| `/admin/evaluations` | POST | Create new evaluation |
| `/admin/evaluations/{id}` | GET | Get evaluation with test cases |
| `/admin/evaluations/{id}` | DELETE | Delete evaluation |
| `/admin/evaluations/{id}/test-cases` | POST | Add test case |
| `/admin/evaluations/{id}/test-cases/{tc_id}` | DELETE | Delete test case |
| `/admin/evaluations/{id}/run` | POST | Run evaluation (via llm.process queue) |

### Zalo Tokens

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/zalo-tokens/status` | GET | Current token status |
| `/admin/zalo-tokens/pkce` | POST | Generate PKCE pair |
| `/admin/zalo-tokens/refresh` | POST | Refresh access token |
| `/admin/zalo-tokens` | DELETE | Revoke tokens |

### Monitoring

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/monitoring/health` | GET | Detailed health check |
| `/admin/monitoring/health-detail` | GET | Per-service health with latency |
| `/admin/monitoring/metrics` | GET | JSON metrics for UI |
| `/admin/monitoring/metrics-trend` | GET | Current + previous metrics for trend |
| `/admin/monitoring/workers` | GET | Worker status (alive/stale/dead) |
| `/admin/monitoring/queues` | GET | Queue depths, rates, oldest message age |
| `/admin/monitoring/queues/{vhost}/{queue_name}/messages` | GET | Peek messages in queue (without consuming) |

---

## Data Models (PostgreSQL)

### Core

- **Conversations**: `id`, `external_user_id`, `conversation_key`, `status`, `created_at`, `updated_at`
- **Messages**: `id`, `conversation_id`, `direction` (inbound/outbound), `text`, `message_id`, `model`, `latency_ms`, `token_usage` (JSON), `error`, `prompt_version`, `created_at`
- **ToolCalls**: `id`, `message_id`, `tool_name`, `input` (JSON), `output` (JSON), `success`, `latency_ms`, `created_at`
- **DeliveryAttempts**: `id`, `message_id`, `status`, `attempt_no`, `response`, `error`, `created_at`
- **Prompts**: `id`, `name`, `template`, `created_at`, `updated_at`, `active_version`
- **PromptVersions**: `id`, `prompt_id`, `version`, `template`, `created_at`
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
- **Tool interception:** `delegate_to_quote_agent` — intercepted by `on_tool_call`, replaced with quote subagent result
- **Tool call recording:** Persisted to `tool_calls` table via `on_tool_call` callback

### Tools

Available tools defined in `app/workers/conversation/registry.py`:

- `calculate_shipping_quote` — Calculate shipping quote
- `get_delivery_date` — Estimate delivery date
- `track_order` — Track order status
- `delegate_to_quote_agent` — Delegate to quote subagent (intercepted)
- (others per `MAIN_AGENT_TOOLS` and `QUOTE_AGENT_TOOLS`)

### Quote Subagent

Runs with `calculate_shipping_quote` tool only. Returns structured JSON:
```json
{
  "status": "success" | "manual_review" | "error",
  "message_to_customer": "...",
  "quote_amount": 45000,
  "delivery_days": 3,
  "reason": "...",
  "raw_text": "..."
}
```

---

## Redis Usage

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `session:{session_id}` | Admin session data | 24h fixed |
| `prompt:cache:{version}` | Cached prompt templates | none |
| `dedup:zalo:{message_id}` | Zalo message deduplication | 5 min |
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

- **Future: MCP integration:** Tool call and subagent system will be replaced by MCP (Model Context Protocol) in a future phase.
