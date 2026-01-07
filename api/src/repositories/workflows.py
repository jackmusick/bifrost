"""
Workflow Repository

Database operations for workflow registry.
Replaces scan_all_workflows() with efficient database queries.

The workflows table now stores all executable types:
- 'workflow': Standard workflows (@workflow decorator)
- 'tool': AI agent tools (@tool decorator)
- 'data_provider': Data providers for forms/app builder (@data_provider decorator)

Organization Scoping:
- Workflows with organization_id = NULL are global (available to all orgs)
- Workflows with organization_id set are org-scoped
- Queries filter: global + user's org (unless platform admin requests all)
"""

from datetime import datetime
from typing import Literal, Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.sql import Select

from src.models import Workflow
from src.repositories.base import BaseRepository

# Type discriminator values
WorkflowType = Literal["workflow", "tool", "data_provider"]


class WorkflowRepository(BaseRepository[Workflow]):
    """Repository for workflow registry operations."""

    model = Workflow

    # ==========================================================================
    # Organization Scoping Helpers
    # ==========================================================================

    def _apply_org_filter(
        self,
        stmt: Select,
        org_id: UUID | None = None,
        include_global: bool = True,
    ) -> Select:
        """Apply organization scoping filter to a query.

        Args:
            stmt: SQLAlchemy select statement
            org_id: If provided, filter to this org (+ global if include_global=True)
                   If None, return all workflows (no org filter)
            include_global: Whether to include global (organization_id=NULL) workflows

        Returns:
            Modified statement with org filter applied
        """
        if org_id is None:
            # No filtering - return all (for platform admins viewing all)
            return stmt

        if include_global:
            # Standard case: org's workflows + global workflows
            return stmt.where(
                or_(
                    Workflow.organization_id == org_id,
                    Workflow.organization_id.is_(None),
                )
            )
        else:
            # Only org-specific workflows (no global)
            return stmt.where(Workflow.organization_id == org_id)

    # ==========================================================================
    # Type-Based Queries
    # ==========================================================================

    async def get_by_type(
        self,
        type: WorkflowType,
        active_only: bool = True,
        org_id: UUID | None = None,
    ) -> Sequence[Workflow]:
        """Get workflows filtered by type.

        Args:
            type: The type to filter by ('workflow', 'tool', 'data_provider')
            active_only: If True, only return active workflows
            org_id: If provided, filter to org + global. If None, return all.

        Returns:
            Sequence of workflows matching the type
        """
        stmt = select(Workflow).where(Workflow.type == type)
        if active_only:
            stmt = stmt.where(Workflow.is_active.is_(True))
        stmt = self._apply_org_filter(stmt, org_id)
        stmt = stmt.order_by(Workflow.name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_data_providers(
        self,
        active_only: bool = True,
        org_id: UUID | None = None,
    ) -> Sequence[Workflow]:
        """Get all data providers.

        Convenience method for get_by_type('data_provider').
        """
        return await self.get_by_type("data_provider", active_only=active_only, org_id=org_id)

    async def get_tools(
        self,
        active_only: bool = True,
        org_id: UUID | None = None,
    ) -> Sequence[Workflow]:
        """Get all AI agent tools.

        Convenience method for get_by_type('tool').
        """
        return await self.get_by_type("tool", active_only=active_only, org_id=org_id)

    async def get_workflows_only(
        self,
        active_only: bool = True,
        org_id: UUID | None = None,
    ) -> Sequence[Workflow]:
        """Get only workflows (excludes tools and data providers).

        Convenience method for get_by_type('workflow').
        """
        return await self.get_by_type("workflow", active_only=active_only, org_id=org_id)

    # ==========================================================================
    # Standard Queries
    # ==========================================================================

    async def get_by_name(self, name: str) -> Workflow | None:
        """Get workflow by name."""
        result = await self.session.execute(
            select(Workflow).where(Workflow.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_name_and_type(
        self,
        name: str,
        type: WorkflowType,
        active_only: bool = True,
    ) -> Workflow | None:
        """Get workflow by name and type.

        Args:
            name: Workflow name to look up
            type: Type filter ('workflow', 'tool', 'data_provider')
            active_only: If True, only return active workflows

        Returns:
            Workflow if found, None otherwise
        """
        stmt = select(Workflow).where(
            Workflow.name == name,
            Workflow.type == type,
        )
        if active_only:
            stmt = stmt.where(Workflow.is_active.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(self, org_id: UUID | None = None) -> Sequence[Workflow]:
        """Get all active workflows.

        Args:
            org_id: If provided, filter to org + global. If None, return all.
        """
        stmt = select(Workflow).where(Workflow.is_active.is_(True))
        stmt = self._apply_org_filter(stmt, org_id)
        stmt = stmt.order_by(Workflow.name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_scheduled(self) -> Sequence[Workflow]:
        """Get all active workflows with schedules (for CRON processing)."""
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.schedule.isnot(None))
            .order_by(Workflow.name)
        )
        return result.scalars().all()

    async def get_endpoint_enabled(self) -> Sequence[Workflow]:
        """Get all active workflows with endpoint enabled."""
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.endpoint_enabled.is_(True))
            .order_by(Workflow.name)
        )
        return result.scalars().all()

    async def get_by_category(self, category: str) -> Sequence[Workflow]:
        """Get all active workflows in a category."""
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.category == category)
            .order_by(Workflow.name)
        )
        return result.scalars().all()

    async def count_active(self) -> int:
        """Count all active workflows."""
        result = await self.session.execute(
            select(func.count(Workflow.id))
            .where(Workflow.is_active.is_(True))
        )
        return result.scalar() or 0

    async def search(
        self,
        query: str | None = None,
        category: str | None = None,
        type: WorkflowType | None = None,
        has_schedule: bool | None = None,
        endpoint_enabled: bool | None = None,
        org_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Workflow]:
        """Search workflows with filters.

        Args:
            query: Text search in name/description
            category: Filter by category
            type: Filter by type ('workflow', 'tool', 'data_provider')
            has_schedule: Filter by whether schedule is set
            endpoint_enabled: Filter by endpoint_enabled flag
            org_id: If provided, filter to org + global. If None, return all.
            limit: Maximum number of results
            offset: Result offset for pagination

        Returns:
            Sequence of matching workflows
        """
        stmt = select(Workflow).where(Workflow.is_active.is_(True))

        # Apply org filter
        stmt = self._apply_org_filter(stmt, org_id)

        if query:
            stmt = stmt.where(
                Workflow.name.ilike(f"%{query}%") |
                Workflow.description.ilike(f"%{query}%")
            )

        if category:
            stmt = stmt.where(Workflow.category == category)

        if type:
            stmt = stmt.where(Workflow.type == type)

        if has_schedule is not None:
            if has_schedule:
                stmt = stmt.where(Workflow.schedule.isnot(None))
            else:
                stmt = stmt.where(Workflow.schedule.is_(None))

        if endpoint_enabled is not None:
            stmt = stmt.where(Workflow.endpoint_enabled == endpoint_enabled)

        stmt = stmt.order_by(Workflow.name).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ==========================================================================
    # API Key Operations
    # ==========================================================================

    async def get_by_api_key_hash(self, key_hash: str) -> Workflow | None:
        """Get workflow by API key hash."""
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.api_key_hash == key_hash)
            .where(Workflow.api_key_enabled.is_(True))
            .where(Workflow.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def set_api_key(
        self,
        workflow_id: UUID,
        key_hash: str,
        description: str | None,
        created_by: str,
        expires_at: datetime | None = None,
    ) -> Workflow | None:
        """Set API key for a workflow."""
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            return None

        workflow.api_key_hash = key_hash
        workflow.api_key_description = description
        workflow.api_key_enabled = True
        workflow.api_key_created_by = created_by
        workflow.api_key_created_at = datetime.utcnow()
        workflow.api_key_expires_at = expires_at
        workflow.api_key_last_used_at = None

        await self.session.flush()
        return workflow

    async def revoke_api_key(self, workflow_id: UUID) -> Workflow | None:
        """Revoke API key for a workflow."""
        workflow = await self.get_by_id(workflow_id)
        if not workflow:
            return None

        workflow.api_key_enabled = False
        await self.session.flush()
        return workflow

    async def update_api_key_last_used(self, workflow_id: UUID) -> None:
        """Update last used timestamp for API key."""
        workflow = await self.get_by_id(workflow_id)
        if workflow:
            workflow.api_key_last_used_at = datetime.utcnow()
            await self.session.flush()

    async def get_endpoint_workflow_by_name(self, name: str) -> Workflow | None:
        """
        Get endpoint-enabled workflow by name.

        Used by the /api/endpoints/{workflow_name} route to resolve
        user-friendly names to workflow IDs.

        Args:
            name: Workflow name to look up

        Returns:
            Workflow if exactly one found, None if not found

        Raises:
            ValueError: If multiple endpoint-enabled workflows have the same name
                        (includes file paths for debugging)
        """
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.name == name)
            .where(Workflow.endpoint_enabled.is_(True))
            .where(Workflow.is_active.is_(True))
        )
        workflows = list(result.scalars().all())

        if len(workflows) == 0:
            return None

        if len(workflows) > 1:
            paths = [w.path for w in workflows]
            raise ValueError(
                f"Multiple endpoint-enabled workflows named '{name}' found: {paths}"
            )

        return workflows[0]

    async def validate_api_key(
        self,
        key_hash: str,
        workflow_name: str | None = None,
    ) -> tuple[bool, UUID | None]:
        """
        Validate an API key.

        Args:
            key_hash: SHA-256 hash of the API key
            workflow_name: If provided, validates key works for this workflow

        Returns:
            Tuple of (is_valid, workflow_id)
        """
        # Check for workflow-specific key
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.api_key_hash == key_hash)
            .where(Workflow.api_key_enabled.is_(True))
            .where(Workflow.is_active.is_(True))
        )
        workflow = result.scalar_one_or_none()

        if workflow:
            # Check expiration
            if workflow.api_key_expires_at and workflow.api_key_expires_at < datetime.utcnow():
                return False, None

            # If workflow_name provided, verify it matches
            if workflow_name and workflow.name != workflow_name:
                return False, None

            return True, workflow.id

        return False, None
