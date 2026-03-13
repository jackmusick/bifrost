"""
Requirements.txt Persistence Architecture
=========================================

This module is part of the package persistence system that ensures
installed packages survive container restarts.

Persistence Flow:
1. User installs package via /api/packages/install
2. API handler appends package to requirements, saves to S3 + Redis cache
3. API broadcasts "recycle_workers" to all workers
4. Workers recycle processes; ProcessPoolManager calls install_requirements_from_cache() once at pool startup
5. pip install runs from cached requirements.txt (shared filesystem, all workers inherit)

Source of truth: S3 (_repo/requirements.txt) via RepoStorage
Cache: Redis (bifrost:requirements:content) — pool reads this synchronously at startup

Related Files:
- api/src/routers/packages.py - Saves requirements + broadcasts recycle
- api/scripts/init_container.py - Warms cache on container startup
- api/src/services/execution/simple_worker.py - Installs on worker startup

Key Pattern:
- bifrost:requirements:content - JSON: {content, hash}
"""

import hashlib
import json
import logging
from typing import TypedDict

from src.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

REQUIREMENTS_KEY = "bifrost:requirements:content"


class CachedRequirements(TypedDict):
    """Schema for cached requirements data."""

    content: str
    hash: str


async def get_requirements() -> CachedRequirements | None:
    """
    Fetch requirements.txt content from cache.

    Returns:
        CachedRequirements dict if found, None otherwise
    """
    redis = get_redis_client()
    data = await redis.get(REQUIREMENTS_KEY)
    if data:
        return json.loads(data)
    return None


async def set_requirements(content: str, content_hash: str) -> None:
    """
    Cache requirements.txt content.

    Args:
        content: Full requirements.txt content
        content_hash: SHA-256 hash of content (for change detection)
    """
    redis = get_redis_client()
    cached = CachedRequirements(content=content, hash=content_hash)
    await redis.setex(REQUIREMENTS_KEY, 86400, json.dumps(cached))  # 24hr TTL
    logger.debug("Cached requirements.txt")


async def warm_requirements_cache() -> bool:
    """
    Load requirements.txt from S3 into Redis cache.

    Called by init container or API startup to ensure cache is warm.
    Also called before broadcasting recycle when installing from requirements.txt,
    to ensure workers pick up the latest file content.

    Returns:
        True if requirements.txt was cached, False if not found
    """
    from src.services.repo_storage import RepoStorage

    try:
        repo = RepoStorage()
        content_bytes = await repo.read("requirements.txt")
        content = content_bytes.decode()

        if content.strip():
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            await set_requirements(content=content, content_hash=content_hash)
            logger.info("Warmed requirements cache from S3")
            return True

        logger.info("requirements.txt in S3 is empty")
        return False
    except Exception as e:
        # File may not exist yet in S3
        logger.info(f"No requirements.txt found in S3: {e}")
        return False


async def save_requirements(content: str) -> None:
    """
    Save requirements.txt to S3 and update Redis cache.

    Args:
        content: Full requirements.txt content
    """
    from src.services.repo_storage import RepoStorage

    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Write to S3 (source of truth)
    repo = RepoStorage()
    await repo.write("requirements.txt", content.encode())

    # Update Redis cache (workers read this synchronously at startup)
    await set_requirements(content, content_hash)
    logger.info("Saved requirements.txt to S3 and cache")


def append_package_to_requirements(
    current: str, package: str, version: str | None
) -> tuple[str, bool]:
    """
    Append or update a package in requirements.txt content.

    Args:
        current: Current requirements.txt content
        package: Package name
        version: Optional version specifier

    Returns:
        Tuple of (updated content, is_update) where is_update is True if
        an existing package was updated (needs process recycle to clear
        sys.modules), False if a new package was added.
    """
    lines = current.strip().split("\n") if current.strip() else []
    package_lower = package.lower()
    package_spec = f"{package}=={version}" if version else package

    # Find and update existing entry, or append
    found = False
    for i, line in enumerate(lines):
        # Parse package name from line (handles ==, >=, etc.)
        line_package = (
            line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
        )
        if line_package.lower() == package_lower:
            lines[i] = package_spec
            found = True
            break

    if not found:
        lines.append(package_spec)

    # Filter empty lines and ensure trailing newline
    lines = [line for line in lines if line.strip()]
    return ("\n".join(lines) + "\n" if lines else "", found)
