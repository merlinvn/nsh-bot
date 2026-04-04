"""PostgreSQL async connection via SQLAlchemy."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
    pool_pre_ping=True,
)
_async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session."""
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for async session (for use outside request scope)."""
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Return True if the database is reachable."""
    try:
        async with _async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False
