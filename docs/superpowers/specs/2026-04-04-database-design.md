# Database Design - NeoChatPlatform Phase 1

## Entity Relationship Overview

```
Conversations (1)───(∞) Messages (1)───(∞) ToolCalls
                              │
                              └───(∞) DeliveryAttempts

Prompts (standalone, referenced by Messages.prompt_version)
```

- `Conversations` is the root entity. A conversation groups all messages for a given user on a Zalo OA.
- `Messages` are linked to their parent `Conversation`. Each message records direction, text, model metadata, and latency.
- `ToolCalls` are linked to the `Message` that triggered them. A message may have zero, one, or many tool calls.
- `DeliveryAttempts` are linked to the `Message` they attempt to deliver. A message may have multiple delivery attempts (retry logic).
- `Prompts` is a standalone configuration table. Messages reference the prompt version used at call time.

## Base Model Mixin

```python
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """Adds a server-generated UUID primary key."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
```

All Phase 1 models inherit from `Base` and mix in `TimestampMixin` and `UUIDMixin`.

## Table Specifications

### 1. conversations

| Column             | Type                                              | Constraints                        |
|--------------------|---------------------------------------------------|------------------------------------|
| id                 | UUID                                              | PK, server-generated               |
| external_user_id   | VARCHAR(128)                                      | NOT NULL                           |
| conversation_key   | VARCHAR(256)                                      | NOT NULL, UNIQUE                   |
| status             | VARCHAR(16)                                       | NOT NULL, DEFAULT 'active'         |
| created_at         | TIMESTAMP WITH TIME ZONE                          | NOT NULL, server default           |
| updated_at         | TIMESTAMP WITH TIME ZONE                          | NOT NULL, server default + update  |

**Status enum values**: `active`, `closed`

```python
import enum


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class Conversation(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "conversations"

    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    status: Mapped[ConversationStatus] = mapped_column(
        String(16),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
```

### 2. messages

