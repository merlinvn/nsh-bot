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
docker-compose -f docker-compose.dev.yml up -d

# Run database migration
docker-compose -f docker-compose.dev.yml exec api alembic upgrade head

# View logs
docker-compose -f docker-compose.dev.yml logs -f api
```

## Zalo OA Integration Setup

### Prerequisites

1. **Zalo OA Account** - You need a Zalo Official Account (OA)
2. **Zalo Developer Console** - Access at https://developers.zalo.me/

### Step 1: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Zalo credentials
nano .env
```

Required environment variables:

```env
# Zalo OA Configuration
ZALO_APP_ID=your_zalo_app_id          # From Zalo Developer Console
ZALO_APP_SECRET=your_zalo_app_secret  # From Zalo Developer Console
ZALO_ACCESS_TOKEN=your_access_token    # OAuth token for API calls
ZALO_WEBHOOK_SECRET=your_secret      # Verify webhook authenticity
ZALO_OA_ID=your_oa_id                 # Your OA ID

# LLM Configuration (supports Anthropic or OpenAI-compatible)
LLM_PROVIDER=openai-compat            # "anthropic" or "openai-compat"

# If LLM_PROVIDER=anthropic:
ANTHROPIC_API_KEY=sk-ant-...         # Anthropic API key
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# If LLM_PROVIDER=openai-compat (Ollama, LM Studio, LocalAI, etc.):
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3.2

# Internal API (for admin operations)
INTERNAL_API_KEY=your_internal_api_key
```

### Step 2: Start Development Environment

```bash
# Start all services (postgres, redis, rabbitmq, api, workers)
docker-compose -f docker-compose.dev.yml up -d

# Verify services are healthy
docker-compose -f docker-compose.dev.yml ps

# Run database migrations
docker-compose -f docker-compose.dev.yml exec api alembic upgrade head
```

### Step 3: Configure Zalo Webhook

1. Go to [Zalo Developer Console](https://developers.zalo.me/)
2. Select your OA application
3. Navigate to **Webhooks** section
4. Configure your webhook URL:
   ```
   https://your-domain-or-ngrok-url/webhooks/zalo
   ```
5. Set the webhook verification token (must match `ZALO_WEBHOOK_SECRET`)
6. Enable webhook events you want to receive (messages, user actions, etc.)

### Step 4: Expose Your Development Server

For local development, use ngrok:

```bash
# Install ngrok
brew install ngrok  # macOS

# Or download from https://ngrok.com/download

# Start ngrok tunnel to your API
ngrok http 8000

# Note the https URL (e.g., https://abc123.ngrok.io)
# Use this URL when configuring Zalo webhook
```

### Step 5: Verify Integration

1. **Check Health Endpoints:**
   ```bash
   curl http://localhost:8000/health/live
   # Should return: {"status":"alive"}

   curl http://localhost:8000/health/ready
   # Should return: {"status":"ready"}
   ```

2. **Send a Test Message:**
   - Open Zalo and send a message to your OA
   - The message should be received by the webhook
   - Check logs to see the flow:
   ```bash
   docker-compose -f docker-compose.dev.yml logs -f api
   docker-compose -f docker-compose.dev.yml logs -f conversation-worker
   ```

3. **Verify Database:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec postgres psql -U neochat -d neochat
   ```
   Check `conversations` and `messages` tables for received messages.

### Message Flow

```
User sends message on Zalo
         ↓
Zalo sends webhook to: POST /webhooks/zalo
         ↓
Webhook validates signature & deduplicates via Redis
         ↓
Message published to RabbitMQ: conversation.process queue
         ↓
Conversation Worker picks up message
         ↓
Worker calls LLM (Claude) with tools
         ↓
LLM processes and returns response
         ↓
Response published to: outbound.send queue
         ↓
Outbound Worker picks up outbound message
         ↓
Worker calls Zalo API to send message
         ↓
User receives reply on Zalo
```

### Available Tools (Phase 1)

| Tool | Description |
|------|-------------|
| `lookup_customer` | Find customer by phone or name |
| `get_order_status` | Check order status by order ID |
| `create_support_ticket` | Create a support ticket |
| `handoff_request` | Request human agent handoff |

### Troubleshooting

**Webhook not receiving messages:**
- Verify ngrok/public URL is accessible from Zalo
- Check Zalo developer console for webhook status
- Ensure `ZALO_WEBHOOK_SECRET` matches

**Workers not processing:**
```bash
# Check if workers are running
docker-compose -f docker-compose.dev.yml ps

# View worker logs
docker-compose -f docker-compose.dev.yml logs conversation-worker
docker-compose -f docker-compose.dev.yml logs outbound-worker
```

**Database issues:**
```bash
# Run migrations
docker-compose -f docker-compose.dev.yml exec api alembic upgrade head

# Check migrations status
docker-compose -f docker-compose.dev.yml exec api alembic current
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
