"""
External-user claim resolution (EXT-1).

``User.is_external`` marks portal/guest users whose visibility is restricted
to their own org tier (no global entities, no ``access_level="authenticated"``
entitlement). The restriction applies only to EXTERNAL, NON-BYPASS principals,
where bypass is the canonical scope-bypass rule from
``api/src/repositories/README.md``:

    bypass = is_platform_admin OR is_provider_org

This helper computes the ``is_external`` JWT claim at token mint, neutralizing
the raw DB flag for bypass callers, so every downstream consumer
(``UserPrincipal.is_external`` → repositories, routers, MCP) can treat the
claim as "externally restricted principal" without re-deriving provider-org
membership per request.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_external_claim(db: AsyncSession, user) -> bool:
    """Compute the ``is_external`` token claim for a user.

    Returns True only when the user is flagged external AND is not a bypass
    principal (platform admin or provider-org member). One indexed SELECT
    against the user's org, and only for external-flagged users — login /
    refresh paths only, never per-request.

    Args:
        db: Async DB session.
        user: The ORM ``User`` row being minted a token.
    """
    if not user.is_external:
        return False
    if user.is_superuser:
        # Platform admin: bypass — external restriction never applies.
        return False
    if user.organization_id is None:
        # Unreachable for non-superusers (token parsing rejects org-less
        # non-superusers), but never restrict an org-less principal here.
        return False

    from src.models.orm.organizations import Organization

    is_provider = await db.scalar(
        select(Organization.is_provider).where(
            Organization.id == user.organization_id
        )
    )
    # Provider-org member: bypass — the other half of the C2 bypass rule.
    return not bool(is_provider)
