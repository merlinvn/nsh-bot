"""Pytest configuration for integration tests - uses PostgreSQL via docker-compose."""
import logging
import os
from collections.abc import AsyncGenerator
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Integration tests use PostgreSQL - must be running via docker-compose
# Ensure docker-compose -f docker-compose.test.yml up -d is running before tests
INTEGRATION_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://neochat:changeme@localhost:5432/neochat"
)


def pytest_configure(config):
    """Configure logging to handle structlog-style calls before tests run."""
    _original_log = logging.Logger._log

    def patched_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1, **kwargs):
        return _original_log(self, level, msg, args, exc_info=exc_info, extra=extra,
                           stack_info=stack_info, stacklevel=stacklevel)

    logging.Logger._log = patched_log


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create async SQLAlchemy engine with PostgreSQL for integration tests."""
    engine = create_async_engine(
        INTEGRATION_DATABASE_URL,
        echo=False,
    )

    # Create all tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after all tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(engine):
    """Clean all tables before each test to ensure isolation."""
    async with engine.begin() as conn:
        # Disable foreign key checks temporarily
        await conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        # Truncate all tables in reverse dependency order
        tables = [
            "delivery_attempts",
            "tool_calls",
            "messages",
            "conversations",
            "prompts",
        ]
        for table in tables:
            try:
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            except Exception:
                pass

    yield


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
