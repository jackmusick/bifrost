"""
Roles management SDK for Bifrost.

Provides Python API for role operations (CRUD + user/form assignments).

All methods are async and must be awaited.
"""

from __future__ import annotations

import json as json_module
import logging
from datetime import datetime
from typing import Any

from src.core.cache import (
    get_redis,
    role_forms_key,
    role_users_key,
    roles_hash_key,
)
from src.models import Role as RoleSchema

from ._internal import get_context, require_permission
from ._write_buffer import get_write_buffer

logger = logging.getLogger(__name__)


def _cache_to_schema(cache_data: dict[str, Any]) -> RoleSchema:
    """Convert cached role data to Pydantic RoleSchema."""
    now = datetime.utcnow()
    return RoleSchema(
        id=cache_data.get("id", ""),
        name=cache_data.get("name", ""),
        description=cache_data.get("description"),
        is_active=cache_data.get("is_active", True),
        created_by=cache_data.get("created_by") or "system",
        created_at=cache_data.get("created_at") or now,
        updated_at=cache_data.get("updated_at") or now,
    )


class roles:
    """
    Role management operations.

    Provides CRUD operations for roles and user/form assignments.
    Reads from Redis cache, writes to buffer (flushed post-execution).

    All methods are async - await is required.
    """

    @staticmethod
    async def create(name: str, description: str = "") -> RoleSchema:
        """
        Create a new role.

        Requires: Platform admin or organization admin privileges

        Args:
            name: Role name
            description: Role description (optional)

        Returns:
            Role: Created role object

        Raises:
            PermissionError: If user lacks permission
            ValueError: If validation fails
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> role = await roles.create(
            ...     "Customer Manager",
            ...     description="Can manage customer data"
            ... )
        """
        context = require_permission("roles.create")

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Write to buffer (generates role ID)
        buffer = get_write_buffer()
        role_id = await buffer.add_role_change(
            operation="create",
            role_id=None,
            data={
                "name": name,
                "description": description,
            },
            org_id=org_id,
        )

        # Return schema with generated ID
        now = datetime.utcnow()
        return RoleSchema(
            id=role_id,
            name=name,
            description=description,
            is_active=True,
            created_by=context.user_id,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    async def get(role_id: str) -> RoleSchema:
        """
        Get role by ID.

        Reads from Redis cache (pre-warmed).

        Args:
            role_id: Role ID

        Returns:
            Role: Role object

        Raises:
            ValueError: If role not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> role = await roles.get("role-123")
            >>> print(role.name)
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read from Redis cache (pre-warmed)
        async with get_redis() as r:
            data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]

            if not data:
                raise ValueError(f"Role not found: {role_id}")

            try:
                cache_data = json_module.loads(data)
                return _cache_to_schema(cache_data)
            except json_module.JSONDecodeError:
                raise ValueError(f"Invalid role data: {role_id}")

    @staticmethod
    async def list() -> list[RoleSchema]:
        """
        List all roles in the current organization.

        Reads from Redis cache (pre-warmed).

        Returns:
            list[Role]: List of role objects

        Raises:
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> all_roles = await roles.list()
            >>> for role in all_roles:
            ...     print(f"{role.name}: {role.description}")
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read all roles from Redis hash (pre-warmed)
        async with get_redis() as r:
            all_data = await r.hgetall(roles_hash_key(org_id))  # type: ignore[misc]

            if not all_data:
                return []

            roles_list: list[RoleSchema] = []
            for data in all_data.values():
                try:
                    cache_data = json_module.loads(data)
                    roles_list.append(_cache_to_schema(cache_data))
                except json_module.JSONDecodeError:
                    continue

            # Sort by name
            roles_list.sort(key=lambda r: r.name or "")

            return roles_list

    @staticmethod
    async def update(role_id: str, **updates: Any) -> RoleSchema:
        """
        Update a role.

        Requires: Platform admin or organization admin privileges

        Args:
            role_id: Role ID
            **updates: Fields to update (name, description)

        Returns:
            Role: Updated role object

        Raises:
            PermissionError: If user lacks permission
            ValueError: If role not found or validation fails
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> role = await roles.update(
            ...     "role-123",
            ...     description="Updated description"
            ... )
        """
        context = require_permission("roles.update")

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Verify role exists in cache first
        async with get_redis() as r:
            data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not data:
                raise ValueError(f"Role not found: {role_id}")

            existing = json_module.loads(data)

        # Apply updates
        updated_data = {
            "name": updates.get("name", existing.get("name")),
            "description": updates.get("description", existing.get("description")),
        }

        # Write to buffer
        buffer = get_write_buffer()
        await buffer.add_role_change(
            operation="update",
            role_id=role_id,
            data=updated_data,
            org_id=org_id,
        )

        # Return updated schema
        return RoleSchema(
            id=role_id,
            name=updated_data["name"],
            description=updated_data["description"],
            is_active=existing.get("is_active", True),
            created_by=existing.get("created_by"),
            created_at=existing.get("created_at"),
            updated_at=existing.get("updated_at"),
        )

    @staticmethod
    async def delete(role_id: str) -> None:
        """
        Delete a role (soft delete - sets is_active to false).

        Requires: Platform admin or organization admin privileges

        Args:
            role_id: Role ID

        Raises:
            PermissionError: If user lacks permission
            ValueError: If role not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> await roles.delete("role-123")
        """
        context = require_permission("roles.delete")

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Verify role exists in cache first
        async with get_redis() as r:
            data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not data:
                raise ValueError(f"Role not found: {role_id}")

        # Write delete to buffer
        buffer = get_write_buffer()
        await buffer.add_role_change(
            operation="delete",
            role_id=role_id,
            data={},
            org_id=org_id,
        )

    @staticmethod
    async def list_users(role_id: str) -> list[str]:
        """
        List all user IDs assigned to a role.

        Reads from Redis cache (pre-warmed).

        Args:
            role_id: Role ID

        Returns:
            list[str]: List of user IDs

        Raises:
            ValueError: If role not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> user_ids = await roles.list_users("role-123")
            >>> for user_id in user_ids:
            ...     print(user_id)
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read from Redis cache (pre-warmed)
        async with get_redis() as r:
            # Verify role exists
            role_data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not role_data:
                raise ValueError(f"Role not found: {role_id}")

            # Get user IDs from set
            user_ids = await r.smembers(role_users_key(org_id, role_id))  # type: ignore[misc]
            return list(user_ids) if user_ids else []

    @staticmethod
    async def list_forms(role_id: str) -> list[str]:
        """
        List all form IDs assigned to a role.

        Reads from Redis cache (pre-warmed).

        Args:
            role_id: Role ID

        Returns:
            list[str]: List of form IDs

        Raises:
            ValueError: If role not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> form_ids = await roles.list_forms("role-123")
            >>> for form_id in form_ids:
            ...     print(form_id)
        """
        context = get_context()

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Read from Redis cache (pre-warmed)
        async with get_redis() as r:
            # Verify role exists
            role_data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not role_data:
                raise ValueError(f"Role not found: {role_id}")

            # Get form IDs from set
            form_ids = await r.smembers(role_forms_key(org_id, role_id))  # type: ignore[misc]
            return list(form_ids) if form_ids else []

    @staticmethod
    async def assign_users(role_id: str, user_ids: list[str]) -> None:
        """
        Assign users to a role.

        Requires: Platform admin or organization admin privileges

        Args:
            role_id: Role ID
            user_ids: List of user IDs to assign

        Raises:
            PermissionError: If user lacks permission
            ValueError: If role or users not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> await roles.assign_users("role-123", ["user-1", "user-2"])
        """
        context = require_permission("roles.assign_users")

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Verify role exists in cache
        async with get_redis() as r:
            role_data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not role_data:
                raise ValueError(f"Role not found: {role_id}")

        # Write to buffer
        buffer = get_write_buffer()
        await buffer.add_role_users_change(
            role_id=role_id,
            user_ids=user_ids,
            org_id=org_id,
        )

    @staticmethod
    async def assign_forms(role_id: str, form_ids: list[str]) -> None:
        """
        Assign forms to a role.

        Requires: Platform admin or organization admin privileges

        Args:
            role_id: Role ID
            form_ids: List of form IDs to assign

        Raises:
            PermissionError: If user lacks permission
            ValueError: If role or forms not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import roles
            >>> await roles.assign_forms("role-123", ["form-1", "form-2"])
        """
        context = require_permission("roles.assign_forms")

        org_id = None
        if context.org_id and context.org_id != "GLOBAL":
            org_id = context.org_id

        # Verify role exists in cache
        async with get_redis() as r:
            role_data = await r.hget(roles_hash_key(org_id), role_id)  # type: ignore[misc]
            if not role_data:
                raise ValueError(f"Role not found: {role_id}")

        # Write to buffer
        buffer = get_write_buffer()
        await buffer.add_role_forms_change(
            role_id=role_id,
            form_ids=form_ids,
            org_id=org_id,
        )
