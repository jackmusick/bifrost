"""
Organization Filter Helper

Provides consistent organization filtering logic across endpoints.
Org scoping is selected via the `scope` query parameter.

Scope Parameter Values:
- Not sent / omitted → show all (no filter) - superusers only
- "global" → filter to organization_id IS NULL only
- "{uuid}" → filter to specific org + global records
"""

from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, false, or_

from src.core.auth import UserPrincipal


class OrgFilterType(Enum):
    """Types of organization filtering."""

    ALL = "all"  # No filter, show everything (superuser only)
    GLOBAL_ONLY = "global"  # Only org_id IS NULL
    ORG_ONLY = "org_only"  # Only specific org, NO global fallback (platform admin selecting org)
    ORG_PLUS_GLOBAL = "org"  # Specific org + global records (org users only)
    # EMPTY: match NOTHING (EXT-1 NEW-J). Returned for an org-less EXTERNAL
    # principal — an ``org_id == None`` filter compiles to ``IS NULL`` (the
    # global tier), so an external whose organization_id is None (a
    # misconfiguration — users.py accepts is_external + no org) would otherwise
    # read ALL global entities. This sentinel forces a no-match in every
    # consumer, mirroring OrgScopedRepository.external_restricted's org-less
    # short-circuit.
    EMPTY = "empty"


def org_filter_clause(
    org_column: Any,
    filter_type: "OrgFilterType",
    filter_org_id: UUID | None,
) -> ColumnElement[bool] | None:
    """Build the SQL predicate for a resolved org filter (EXT-1 NEW-J).

    Single source of truth for translating ``(filter_type, filter_org_id)``
    into a WHERE clause, so an inline consumer can never re-derive it wrongly
    (the NEW-J failure: ``org_column == None`` compiling to ``IS NULL``).

    Returns:
        - ``None`` for ALL (caller applies no org predicate).
        - ``false()`` for EMPTY (org-less external — match nothing).
        - the appropriate ``IS NULL`` / ``== org`` / ``(== org OR IS NULL)``
          predicate otherwise. ORG_ONLY/ORG_PLUS_GLOBAL with a None org_id
          collapse to a no-match rather than leaking the global tier.
    """
    if filter_type is OrgFilterType.ALL:
        return None
    if filter_type is OrgFilterType.EMPTY:
        return false()
    if filter_type is OrgFilterType.GLOBAL_ONLY:
        return org_column.is_(None)
    if filter_type is OrgFilterType.ORG_ONLY:
        # NO global fallback. A None org here is not a license to read global —
        # it means "no rows" (defense in depth; resolve_org_filter already maps
        # the org-less external to EMPTY).
        if filter_org_id is None:
            return false()
        return org_column == filter_org_id
    # ORG_PLUS_GLOBAL
    if filter_org_id is None:
        return org_column.is_(None)
    return or_(org_column == filter_org_id, org_column.is_(None))


def resolve_org_filter(
    user: UserPrincipal,
    scope: str | None = None,
) -> tuple[OrgFilterType, UUID | None]:
    """
    Resolve organization filter for list queries.

    This helper provides consistent organization filtering logic:
    - Superusers can view all data (scope omitted), global only (scope=global),
      or ONLY a specific org's data (scope={uuid}) - no global fallback
    - Org users always see their org's data + global records (scope is ignored)

    Args:
        user: The authenticated user principal
        scope: Filter scope - None (all), "global", or org UUID string

    Returns:
        tuple of (filter_type, org_id):
        - filter_type: OrgFilterType indicating how to filter
        - org_id: The organization UUID to filter by (only for ORG_PLUS_GLOBAL)

    Examples:
        Superuser with scope omitted:
            -> (ALL, None) - show all records (no org filter at all)

        Superuser with scope="global":
            -> (GLOBAL_ONLY, None) - show only global records (org_id IS NULL)

        Superuser with scope="{uuid}":
            -> (ORG_ONLY, uuid) - show ONLY that org's records (no global)

        Org user (any scope value):
            -> (ORG_PLUS_GLOBAL, user.organization_id) - always show their org + global

        Org user with no org assigned:
            -> (GLOBAL_ONLY, None) - only global records visible (edge case)

    Raises:
        ValueError: If scope is not a valid UUID or "global"
    """
    if user.is_superuser:
        if scope is None or scope == "":
            # Superuser with no filter - show ALL records
            return (OrgFilterType.ALL, None)
        elif scope == "global":
            # Superuser filtering to global only
            return (OrgFilterType.GLOBAL_ONLY, None)
        else:
            # Superuser filtering by specific org - ONLY that org (no global)
            try:
                org_uuid = UUID(scope)
                return (OrgFilterType.ORG_ONLY, org_uuid)
            except ValueError:
                raise ValueError(f"Invalid scope value: {scope}")
    elif getattr(user, "is_external", False):
        # External (portal/guest) users: their OWN org tier ONLY — no global
        # fallback (EXT-1 rule 1).
        if user.organization_id is None:
            # EXT-1 NEW-J: an org-less external must read NOTHING. Returning
            # (ORG_ONLY, None) would let a consumer compile ``org_id == None``
            # to ``IS NULL`` and leak the GLOBAL tier. EMPTY forces a no-match.
            return (OrgFilterType.EMPTY, None)
        return (OrgFilterType.ORG_ONLY, user.organization_id)
    else:
        # Org users: always filter to their organization, ignore the scope parameter
        if user.organization_id is not None:
            return (OrgFilterType.ORG_PLUS_GLOBAL, user.organization_id)
        else:
            # Edge case: org user with no org assigned sees only global
            return (OrgFilterType.GLOBAL_ONLY, None)


def resolve_target_org(
    user: UserPrincipal,
    scope: str | None,
    default_org_id: UUID | None = None,
) -> UUID | None:
    """
    Resolve target organization ID for write operations.

    This helper provides consistent organization targeting for create/update/delete:
    - Superusers can target any org via scope parameter
    - Non-superusers always target their own org (scope is ignored)

    Args:
        user: The authenticated user principal
        scope: Target scope - None (use default), "global", or org UUID string
        default_org_id: Default org ID when scope is None (usually from context)

    Returns:
        UUID of target organization, or None for global scope

    Examples:
        Superuser with scope=None:
            -> default_org_id (usually their context org or None)

        Superuser with scope="global":
            -> None (targets global/platform-level resources)

        Superuser with scope="{uuid}":
            -> UUID (targets specific org)

        Non-superuser (any scope value):
            -> user.organization_id (always their own org, scope ignored)

    Raises:
        ValueError: If scope is not a valid UUID or "global"
    """
    if user.is_superuser:
        if scope is None:
            return default_org_id
        if scope == "global":
            return None
        try:
            return UUID(scope)
        except ValueError:
            raise ValueError(f"Invalid scope value: {scope}")
    else:
        # Non-superusers always use their own org, scope is ignored
        return user.organization_id
