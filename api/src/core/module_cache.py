"""
Async Redis client for module caching.

Used by API services and background jobs that have async context.
Workers read modules from this cache during virtual imports.

Key patterns:
- bifrost:module:{path} - JSON: {content, path, hash}
- bifrost:module:index - SET of all module paths
"""

import json
import logging
from typing import Awaitable, TypedDict, cast

from src.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

MODULE_KEY_PREFIX = "bifrost:module:"
MODULE_INDEX_KEY = "bifrost:module:index"


class CachedModule(TypedDict):
    """Schema for cached module data."""

    content: str
    path: str
    hash: str


async def get_module(path: str) -> CachedModule | None:
    """
    Fetch a single module from cache.

    Args:
        path: Module path relative to workspace (e.g., "shared/halopsa.py")

    Returns:
        CachedModule dict if found, None otherwise
    """
    redis = get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_module(path: str, content: str, content_hash: str) -> None:
    """
    Cache a module and add to index.

    Called by file_ops when a module is written.

    Args:
        path: Module path relative to workspace
        content: Python source code
        content_hash: SHA-256 hash of content (for change detection)
    """
    redis = get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"

    cached = CachedModule(content=content, path=path, hash=content_hash)
    await redis.setex(key, 86400, json.dumps(cached))  # 24hr TTL

    # Add to index set
    redis_conn = await redis._get_redis()
    await cast(Awaitable[int], redis_conn.sadd(MODULE_INDEX_KEY, path))

    logger.debug(f"Cached module: {path}")


async def invalidate_module(path: str) -> None:
    """
    Remove module from cache and index.

    Called by file_ops when a module is deleted.

    Args:
        path: Module path to invalidate
    """
    redis = get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"

    await redis.delete(key)

    # Remove from index set
    redis_conn = await redis._get_redis()
    await cast(Awaitable[int], redis_conn.srem(MODULE_INDEX_KEY, path))

    logger.debug(f"Invalidated module cache: {path}")


async def get_all_module_paths() -> set[str]:
    """
    Get all cached module paths.

    Used by import hook to check if a module exists in cache.

    Returns:
        Set of all cached module paths
    """
    redis = get_redis_client()
    redis_conn = await redis._get_redis()
    paths = await cast(Awaitable[set[str]], redis_conn.smembers(MODULE_INDEX_KEY))
    return {p if isinstance(p, str) else p.decode() for p in paths}


async def warm_cache_from_db(session=None) -> int:
    """
    Load all modules from database into Redis cache.

    Called by init container or API startup to ensure cache is warm.

    Args:
        session: Optional SQLAlchemy AsyncSession. If not provided, creates its own.
                 Pass a session during testing to avoid event loop conflicts.

    Returns:
        Number of modules cached
    """
    from sqlalchemy import select

    from src.models.orm.workspace import WorkspaceFile

    async def _warm_with_session(db_session) -> int:
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.entity_type == "module",
            WorkspaceFile.is_deleted == False,  # noqa: E712
            WorkspaceFile.content.isnot(None),
        )
        result = await db_session.execute(stmt)
        modules = result.scalars().all()

        count = 0
        for module in modules:
            if module.content:  # Double-check content exists
                await set_module(
                    path=module.path,
                    content=module.content,
                    content_hash=module.content_hash or "",
                )
                count += 1

        logger.info(f"Warmed module cache with {count} modules")
        return count

    if session is not None:
        return await _warm_with_session(session)
    else:
        from src.core.database import get_db_context

        async with get_db_context() as db_session:
            return await _warm_with_session(db_session)


async def clear_module_cache() -> int:
    """
    Clear all cached modules.

    Used for testing and cache invalidation.

    Returns:
        Number of modules cleared
    """
    redis = get_redis_client()
    redis_conn = await redis._get_redis()

    # Get all module paths from index
    paths = await cast(Awaitable[set[str]], redis_conn.smembers(MODULE_INDEX_KEY))
    count = len(paths)

    if paths:
        # Delete all module keys
        keys = [f"{MODULE_KEY_PREFIX}{p if isinstance(p, str) else p.decode()}" for p in paths]
        await cast(Awaitable[int], redis_conn.delete(*keys))

    # Clear the index
    await cast(Awaitable[int], redis_conn.delete(MODULE_INDEX_KEY))

    logger.info(f"Cleared {count} modules from cache")
    return count
