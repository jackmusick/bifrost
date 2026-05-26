"""OAuth provider and token repositories.

Both extend ``OrgScopedRepository`` so cascade (org-specific → global) is
handled by the base class. No inline cascade primitives.

This is the canonical access path for OAuth provider/token reads from the
SDK execution surface. The pre-overhaul ``IntegrationsRepository.get_provider_org_token``
had no ``organization_id`` filter at all and could return any org's
``user_id=NULL`` token; it was the carrier of the cross-tenant token leak
fixed in the 2026-05 overhaul.

See ``api/src/repositories/README.md`` for the full pattern.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.oauth import OAuthProvider, OAuthToken
from src.repositories.org_scoped import OrgScopedRepository


class OAuthProviderRepository(OrgScopedRepository[OAuthProvider]):
    """Cascade-scoped access to OAuth provider rows.

    Used for resolving a provider by ``provider_name`` from the SDK
    execution path. Org-specific providers win on name collision; falls
    back to global (``organization_id IS NULL``).
    """

    model = OAuthProvider
    role_table = None  # OAuth providers have no role-based access


class OAuthTokenRepository(OrgScopedRepository[OAuthToken]):
    """Cascade-scoped access to OAuth token rows (org-level, user_id=NULL).

    Used for resolving the org-level OAuth token for a given provider
    from the SDK execution path. Org-specific tokens win; falls back to
    global (``organization_id IS NULL``).

    The base class ``get(**filters)`` enforces the cascade. This subclass
    adds one helper for the common "give me the org-level token for this
    provider" lookup, which combines the provider_id filter with the
    ``user_id IS NULL`` constraint that distinguishes org-level tokens
    from per-user tokens.
    """

    model = OAuthToken
    role_table = None  # OAuth tokens have no role-based access

    def __init__(
        self,
        session: AsyncSession,
        org_id: UUID | str | None,
        user_id: UUID | str | None = None,
        is_superuser: bool = False,
    ):
        super().__init__(session, org_id, user_id, is_superuser)

    async def get_org_level_for_provider(
        self, provider_id: UUID
    ) -> Any:
        """Get the org-level OAuth token for a provider (``user_id IS NULL``).

        Applies the standard cascade: prefer the token bound to this
        repository's ``org_id``; fall back to the global token if no
        org-specific row exists. NEVER returns another org's token —
        the cascade explicitly filters by either this org or NULL.

        Args:
            provider_id: ``OAuthProvider`` UUID.

        Returns:
            ``OAuthToken`` or ``None`` if not found in either scope.
        """
        # Try org-specific first (if we have an org).
        if self.org_id is not None:
            result = await self.session.execute(
                select(OAuthToken).where(
                    OAuthToken.provider_id == provider_id,
                    OAuthToken.organization_id == self.org_id,
                    OAuthToken.user_id.is_(None),
                )
            )
            token = result.scalars().first()
            if token is not None:
                return token

        # Fall back to global.
        result = await self.session.execute(
            select(OAuthToken).where(
                OAuthToken.provider_id == provider_id,
                OAuthToken.organization_id.is_(None),
                OAuthToken.user_id.is_(None),
            )
        )
        return result.scalars().first()
