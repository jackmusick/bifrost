"""
Organization-Scoped Repository

Provides base repository with standardized organization scoping patterns.
All org-scoped repositories should extend this class for consistent
tenant isolation and access control.

Scoping Patterns:
    - ALL: No filter, superuser sees everything
    - GLOBAL_ONLY: Only global resources (NULL org_id)
    - ORG_ONLY: Only specific org resources (no global fallback)
    - ORG_PLUS_GLOBAL: Org resources + global (NULL) resources (cascade pattern)
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.org_filter import OrgFilterType
from src.models import Base
from src.repositories.base import BaseRepository

ModelT = TypeVar("ModelT", bound=Base)


def _org_filter(model: Any, org_id: UUID | None) -> Any:
    """Filter by organization_id - bypasses type checking for generic model."""
    return model.organization_id == org_id


def _org_is_null(model: Any) -> Any:
    """Check if organization_id is NULL - bypasses type checking for generic model."""
    return model.organization_id.is_(None)


class OrgScopedRepository(BaseRepository[ModelT], Generic[ModelT]):
    """
    Repository with standardized organization scoping patterns.

    Extends BaseRepository with org-aware query filtering methods.
    Use filter_strict() for resources that should only belong to one org.
    Use filter_cascade() for resources that can fall back to global (NULL org).

    Example usage:
        class SecretRepository(OrgScopedRepository[Secret]):
            model = Secret

            async def list_secrets(self) -> list[Secret]:
                query = select(self.model)
                query = self.filter_cascade(query)  # Include global secrets
                result = await self.session.execute(query)
                return list(result.scalars().all())

        class ExecutionRepository(OrgScopedRepository[Execution]):
            model = Execution

            async def list_executions(self) -> list[Execution]:
                query = select(self.model)
                query = self.filter_strict(query)  # Only this org's executions
                result = await self.session.execute(query)
                return list(result.scalars().all())
    """

    def __init__(self, session: AsyncSession, org_id: UUID | None):
        """
        Initialize repository with database session and organization scope.

        Args:
            session: SQLAlchemy async session
            org_id: Organization UUID for scoping (None for global/platform admin scope)
        """
        super().__init__(session)
        self.org_id = org_id

    def filter_strict(self, query: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        """
        Apply strict organization filtering.

        Pattern 1: Only resources belonging to this specific organization.
        Use for: executions, audit_logs, user data

        The resulting query: WHERE organization_id = :org_id

        Args:
            query: SQLAlchemy select query

        Returns:
            Query with org filter applied
        """
        return query.where(_org_filter(self.model, self.org_id))

    def filter_cascade(self, query: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        """
        Apply cascading organization filtering with global fallback.

        Pattern 2: Org-specific resources + global (NULL) resources.
        Use for: forms, secrets, roles, config

        When org_id is set: WHERE organization_id = :org_id OR organization_id IS NULL
        When org_id is None (global scope): WHERE organization_id IS NULL

        Args:
            query: SQLAlchemy select query

        Returns:
            Query with org + global filter applied
        """
        if self.org_id:
            return query.where(
                or_(
                    _org_filter(self.model, self.org_id),
                    _org_is_null(self.model),
                )
            )
        # Global scope (platform admin with no org selected) - only global resources
        return query.where(_org_is_null(self.model))

    def filter_org_only(self, query: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        """
        Filter for resources belonging only to the current org (no global).

        Use when you need org-specific resources without global fallback.
        For example, when creating a resource that should be org-specific.

        Args:
            query: SQLAlchemy select query

        Returns:
            Query filtered to current org only (excludes global)
        """
        if self.org_id:
            return query.where(_org_filter(self.model, self.org_id))
        # Global scope - only global resources
        return query.where(_org_is_null(self.model))

    def filter_global_only(self, query: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        """
        Filter for global resources only (NULL organization_id).

        Use when you specifically need platform-wide resources.

        Args:
            query: SQLAlchemy select query

        Returns:
            Query filtered to global resources only
        """
        return query.where(_org_is_null(self.model))

    @property
    def is_global_scope(self) -> bool:
        """Check if repository is operating in global scope."""
        return self.org_id is None

    def apply_filter(
        self,
        query: Select[tuple[ModelT]],
        filter_type: OrgFilterType,
        filter_org: UUID | None = None,
    ) -> Select[tuple[ModelT]]:
        """
        Apply organization filter based on filter type.

        This is the unified filtering method that handles all OrgFilterType cases.
        Use this in list endpoints that support the `scope` query parameter.

        Args:
            query: SQLAlchemy select query
            filter_type: The type of filter to apply (from resolve_org_filter)
            filter_org: Organization UUID for ORG_ONLY and ORG_PLUS_GLOBAL
                        (defaults to self.org_id if not provided)

        Returns:
            Query with organization filter applied

        Example:
            filter_type, filter_org = resolve_org_filter(ctx.user, scope)
            repo = MyRepository(ctx.db, filter_org)
            query = select(Model)
            query = repo.apply_filter(query, filter_type, filter_org)
        """
        # Use provided filter_org or fall back to instance org_id
        org_id = filter_org if filter_org is not None else self.org_id

        if filter_type == OrgFilterType.ALL:
            # No filter - superuser sees everything
            return query
        elif filter_type == OrgFilterType.GLOBAL_ONLY:
            # Only global resources (NULL org_id)
            return query.where(_org_is_null(self.model))
        elif filter_type == OrgFilterType.ORG_ONLY:
            # Only specific org resources (no global fallback)
            return query.where(_org_filter(self.model, org_id))
        elif filter_type == OrgFilterType.ORG_PLUS_GLOBAL:
            # Org resources + global (cascade pattern)
            if org_id:
                return query.where(
                    or_(
                        _org_filter(self.model, org_id),
                        _org_is_null(self.model),
                    )
                )
            # If no org_id, fall back to global only
            return query.where(_org_is_null(self.model))
        else:
            # Unknown filter type - default to global only (safest)
            return query.where(_org_is_null(self.model))
