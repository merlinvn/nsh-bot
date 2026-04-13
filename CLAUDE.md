# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NeoChatPlatform is a multi-phase AI conversation platform starting with Zalo OA (Vietnamese messaging platform). Phase 1 focuses on building a production-ready Zalo chatbot agent.

## Architecture

```
Zalo → Webhook (FastAPI) → RabbitMQ (conversation.process) → Conversation Worker → RabbitMQ (outbound.send) → Outbound Worker → Zalo API
         ↓
Admin Browser (Next.js) ──► Admin API (FastAPI /admin/*) ──► PostgreSQL / Redis / RabbitMQ
                                                                  │
                                                          ┌───────┴───────┐
                                                          │  llm.process  │ ← LLMWorker (playground + evaluation)
                                                          └───────────────┘
```

### Message Queues

| Queue | Consumer | Purpose |
|-------|----------|---------|
| `conversation.process` | ConversationWorker | Zalo inbound message processing |
| `outbound.send` | OutboundWorker | Zalo outbound delivery |
| `llm.process` | LLMWorker | Playground chat, evaluation test cases |

### Components

**Workers (all run as separate containers):**
- **Conversation Worker**: Consumes `conversation.process`, runs LLM agent + tools, publishes to `outbound.send`
- **Outbound Worker**: Consumes `outbound.send`, calls Zalo API with retry logic
- **LLM Worker**: Consumes `llm.process`, handles playground chat and evaluation LLM calls. Routes responses by `channel`: `playground` → Redis pub/sub, `evaluation` → DB update, `zalo` → `outbound.send`

**Backend (FastAPI):**
- **Webhook API**: Receives Zalo webhooks, response < 200ms
- **Admin API**: `/admin/*` routes for the control plane

**Frontend (Next.js 14):**
- **Admin UI**: `/admin/*` pages

**Data Stores:**
- **PostgreSQL**: conversations, messages, tool_calls, delivery_attempts, prompts, admin_users, benchmark_results, prompt_evaluations, evaluation_test_cases
- **Redis**: message deduplication, admin sessions, LLM response pub/sub
- **RabbitMQ**: durable message queues

## Package Management

Uses **uv** for Python dependency management.

```bash
# Install dependencies
uv sync

# Add a dependency
uv add <package>

# Run with uv (used in Dockerfiles)
uv run python -m app.api.main
```

## Development Commands

```bash
# Docker Compose (full stack)
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f api
docker-compose -f docker-compose.dev.yml logs -f conversation-worker
docker-compose -f docker-compose.dev.yml logs -f llm-worker

# Run database migration
docker-compose -f docker-compose.dev.yml exec api alembic upgrade head

# Open shell in running container
docker-compose -f docker-compose.dev.yml exec api /bin/sh
```

## Key Patterns

### LLM Queue (Channel-based Routing)

All LLM calls for playground and evaluation go through `llm.process` queue. Workers publish responses via Redis pub/sub or DB update.

```python
# API: enqueue_llm_request() from app.api.services.llm_queue
result = await enqueue_llm_request({
    "channel": "playground",      # or "evaluation"
    "system_prompt": "...",
    "messages": [...],
    "new_message": "...",
})
```

```python
# Worker processes based on channel field
if channel == "playground":
    # → Redis pub/sub response
elif channel == "evaluation":
    # → DB update + Redis pub/sub
elif channel == "zalo":
    # → outbound.send queue
```

### Webhook Processing
- Always use queue (never block webhook with direct API calls)
- Deduplicate messages via Redis
- Push to `conversation.process` queue

### Agent (AgentRunner)
- Shared between ConversationWorker, Playground, and Evaluation
- `app/workers/conversation/agent.py`: `AgentRunner` class with `on_tool_call` callback
- Max 3 steps, max 2 tool calls per step
- `on_tool_call`: intercepts `delegate_to_quote_agent` for quote subagent, persists ToolCall records to DB

