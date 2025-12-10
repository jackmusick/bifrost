"""
Organization-Scoped Repository

Provides base repository with standardized organization scoping patterns.
All org-scoped repositories should extend this class for consistent
tenant isolation and access control.

Scoping Patterns:
    - Strict: Only resources belonging to the specific org (executions, audit_logs)
    - Cascade: Org resources + global (NULL) resources (forms, secrets, roles, config)
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, or_
from sqlalchemy.ext.asyncio import AsyncSession

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
