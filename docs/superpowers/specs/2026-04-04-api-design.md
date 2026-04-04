# API Design - NeoChatPlatform Phase 1

## Endpoint Specifications

### Public Endpoints

#### POST /webhooks/zalo

Receives inbound messages from Zalo. Must respond in < 200ms.

**Request**

- Headers:
  - `X-Zalo-Signature` (required): HMAC-SHA256 signature for webhook verification
  - `Content-Type: application/json`
- Body:
  ```json
  {
    "event_name": "send_message",
    "sender": {
      "id": "string"
    },
    "recipient": {
      "id": "string"
    },
    "message": {
      "message_id": "string",
      "text": "string",
      "attachments": []
    },
    "timestamp": 1234567890
  }
  ```

**Response**

- `200 OK` — message accepted
  ```json
  { "success": true }
  ```
- `400 Bad Request` — invalid payload
- `401 Unauthorized` — invalid signature
- `429 Too Many Requests` — rate limited (Zalo retry scenario)

**Behavior**

1. Verify `X-Zalo-Signature` using HMAC-SHA256 with Zalo webhook secret
2. Parse body extracting `sender.id` (user_id), `message.message_id`, `message.text`
3. Check Redis for `message_id` (TTL 24h); if exists, return `{"success": true}` immediately (dedupe)
4. Store `message_id` in Redis with 24h TTL
5. Publish to RabbitMQ queue `conversation.process`:
   ```json
   {
     "message_id": "string",
     "user_id": "string",
     "text": "string",
     "timestamp": 1234567890,
     "received_at": "ISO8601"
   }
   ```
6. Return `{"success": true}` immediately

**Logging:** Log full inbound payload (sender, recipient, message, timestamp). Never log `X-Zalo-Signature` token.

---

#### GET /health/live

Liveness probe — no dependency checks.

**Response**

- `200 OK`
  ```json
  { "status": "alive" }
  ```

---

#### GET /health/ready

Readiness probe — verifies all infrastructure dependencies.

**Response**

- `200 OK` — all checks pass
  ```json
  {
    "status": "ready",
    "checks": {
      "database": "ok",
      "redis": "ok",
      "rabbitmq": "ok"
    }
  }
  ```
- `503 Service Unavailable` — one or more checks fail
  ```json
  {
    "status": "not_ready",
    "checks": {
      "database": "ok",
      "redis": "error: connection refused",
      "rabbitmq": "ok"
    }
  }
  ```

---

### Internal Endpoints

All internal endpoints require `X-Internal-Api-Key` header (Bearer token). Rate limited to 100 req/min per IP.

#### GET /internal/conversations

Paginated list of conversations with optional filters.

**Query Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `limit` | int | 50 | Items per page (max 100) |
| `user_id` | string | null | Filter by external user ID |
| `status` | string | null | Filter by status: `active`, `closed`, `pending` |

**Response**

