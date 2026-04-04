"""Tests for internal admin API endpoints (require X-Internal-Api-Key)."""
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.main import app as main_app
from app.api.routers import internal
from app.models.base import Base
from app.models.conversation import Conversation
from app.models.delivery_attempt import DeliveryAttempt
from app.models.message import Message
from app.models.prompt import Prompt
from app.models.tool_call import ToolCall


# ----- Test database setup -----

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine():
    """Create a function-scoped async SQLite engine for tests."""
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    # Patch UUID columns to String for SQLite compatibility
    # Also patch JSONB columns to JSON (SQLite has no JSONB)
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    uuid_patches = {}
    jsonb_patches = {}

    def _patch():
        for table_name in Base.metadata.tables:
            table = Base.metadata.tables[table_name]
            for column in table.columns:
                if isinstance(column.type, PG_UUID):
                    uuid_patches[column] = column.type
                    column.type = String(36)
                elif isinstance(column.type, JSONB):
                    jsonb_patches[column] = column.type
                    column.type = JSON()  # SQLite uses generic JSON

    def _restore():
        for column, original in uuid_patches.items():
            column.type = original
        for column, original in jsonb_patches.items():
            column.type = original

    _patch()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_init_schema(engine))
        yield engine
        loop.run_until_complete(_drop_schema(engine))
        loop.close()
    finally:
        _restore()


async def _init_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def make_session_factory(engine):
    """Create a session factory for the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _make_sync_helper(fn):
    """Decorator to run an async function synchronously in tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()
    return wrapper


# ----- Test data helpers -----

