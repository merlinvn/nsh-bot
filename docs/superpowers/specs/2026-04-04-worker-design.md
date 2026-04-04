# Worker Design - NeoChatPlatform Phase 1

## Overview

Two standalone Python workers consume from RabbitMQ queues, process messages asynchronously, and produce output to downstream queues or external APIs. Both workers run as long-running processes managed by Docker Compose.

```
RabbitMQ (conversation.process)
        ↓
Conversation Worker
        ↓
RabbitMQ (outbound.send)
        ↓
Outbound Worker
        ↓
Zalo API
```

---

## Conversation Worker

### Processing Flow

```
1. Consume message from `conversation.process` queue
   - auto_ack=False (manual ack after full processing)
   - Queue is durable, messages survive broker restart

2. Parse job payload:
   {
     "message_id": str,        # Zalo message ID (dedup key)
     "external_user_id": str,   # Zalo user ID
     "text": str,              # inbound message text
     "received_at": str,       # ISO timestamp
     "correlation_id": str,   # for tracing across workers
     "zalo_message_id": str    # for delivery tracking
   }

3. Load or create conversation:
   - Query DB by external_user_id
   - If not found → create new conversation record
   - conversation_key = f"zalo:{external_user_id}"

4. Save inbound message to DB:
   - direction = "inbound"
   - conversation_id = loaded/created conversation.id

5. Build prompt:
   - Fetch active system prompt from DB (prompts table, active_version)
   - Append last N messages from conversation history (N = context_window, default 10)
   - Include tool descriptions from tool policy prompt

6. Call LLM (Anthropic Claude API)

7. Parse response:
   - If text only: use as final response text
   - If tool calls present: execute up to 2 tools, then re-call LLM with results

8. Save outbound message to DB:
   - direction = "outbound"
   - Include model name, latency, token_usage

9. Publish to outbound.send queue:
   {
     "message_id": str,          # original Zalo message ID
     "external_user_id": str,
     "text": str,                # final response text
     "correlation_id": str,
     "conversation_id": int,
     "attempt_no": 1
   }

10. Acknowledge message on success, nack with requeue on transient errors
```

### LLM Integration

- **SDK**: Anthropic Python SDK (`anthropic` package)
- **Model**: `claude-sonnet-4-20250514` (configurable via env `ANTHROPIC_MODEL`)
- **Timeout**: 15 seconds total (enforced via `timeout=15` on the API call)
- **Max tokens**: 1024 for response (configurable)
- **Preloading**: System prompt fetched from DB at startup and cached; refreshed every 5 minutes or on cache miss

#### API Call Shape

```python
response = client.messages.create(
    model=model_name,
    max_tokens=1024,
    system=system_prompt_text,
    messages=conversation_history,
    tools=tool_descriptions,  # if tools enabled
    timeout=15,
)
```

- **Token usage** captured from `response.usage` (input + output tokens)
- **Latency** measured as `time.time()` delta from call start to response received
- Both stored on the outbound message record

### Tool Calling

Tools are defined as Anthropic tool schemas and executed by the worker.

#### Available Tools

| Tool | Purpose | Timeout |
|------|---------|---------|
| `lookup_customer` | Find customer by phone/name | 5s |
| `get_order_status` | Query order by order_id | 5s |
| `create_support_ticket` | Open a support ticket | 5s |
| `handoff_request` | Flag conversation for human handoff | 3s |

#### Tool Execution Flow

```
1. LLM returns response with tool_use blocks
2. Validate tool name is in whitelist (reject others defensively)
3. For each tool call (max 2):
   a. Log tool call start (tool_name, input, correlation_id)
   b. Execute tool with timeout
   c. Log tool call result (output, success, latency)
   d. Store tool_call record in DB (tool_name, input, output, success, latency)
4. Re-call LLM with original messages + tool results appended as tool result content blocks
5. Use final text response
```

#### Tool Error Handling

- **Timeout**: Log as failed tool call, return error message to LLM, continue
- **Exception**: Log error, return error message to LLM, continue
- **Unknown tool**: Reject and return error; LLM should respond without that tool
- **Max tool calls exceeded**: Stop executing, return error to LLM

### Error Handling

| Error Type | Action |
|------------|--------|
| LLM API error (5xx, network) | Nack + requeue (transient) |
| LLM API error (4xx, bad request) | Ack, publish fallback to outbound.send |
| Tool timeout | Execute remaining tools, continue |
| Tool exception | Execute remaining tools, continue |
| DB error | Nack + requeue (transient) |
| Queue publish error | Nack + requeue (transient) |
| Unknown exception | Log, ack, publish fallback |

