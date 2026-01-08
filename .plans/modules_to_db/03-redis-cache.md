# Phase 3: Redis Module Cache

## Overview

Redis serves as the primary cache for module content. Workers read exclusively from Redis (never touch DB directly for modules).

## Key Patterns

```
bifrost:module:{path}    # JSON: {content, path, hash}
bifrost:module:index     # SET of all module paths
```

## Async Client (API/Services)

**File:** `api/src/core/module_cache.py`

```python
"""
Async Redis client for module caching.

Used by API services and background jobs that have async context.
"""

import json
import logging
from typing import TypedDict

from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)

MODULE_KEY_PREFIX = "bifrost:module:"
MODULE_INDEX_KEY = "bifrost:module:index"


class CachedModule(TypedDict):
    content: str
    path: str
    hash: str


async def get_module(path: str) -> CachedModule | None:
    """Fetch a single module from cache."""
    redis = await get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_module(path: str, content: str, content_hash: str) -> None:
    """Cache a module and add to index."""
    redis = await get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"

    cached = CachedModule(content=content, path=path, hash=content_hash)
    await redis.set(key, json.dumps(cached))
    await redis.sadd(MODULE_INDEX_KEY, path)

    logger.debug(f"Cached module: {path}")


async def invalidate_module(path: str) -> None:
    """Remove module from cache and index."""
    redis = await get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"

    await redis.delete(key)
    await redis.srem(MODULE_INDEX_KEY, path)

    logger.debug(f"Invalidated module cache: {path}")


async def get_all_module_paths() -> set[str]:
    """Get all cached module paths (for import hook index)."""
    redis = await get_redis_client()
    paths = await redis.smembers(MODULE_INDEX_KEY)
    return {p.decode() if isinstance(p, bytes) else p for p in paths}


async def warm_cache_from_db() -> int:
    """
    Load all modules from database into Redis cache.

    Called by init container on startup.

    Returns:
        Number of modules cached
    """
    from sqlalchemy import select
    from src.core.database import get_async_session
    from src.models.orm.workspace import WorkspaceFile

    async with get_async_session() as session:
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.entity_type == "module",
            WorkspaceFile.is_deleted == False,
            WorkspaceFile.content.isnot(None),
        )
        result = await session.execute(stmt)
        modules = result.scalars().all()

        count = 0
        for module in modules:
            await set_module(
                path=module.path,
                content=module.content,
                content_hash=module.content_hash or "",
            )
            count += 1

        logger.info(f"Warmed module cache with {count} modules")
        return count
```

## Sync Client (Import Hook)

**File:** `api/src/core/module_cache_sync.py`

```python
"""
Synchronous Redis client for import hook.

Python's import system runs synchronously - we need sync Redis access
for the MetaPathFinder to fetch modules during import.
"""

import json
import os
from typing import Any

import redis

from src.core.module_cache import MODULE_KEY_PREFIX, MODULE_INDEX_KEY, CachedModule


def _get_sync_redis() -> redis.Redis:
    """Get synchronous Redis client."""
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def get_module_sync(path: str) -> CachedModule | None:
    """Fetch a single module from cache (synchronous)."""
    client = _get_sync_redis()
    key = f"{MODULE_KEY_PREFIX}{path}"
    data = client.get(key)
    if data:
        return json.loads(data)
    return None


def get_module_index_sync() -> set[str]:
    """Get all cached module paths (synchronous)."""
    client = _get_sync_redis()
    paths = client.smembers(MODULE_INDEX_KEY)
    return {p if isinstance(p, str) else p.decode() for p in paths}
```

## Cache Invalidation Strategy

Cache is invalidated via the API on file mutations:

| Operation | Cache Action |
|-----------|--------------|
| Write module | `set_module(path, content, hash)` |
| Delete module | `invalidate_module(path)` |
| Move module | `invalidate_module(old_path)` + `set_module(new_path, ...)` |

Workers never invalidate cache - they only read from it.

## Fallback Behavior

If a module is not in cache (cache miss):
1. Import hook returns `None` - lets filesystem finder try
2. Since `/tmp/bifrost/workspace` is virtual/empty, import fails
3. Workflow gets `ImportError` with clear message

This is intentional - cache should always be warm. A cache miss indicates:
- Module was just created (API should have cached it)
- Cache was cleared (init container should rewarm)
- Bug in cache invalidation logic
