"""
Cache invalidation functions for Bifrost.

Used by API routes to invalidate Redis cache after write operations.
All functions are async and use the shared Redis client.

Pattern:
    1. API route writes to Postgres
    2. API route calls invalidate_* to clear Redis cache
    3. Next execution pre-warms fresh data from Postgres
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .keys import (
    config_hash_key,
    config_key,
    form_key,
    forms_hash_key,
    oauth_hash_key,
    oauth_provider_key,
    org_key,
    orgs_list_key,
    role_forms_key,
    role_key,
    role_users_key,
    roles_hash_key,
    user_forms_key,
)
from .redis_client import get_shared_redis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Config Invalidation
# =============================================================================


async def invalidate_config(org_id: str | None, key: str | None = None) -> None:
    """
    Invalidate config cache after a config write operation.

    Args:
        org_id: Organization ID or None for global config
        key: Specific config key to invalidate, or None to invalidate all
    """
    try:
        r = await get_shared_redis()

        # Always invalidate the hash (contains all configs)
        await r.delete(config_hash_key(org_id))

        # Also invalidate specific key if provided
        if key:
            await r.delete(config_key(org_id, key))

        logger.debug(f"Invalidated config cache: org={org_id}, key={key}")
    except Exception as e:
        # Log but don't fail - cache invalidation is best-effort
        # TTL will eventually clear stale data
        logger.warning(f"Failed to invalidate config cache: {e}")


async def invalidate_all_config(org_id: str | None) -> None:
    """Invalidate all config cache for an organization."""
    await invalidate_config(org_id, key=None)


# =============================================================================
# OAuth Invalidation
# =============================================================================


async def invalidate_oauth(org_id: str | None, provider: str | None = None) -> None:
    """
    Invalidate OAuth cache after provider or token update.

    Args:
        org_id: Organization ID or None for global
        provider: Specific provider to invalidate, or None to invalidate all
    """
    try:
        r = await get_shared_redis()

        # Always invalidate the hash (contains all providers)
        await r.delete(oauth_hash_key(org_id))

        # Also invalidate specific provider if provided
        if provider:
            await r.delete(oauth_provider_key(org_id, provider))

        logger.debug(f"Invalidated OAuth cache: org={org_id}, provider={provider}")
    except Exception as e:
        logger.warning(f"Failed to invalidate OAuth cache: {e}")


async def invalidate_oauth_token(org_id: str | None, provider: str) -> None:
    """Invalidate OAuth cache after token refresh."""
    await invalidate_oauth(org_id, provider)


# =============================================================================
# Form Invalidation
# =============================================================================


async def invalidate_form(org_id: str | None, form_id: str | None = None) -> None:
    """
    Invalidate form cache after form CRUD operation.

    Args:
        org_id: Organization ID or None for global
        form_id: Specific form to invalidate, or None to invalidate all
    """
    try:
        r = await get_shared_redis()

        # Always invalidate the hash (contains all forms)
        await r.delete(forms_hash_key(org_id))

        # Also invalidate specific form if provided
        if form_id:
            await r.delete(form_key(org_id, form_id))

        # Invalidate user-specific form lists (use pattern delete)
        # This is needed because form-role assignments affect which forms users can see
        pattern = f"bifrost:{_get_scope(org_id)}:user_forms:*"
        async for key in r.scan_iter(pattern):
            await r.delete(key)

        logger.debug(f"Invalidated form cache: org={org_id}, form_id={form_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate form cache: {e}")


def _get_scope(org_id: str | None) -> str:
    """Get the scope prefix for a key."""
    if org_id and org_id != "GLOBAL":
        return f"org:{org_id}"
    return "global"


async def invalidate_form_assignment(org_id: str | None, form_id: str) -> None:
    """Invalidate form cache after role-form assignment change."""
    await invalidate_form(org_id, form_id)


# =============================================================================
# Role Invalidation
# =============================================================================


async def invalidate_role(org_id: str | None, role_id: str | None = None) -> None:
    """
    Invalidate role cache after role CRUD operation.

    Args:
        org_id: Organization ID or None for global
        role_id: Specific role to invalidate, or None to invalidate all
    """
    try:
        r = await get_shared_redis()

        # Always invalidate the hash (contains all roles)
        await r.delete(roles_hash_key(org_id))

        # Also invalidate specific role if provided
        if role_id:
            await r.delete(role_key(org_id, role_id))
            await r.delete(role_users_key(org_id, role_id))
            await r.delete(role_forms_key(org_id, role_id))

        logger.debug(f"Invalidated role cache: org={org_id}, role_id={role_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate role cache: {e}")


async def invalidate_role_users(org_id: str | None, role_id: str) -> None:
    """Invalidate role user assignments cache."""
    try:
        r = await get_shared_redis()
        await r.delete(role_users_key(org_id, role_id))
        # Also invalidate user_forms since role assignment affects form access
        pattern = f"bifrost:{_get_scope(org_id)}:user_forms:*"
        async for key in r.scan_iter(pattern):
            await r.delete(key)
        logger.debug(f"Invalidated role users cache: org={org_id}, role_id={role_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate role users cache: {e}")


async def invalidate_role_forms(org_id: str | None, role_id: str) -> None:
    """Invalidate role form assignments cache."""
    try:
        r = await get_shared_redis()
        await r.delete(role_forms_key(org_id, role_id))
        # Also invalidate user_forms since role-form assignment affects form access
        pattern = f"bifrost:{_get_scope(org_id)}:user_forms:*"
        async for key in r.scan_iter(pattern):
            await r.delete(key)
        logger.debug(f"Invalidated role forms cache: org={org_id}, role_id={role_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate role forms cache: {e}")


# =============================================================================
# Organization Invalidation
# =============================================================================


async def invalidate_org(org_id: str) -> None:
    """
    Invalidate organization cache after org CRUD operation.

    Args:
        org_id: Organization ID to invalidate
    """
    try:
        r = await get_shared_redis()
        await r.delete(org_key(org_id))
        await r.delete(orgs_list_key())
        logger.debug(f"Invalidated org cache: org_id={org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate org cache: {e}")


async def invalidate_all_orgs() -> None:
    """Invalidate all organization cache."""
    try:
        r = await get_shared_redis()
        await r.delete(orgs_list_key())
        # Scan for individual org keys
        pattern = "bifrost:global:orgs:*"
        async for key in r.scan_iter(pattern):
            await r.delete(key)
        logger.debug("Invalidated all org cache")
    except Exception as e:
        logger.warning(f"Failed to invalidate all org cache: {e}")


# =============================================================================
# Execution Cleanup
# =============================================================================


async def cleanup_execution_cache(execution_id: str) -> None:
    """
    Clean up all execution-scoped cache entries.

    Called after execution completes to remove:
    - Pending changes (should already be flushed)
    - Log stream (if using Redis streams)
    - Any other execution-scoped data

    Args:
        execution_id: Execution ID to clean up
    """
    from .keys import execution_logs_stream_key, pending_changes_key

    try:
        r = await get_shared_redis()
        await r.delete(pending_changes_key(execution_id))
        await r.delete(execution_logs_stream_key(execution_id))
        logger.debug(f"Cleaned up execution cache: execution_id={execution_id}")
    except Exception as e:
        logger.warning(f"Failed to cleanup execution cache: {e}")
