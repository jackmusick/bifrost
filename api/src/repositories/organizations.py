"""
Organization Repository

Data access for organization entities. Includes Redis-backed cache for
the workflow-execution hot-path (``get_with_cache``), absorbed from the
deleted ``ConfigResolver.get_organization`` in the 2026-05 overhaul.
"""

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Organization
# SDK Organization dataclass returned by get_with_cache — distinct from the ORM
# Organization above (which this repo is generic over). Imported at module level
# so the return annotation resolves to the right type; src.sdk.context is a thin
# re-export of bifrost._execution_context with no circular-import risk here.
from src.sdk.context import Organization as SDKOrg
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class OrganizationRepository(BaseRepository[Organization]):  # type: ignore[type-var]
    """
    Repository for Organization entities.
    """

    model = Organization

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_with_cache(
        self, org_id: str
    ) -> "SDKOrg | None":
        """Get an organization by ID, Redis-cached.

        Accepts either a bare UUID or ``"ORG:<uuid>"`` (the latter is a
        legacy scope-string format from pre-overhaul callers).

        Returns the SDK ``Organization`` dataclass (NOT the ORM row), so
        callers can pass it through the execution context without
        carrying a SQLAlchemy session.
        """
        # Parse legacy "ORG:<uuid>" format.
        org_uuid_str = org_id[4:] if org_id.startswith("ORG:") else org_id
        try:
            org_uuid = UUID(org_uuid_str)
        except ValueError:
            logger.warning(f"Invalid organization ID format: {org_id}")
            return None

        # Read-through cache.
        cached = await self._get_from_cache(str(org_uuid))
        if cached is not None:
            return SDKOrg(
                id=cached["id"],
                name=cached["name"],
                is_active=cached["is_active"],
                is_provider=cached.get("is_provider", False),
            )

        # Cache miss — load from DB.
        result = await self.session.execute(
            select(Organization).where(Organization.id == org_uuid)
        )
        org_entity = result.scalar_one_or_none()
        if org_entity is None:
            return None

        # Write-through cache.
        await self._set_cache(
            org_id=str(org_entity.id),
            name=org_entity.name,
            domain=org_entity.domain,
            is_active=org_entity.is_active,
            is_provider=org_entity.is_provider,
        )

        return SDKOrg(
            id=str(org_entity.id),
            name=org_entity.name,
            is_active=org_entity.is_active,
            is_provider=org_entity.is_provider,
        )

    async def _get_from_cache(self, org_id: str) -> dict[str, Any] | None:
        try:
            from src.core.cache import get_shared_redis, org_key

            r = await get_shared_redis()
            data = await r.get(org_key(org_id))
            if not data:
                return None
            data_str = data.decode() if isinstance(data, bytes) else data
            return json.loads(data_str)
        except Exception as e:
            logger.warning(f"Failed to get org from cache: {e}")
            return None

    async def _set_cache(
        self,
        org_id: str,
        name: str,
        domain: str | None,
        is_active: bool,
        is_provider: bool = False,
    ) -> None:
        try:
            from src.core.cache import TTL_ORGS, get_shared_redis, org_key

            r = await get_shared_redis()
            await r.set(
                org_key(org_id),
                json.dumps(
                    {
                        "id": org_id,
                        "name": name,
                        "domain": domain,
                        "is_active": is_active,
                        "is_provider": is_provider,
                    }
                ),
                ex=TTL_ORGS,
            )
        except Exception as e:
            logger.warning(f"Failed to populate org cache: {e}")

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
        created_by: str,
        domain: str | None = None,
    ) -> Organization:
        """
        Create a new organization.

        Args:
            name: Organization display name
            created_by: User ID who created the org
            domain: Email domain for auto-provisioning

        Returns:
            Created organization
        """
        org = Organization(
            name=name,
            domain=domain.lower() if domain else None,
            created_by=created_by,
            is_active=True,
        )
        return await self.create(org)
