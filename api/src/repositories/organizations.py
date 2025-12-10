"""
Organization Repository

Data access for organization entities.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Organization
from src.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """
    Repository for Organization entities.
    """

    model = Organization

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_slug(self, slug: str) -> Organization | None:
        """
        Get organization by slug.

        Args:
            slug: Organization slug (unique identifier)

        Returns:
            Organization or None if not found
        """
        result = await self.session.execute(
            select(Organization).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> Organization | None:
        """
        Get organization by email domain.

        Args:
            domain: Email domain (e.g., 'acme.com')

        Returns:
            Organization or None if not found
        """
        result = await self.session.execute(
            select(Organization).where(Organization.domain == domain.lower())
        )
        return result.scalar_one_or_none()

    async def get_active(self, limit: int = 100, offset: int = 0) -> list[Organization]:
        """
        Get all active organizations.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of active organizations
        """
        result = await self.session.execute(
            select(Organization)
            .where(Organization.is_active == True)  # noqa: E712
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create_organization(
        self,
        name: str,
        slug: str,
        created_by: str,
        domain: str | None = None,
    ) -> Organization:
        """
        Create a new organization.

        Args:
            name: Organization display name
            slug: URL-friendly unique identifier
            created_by: User ID who created the org
            domain: Email domain for auto-provisioning

        Returns:
            Created organization
        """
        org = Organization(
            name=name,
            slug=slug,
            domain=domain.lower() if domain else None,
            created_by=created_by,
            is_active=True,
        )
        return await self.create(org)
