"""
Authorization Service

Provides permission checking and access control for the Bifrost platform.
This service handles three layers of access control:

1. Organization Scoping (OrgScopedRepository)
   - Tenant isolation via organization_id filtering
   - PlatformAdmins can access any org via X-Organization-Id header

2. Role-Based Access Control
   - Forms can be restricted to specific roles
   - accessLevel: "authenticated" (any logged-in user) or "role_based" (role membership required)

3. User-Level Ownership
   - Executions are filtered by the user who triggered them
   - PlatformAdmins can view all executions in scope
"""

import logging
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import ExecutionContext
from src.models import Form, UserRole, Execution

logger = logging.getLogger(__name__)


class AuthorizationService:
    """
    Service for checking user permissions and access control.

    This service is stateless and operates on the provided ExecutionContext.
    """

    def __init__(self, db: AsyncSession, context: ExecutionContext):
        """
        Initialize authorization service.

        Args:
            db: Database session
            context: Execution context with user and org scope
        """
        self.db = db
        self.context = context

    # =========================================================================
    # Role Queries
    # =========================================================================

    async def get_user_role_ids(self, user_id: UUID | None = None) -> list[str]:
        """
        Get all role IDs (UUIDs) assigned to a user.

        Args:
            user_id: User ID (defaults to current user from context)

        Returns:
            List of role UUID strings
        """
        uid = user_id or self.context.user.user_id

        query = select(UserRole.role_id).where(UserRole.user_id == uid)
        result = await self.db.execute(query)
        return [str(row) for row in result.scalars().all()]

    async def get_form_role_ids(self, form_id: UUID) -> list[str]:
        """
        Get all role IDs (UUIDs) that can access a form.

        Args:
            form_id: Form ID (UUID)

        Returns:
            List of role UUID strings
        """
        # Forms store assigned_roles as a JSON array of role IDs
        query = select(Form.assigned_roles).where(Form.id == form_id)
        result = await self.db.execute(query)
        assigned_roles = result.scalar_one_or_none()

        if assigned_roles is None:
            return []

        return [str(role_id) for role_id in assigned_roles]

    # =========================================================================
    # Form Access Control
    # =========================================================================

    async def can_user_view_form(self, form_id: UUID) -> bool:
        """
        Check if user can view a form.

        Rules:
        - Platform admins: can view all forms (active and inactive)
        - Regular users:
            - Must be active form
            - accessLevel="authenticated" -> any authenticated user
            - accessLevel="role_based" (or None) -> user must have assigned role

        Args:
            form_id: Form ID (UUID)

        Returns:
            True if user can view form, False otherwise
        """
        # Get form (with org scoping - includes global forms)
        form = await self._get_form_with_scoping(form_id)

        if not form:
            return False

        # Platform admins can view all forms (including inactive)
        if self.context.is_platform_admin:
            return True

        # Regular users can only view active forms
        if not form.is_active:
            return False

        # Check access level (default to role_based if not set)
        access_level = form.access_level or "role_based"

        if access_level == "authenticated":
            # Any authenticated user can access
            return True
        elif access_level == "role_based":
            # Check role membership
            user_roles = await self.get_user_role_ids()
            form_roles = await self.get_form_role_ids(form_id)
            return any(role in form_roles for role in user_roles)

        return False

    async def can_user_execute_form(self, form_id: UUID) -> bool:
        """
        Check if user can execute a form.

        Same rules as can_user_view_form (if you can view it, you can execute it).

        Args:
            form_id: Form ID (UUID)

        Returns:
            True if user can execute form, False otherwise
        """
        return await self.can_user_view_form(form_id)

    async def get_user_visible_forms(self, active_only: bool = True) -> list[Form]:
        """
        Get all forms visible to the user (filtered by permissions).

        Rules:
        - Platform admins: see all forms (active and inactive) in context.org_id scope
        - Regular users: see active forms they have access to based on accessLevel:
            - authenticated: all active forms with this access level
            - role_based: only forms where user has an assigned role

        Args:
            active_only: If True, only return active forms (ignored for platform admins)

        Returns:
            List of Form objects
        """
        # Base query with org scoping (org + global)
        query = select(Form)
        if self.context.org_id:
            query = query.where(
                or_(
                    Form.organization_id == self.context.org_id,
                    Form.organization_id.is_(None),
                )
            )
        else:
            query = query.where(Form.organization_id.is_(None))

        # Platform admin sees all forms (including inactive) in their current scope
        if self.context.is_platform_admin:
            if active_only:
                query = query.where(Form.is_active)
            result = await self.db.execute(query)
            return list(result.scalars().all())

        # Regular user: filter to active only
        query = query.where(Form.is_active)
        result = await self.db.execute(query)
        all_forms = list(result.scalars().all())

        # Get user's role IDs once for efficiency
        user_role_ids = await self.get_user_role_ids()

        # Filter forms by access level
        visible_forms = []
        for form in all_forms:
            access_level = form.access_level or "role_based"

            if access_level == "authenticated":
                # Any authenticated user can see this form
                visible_forms.append(form)
            elif access_level == "role_based":
                # Check if user has any of the roles assigned to this form
                form_role_ids = [str(r) for r in (form.assigned_roles or [])]
                if any(role_id in form_role_ids for role_id in user_role_ids):
                    visible_forms.append(form)

        return visible_forms

    # =========================================================================
    # Execution Access Control
    # =========================================================================

    def can_user_view_execution(self, execution: Execution) -> bool:
        """
        Check if user can view an execution.

        Rules:
        - Platform admins: can view all executions
        - Regular users: can only view THEIR executions

        Args:
            execution: Execution entity

        Returns:
            True if user can view execution, False otherwise
        """
        # Platform admins can view all
        if self.context.is_platform_admin:
            return True

        # Regular users can only view their own executions
        return execution.executed_by == self.context.user.user_id

    async def get_user_executions(self, limit: int = 50) -> list[Execution]:
        """
        Get executions visible to the user.

        Rules:
        - Platform admins: all executions in context.org_id scope
        - Regular users: only THEIR executions

        Args:
            limit: Maximum number of executions to return

        Returns:
            List of Execution objects
        """
        query = select(Execution)

        # Org scoping (strict - no global fallback for executions)
        if self.context.org_id:
            query = query.where(Execution.organization_id == self.context.org_id)
        else:
            query = query.where(Execution.organization_id.is_(None))

        # User-level filtering for non-admins
        if not self.context.is_platform_admin:
            query = query.where(Execution.executed_by == self.context.user.user_id)

        # Order by most recent and limit
        query = query.order_by(Execution.started_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _get_form_with_scoping(self, form_id: UUID) -> Form | None:
        """
        Get form by ID with org scoping (includes global forms).

        Args:
            form_id: Form ID

        Returns:
            Form or None if not found/not accessible
        """
        query = select(Form).where(Form.id == form_id)

        # Apply org scoping (cascade pattern - org + global)
        if self.context.org_id:
            query = query.where(
                or_(
                    Form.organization_id == self.context.org_id,
                    Form.organization_id.is_(None),
                )
            )
        else:
            query = query.where(Form.organization_id.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


# Convenience function for creating service from context
def get_authorization_service(context: ExecutionContext) -> AuthorizationService:
    """
    Create authorization service from execution context.

    Args:
        context: Execution context (contains db session)

    Returns:
        AuthorizationService instance
    """
    return AuthorizationService(context.db, context)
