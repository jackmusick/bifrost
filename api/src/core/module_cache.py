"""
Async Redis client for module caching.

Used by API services and background jobs that have async context.
Workers read modules from this cache during virtual imports.

Key patterns:
- bifrost:module:{path} - JSON: {content, path, hash}
- bifrost:module:index - SET of all module paths
"""

import hashlib
import json
import logging
from typing import Awaitable, TypedDict, cast

from src.core.redis_client import get_redis_client
from src.services.repo_storage import RepoStorage

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
    Fetch a module from cache, falling back to S3.

    Lookup order:
    1. Redis cache (fast path)
    2. S3 _repo/ (fallback, re-caches to Redis)
    3. None (module not found)

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

    # Redis miss — try S3 fallback
    try:
        repo = RepoStorage()
        content_bytes = await repo.read(path)
    except Exception:
        logger.debug(f"Module not in cache or S3: {path}")
        return None

    try:
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(f"Could not decode {path} as UTF-8, skipping")
        return None

    content_hash = hashlib.sha256(content_bytes).hexdigest()
    module: CachedModule = {
        "content": content_str,
        "path": path,
        "hash": content_hash,
    }

    # Re-cache to Redis (self-healing)
    try:
        await redis.setex(key, 86400, json.dumps(module))
        redis_conn = await redis._get_redis()
        await cast(Awaitable[int], redis_conn.sadd(MODULE_INDEX_KEY, path))
    except Exception as e:
        logger.warning(f"Failed to re-cache S3 module to Redis: {e}")

    return module


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
