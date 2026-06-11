"""
Shared org-cascade helper for MCP tools.

MCP tools authenticate as the user directly (not the engine sentinel), so they
must enforce the same org-scoping — including external-user isolation — that
``OrgScopedRepository`` enforces on the REST path. Historically each tool
hand-rolled ``org == X OR org IS NULL``, which silently re-opened the global
tier to external (portal/guest) principals (EXT-1 adversarial-review LEAK #3
and siblings).

This helper is the ONE place that applies the cascade for MCP tool queries.
Every tool that filters an execution-resolution model by org must route
through it so the external rule can never drift back in.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, false, or_


def apply_mcp_org_scope(
    query: Select[Any],
    model: Any,
    context: Any,
) -> Select[Any]:
    """Apply org cascade to an MCP tool query, honoring external-user isolation.

    Rules (mirrors ``OrgScopedRepository`` / ``resolve_org_filter``):

    - Platform admin (``context.is_platform_admin``): no filter — full visibility.
    - External, non-admin (``context.is_external``): the caller's OWN org tier
      ONLY (no ``organization_id IS NULL`` arm); a no-org external sees nothing.
    - Regular org user: cascade — own org OR global.
    - Non-admin with no org and not external: global only (legacy behavior).

    Args:
        query: The SELECT to scope.
        model: The ORM model being filtered (must have ``organization_id``).
        context: The MCP context carrying ``is_platform_admin``, ``org_id``,
            and ``is_external``.
    """
    if getattr(context, "is_platform_admin", False):
        return query

    is_external = bool(getattr(context, "is_external", False))
    org_id = getattr(context, "org_id", None)
    if isinstance(org_id, str) and org_id:
        org_id = UUID(org_id)

    if org_id is not None:
        if is_external:
            # External: own org tier only — no global arm (EXT-1 rule 1).
            return query.where(model.organization_id == org_id)
        return query.where(
            or_(
                model.organization_id == org_id,
                model.organization_id.is_(None),
            )
        )

    # No org context.
    if is_external:
        # External with no org: nothing is in reach.
        return query.where(false())
    # Legacy: a non-admin with no org sees only global.
    return query.where(model.organization_id.is_(None))
