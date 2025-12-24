"""
Bifrost Redis Cache Module.

Provides caching infrastructure for SDK operations during workflow execution.

Key Components:
    - keys: Redis key generation functions (single source of truth)
    - redis_client: Async Redis connection factory
    - invalidation: Cache invalidation functions (used by API routes)
    - warming: Pre-warming functions (used by worker before execution)

Usage (SDK reads):
    from src.core.cache import get_redis, config_hash_key

    async with get_redis() as r:
        data = await r.hget(config_hash_key(org_id), key)

Usage (API invalidation):
    from src.core.cache import invalidate_config

    await invalidate_config(org_id, key)

Usage (Pre-warming):
    from src.core.cache import prewarm_sdk_cache

    await prewarm_sdk_cache(execution_id, org_id, user_id)
"""

# Key generation functions
from .keys import (
    TTL_CONFIG,
    TTL_FORMS,
    TTL_ORGS,
    TTL_PENDING,
    TTL_ROLES,
    config_hash_key,
    config_key,
    execution_logs_stream_key,
    form_key,
    forms_hash_key,
    org_key,
    orgs_list_key,
    pending_changes_key,
    role_forms_key,
    role_key,
    role_users_key,
    roles_hash_key,
    user_forms_key,
)

# Redis client
from .redis_client import (
    CacheConnectionError,
    CacheError,
    CacheOperationError,
    close_shared_redis,
    get_redis,
    get_shared_redis,
)

# Invalidation functions
from .invalidation import (
    cleanup_execution_cache,
    invalidate_all_config,
    invalidate_all_orgs,
    invalidate_config,
    invalidate_form,
    invalidate_form_assignment,
    invalidate_org,
    invalidate_role,
    invalidate_role_forms,
    invalidate_role_users,
)

# Pre-warming
from .warming import prewarm_sdk_cache

# Data provider cache
from .data_provider_cache import (
    TTL_DATA_PROVIDER,
    cache_result as cache_data_provider_result,
    compute_param_hash,
    data_provider_cache_key,
    get_cached_result as get_cached_data_provider,
    invalidate_data_provider,
    acquire_compute_lock,
    release_compute_lock,
)

__all__ = [
    # Keys
    "config_hash_key",
    "config_key",
    "forms_hash_key",
    "form_key",
    "user_forms_key",
    "roles_hash_key",
    "role_key",
    "role_users_key",
    "role_forms_key",
    "org_key",
    "orgs_list_key",
    "pending_changes_key",
    "execution_logs_stream_key",
    # TTLs
    "TTL_CONFIG",
    "TTL_FORMS",
    "TTL_ROLES",
    "TTL_ORGS",
    "TTL_PENDING",
    # Redis client
    "get_redis",
    "get_shared_redis",
    "close_shared_redis",
    "CacheError",
    "CacheConnectionError",
    "CacheOperationError",
    # Invalidation
    "invalidate_config",
    "invalidate_all_config",
    "invalidate_form",
    "invalidate_form_assignment",
    "invalidate_role",
    "invalidate_role_users",
    "invalidate_role_forms",
    "invalidate_org",
    "invalidate_all_orgs",
    "cleanup_execution_cache",
    # Pre-warming
    "prewarm_sdk_cache",
    # Data provider cache
    "TTL_DATA_PROVIDER",
    "data_provider_cache_key",
    "compute_param_hash",
    "get_cached_data_provider",
    "cache_data_provider_result",
    "invalidate_data_provider",
    "acquire_compute_lock",
    "release_compute_lock",
]