| Column          | Type                         | Constraints                                       |
|-----------------|------------------------------|---------------------------------------------------|
| id              | UUID                         | PK, server-generated                              |
| conversation_id | UUID                         | FK → conversations.id, NOT NULL, ON DELETE CASCADE |
| direction       | VARCHAR(16)                  | NOT NULL                                          |
| text            | TEXT                         | NOT NULL                                          |
| model           | VARCHAR(64)                  | NULLABLE                                          |
| latency_ms      | INTEGER                      | NULLABLE                                          |
| token_usage     | JSONB                        | NULLABLE                                          |
| message_id      | VARCHAR(128)                 | NOT NULL (Zalo's original message_id for dedup)  |
| prompt_version  | VARCHAR(32)                  | NOT NULL                                          |
| created_at      | TIMESTAMP WITH TIME ZONE     | NOT NULL, server default                          |

**Direction enum values**: `inbound`, `outbound`

```python
class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Message(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[MessageDirection] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        "ToolCall", back_populates="message", cascade="all, delete-orphan"
    )
    delivery_attempts: Mapped[list["DeliveryAttempt"]] = relationship(
        "DeliveryAttempt", back_populates="message", cascade="all, delete-orphan"
    )
```

### 3. tool_calls

| Column      | Type                      | Constraints                                      |
|-------------|---------------------------|--------------------------------------------------|
| id          | UUID                      | PK, server-generated                             |
| message_id  | UUID                      | FK → messages.id, NOT NULL, ON DELETE CASCADE   |
| tool_name   | VARCHAR(64)               | NOT NULL                                         |
| input       | JSONB                     | NOT NULL                                         |
| output      | JSONB                     | NOT NULL                                         |
| success     | BOOLEAN                   | NOT NULL                                         |
| error       | TEXT                      | NULLABLE                                         |
| latency_ms  | INTEGER                   | NOT NULL                                         |
| created_at  | TIMESTAMP WITH TIME ZONE  | NOT NULL, server default                        |

```python
class ToolCall(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "tool_calls"

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="tool_calls")
```

### 4. delivery_attempts

| Column      | Type                      | Constraints                                     |
|-------------|---------------------------|------------------------------------------------|
| id          | UUID                      | PK, server-generated                            |
| message_id  | UUID                      | FK → messages.id, NOT NULL, ON DELETE CASCADE  |
| attempt_no  | INTEGER                   | NOT NULL                                        |
| status      | VARCHAR(16)               | NOT NULL                                        |
| response    | JSONB                     | NULLABLE                                        |
| error       | TEXT                      | NULLABLE                                        |
| created_at  | TIMESTAMP WITH TIME ZONE | NOT NULL, server default                       |

**Status enum values**: `pending`, `success`, `failed`

```python
class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class DeliveryAttempt(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "delivery_attempts"

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(String(16), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    message: Mapped["Message"] = relationship(
        "Message", back_populates="delivery_attempts"
    )
```

### 5. prompts

| Column           | Type                      | Constraints                                     |
|------------------|---------------------------|------------------------------------------------|
| id               | UUID                      | PK, server-generated                            |
| name             | VARCHAR(64)               | NOT NULL, UNIQUE                               |
| template         | TEXT                      | NOT NULL                                        |
| versions         | JSONB                     | NOT NULL, DEFAULT '[]'                          |
| active_version   | VARCHAR(32)               | NOT NULL                                        |
| created_at       | TIMESTAMP WITH TIME ZONE  | NOT NULL, server default                        |
| updated_at       | TIMESTAMP WITH TIME ZONE  | NOT NULL, server default + update              |

**versions JSONB structure**:
```json
[
  {
    "version": "v1.0",
    "template": "You are a helpful...",
    "created_at": "2026-04-01T00:00:00Z",
    "active": true
  }
]
```

```python
class Prompt(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "prompts"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    versions: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    active_version: Mapped[str] = mapped_column(String(32), nullable=False)
```

## Indexes

| Table             | Index Name                         | Columns / Expression                              | Type      | Purpose                                          |
|-------------------|------------------------------------|---------------------------------------------------|-----------|--------------------------------------------------|
| conversations     | ix_conversations_external_user_id | external_user_id, created_at DESC                | B-tree    | Fetch user's conversations, latest first         |
| conversations     | ix_conversations_conversation_key  | conversation_key                                   | B-tree    | Unique lookup by conversation_key (dedup)         |
| conversations     | ix_conversations_status            | status                                            | B-tree    | Filter by status (e.g., list active conversations) |
| messages          | ix_messages_conversation_created   | conversation_id, created_at                       | B-tree    | Fetch conversation history in order              |
| messages          | ix_messages_message_id             | message_id                                        | B-tree    | Deduplication check against Zalo's message_id    |
| tool_calls        | ix_tool_calls_message_id           | message_id                                        | B-tree    | Find all tool calls for a message                |
| delivery_attempts | ix_delivery_attempts_message_id    | message_id                                        | B-tree    | Find all delivery attempts for a message         |
| delivery_attempts | ix_delivery_attempts_status       | status                                            | B-tree    | Find messages stuck in pending/failed state      |
| prompts           | ix_prompts_name                    | name                                              | B-tree    | Unique lookup by prompt name                     |

```python
from sqlalchemy import Index

# On Conversation
__table_args__ = (
    Index("ix_conversations_external_user_id", "external_user_id", "created_at"),
    Index("ix_conversations_conversation_key", "conversation_key"),
    Index("ix_conversations_status", "status"),
)

# On Message
__table_args__ = (
    Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    Index("ix_messages_message_id", "message_id"),
)
```

### Index Rationale

- `(external_user_id, created_at DESC)` on `conversations` — supports the common query "get all conversations for this user, newest first".
- `conversation_key` unique index — enables fast dedup lookups before creating new conversations.
- `(conversation_id, created_at)` on `messages` — supports fetching full conversation history in chronological order.
- `message_id` on `messages` — enables the Redis-free fallback dedup path (though primary dedup is in Redis at the webhook layer).
- `status` on `delivery_attempts` — enables the outbound worker to efficiently poll for stuck messages.

## Alembic Migration Strategy

### Single Initial Migration

A single migration `001_initial_schema.py` creates all tables, indexes, constraints, and enums in dependency order. No partial or incremental migrations for Phase 1.

```
migrations/
  versions/
    001_initial_schema.py
```

### Migration Order

1. Create enum types (`conversation_status`, `message_direction`, `delivery_status`)
2. Create `prompts` table (no FK dependencies)
3. Create `conversations` table
4. Create `messages` table
5. Create `tool_calls` table
6. Create `delivery_attempts` table
7. Create all indexes

### Example Migration Skeleton

```python
"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enums
    op.execute("CREATE TYPE conversation_status AS ENUM ('active', 'closed')")
    op.execute("CREATE TYPE message_direction AS ENUM ('inbound', 'outbound')")
    op.execute("CREATE TYPE delivery_status AS ENUM ('pending', 'success', 'failed')")

    # 2. prompts (no FKs)
    op.create_table(
        "prompts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("versions", JSONB(), nullable=False, server_default="[]"),
        sa.Column("active_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_prompts_name", "prompts", ["name"])

    # 3. conversations
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id", sa.String(128), nullable=False),
        sa.Column("conversation_key", sa.String(256), nullable=False),
        sa.Column("status", sa.Enum("active", "closed", name="conversation_status"), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_key"),
    )
    op.create_index("ix_conversations_external_user_id", "conversations", ["external_user_id", "created_at"])
    op.create_index("ix_conversations_status", "conversations", ["status"])

    # 4. messages
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.Enum("inbound", "outbound", name="message_direction"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", JSONB(), nullable=True),
        sa.Column("message_id", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_index("ix_messages_message_id", "messages", ["message_id"])

    # 5. tool_calls
    op.create_table(
        "tool_calls",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("output", JSONB(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_message_id", "tool_calls", ["message_id"])

    # 6. delivery_attempts
    op.create_table(
        "delivery_attempts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "success", "failed", name="delivery_status"), nullable=False),
        sa.Column("response", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_attempts_message_id", "delivery_attempts", ["message_id"])
    op.create_index("ix_delivery_attempts_status", "delivery_attempts", ["status"])


def downgrade() -> None:
    op.drop_table("delivery_attempts")
    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("prompts")
    op.execute("DROP TYPE delivery_status")
    op.execute("DROP TYPE message_direction")
    op.execute("DROP TYPE conversation_status")
```

## Session Management

### Scoped Session Pattern

Use SQLAlchemy's `scoped_session` with a session factory, managed via FastAPI's dependency injection.

```python
# app/db/session.py
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base


DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,        # Verify connection health before checkout
    pool_recycle=3600,         # Recycle connections after 1 hour
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a session, ensures rollback on error."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for use outside the request cycle (workers)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Usage in FastAPI (Webhook API)

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()
get_db = session.get_db  # from above


@router.post("/webhooks/zalo")
async def handle_zalo_webhook(
    payload: ZaloWebhookPayload,
    db: Session = Depends(get_db),
):
    # FastAPI automatically commits on success or rolls back on exception
    message = Message(
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        text=payload.text,
        message_id=payload.message_id,
        prompt_version="v1.0",
    )
    db.add(message)
    # No explicit commit needed — Depends(get_db) auto-commits on success
    return {"status": "queued"}
```

### Usage in Workers

Workers run outside the FastAPI request lifecycle. Use the context manager:

```python
# In conversation_worker.py or outbound_worker.py
from app.db.session import get_db_context


def process_message(message_data: dict) -> None:
    with get_db_context() as db:
        # Query and update within the same session
        msg = db.query(Message).filter(Message.id == message_data["id"]).first()
        msg.direction = MessageDirection.OUTBOUND
        # Context exit commits; exception causes rollback
```

### Key Principles

1. **Short transactions** — Webhook handler opens a session, persists the inbound message, and closes. No long-lived transactions.
2. **Pool pre-ping** — `pool_pre_ping=True` prevents "connection dead" errors after DB restarts.
3. **Autoflush=False** — Disables auto-flush so explicit `db.commit()` / context-exit commits are the only commit points. Avoids implicit flush surprises.
4. **ON DELETE CASCADE** — All FK relationships cascade deletes. If a `Message` is deleted, its `ToolCalls` and `DeliveryAttempts` are automatically removed. `Conversation` cascade reaches `Messages` as well.
5. **Scoped session per request** — FastAPI `Depends(get_db)` creates a new session per HTTP request. Workers use `get_db_context()` for each message they process.