### Outbound
- Send via `outbound.send` queue
- Retry with exponential backoff (max 3 attempts)
- Log all delivery attempts

## Data Model

### Core
- **Conversations**: id, external_user_id, conversation_key, status, timestamps
- **Messages**: id, conversation_id, direction, text, model, latency, token_usage, error
- **ToolCalls**: tool_name, input, output, success, latency
- **DeliveryAttempts**: status, attempt_no, response, error
- **Prompts**: template, versions, active_version
- **AdminUsers**: id, username, password_hash, is_active, last_login_at, failed_login_attempts, locked_until

### Benchmark
- **BenchmarkResults**: id, name, status, iterations, error, created_at, completed_at
- **BenchmarkItems**: id, benchmark_id, model_provider, model_name, avg_latency_ms, p95_latency_ms, avg_input_tokens, avg_output_tokens, total_cost, raw_results

### Evaluation
- **PromptEvaluations**: id, name, prompt_name, status, total, passed, failed, error, created_at, completed_at
- **EvaluationTestCases**: id, evaluation_id, question, expected_answer, actual_answer, passed, judgment, latency_ms, error, created_at

## Admin API Endpoints

All `/admin/*` routes require session cookie authentication (except login).

| Route | Description |
|-------|-------------|
| `POST /admin/auth/login` | Login with username/password |
| `POST /admin/auth/logout` | Logout (clear session) |
| `GET /admin/auth/me` | Get current user info |
| `POST /admin/auth/password` | Change own password |
| `GET /admin/prompts` | List all prompts |
| `POST /admin/prompts` | Create new prompt |
| `GET /admin/prompts/{name}` | Get prompt detail |
| `PUT /admin/prompts/{name}` | Update prompt (new version) |
| `DELETE /admin/prompts/{name}` | Delete prompt |
| `POST /admin/prompts/{name}/versions` | Create new version |
| `POST /admin/prompts/{name}/activate` | Activate a version |
| `GET /admin/prompts/{name}/versions` | List all versions |
| `GET /admin/conversations` | List conversations (paginated) |
| `GET /admin/conversations/{id}` | Get conversation + messages |
| `POST /admin/conversations/{id}/replay` | Dry-run replay (no Zalo delivery) |
| `GET /admin/conversations/stats` | Conversation statistics |
| `GET /admin/conversations/{id}/messages` | List messages in conversation |
| `GET /admin/analytics/overview` | Dashboard overview |
| `GET /admin/analytics/messages` | Message volume over time |
| `GET /admin/analytics/latency` | LLM latency percentiles |
| `GET /admin/analytics/tools` | Tool usage breakdown |
| `GET /admin/analytics/fallbacks` | Fallback rates |
| `GET /admin/analytics/tokens` | Token usage summary |
| `POST /admin/playground/chat` | Chat via llm.process queue (uses AgentRunner) |
| `POST /admin/playground/complete` | Single completion test |
| `POST /admin/playground/benchmark` | Run benchmark |
| `GET /admin/playground/benchmark/{id}` | Get benchmark result |
| `GET /admin/playground/benchmark/{id}/results` | Get benchmark detailed results |
| `GET /admin/playground/models` | List available models |
| `GET /admin/evaluations` | List all evaluations |
| `POST /admin/evaluations` | Create new evaluation |
| `GET /admin/evaluations/{id}` | Get evaluation with test cases |
| `DELETE /admin/evaluations/{id}` | Delete evaluation |
| `POST /admin/evaluations/{id}/test-cases` | Add test case |
| `DELETE /admin/evaluations/{id}/test-cases/{tc_id}` | Delete test case |
| `POST /admin/evaluations/{id}/run` | Run evaluation (via llm.process queue) |
| `GET /admin/zalo-tokens/status` | Current token status |
| `POST /admin/zalo-tokens/pkce` | Generate PKCE pair |
| `POST /admin/zalo-tokens/refresh` | Refresh access token |
| `DELETE /admin/zalo-tokens` | Revoke tokens |
| `GET /admin/monitoring/health` | Detailed health check |
| `GET /admin/monitoring/metrics` | JSON metrics for UI |
| `GET /admin/monitoring/workers` | Worker status |
| `GET /admin/monitoring/queues` | Queue depths |