**Fallback response**: When a non-transient error occurs, the worker publishes a predefined fallback text to `outbound.send`:

> "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau ít phút."

The fallback is stored in the prompts table (`fallback_prompt` template) and fetched at startup.

---

## Outbound Worker

### Processing Flow

```
1. Consume message from `outbound.send` queue
   - auto_ack=False
   - Durable queue

2. Parse job payload:
   {
     "message_id": str,           # original Zalo message ID
     "external_user_id": str,      # Zalo user ID
     "text": str,                 # response text to send
     "correlation_id": str,
     "conversation_id": int,
     "attempt_no": int            # starts at 1
   }

3. Get Zalo access token:
   - From config/env: ZALO_ACCESS_TOKEN
   - Token refreshed via separate job (Phase 2)

4. Call ZaloClient.send_text(user_id=external_user_id, text=text, token=access_token)

5. On success:
   a. Save delivery_attempt record (status="success", attempt_no, response)
   b. Ack message
   c. Update conversation status to "resolved" if applicable

6. On failure → retry logic (see Retry Strategy)

7. After max retries exhausted → dead letter handling
```

### Retry Strategy

Retry is triggered on transient failures. The backoff is exponential: `2^attempt_no` seconds.

| Attempt | Delay Before Retry |
|---------|-------------------|
| 1 → 2 | 2 seconds |
| 2 → 3 | 4 seconds |
| 3 (final) | — |

#### Error Classification

| Error | Type | Action |
|-------|------|--------|
| HTTP 429 (rate limit) | Transient | Backoff + retry |
| HTTP 401/403 (invalid/expired token) | Non-transient | Flag for admin, max retries then DLQ |
| HTTP 500/502/503/504 (server error) | Transient | Backoff + retry |
| HTTP 400 (bad request) | Non-transient | Max retries then DLQ |
| Connection timeout / network error | Transient | Backoff + retry |
| Unknown exception | Transient | Backoff + retry |

#### Retry Execution

- Use RabbitMQ's `basic_nack` with `requeue=True` for transient errors
- Set `x-delay` header or publish to a retry queue with TTL
- Track attempt count in message headers or payload
- On attempt_no >= 3 and transient error → dead letter

### Dead Letter Handling

Messages that exhaust all retries are routed to the dead-letter queue (`outbound.send.dlq`).

```
Dead Letter Queue: outbound.send.dlq
Exchange: neochat.dlx
Routing Key: outbound.send.dead
```

**DLQ Message Contents** (same as original + metadata):

```json
{
  "original_payload": { ... },
  "final_error": str,
  "total_attempts": int,
  "first_attempt_at": str,
  "last_attempt_at": str,
  "correlation_id": str
}
```

**Actions on DLQ entry**:
1. Save delivery_attempt record with `status="failed"`, include error message
2. Ack the original message (remove from `outbound.send`)
3. Log warning with full context (correlation_id, error, user_id — PII masked)
4. Alert via structured log (slack/ops alert in Phase 2)

---

## Shared Worker Concerns

### Graceful Shutdown

Both workers handle `SIGTERM` and `SIGINT`:

1. Stop consuming new messages from the queue
2. Finish processing any in-flight message (with a 30-second timeout)
3. Close database connections
4. Close RabbitMQ channel and connection
5. Exit cleanly

```python
import signal

shutdown_event = threading.Event()

def handle_signal(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    shutdown_event.set()

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
```

### Structured Logging

All log output is structured JSON to stdout, consumed by the Docker logging driver.

**Required log fields per message**:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC |
| `level` | INFO, WARNING, ERROR, DEBUG |
| `service` | `conversation-worker` or `outbound-worker` |
| `correlation_id` | UUID from original webhook, propagated everywhere |
| `message` | Human-readable description |
| `extra` | Dict with contextual fields (user_id masked, etc.) |

**Log events** (minimum set per worker):

*Conversation Worker*:
- `message_received` — job payload received
- `conversation_loaded` / `conversation_created`
- `inbound_message_saved`
- `llm_call_start` / `llm_call_end` (with latency, model, token usage)
- `tool_call_start` / `tool_call_end` (with tool_name, success, latency)
- `tool_call_error` (with error, tool_name)
- `response_published`
- `ack_sent` / `nack_sent` (with requeue flag)
- `fallback_triggered` (with reason)
- `error` (with exception type, traceback truncated to 500 chars)