- `200 OK`
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "external_user_id": "string",
        "conversation_key": "string",
        "status": "active",
        "message_count": 5,
        "created_at": "ISO8601",
        "updated_at": "ISO8601"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 50,
      "total": 123,
      "total_pages": 3
    }
  }
  ```

---

#### GET /internal/conversations/{id}

Full conversation detail including messages, tool calls, and delivery attempts.

**Path Parameters**

- `id` (uuid): Conversation ID

**Response**

- `200 OK`
  ```json
  {
    "id": "uuid",
    "external_user_id": "string",
    "conversation_key": "string",
    "status": "active",
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "messages": [
      {
        "id": "uuid",
        "direction": "inbound",
        "text": "string",
        "model": "claude-3-5-sonnet",
        "latency_ms": 1250,
        "token_usage": {
          "input_tokens": 500,
          "output_tokens": 120
        },
        "tool_calls": [
          {
            "id": "uuid",
            "tool_name": "lookup_customer",
            "input": { "user_id": "string" },
            "output": { "name": "Nguyen Van A", "tier": "gold" },
            "success": true,
            "latency_ms": 320,
            "called_at": "ISO8601"
          }
        ],
        "created_at": "ISO8601"
      },
      {
        "id": "uuid",
        "direction": "outbound",
        "text": "Xin chao Nguyen Van A!",
        "model": "claude-3-5-sonnet",
        "latency_ms": 890,
        "token_usage": {
          "input_tokens": 620,
          "output_tokens": 45
        },
        "tool_calls": [],
        "delivery_attempts": [
          {
            "attempt_no": 1,
            "status": "delivered",
            "response": { "mid": "zalo_msg_id" },
            "error": null,
            "attempted_at": "ISO8601"
          }
        ],
        "created_at": "ISO8601"
      }
    ]
  }
  ```
- `404 Not Found`
  ```json
  { "detail": "Conversation not found" }
  ```

---

#### POST /internal/replay

Re-queues a conversation for reprocessing. Clears existing agent state and re-processes from the last user message.

**Request Body**

```json
{
  "conversation_id": "uuid"
}
```

**Response**

- `202 Accepted`
  ```json
  {
    "message": "Conversation re-queued for reprocessing",
    "conversation_id": "uuid",
    "message_id": "uuid"
  }
  ```
- `404 Not Found`
  ```json
  { "detail": "Conversation not found" }
  ```
- `400 Bad Request` — no messages to replay
  ```json
  { "detail": "No messages to replay" }
  ```

**Behavior**

1. Fetch conversation and its messages
2. Extract the last inbound message
3. Re-publish to `conversation.process` queue
4. Return 202 with new message ID for tracking

---

#### GET /internal/prompts

List all prompts with their versions.

**Response**

- `200 OK`
  ```json
  {
    "prompts": [
      {
        "name": "system",
        "description": "Main system prompt for the agent",
        "versions": [
          { "version": 1, "active": false, "created_at": "ISO8601", "created_by": "admin" },
          { "version": 2, "active": true, "created_at": "ISO8601", "created_by": "admin" }
        ],
        "active_version": 2,
        "active_template": "You are a helpful Zalo OA assistant..."
      },
      {
        "name": "tool_policy",
        "description": "Tool calling guidelines",
        "versions": [
          { "version": 1, "active": true, "created_at": "ISO8601", "created_by": "admin" }
        ],
        "active_version": 1,
        "active_template": "Only use tools when necessary..."
      },
      {
        "name": "fallback",
        "description": "Fallback response for unclear intents",
        "versions": [
          { "version": 1, "active": true, "created_at": "ISO8601", "created_by": "admin" }
        ],
        "active_version": 1,
        "active_template": "Xin loi, toi chua hieu ro y cua ban..."
      }
    ]
  }
  ```

---

#### POST /internal/prompts/activate

Activate a specific version of a prompt.

**Request Body**

```json
{
  "prompt_name": "system",
  "version": 3
}
```

**Response**

- `200 OK`
  ```json
  {
    "message": "Prompt version activated",
    "prompt_name": "system",
    "version": 3,
    "previous_version": 2
  }
  ```
- `404 Not Found` — prompt name or version not found
  ```json
  { "detail": "Prompt 'system' version 3 not found" }
  ```
- `400 Bad Request` — already active
  ```json
  { "detail": "Version 3 is already the active version" }
  ```

---

## Webhook Verification

Zalo webhooks are signed using HMAC-SHA256. The signature is computed over the raw request body.

**Algorithm (pseudocode):**

```
signature = HMAC-SHA256(webhook_secret, raw_body)
expected = hex(signature)
received = request.headers["X-Zalo-Signature"]
if not constant_time_compare(expected, received):
    return 401 Unauthorized