## Phase Roadmap

1. **Phase 1** ✅: Zalo Chat Agent MVP
2. **Phase 2** ✅ (mostly): Admin Control Plane — auth, analytics, prompt management, LLM playground, token management, monitoring, prompt evaluation with LLM judge
3. **Phase 3**: Multi-channel (Telegram, Facebook Messenger)
4. **Phase 4**: RAG/knowledge base
5. **Phase 5**: Multi-tenant, Kubernetes, A/B testing

## Important Notes

- Never log access tokens
- Mask PII in logs
- Validate all webhook input
- All Zalo API calls go through outbound worker (never directly from webhook)
- **LLM Tool Format**: OpenAI-compatible LLM clients use `{"type": "function", "function": {...}}` format, NOT Anthropic's `{"name": ..., "input_schema": ...}`. The `OpenAICompatLLM._convert_tools()` method handles this conversion.
- **Zalo Token**: All token operations (status/refresh/revoke) are delegated to `ZaloTokenManager` in `app/workers/shared/zalo_token_manager.py`. If Zalo returns `-216 Access token is invalid`, the token was revoked server-side. Update via script: `docker-compose exec -T api uv run python app/api/scripts/update_zalo_token.py --access-token "token"`
- **Admin Bootstrap**: After first DB setup, create the initial admin user: `docker-compose exec api uv run python app/api/scripts/create_admin_user.py --username admin --password 'your-password'`
- **Admin Session**: Sessions are Redis-backed (24h fixed TTL). Cookie is httpOnly + SameSite=Lax. CSRF token returned in login response body, sent as `X-CSRF-Token` header on state-changing requests.
- **LLM Worker**: Playground chat and evaluation LLM calls go through `llm.process` queue. Response delivered via Redis pub/sub for playground/evaluation, via `outbound.send` for zalo channel.
- **LLM Judge (Evaluation)**: Each evaluation test case is judged by a second LLM call asking if actual answer matches expected answer semantically. Returns PASS/FAIL with reasoning in Vietnamese.

## Testing

### Unit Tests (no external dependencies)
```bash
uv run pytest tests/unit/ -v
```

Unit tests use mocks for all external services (database, Redis, RabbitMQ).

### Integration Tests (requires Docker)
```bash
# Start test infrastructure
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be ready
sleep 10

# Run integration tests
DATABASE_URL="postgresql+asyncpg://neochat:changeme@localhost:5432/neochat" \
uv run pytest tests/integration/ -v

# Stop test infrastructure
docker-compose -f docker-compose.test.yml down -v
```

### Test Structure
```
tests/
├── unit/                    # Unit tests with mocks
│   ├── conftest.py
│   ├── test_tools.py
│   ├── test_llm.py
│   ├── test_prompts.py
│   ├── test_processor.py
│   ├── test_zalo_client.py
│   ├── test_consumer.py
│   └── test_health.py
└── integration/             # Integration tests (requires Docker)
    ├── conftest.py
    ├── models/
    │   ├── test_conversation.py
    │   ├── test_message.py
    │   ├── test_delivery_attempt.py
    │   ├── test_tool_call.py
    │   └── test_prompt.py
    ├── test_internal.py
    ├── test_webhooks.py
    └── test_processor.py
```

### Pytest Configuration
- `asyncio_mode = "auto"` - async tests run automatically
- `addopts = "--import-mode=importlib"` - prevents module name collision between test files with same names (e.g., `test_processor.py` in both unit/ and integration/)
- Tests can run together: `uv run pytest tests/ -v`
