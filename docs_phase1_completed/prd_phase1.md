# 🧠 **NeoChatPlatform – PRD (v1.0)**

## 1. Mục tiêu sản phẩm

### Mục tiêu ngắn hạn (Phase 1)

Xây dựng một **chatbot agent production-ready cho Zalo OA** có khả năng:

- phản hồi khách hàng tự động
- hiểu intent cơ bản
- gọi **tools nội bộ**
- xử lý qua queue (ổn định, không block webhook)
- có logging đầy đủ
- có thể vận hành thực tế với khách hàng

### Mục tiêu dài hạn

Phát triển thành **multi-channel AI conversation platform**:

- Zalo + Telegram + Facebook Messenger
- có RAG / knowledge base
- có web admin (prompt, logs, evaluation)
- multi-tenant
- analytics + optimization

---

# 2. Scope tổng thể theo phase

## Phase 1 — Zalo Chat Agent (🔥 trọng tâm)

- Zalo webhook + outbound
- agent + tool calling
- queue-based architecture
- conversation logging
- prompt versioning (basic)
- retry + delivery tracking
- Docker deploy

❌ Không có:

- RAG
- multi-channel
- web admin UI
- advanced evaluation

---

## Phase 2 — Admin & Observability

- Chat log viewer (Inbox)
- Prompt management UI
- Analytics dashboard
- Evaluation (basic)
- Audit logs

---

## Phase 3 — Multi-channel

- Telegram bot
- Facebook Messenger
- Channel abstraction layer
- Unified schema

---

## Phase 4 — RAG

- Knowledge base
- Vector DB
- Retrieval pipeline
- Document management UI

---

## Phase 5 — Scale & Enterprise

- Multi-tenant
- Kubernetes
- Prompt A/B testing
- Model routing
- Cost optimization
- Advanced evaluation

---

# 3. Phase 1 – Product Requirements (chi tiết)

## 3.1 User stories

### 1. Khách hàng

- Tôi có thể nhắn tin Zalo OA và nhận phản hồi ngay
- Tôi có thể hỏi:
  - trạng thái đơn hàng
  - thông tin cơ bản
  - yêu cầu hỗ trợ

- Tôi nhận câu trả lời nhanh, rõ ràng

### 2. Hệ thống

- Nhận webhook nhanh (< 200ms)
- Không mất message khi load cao
- Retry khi gửi tin thất bại
- Không trả lời trùng message

### 3. Dev / Ops

- Có thể xem logs hội thoại
- Có thể replay conversation
- Có thể đổi prompt (basic)

---

# 4. Functional requirements (Phase 1)

## 4.1 Zalo integration

### Inbound

- nhận webhook từ Zalo
- parse message:
  - user_id
  - text
  - message_id

- dedupe message
- push vào queue

### Outbound

- gửi text message
- retry nếu fail
- log delivery status

---

## 4.2 Conversation engine

### Features

- tạo conversation mới nếu chưa tồn tại
- lưu lịch sử message
- giới hạn context (last N messages)

---

## 4.3 Agent (LLM-based)

### Input

- user message
- recent history
- system prompt

### Output

- 1 câu trả lời text

### Behavior

- trả lời ngắn gọn
- hỏi lại nếu thiếu thông tin
- không hallucinate
- fallback nếu không hiểu

---

## 4.4 Tool calling

### Tools Phase 1

- `lookup_customer`
- `get_order_status`
- `create_support_ticket`
- `handoff_request`

### Requirements

- agent chỉ gọi tool trong whitelist
- max 2 tool calls / request
- log toàn bộ input/output
- timeout mỗi tool

---

## 4.5 Prompt system

### Required

- system prompt
- tool policy prompt
- fallback prompt

### Capabilities

- versioning
- activate version
- log prompt version used

---

## 4.6 Logging

### Must log

- inbound message
- outbound message
- tool calls
- prompt version
- model used
- latency
- errors
- delivery status

---

## 4.7 Retry & reliability

- outbound retry (max 3 lần)
- exponential backoff
- dead-letter queue
- idempotency

