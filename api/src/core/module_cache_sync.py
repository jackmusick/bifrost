"""
Synchronous Redis client for import hook.

Python's import system runs synchronously - we need sync Redis access
for the MetaPathFinder to fetch modules during import.

This module provides synchronous versions of the cache functions
specifically for use in virtual_import.py's MetaPathFinder.

When a cache miss occurs, we fall back to S3 to fetch the module
and re-cache it in Redis. This provides self-healing behavior when:
- Redis cache entries expire (24hr TTL)
- Redis restarts or evicts keys
- Cache warming at startup was incomplete
"""

import hashlib
import json
import logging
import os
from functools import lru_cache
from typing import Any

import redis

from src.core.module_cache import MODULE_INDEX_KEY, MODULE_KEY_PREFIX, CachedModule

logger = logging.getLogger(__name__)

# TTL for cached modules (24 hours)
MODULE_CACHE_TTL = 86400

REPO_PREFIX = "_repo/"


@lru_cache(maxsize=1)
def _get_sync_redis() -> Any:
    """
    Get synchronous Redis client.

    Uses lru_cache to reuse connection across imports.
    """
    return redis.Redis.from_url(
        os.environ.get("BIFROST_REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def _get_s3_module(path: str) -> bytes | None:
    """
    Fetch a module from S3 _repo/ prefix (synchronous).

    Uses boto3 sync client since this runs in worker subprocesses.
    Returns raw bytes or None if not found.
    """
    try:
        import boto3  # type: ignore[import-untyped]

        endpoint_url = os.environ.get("BIFROST_S3_ENDPOINT_URL")
        access_key = os.environ.get("BIFROST_S3_ACCESS_KEY")
        secret_key = os.environ.get("BIFROST_S3_SECRET_KEY")
        bucket = os.environ.get("BIFROST_S3_BUCKET")
        region = os.environ.get("BIFROST_S3_REGION", "us-east-1")

        if not all([bucket, access_key, secret_key]):
            logger.debug("S3 not configured, skipping S3 fallback")
            return None

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

        key = f"{REPO_PREFIX}{path}"
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    except Exception as e:
        # Check for S3 NoSuchKey specifically
        error_code = getattr(getattr(e, "response", None), "get", lambda *_: None)
        if callable(error_code):
            resp = getattr(e, "response", None)
            if isinstance(resp, dict):
                code = resp.get("Error", {}).get("Code", "")
                if code == "NoSuchKey":
                    logger.debug(f"Module not found in S3: {path}")
                    return None
        logger.warning(f"S3 fallback error for {path}: {e}")
        return None


def get_module_sync(path: str) -> CachedModule | None:
    """
    Fetch a single module from cache (synchronous).

    Called by VirtualModuleFinder.find_spec() during import resolution.

    Lookup order:
    1. Redis cache (fast path)
    2. S3 _repo/ (fallback, re-caches to Redis)
    3. None (module not found)
    """
    try:
        client = _get_sync_redis()
        key = f"{MODULE_KEY_PREFIX}{path}"
        data = client.get(key)
        if data:
            return json.loads(data)

        # Redis miss — try S3 fallback
        s3_content = _get_s3_module(path)
        if s3_content is not None:
            try:
                content_str = s3_content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"Could not decode S3 module as UTF-8: {path}")
                return None

            content_hash = hashlib.sha256(s3_content).hexdigest()
            module: CachedModule = {
                "content": content_str,
                "path": path,
                "hash": content_hash,
            }

            # Cache back to Redis
            try:
                client.setex(key, MODULE_CACHE_TTL, json.dumps(module))
                # Also add to module index
                client.sadd(MODULE_INDEX_KEY, path)
            except redis.RedisError as e:
                logger.warning(f"Failed to cache S3 module to Redis: {e}")

            return module

        logger.debug(f"Module not in cache or S3: {path}")
        return None

    except redis.RedisError as e:
        logger.warning(f"Redis error fetching module {path}: {e}")
        return None


def get_module_index_sync() -> set[str]:
    """
    Get all cached module paths (synchronous).
    """
    try:
        client = _get_sync_redis()
        paths = client.smembers(MODULE_INDEX_KEY)
        return {p if isinstance(p, str) else p.decode() for p in paths}
    except redis.RedisError as e:
        logger.warning(f"Redis error fetching module index: {e}")
        return set()


def reset_sync_redis() -> None:
    """Reset the sync Redis client."""
    _get_sync_redis.cache_clear()