*Outbound Worker*:
- `message_received`
- `send_attempt_start` (with attempt_no)
- `send_attempt_end` (with status, attempt_no)
- `retry_scheduled` (with attempt_no, delay_seconds)
- `rate_limit_hit` (with retry_after if available)
- `token_invalid` (flagged for admin)
- `delivery_success`
- `delivery_failed` (with total_attempts, final_error)
- `dlq_published`
- `ack_sent` / `nack_sent`
- `error`

### Health Check Endpoint

Each worker exposes an HTTP health endpoint on a configurable port (default `8080` for conversation-worker, `8081` for outbound-worker):

```
GET /health/live   → 200 OK if process is alive
GET /health/ready  → 200 OK if DB + RabbitMQ connections are healthy
```

The `ready` endpoint pings:
- PostgreSQL connection pool
- RabbitMQ channel (via `channel.is_open`)

Response body: `{"status": "ok", "service": "...", "checks": {...}}`

### Metrics

Workers emit metrics in Prometheus exposition format at `GET /metrics`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `worker_messages_processed_total` | Counter | `worker`, `status` (success/failure/fallback) | Total messages processed |
| `worker_processing_duration_seconds` | Histogram | `worker` | Time from consume to ack/nack |
| `worker_llm_call_duration_seconds` | Histogram | `model` | LLM API call latency |
| `worker_llm_tokens_total` | Counter | `model`, `type` (input/output) | Token usage |
| `worker_tool_calls_total` | Counter | `tool_name`, `status` (success/error) | Tool invocations |
| `worker_tool_duration_seconds` | Histogram | `tool_name` | Per-tool execution latency |
| `worker_retry_total` | Counter | `worker`, `attempt` | Retry events |
| `worker_dlq_messages_total` | Counter | `worker` | Messages sent to DLQ |
| `worker_outbound_delivery_total` | Counter | `status` (success/failed) | Zalo API delivery outcomes |

All histograms have configurable buckets (default: `[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]`).

### Project Structure

```
src/
  workers/
    conversation/
      __init__.py
      main.py          # entry point, signal handling, health/metrics servers
      consumer.py     # RabbitMQ consumer loop
      processor.py    # core processing logic
      llm.py           # Anthropic client wrapper
      tools.py         # tool registry and executors
      prompts.py       # prompt loading and caching
      models.py        # Pydantic models for job payload, DB records

    outbound/
      __init__.py
      main.py
      consumer.py
      processor.py
      zalo_client.py   # Zalo API client
      retry.py         # retry logic and backoff

    shared/
      __init__.py
      logging.py       # structured JSON logger setup
      db.py            # asyncpg / SQLAlchemy connection
      queue.py         # RabbitMQ connection/channel factory
      health.py        # health check logic
      metrics.py       # Prometheus metrics registry
```

### Configuration (Environment Variables)

| Variable | Worker | Default | Description |
|----------|--------|---------|-------------|
| `RABBITMQ_URL` | Both | `amqp://guest:guest@localhost:5672` | RabbitMQ connection string |
| `DATABASE_URL` | Both | `postgresql://...` | PostgreSQL DSN |
| `ANTHROPIC_API_KEY` | Conv | — | Anthropic API key |
| `ANTHROPIC_MODEL` | Conv | `claude-sonnet-4-20250514` | Model name |
| `ZALO_ACCESS_TOKEN` | Out | — | Zalo API access token |
| `ZALO_OA_ID` | Out | — | Zalo Official Account ID |
| `CONTEXT_WINDOW_SIZE` | Conv | `10` | Number of prior messages in prompt |
| `MAX_TOOL_CALLS` | Conv | `2` | Maximum tool calls per request |
| `LLM_TIMEOUT_SECONDS` | Conv | `15` | LLM API call timeout |
| `LOG_LEVEL` | Both | `INFO` | Logging level |
| `WORKER_PORT` | Both | `8080` / `8081` | Health/metrics HTTP port |

---

## Acceptance Criteria

- Conversation worker consumes, processes, and publishes within 15s total (LLM timeout enforced)
- Outbound worker retries up to 3 times with exponential backoff before DLQ
- No access tokens or raw PII appear in logs
- Graceful shutdown completes in-flight work within 30s
- Health endpoints return accurate status
- Prometheus metrics are exposed and scrapable
- All structured log events fire at the defined points
