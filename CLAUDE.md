# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NeoChatPlatform is a multi-phase AI conversation platform starting with Zalo OA (Vietnamese messaging platform). Phase 1 focuses on building a production-ready Zalo chatbot agent.

## Architecture (Phase 1)

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
docker-compose up -d

# Run specific service
docker-compose up -d api

# View logs
docker-compose logs -f api
docker-compose logs -f conversation-worker

# Run database migration
docker-compose exec api alembic upgrade head

# Open shell in running container
docker-compose exec api /bin/sh
```

## Key Patterns

### Webhook Processing
- Always use queue (never block webhook with direct API calls)
- Deduplicate messages via Redis
- Push to `conversation.process` queue

### Outbound
- Send via `outbound.send` queue
- Retry with exponential backoff (max 3 attempts)
- Log all delivery attempts

### Agent
- Max 3 steps, max 2 tool calls
- Tool whitelist: `lookup_customer`, `get_order_status`, `create_support_ticket`, `handoff_request`
- Fallback prompts for unclear intents

## Data Model

- **Conversations**: id, external_user_id, conversation_key, status, timestamps
- **Messages**: id, conversation_id, direction, text, model, latency, token_usage
- **ToolCalls**: tool_name, input, output, success, latency
- **DeliveryAttempts**: status, attempt_no, response, error
- **Prompts**: template, versions, active_version

## API Endpoints

Public: `POST /webhooks/zalo`, `GET /health/live`, `GET /health/ready`
Internal: conversation management, replay, prompt activation

## Phase Roadmap

1. **Phase 1** (current): Zalo Chat Agent MVP
2. **Phase 2**: Admin UI, analytics, prompt management
3. **Phase 3**: Multi-channel (Telegram, Facebook Messenger)
4. **Phase 4**: RAG/knowledge base
5. **Phase 5**: Multi-tenant, Kubernetes, A/B testing

## Important Notes

- Never log access tokens
- Mask PII in logs
- Validate all webhook input
- All Zalo API calls go through outbound worker (never directly from webhook)