```

**Security Notes:**

- Webhook secret is read from `config.zalo_webhook_secret`
- Use constant-time comparison (`hmac.compare_digest`) to prevent timing attacks
- Signature header is never logged
- Raw body must be used (not parsed-then-serialized)

---

## Middleware

### Request ID Middleware (`X-Request-ID`)

- Generates a UUID v4 for every request if not provided
- Adds `X-Request-ID` to response headers
- Includes request ID in all log entries

### Structured Logging (JSON)

All logs are JSON-formatted with consistent fields:

```json
{
  "timestamp": "ISO8601",
  "level": "INFO",
  "request_id": "uuid",
  "service": "api",
  "message": "Webhook received",
  "path": "/webhooks/zalo",
  "method": "POST",
  "status_code": 200,
  "latency_ms": 45
}
```

Additional context fields are added per endpoint:
- Webhook: `user_id`, `message_id`, `deduped` (bool)
- Internal: `endpoint`, `filters`, `pagination`

### CORS Configuration

- Allowed origins: configured via `config.cors_origins` (env var `CORS_ORIGINS`)
- Allowed methods: `GET`, `POST`, `OPTIONS`
- Allowed headers: `Content-Type`, `X-Request-ID`, `X-Internal-Api-Key`
- Max age: 600 seconds

### PII Masking

All log messages and structured log fields are scanned for PII patterns before output:
- Phone numbers: `+84XXXXXXXXX` → `+84********`
- Email addresses: `user@domain.com` → `u***@d***.com`
- Zalo user IDs are NOT masked (internal identifiers)

---

## Error Handling

### Custom Exception Classes

| Exception | HTTP Status | Error Code | Description |
|-----------|-------------|------------|-------------|
| `WebhookSignatureError` | 401 | `INVALID_SIGNATURE` | Zalo signature mismatch |
| `DuplicateMessageError` | 200 | (silent) | Duplicate message, returns success |
| `ConversationNotFoundError` | 404 | `CONVERSATION_NOT_FOUND` | Conversation ID not found |
| `PromptNotFoundError` | 404 | `PROMPT_NOT_FOUND` | Prompt name or version not found |
| `QueuePublishError` | 503 | `QUEUE_UNAVAILABLE` | RabbitMQ publish failed |
| `RateLimitExceededError` | 429 | `RATE_LIMIT_EXCEEDED` | 100 req/min exceeded |

### Global Exception Handler

All unhandled exceptions return:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred",
    "request_id": "uuid"
  }
}
```

5xx errors do not include the internal error message to prevent information leakage.

