"""
Database Configuration and Session Management

Provides async SQLAlchemy engine and session factory for PostgreSQL.
Uses async connection pooling for optimal performance.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Settings, get_settings
from src.models import Base  # noqa: F401 - imported for Alembic


# Global engine and session factory (initialized on startup)
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """
    Get or create the async SQLAlchemy engine.

    Args:
        settings: Optional settings override (for testing)

    Returns:
        AsyncEngine instance
    """
    global _engine

    if _engine is None:
        if settings is None:
            settings = get_settings()

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,  # Verify connections before use
        )

    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """
    Get or create the async session factory.

    Args:
        settings: Optional settings override (for testing)

    Returns:
        async_sessionmaker instance
    """
    global _async_session_factory

    if _async_session_factory is None:
        engine = get_engine(settings)
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting database sessions in FastAPI routes.

    Yields:
        AsyncSession that is automatically closed after request

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_optional_db() -> AsyncGenerator[AsyncSession | None, None]:
    """
    Dependency for optional database sessions.

    Use for endpoints that may not always need the database.

    Yields:
        AsyncSession or None
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for optional database injection
OptionalDbSession = Annotated[AsyncSession | None, Depends(get_optional_db)]


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting database sessions outside of FastAPI routes.

    Useful for background tasks, CLI commands, and tests.

    Usage:
        async with get_db_context() as db:
            result = await db.execute(select(User))
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Initialize database connection and verify connectivity.

    Called on application startup.
    """
    engine = get_engine()

    # Test connection
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)


async def close_db() -> None:
    """
    Close database connections.

    Called on application shutdown.
    """
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


def reset_db_state() -> None:
    """
    Reset database state (for testing).

    Clears the engine and session factory so they are recreated
    with fresh settings on next access.
    """
    global _engine, _async_session_factory
    _engine = None
    _async_session_factory = None
