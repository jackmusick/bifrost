"""
Async Redis connection factory for Bifrost cache.

Provides per-call Redis connections that work within worker threads
that have their own event loops (created via asyncio.run()).

The per-call pattern avoids event loop affinity issues that occur when
sharing async Redis connections across different event loops.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

import redis.asyncio as redis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CacheError(Exception):
    """Base exception for cache operations."""

    pass


class CacheConnectionError(CacheError):
    """Failed to connect to Redis."""

    pass


class CacheOperationError(CacheError):
    """Redis operation failed."""

    pass


def _get_redis_url() -> str:
    """Get Redis URL from settings."""
    from src.config import get_settings

    return get_settings().redis_url


@asynccontextmanager
async def get_redis() -> AsyncIterator[redis.Redis]:
    """
    Get an async Redis connection for a single operation.

    Creates a new connection for each call to avoid event loop affinity
    issues when called from worker threads with their own event loops.

    Usage:
        async with get_redis() as r:
            value = await r.get("key")

    Yields:
        redis.Redis: Async Redis client connection

    Raises:
        CacheConnectionError: If connection fails
        CacheOperationError: If operation fails
    """
    client: redis.Redis | None = None
    try:
        client = redis.from_url(
            _get_redis_url(),
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
        # Verify connection
        await client.ping()  # type: ignore[misc]
        yield client
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        raise CacheConnectionError(f"Failed to connect to Redis: {e}") from e
    except redis.RedisError as e:
        logger.error(f"Redis operation failed: {e}")
        raise CacheOperationError(f"Redis error: {e}") from e
    finally:
        if client:
            await client.aclose()


# =============================================================================
# Shared Redis Client (for API/long-running processes)
# =============================================================================

# Global Redis client for API routes (shared connection)
_shared_client: redis.Redis | None = None


async def get_shared_redis() -> redis.Redis:
    """
    Get the shared async Redis client for API routes.

    Unlike get_redis(), this reuses a single connection for the lifetime
    of the process. Use this in API routes where we're in the main event loop.

    For SDK operations in worker threads, use get_redis() instead.

    Returns:
        redis.Redis: Shared async Redis client

    Raises:
        CacheConnectionError: If connection fails
    """
    global _shared_client
    if _shared_client is None:
        try:
            _shared_client = redis.from_url(
                _get_redis_url(),
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            await _shared_client.ping()  # type: ignore[misc]
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise CacheConnectionError(f"Failed to connect to Redis: {e}") from e
    return _shared_client


async def close_shared_redis() -> None:
    """Close the shared Redis client. Call on shutdown."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None
        logger.debug("Closed shared Redis client")
