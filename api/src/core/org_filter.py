"""
Organization Filter Helper

Provides consistent organization filtering logic across endpoints.
Replaces the deprecated X-Organization-Id header approach with query parameters.

Scope Parameter Values:
- Not sent / omitted → show all (no filter) - superusers only
- "global" → filter to organization_id IS NULL only
- "{uuid}" → filter to specific org + global records
"""

from enum import Enum
from uuid import UUID

from src.core.auth import UserPrincipal


class OrgFilterType(Enum):
    """Types of organization filtering."""

    ALL = "all"  # No filter, show everything (superuser only)
    GLOBAL_ONLY = "global"  # Only org_id IS NULL
    ORG_ONLY = "org_only"  # Only specific org, NO global fallback (platform admin selecting org)
    ORG_PLUS_GLOBAL = "org"  # Specific org + global records (org users only)


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
    else:
        # Org users: always filter to their organization, ignore the scope parameter
        if user.organization_id is not None:
            return (OrgFilterType.ORG_PLUS_GLOBAL, user.organization_id)
        else:
            # Edge case: org user with no org assigned sees only global
            return (OrgFilterType.GLOBAL_ONLY, None)
