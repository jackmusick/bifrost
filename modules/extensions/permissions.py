"""
Bifrost Permission Utilities

Reusable role-checking helpers for workflows and platform access control.
Import this module in any workflow that needs to enforce or inspect role membership.

Usage:
    from modules.extensions.permissions import require_role, user_has_role, HR_ADMIN

    @workflow(...)
    async def my_workflow():
        await require_role(HR_ADMIN)  # raises UserError if not authorized
        ...
"""

import logging
import time

from bifrost import roles, users, context, UserError

_ROLES_CACHE_TTL = 300  # 5 minutes
_roles_cache: dict[str, tuple[float, list[str]]] = {}

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role name constants — use these instead of bare strings to avoid typos
# ---------------------------------------------------------------------------

HR_ADMIN = "HR Admin"
SALES = "Sales"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


async def is_provider(user_id: str | None = None) -> bool:
    """
    Return True if the user is a platform-level provider (superuser or no org).

    Provider users bypass all role-based access checks. A user is considered
    a provider if they have no org_id in context (platform-level session) or
    their Bifrost account has is_superuser=True.

    Args:
        user_id: Optional override; defaults to context.user_id.
    """
    uid = user_id or context.user_id

    # No org_id in execution context → platform-level session
    if not context.org_id:
        return True

    if not uid:
        return False

    user = await users.get(uid)
    return bool(user and getattr(user, "is_superuser", False))


async def get_user_roles(user_id: str) -> list[str]:
    """
    Return a list of role names the given user belongs to.

    Makes one call to list all roles, then checks membership for each.
    Results are cached per user for _ROLES_CACHE_TTL seconds since role
    memberships change infrequently.

    Args:
        user_id: The Bifrost user ID to inspect.
    """
    entry = _roles_cache.get(user_id)
    if entry is not None:
        ts, cached_roles = entry
        if time.monotonic() - ts < _ROLES_CACHE_TTL:
            return cached_roles

    all_roles = await roles.list()
    user_role_names: list[str] = []

    for role in all_roles:
        members = await roles.list_users(role.id)
        if user_id in members:
            user_role_names.append(role.name)

    _roles_cache[user_id] = (time.monotonic(), user_role_names)
    return user_role_names


async def user_has_role(user_id: str, role_name: str) -> bool:
    """
    Return True if the user belongs to the named Bifrost role.

    Args:
        user_id: The Bifrost user ID to check.
        role_name: Exact role name (e.g. HR_ADMIN).
    """
    return role_name in await get_user_roles(user_id)


async def require_role(role_name: str, user_id: str | None = None) -> None:
    """
    Assert that the calling user has the named role. Raises UserError if not.

    Provider users (superusers or no org_id in context) always pass.

    Args:
        role_name: The required Bifrost role name (use constants above).
        user_id:   Optional override; defaults to context.user_id.

    Raises:
        UserError: If the user is not authenticated or lacks the role.
    """
    uid = user_id or context.user_id

    if not uid:
        raise UserError("Authentication required.")

    if await is_provider(uid):
        return  # Providers bypass all role checks

    if not await user_has_role(uid, role_name):
        raise UserError(f"Access denied: '{role_name}' role required.")


async def get_or_create_role(role_name: str, description: str = "") -> object:
    """
    Fetch a role by name, creating it if it doesn't exist yet.

    Args:
        role_name:   Exact role name.
        description: Description used only when creating the role.

    Returns:
        The Role object (has .id and .name attributes).
    """
    all_roles = await roles.list()
    for role in all_roles:
        if role.name == role_name:
            return role

    logger.info(f"Role '{role_name}' not found — creating it.")
    return await roles.create(name=role_name, description=description)
