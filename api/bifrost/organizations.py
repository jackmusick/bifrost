"""
Organization management SDK for Bifrost.

Provides Python API for organization operations from workflows.

All methods are async and must be awaited.
"""

from __future__ import annotations

import json as json_module
import logging
from datetime import datetime
from typing import Any

from src.core.cache import get_redis, org_key, orgs_list_key
from src.models.models import Organization as OrganizationSchema

from ._internal import get_context, require_admin
from ._write_buffer import get_write_buffer

logger = logging.getLogger(__name__)


def _cache_to_schema(cache_data: dict[str, Any]) -> OrganizationSchema:
    """Convert cached org data to Pydantic OrganizationSchema."""
    now = datetime.utcnow()
    return OrganizationSchema(
        id=cache_data.get("id", ""),
        name=cache_data.get("name", ""),
        domain=cache_data.get("domain"),
        is_active=cache_data.get("is_active", True),
        created_by=cache_data.get("created_by") or "system",
        created_at=cache_data.get("created_at") or now,
        updated_at=cache_data.get("updated_at") or now,
    )


class organizations:
    """
    Organization management operations.

    Reads from Redis cache, writes to buffer (flushed post-execution).
    All methods enforce permissions via the execution context.

    All methods are async - await is required.
    """

    @staticmethod
    async def create(name: str, domain: str | None = None, is_active: bool = True) -> OrganizationSchema:
        """
        Create a new organization.

        Requires: Platform admin privileges

        Args:
            name: Organization name
            domain: Organization domain (optional)
            is_active: Whether the organization is active (default: True)

        Returns:
            Organization: Created organization object

        Raises:
            PermissionError: If user is not platform admin
            ValueError: If validation fails
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import organizations
            >>> org = await organizations.create("Acme Corp", domain="acme.com")
        """
        context = require_admin()

        # Write to buffer (generates org ID)
        buffer = get_write_buffer()
        org_id = await buffer.add_org_change(
            operation="create",
            org_id=None,
            data={
                "name": name,
                "domain": domain,
                "is_active": is_active,
            },
        )

        # Return schema with generated ID
        now = datetime.utcnow()
        return OrganizationSchema(
            id=org_id,
            name=name,
            domain=domain,
            is_active=is_active,
            created_by=context.user_id,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    async def get(org_id: str) -> OrganizationSchema:
        """
        Get organization by ID.

        Reads from Redis cache (pre-warmed).

        Args:
            org_id: Organization ID

        Returns:
            Organization: Organization object

        Raises:
            ValueError: If organization not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import organizations
            >>> org = await organizations.get("org-123")
            >>> print(org.name)
        """
        get_context()  # Validates user is authenticated

        # Read from Redis cache (pre-warmed)
        async with get_redis() as r:
            data = await r.get(org_key(org_id))  # type: ignore[misc]

            if not data:
                raise ValueError(f"Organization not found: {org_id}")

            try:
                cache_data = json_module.loads(data)
                return _cache_to_schema(cache_data)
            except json_module.JSONDecodeError:
                raise ValueError(f"Invalid organization data: {org_id}")

    @staticmethod
    async def list() -> list[OrganizationSchema]:
        """
        List all organizations.

        Requires: Platform admin privileges

        Note: This currently queries Postgres since the org list may be large
        and is typically only used by platform admins. For execution-time
        org lookups, use get() which reads from cache.

        Returns:
            list[Organization]: List of organization objects

        Raises:
            PermissionError: If user is not platform admin
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import organizations
            >>> orgs = await organizations.list()
            >>> for org in orgs:
            ...     print(f"{org.name}: {org.domain}")
        """
        require_admin()

        # Read from Redis list (if available)
        async with get_redis() as r:
            org_ids = await r.smembers(orgs_list_key())  # type: ignore[misc]

            if not org_ids:
                return []

            orgs_list: list[OrganizationSchema] = []
            for oid in org_ids:
                data = await r.get(org_key(oid))  # type: ignore[misc]
                if data:
                    try:
                        cache_data = json_module.loads(data)
                        if cache_data.get("is_active", True):
                            orgs_list.append(_cache_to_schema(cache_data))
                    except json_module.JSONDecodeError:
                        continue

            # Sort by name
            orgs_list.sort(key=lambda o: o.name or "")

            return orgs_list

    @staticmethod
    async def update(org_id: str, **updates: Any) -> OrganizationSchema:
        """
        Update an organization.

        Requires: Platform admin privileges

        Args:
            org_id: Organization ID
            **updates: Fields to update (name, domain, is_active)

        Returns:
            Organization: Updated organization object

        Raises:
            PermissionError: If user is not platform admin
            ValueError: If organization not found or validation fails
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import organizations
            >>> org = await organizations.update("org-123", name="New Name")
        """
        require_admin()

        # Verify org exists in cache first
        async with get_redis() as r:
            data = await r.get(org_key(org_id))  # type: ignore[misc]
            if not data:
                raise ValueError(f"Organization not found: {org_id}")

            existing = json_module.loads(data)

        # Apply updates
        updated_data = {
            "name": updates.get("name", existing.get("name")),
            "domain": updates.get("domain", existing.get("domain")),
            "is_active": updates.get("is_active", existing.get("is_active")),
        }

        # Write to buffer
        buffer = get_write_buffer()
        await buffer.add_org_change(
            operation="update",
            org_id=org_id,
            data=updated_data,
        )

        # Return updated schema
        return OrganizationSchema(
            id=org_id,
            name=updated_data["name"],
            domain=updated_data["domain"],
            is_active=updated_data["is_active"],
            created_by=existing.get("created_by"),
            created_at=existing.get("created_at"),
            updated_at=existing.get("updated_at"),
        )

    @staticmethod
    async def delete(org_id: str) -> bool:
        """
        Delete an organization (soft delete - sets is_active to false).

        Requires: Platform admin privileges

        Args:
            org_id: Organization ID

        Returns:
            bool: True if organization was deleted

        Raises:
            PermissionError: If user is not platform admin
            ValueError: If organization not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import organizations
            >>> deleted = await organizations.delete("org-123")
        """
        require_admin()

        # Verify org exists in cache first
        async with get_redis() as r:
            data = await r.get(org_key(org_id))  # type: ignore[misc]
            if not data:
                raise ValueError(f"Organization not found: {org_id}")

        # Write delete to buffer
        buffer = get_write_buffer()
        await buffer.add_org_change(
            operation="delete",
            org_id=org_id,
            data={},
        )

        return True
