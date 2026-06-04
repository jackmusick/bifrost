"""
Solution Repository

Data access for Solution *install* entities. A Solution is an identity-style
entity (like Organization): it belongs to a scope but is never resolved by name
with cascade, so it does NOT go through OrgScopedRepository. See
api/src/repositories/README.md.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Solution
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SolutionRepository(BaseRepository[Solution]):  # type: ignore[type-var]
    """Repository for Solution install entities."""

    model = Solution

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_slug_and_scope(
        self, slug: str, organization_id: str | None
    ) -> Solution | None:
        """Find the single install of ``slug`` at the given scope.

        ``organization_id`` is the org UUID for an org-scoped install, or None
        for the global-scoped install. Install identity is unique per
        (slug, scope) — success-criteria §3.4.
        """
        stmt = select(Solution).where(Solution.slug == slug)
        if organization_id is None:
            stmt = stmt.where(Solution.organization_id.is_(None))
        else:
            stmt = stmt.where(Solution.organization_id == organization_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