### Validation Errors (422)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "conversation_id",
        "message": "Invalid UUID format"
      }
    ],
    "request_id": "uuid"
  }
}
```

---

## Rate Limiting

### Strategy

- **Library:** `slowapi` (built on `limits` library)
- **Storage:** Redis backend for distributed rate limiting across multiple API instances
- **Limit:** 100 requests per minute per IP address
- **Scope:** All `/internal/*` endpoints
- **Public endpoints:** Exempt (Zalo must be able to send webhooks at any rate)

### Response on Limit Exceeded (429)

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Limit: 100 requests per minute.",
    "retry_after": 30
  }
}
```

Headers:
- `Retry-After: 30`
- `X-RateLimit-Limit: 100`
- `X-RateLimit-Remaining: 0`
- `X-RateLimit-Reset: 1700000000`

---

## Pydantic Schemas

### Webhook Schemas

```python
class ZaloMessageContent(BaseModel):
    message_id: str
    text: str | None = None
    attachments: list = []

class ZaloSender(BaseModel):
    id: str

class ZaloRecipient(BaseModel):
    id: str

class ZaloWebhookPayload(BaseModel):
    event_name: str
    sender: ZaloSender
    recipient: ZaloRecipient
    message: ZaloMessageContent
    timestamp: int

    model_config = {"extra": "allow"}

class WebhookSuccessResponse(BaseModel):
    success: Literal[True] = True
```

### Health Schemas

```python
class HealthCheck(BaseModel):
    status: Literal["alive"]

class HealthCheckResult(BaseModel):
    database: Literal["ok"] | str
    redis: Literal["ok"] | str
    rabbitmq: Literal["ok"] | str

class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: HealthCheckResult
```

### Conversation Schemas

```python
class ConversationSummary(BaseModel):
    id: UUID
    external_user_id: str
    conversation_key: str
    status: Literal["active", "closed", "pending"]
    message_count: int
    created_at: datetime
    updated_at: datetime

class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int

class ConversationListResponse(BaseModel):
    data: list[ConversationSummary]
    pagination: PaginationMeta

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int

class ToolCallRecord(BaseModel):
    id: UUID
    tool_name: Literal["lookup_customer", "get_order_status", "create_support_ticket", "handoff_request"]
    input: dict
    output: dict | None
    success: bool
    latency_ms: int
    called_at: datetime

class DeliveryAttempt(BaseModel):
    attempt_no: int
    status: Literal["pending", "delivered", "failed"]
    response: dict | None
    error: str | None
    attempted_at: datetime

class MessageDetail(BaseModel):
    id: UUID
    direction: Literal["inbound", "outbound"]
    text: str
    model: str | None
    latency_ms: int | None
    token_usage: TokenUsage | None
    tool_calls: list[ToolCallRecord]
    delivery_attempts: list[DeliveryAttempt] | None
    created_at: datetime

class ConversationDetailResponse(BaseModel):
    id: UUID
    external_user_id: str
    conversation_key: str
    status: Literal["active", "closed", "pending"]
    created_at: datetime
    updated_at: datetime
    messages: list[MessageDetail]
```

### Internal/Admin Schemas

```python
class ReplayRequest(BaseModel):
    conversation_id: UUID

class ReplayResponse(BaseModel):
    message: str
    conversation_id: UUID
    message_id: UUID

class PromptVersion(BaseModel):
    version: int
    active: bool
    created_at: datetime
    created_by: str

class PromptDetail(BaseModel):
    name: str
    description: str
    versions: list[PromptVersion]
    active_version: int
    active_template: str

class PromptListResponse(BaseModel):
    prompts: list[PromptDetail]

class ActivatePromptRequest(BaseModel):
    prompt_name: str
    version: int

class ActivatePromptResponse(BaseModel):
    message: str
    prompt_name: str
    version: int
    previous_version: int | None
```

### Error Schemas

```python
class ErrorDetail(BaseModel):
    field: str
    message: str

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
    request_id: UUID | None = None
    retry_after: int | None = None

class ErrorResponse(BaseModel):
    error: ErrorBody
```

---

## Configuration

Environment variables consumed by the API:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ZALO_WEBHOOK_SECRET` | str | required | Zalo webhook HMAC secret |
| `ZALO_OA_ID` | str | required | Zalo Official Account ID |
| `DATABASE_URL` | str | required | PostgreSQL connection string |
| `REDIS_URL` | str | required | Redis connection string |
| `RABBITMQ_URL` | str | required | RabbitMQ connection string |
| `INTERNAL_API_KEY` | str | required | Bearer token for internal endpoints |
| `CORS_ORIGINS` | str | `*` | Comma-separated list of allowed origins |
| `LOG_LEVEL` | str | `INFO` | Logging level |
| `RATE_LIMIT_PER_MINUTE` | int | `100` | Rate limit for internal endpoints |

---

## Project Structure

```
src/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, CORS, exception handlers
│   ├── config.py            # Settings from env vars
│   ├── middleware.py        # Request ID, structured logging, PII masking
│   ├── dependencies.py      # DB, Redis, RabbitMQ, auth dependencies
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── webhooks.py       # POST /webhooks/zalo
│   │   ├── health.py         # GET /health/live, GET /health/ready
│   │   └── internal.py       # All /internal/* endpoints
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── webhook.py        # Zalo payload, response schemas
│   │   ├── health.py         # Health check schemas
│   │   ├── conversation.py   # Conversation list/detail schemas
│   │   ├── prompt.py         # Prompt schemas
│   │   └── errors.py         # Error schemas
│   └── services/
│       ├── __init__.py
│       ├── signature.py      # Zalo HMAC signature verification
│       ├── dedup.py          # Redis dedup service
│       └── queue.py          # RabbitMQ publisher
└── tests/
    └── api/
        ├── conftest.py
        ├── test_webhooks.py
        ├── test_health.py
        └── test_internal.py
```
