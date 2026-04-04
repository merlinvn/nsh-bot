# NeoChatPlatform

Multi-phase AI conversation platform starting with Zalo OA (Vietnamese messaging platform). Phase 1 focuses on building a production-ready Zalo chatbot agent.

## Architecture

```
Zalo → Webhook (FastAPI) → RabbitMQ (conversation.process) → Conversation Worker → RabbitMQ (outbound.send) → Outbound Worker → Zalo API
```

### Components

- **Webhook API**: FastAPI service receiving Zalo webhooks, response < 200ms
- **Conversation Worker**: Processes messages through LLM agent + tools
- **Outbound Worker**: Sends messages to Zalo API with retry logic
- **PostgreSQL**: Stores conversations, messages, tool calls, delivery attempts, prompts
- **Redis**: Message deduplication, caching
- **RabbitMQ**: Durable message queues for async processing

## Quick Start

```bash
# Install dependencies
uv sync

# Start all services
docker-compose up -d

# Run database migration
docker-compose exec api alembic upgrade head

# View logs
docker-compose logs -f api
```

## Development

```bash
# Run specific service
docker-compose up -d api

# Open shell in running container
docker-compose exec api /bin/sh
```

## Testing

### All Tests
```bash
# Run all tests (unit + integration)
uv run pytest tests/ -v

# Run only unit tests (fast, no external dependencies)
uv run pytest tests/unit/ -v

# Run only integration tests (requires Docker)
DATABASE_URL="postgresql+asyncpg://neochat:changeme@localhost:5432/neochat" \
uv run pytest tests/integration/ -v
```

### Test Infrastructure (for integration tests)
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
├── unit/                    # Unit tests with mocks (54 tests)
│   ├── conftest.py
│   ├── test_tools.py
│   ├── test_llm.py
│   ├── test_prompts.py
│   ├── test_processor.py
│   ├── test_zalo_client.py
│   ├── test_consumer.py
│   └── test_health.py
└── integration/             # Integration tests (63 tests)
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

**Total: 117 tests** (54 unit + 63 integration)

## Key Patterns

### Webhook Processing
- Always use queue (never block webhook with direct API calls)
- Deduplicate messages via Redis
- Push to `conversation.process` queue

### Outbound
- Send via `outbound.send` queue
- Retry with exponential backoff (max 3 attempts)
- Record all delivery attempts

### Agent
- Max 3 steps, max 2 tool calls
- Tool whitelist: `lookup_customer`, `get_order_status`, `create_support_ticket`, `handoff_request`
- Fallback prompts for unclear intents

## API Endpoints

Public: `POST /webhooks/zalo`, `GET /health/live`, `GET /health/ready`
Internal: conversation management, replay, prompt activation

## Phase Roadmap

1. **Phase 1** (current): Zalo Chat Agent MVP
2. **Phase 2**: Admin UI, analytics, prompt management
3. **Phase 3**: Multi-channel (Telegram, Facebook Messenger)
4. **Phase 4**: RAG/knowledge base
5. **Phase 5**: Multi-tenant, Kubernetes, A/B testing