---

# 5. Non-functional requirements

## Performance

- webhook response < 200ms
- xử lý conversation < 2–5s

## Reliability

- không mất message
- retry outbound
- queue durable

## Scalability (phase 1)

- 100–1000 conversations/day

## Security

- không log access token
- mask PII cơ bản
- validate input

---

# 6. System design (Phase 1)

```text
Zalo
  ↓
Webhook (FastAPI)
  ↓
RabbitMQ (conversation.process)
  ↓
Conversation Worker (Agent + Tools)
  ↓
RabbitMQ (outbound.send)
  ↓
Outbound Worker
  ↓
Zalo API
```

---

# 7. Data model (core)

## Conversations

- id
- external_user_id
- conversation_key
- status
- timestamps

## Messages

- id
- conversation_id
- direction
- text
- model
- latency
- token usage

## Tool Calls

- tool_name
- input
- output
- success
- latency

## Delivery Attempts

- status
- attempt_no
- response
- error

## Prompt

- template
- versions
- active version

---

# 8. API spec (Phase 1)

## Public

- `POST /webhooks/zalo`
- `GET /health/live`
- `GET /health/ready`

## Internal

- `GET /internal/conversations`
- `GET /internal/conversations/{id}`
- `POST /internal/replay`
- `GET /internal/prompts`
- `POST /internal/prompts/activate`

---

# 9. Agent design (Phase 1)

## Pipeline

```text
User input
 → Intent router
 → Policy check
 → LLM
 → Tool call (optional)
 → Final response
```

## Constraints

- max_steps = 3
- max_tool_calls = 2
- timeout_total = 15s

## Fallback

- nếu không hiểu → hỏi lại
- nếu lỗi → fallback message

---

# 10. Prompt design

## System prompt

- vai trò chatbot CSKH
- ngắn gọn
- không bịa
- dùng tool khi cần

## Tool prompt

- không gọi tool quá mức
- validate input

## Fallback

- xin lỗi + hỏi lại

---

# 11. Metrics (Phase 1)

## Operational

- webhook latency
- queue depth
- processing time
- outbound success rate

## Product

- số hội thoại/ngày
- số message/người dùng
- fallback rate
- tool usage rate

---

# 12. Deployment

## Stack

- FastAPI
- PostgreSQL
- Redis
- RabbitMQ
- Docker Compose

## Services

- api
- conversation-worker
- outbound-worker
- postgres
- redis
- rabbitmq

---

# 13. Acceptance criteria (Phase 1)

Hệ thống được coi là **production-ready khi:**

✅ nhận webhook từ Zalo
✅ không block webhook
✅ xử lý qua queue
✅ agent trả lời đúng
✅ tool hoạt động
✅ outbound gửi thành công
✅ retry hoạt động
✅ logs đầy đủ
✅ prompt có version
✅ chạy ổn trên Docker

---

# 14. Phase 2 preview (Admin)

Sẽ thêm:

- Inbox (chat logs UI)
- Prompt Studio
- Analytics Dashboard
- Evaluation tool

---

# 15. Rủi ro & mitigation

## Rủi ro 1: Agent trả lời sai

→ fallback + hạn chế scope

## Rủi ro 2: Tool lỗi

→ retry + graceful fallback

## Rủi ro 3: Zalo rate limit

→ queue + backoff

## Rủi ro 4: duplicate webhook

→ Redis dedupe

## Rủi ro 5: token hết hạn

→ refresh token job (Phase 2)

---

# 16. Roadmap tóm tắt

```text
Phase 1 → Zalo Agent MVP (🔥)
Phase 2 → Admin + Observability
Phase 3 → Multi-channel
Phase 4 → RAG
Phase 5 → Scale
```

---

# 🔥 Kết luận

**NeoChatPlatform Phase 1 = một chatbot agent Zalo production-ready**

- dùng **FastAPI + queue + worker**
- có **tool calling có kiểm soát**
- có **logging + retry + prompt versioning**
- không RAG để giữ đơn giản
- kiến trúc đủ sạch để mở rộng sau