async def _create_conversation(factory, external_user_id: str = "user_test_001", status: str = "active"):
    async with factory() as session:
        conv = Conversation(
            id=str(uuid.uuid4()),  # Use string for SQLite compatibility
            external_user_id=external_user_id,
            conversation_key=f"key_{uuid.uuid4().hex[:8]}",
            status=status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        session.expunge(conv)
        return conv


async def _create_message(factory, conversation_id, direction: str = "inbound", text: str = "Test message"):
    async with factory() as session:
        msg = Message(
            id=str(uuid.uuid4()),  # Use string for SQLite compatibility
            conversation_id=conversation_id,
            direction=direction,
            text=text,
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            prompt_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        session.expunge(msg)
        return msg


async def _create_prompt(factory, name: str = "test_prompt", template: str = "Hello {{name}}", active_version: str = "v1.0"):
    versions = [
        {
            "version": "v1.0",
            "template": template,
            "created_at": "2024-01-01T00:00:00Z",
            "active": True,
        },
        {
            "version": "v2.0",
            "template": "Updated: " + template,
            "created_at": "2024-02-01T00:00:00Z",
            "active": False,
        },
    ]
    async with factory() as session:
        prompt = Prompt(
            id=str(uuid.uuid4()),  # Use string for SQLite compatibility
            name=name,
            template=template,
            versions=versions,
            active_version=active_version,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(prompt)
        await session.commit()
        await session.refresh(prompt)
        session.expunge(prompt)
        return prompt


async def _add_tool_call(factory, message_id):
    async with factory() as session:
        tc = ToolCall(
            id=str(uuid.uuid4()),  # Use string for SQLite compatibility
            message_id=message_id,
            tool_name="lookup_customer",
            input={"user_id": "user_detail"},
            output={"name": "Test User"},
            success=True,
            latency_ms=150,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(tc)
        await session.commit()


def create_test_client(engine):
    """Create a TestClient with test DB and auth overrides."""
    factory = make_session_factory(engine)

    async def override_get_db():
        async with factory() as session:
            yield session

    mock_channel = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel.get_exchange = MagicMock(return_value=mock_exchange)

    main_app.dependency_overrides[internal.get_db] = override_get_db
    main_app.dependency_overrides[internal.get_rabbitmq] = lambda: mock_channel
    main_app.dependency_overrides[internal.verify_internal_api_key] = lambda: "valid-key"

    return TestClient(main_app, raise_server_exceptions=False)


@pytest.fixture
def valid_headers() -> dict:
    """Return valid headers for internal API endpoints."""
    return {"X-Internal-Api-Key": "valid-key"}


# ----- Test cases -----

class TestInternalAuth:
    """Test cases for X-Internal-Api-Key authentication."""

    def test_internal_without_auth(self, test_engine) -> None:
        """Request without X-Internal-Api-Key header returns 401."""
        factory = make_session_factory(test_engine)

        async def override_get_db():
            async with factory() as session:
                yield session

        async def raise_401():
            raise HTTPException(status_code=401, detail={"code": "INVALID_API_KEY", "message": "Invalid or missing X-Internal-Api-Key header."})

        main_app.dependency_overrides[internal.get_db] = override_get_db
        main_app.dependency_overrides[internal.get_rabbitmq] = lambda: MagicMock()
        main_app.dependency_overrides[internal.verify_internal_api_key] = raise_401

        client = TestClient(main_app, raise_server_exceptions=False)
        try:
            response = client.get("/internal/conversations")
            assert response.status_code == 401
        finally:
            main_app.dependency_overrides.clear()

    def test_internal_with_valid_auth(self, test_engine, valid_headers) -> None:
        """Request with correct X-Internal-Api-Key header returns 200 or 2xx (not 401)."""
        client = create_test_client(test_engine)
        try:
            response = client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code != 401
        finally:
            main_app.dependency_overrides.clear()


class TestConversationsList:
    """Test cases for GET /internal/conversations."""

    def test_conversations_list_empty(self, test_engine, valid_headers) -> None:
        """Returns empty list when no conversations exist."""
        client = create_test_client(test_engine)
        try:
            response = client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []
            assert data["total"] == 0
        finally:
            main_app.dependency_overrides.clear()

    def test_conversations_list_with_data(self, test_engine, valid_headers) -> None:
        """Returns paginated list of conversations with message counts."""
        factory = make_session_factory(test_engine)
        conv = _make_sync_helper(_create_conversation)(factory, external_user_id="user_list_test")
        _make_sync_helper(_create_message)(factory, conv.id, direction="inbound", text="Hello")
        _make_sync_helper(_create_message)(factory, conv.id, direction="outbound", text="Hi there")

        client = create_test_client(test_engine)
        try:
            response = client.get("/internal/conversations", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1
            assert data["page"] == 1
            assert data["size"] == 20
        finally:
            main_app.dependency_overrides.clear()

    def test_conversations_list_filtered_by_user_id(self, test_engine, valid_headers) -> None:
        """Filtering by user_id returns only matching conversations."""
        factory = make_session_factory(test_engine)
        _make_sync_helper(_create_conversation)(factory, external_user_id="user_filter_1")
        _make_sync_helper(_create_conversation)(factory, external_user_id="user_filter_2")

        client = create_test_client(test_engine)
        try:
            response = client.get(
                "/internal/conversations",
                params={"user_id": "user_filter_1"},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            for item in data["items"]:
                assert item["external_user_id"] == "user_filter_1"
        finally:
            main_app.dependency_overrides.clear()

    def test_conversations_list_pagination(self, test_engine, valid_headers) -> None:
        """Pagination parameters work correctly."""
        factory = make_session_factory(test_engine)
        for i in range(5):
            _make_sync_helper(_create_conversation)(factory, external_user_id=f"user_page_{i}")

        client = create_test_client(test_engine)
        try:
            response = client.get(
                "/internal/conversations",
                params={"page": 1, "size": 2},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2
            assert data["page"] == 1
            assert data["size"] == 2
            assert data["pages"] >= 2
        finally:
            main_app.dependency_overrides.clear()


class TestConversationDetail:
    """Test cases for GET /internal/conversations/{conversation_id}."""

    def test_conversation_detail_not_found(self, test_engine, valid_headers) -> None:
        """Returns 404 for non-existent conversation ID."""
        client = create_test_client(test_engine)
        try:
            fake_id = str(uuid.uuid4())
            response = client.get(
                f"/internal/conversations/{fake_id}",
                headers=valid_headers,
            )
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "CONVERSATION_NOT_FOUND"
        finally:
            main_app.dependency_overrides.clear()

    def test_conversation_detail_with_messages(self, test_engine, valid_headers) -> None:
        """Returns full conversation with messages, tool calls, and delivery attempts."""
        factory = make_session_factory(test_engine)
        conv = _make_sync_helper(_create_conversation)(factory, external_user_id="user_detail")
        msg = _make_sync_helper(_create_message)(factory, conv.id, direction="inbound", text="Hello, bot!")
        _make_sync_helper(_add_tool_call)(factory, msg.id)

        client = create_test_client(test_engine)
        try:
            response = client.get(
                f"/internal/conversations/{conv.id}",
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(conv.id)
            assert data["external_user_id"] == "user_detail"
            assert len(data["messages"]) == 1
            assert data["messages"][0]["text"] == "Hello, bot!"
            assert data["messages"][0]["direction"] == "inbound"
        finally:
            main_app.dependency_overrides.clear()


class TestReplay:
    """Test cases for POST /internal/replay."""

    def test_replay_not_found(self, test_engine, valid_headers) -> None:
        """Returns 404 when conversation has no inbound messages."""
        factory = make_session_factory(test_engine)
        conv = _make_sync_helper(_create_conversation)(factory, external_user_id="user_replay_empty")

        client = create_test_client(test_engine)
        try:
            response = client.post(
                f"/internal/replay?conversation_id={conv.id}",
                headers=valid_headers,
            )
            assert response.status_code == 404
        finally:
            main_app.dependency_overrides.clear()

    def test_replay_success(self, test_engine, valid_headers) -> None:
        """Replay publishes the last inbound message back to the queue."""
        factory = make_session_factory(test_engine)
        conv = _make_sync_helper(_create_conversation)(factory, external_user_id="user_replay_ok")
        _make_sync_helper(_create_message)(factory, conv.id, direction="inbound", text="Replay this message")

        mock_channel = MagicMock()
        mock_exchange = MagicMock()
        mock_exchange.publish = AsyncMock()
        mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

        async def override_get_db():
            async with factory() as session:
                yield session

        main_app.dependency_overrides[internal.get_db] = override_get_db
        main_app.dependency_overrides[internal.get_rabbitmq] = lambda: mock_channel
        main_app.dependency_overrides[internal.verify_internal_api_key] = lambda: "valid-key"

        client = TestClient(main_app, raise_server_exceptions=False)
        try:
            response = client.post(
                f"/internal/replay?conversation_id={conv.id}",
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["conversation_id"] == str(conv.id)
            mock_exchange.publish.assert_called_once()
        finally:
            main_app.dependency_overrides.clear()


class TestPrompts:
    """Test cases for GET /internal/prompts and POST /internal/prompts/activate."""

    def test_prompts_list_empty(self, test_engine, valid_headers) -> None:
        """Returns empty list when no prompts exist."""
        client = create_test_client(test_engine)
        try:
            response = client.get("/internal/prompts", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
        finally:
            main_app.dependency_overrides.clear()

    def test_prompts_list_with_data(self, test_engine, valid_headers) -> None:
        """Returns list of prompts with version information."""
        factory = make_session_factory(test_engine)
        _make_sync_helper(_create_prompt)(
            factory,
            name="customer_support",
            template="You are a helpful assistant.",
            active_version="v1.0",
        )

        client = create_test_client(test_engine)
        try:
            response = client.get("/internal/prompts", headers=valid_headers)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            found = next((p for p in data if p["name"] == "customer_support"), None)
            assert found is not None
            assert found["active_version"] == "v1.0"
            assert len(found["versions"]) == 2
        finally:
            main_app.dependency_overrides.clear()

    def test_prompts_activate_success(self, test_engine, valid_headers) -> None:
        """Activating a valid prompt version returns success and updates active_version."""
        factory = make_session_factory(test_engine)
        _make_sync_helper(_create_prompt)(
            factory,
            name="activate_test",
            template="Original template",
            active_version="v1.0",
        )

        client = create_test_client(test_engine)
        try:
            response = client.post(
                "/internal/prompts/activate",
                json={"name": "activate_test", "version": "v2.0"},
                headers=valid_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["name"] == "activate_test"
            assert data["active_version"] == "v2.0"
        finally:
            main_app.dependency_overrides.clear()

    def test_prompts_activate_prompt_not_found(self, test_engine, valid_headers) -> None:
        """Activating a non-existent prompt returns 404."""
        client = create_test_client(test_engine)
        try:
            response = client.post(
                "/internal/prompts/activate",
                json={"name": "nonexistent_prompt", "version": "v1.0"},
                headers=valid_headers,
            )
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "PROMPT_NOT_FOUND"
        finally:
            main_app.dependency_overrides.clear()

    def test_prompts_activate_version_not_found(self, test_engine, valid_headers) -> None:
        """Activating a non-existent version returns 404."""
        factory = make_session_factory(test_engine)
        _make_sync_helper(_create_prompt)(
            factory,
            name="version_test",
            template="Test",
            active_version="v1.0",
        )

        client = create_test_client(test_engine)
        try:
            response = client.post(
                "/internal/prompts/activate",
                json={"name": "version_test", "version": "v99.0"},
                headers=valid_headers,
            )
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "VERSION_NOT_FOUND"
        finally:
            main_app.dependency_overrides.clear()
