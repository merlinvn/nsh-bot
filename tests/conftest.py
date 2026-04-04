"""Pytest configuration and shared fixtures for all tests."""
import asyncio
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Use SQLite for tests — much faster and no external dependency
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """Create async SQLAlchemy engine with SQLite for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Register JSONB fallback for SQLite (JSONB columns become plain JSON)
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    # Override UUID type for SQLite — store as string
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy import String
    import uuid

    # Patch UUID columns to String for SQLite compatibility
    original_columns = {}

    def _patch_uuid_to_string():
        for table_name in Base.metadata.tables:
            table = Base.metadata.tables[table_name]
            for column in table.columns:
                if isinstance(column.type, PG_UUID):
                    original_type = column.type
                    column.type = String(36)
                    original_columns[column] = original_type

    def _restore_uuid():
        for column, original_type in original_columns.items():
            column.type = original_type

    _patch_uuid_to_string()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
        _restore_uuid()


@pytest_asyncio.fixture
async def session_factory(engine) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Create an async session factory bound to the test engine."""
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Create an async session for a single test."""
    async with session_factory() as session:
        yield session


# --- Conversation worker fixtures ---


@pytest.fixture
def mock_db_session():
    """Provide a mock async database session."""
    @asynccontextmanager
    async def _session():
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        yield session
    return _session


@pytest.fixture
def mock_queue_publisher():
    """Provide a mock RabbitMQ queue publisher."""
    publish_calls = []

    async def _publish(*args, **kwargs):
        publish_calls.append({"args": args, "kwargs": kwargs})

    mock_channel = AsyncMock()
    mock_channel.declare_exchange = AsyncMock()
    mock_exchange = AsyncMock()
    mock_exchange.publish = _publish
    mock_channel.declare_exchange.return_value = mock_exchange

    return mock_channel, mock_exchange, publish_calls


@pytest.fixture
def mock_llm_text_response():
    """Return a mock LLM response with text only."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockResponse:
        def __init__(self, text="Xin chào, tôi có thể giúp gì cho bạn?"):
            self.content = [MockBlock("text", text=text)]
            self.usage = MagicMock()
            self.usage.input_tokens = 100
            self.usage.output_tokens = 50

    return MockResponse


@pytest.fixture
def mock_llm_tool_call_response():
    """Return a mock LLM response with a tool call."""

    class MockBlock:
        def __init__(self, block_type: str, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockResponse:
        def __init__(self, tool_name="lookup_customer", tool_input=None, text=""):
            self.content = []
            if text:
                self.content.append(MockBlock("text", text=text))
            self.content.append(
                MockBlock(
                    "tool_use",
                    id="tc_123",
                    name=tool_name,
                    input=tool_input or {},
                )
            )
            self.usage = MagicMock()
            self.usage.input_tokens = 100
            self.usage.output_tokens = 50

    return MockResponse
