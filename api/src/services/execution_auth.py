"""
Execution Authorization Service

Unified permission checking for workflow and data provider execution.
Determines if a user can execute a workflow based on:
1. Platform admin status
2. API key access
3. Precomputed workflow_access table (populated at mutation time)

Uses the workflow_access table for O(1) lookups instead of JSONB traversal.
The table is populated by form create/update and app publish operations.

All workflow ID checks also cover data providers, since data providers
are now stored in the workflows table with type='data_provider'.
"""

import logging
from uuid import UUID

from sqlalchemy import exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.app_roles import AppRole
from src.models.orm.forms import FormRole
from src.models.orm.integrations import Integration
from src.models.orm.users import UserRole
from src.models.orm.workflow_access import WorkflowAccess

logger = logging.getLogger(__name__)


class ExecutionAuthService:
    """
    Service for checking workflow/data provider execution permissions.

    Permission is granted if ANY of:
    1. User is platform admin (superuser)
    2. Request is via API key
    3. User has access via workflow_access table (precomputed at mutation time)

    The workflow_access table is populated when forms are created/updated
    and when apps are published. This allows O(1) authorization checks
    instead of JSONB traversal at execution time.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_execute_workflow(
        self,
        workflow_id: str,
        user_id: UUID | None,
        user_org_id: UUID | None,
        is_superuser: bool,
        is_api_key: bool = False,
    ) -> bool:
        """
        Check if user can execute a workflow.

        Args:
            workflow_id: UUID string of the workflow (or data provider)
            user_id: User UUID (None for API key requests)
            user_org_id: User's organization UUID
            is_superuser: Whether user is platform admin
            is_api_key: Whether request is via API key

        Returns:
            True if execution is allowed
        """
        # 1. Platform admin - always allowed
        if is_superuser:
            logger.debug("Execution allowed: user is platform admin")
            return True

        # 2. API key - always allowed (key validation happens in router)
        if is_api_key:
            logger.debug("Execution allowed: API key access")
            return True

        # Need user_id for access checks
        if not user_id:
            logger.debug("Execution denied: no user_id for non-admin/non-api-key request")
            return False

        # 3. Check integration-based access (data providers tied to integrations)
        # Any authenticated user can access data providers that are linked to integrations
        if await self._has_integration_access(workflow_id):
            logger.debug(f"Execution allowed: workflow {workflow_id} is tied to an integration")
            return True

        # 4. Check precomputed workflow_access table
        if await self._has_workflow_access(workflow_id, user_id, user_org_id):
            logger.debug(f"Execution allowed: user has access to workflow {workflow_id}")
            return True

        logger.debug(f"Execution denied: no access found for workflow {workflow_id}")
        return False

    async def _has_workflow_access(
        self,
        workflow_id: str,
        user_id: UUID,
        user_org_id: UUID | None,
    ) -> bool:
        """
        Check if user has access to a workflow via the precomputed workflow_access table.

        The query:
        1. Finds workflow_access entries for this workflow in user's org (or global)
        2. Checks if access_level is 'authenticated' (any authenticated user)
        3. Or checks if user has a role that grants access (form_roles or app_roles)

        This is O(1) due to the index on (workflow_id, organization_id).
        """
        try:
            workflow_uuid = UUID(workflow_id)
        except ValueError:
            logger.warning(f"Invalid workflow_id format: {workflow_id}")
            return False

        # Subquery for user's role IDs
        user_roles_subq = select(UserRole.role_id).where(UserRole.user_id == user_id)

        # Build the access check query
        # Check if there's a workflow_access entry that grants access
        query = select(
            exists(
                select(literal(1))
                .select_from(WorkflowAccess)
                .where(
                    # Workflow match
                    WorkflowAccess.workflow_id == workflow_uuid,
                    # Org scoping: user's org or global (NULL)
                    (
                        (WorkflowAccess.organization_id == user_org_id)
                        if user_org_id
                        else WorkflowAccess.organization_id.is_(None)
                    )
                    | WorkflowAccess.organization_id.is_(None),
                    # Access level check
                    (
                        # Authenticated: any authenticated user has access
                        (WorkflowAccess.access_level == "authenticated")
                        |
                        # Role-based: check if user has a matching role
                        (
                            # Form access: check form_roles
                            (
                                (WorkflowAccess.entity_type == "form")
                                & exists(
                                    select(FormRole.form_id).where(
                                        FormRole.form_id == WorkflowAccess.entity_id,
                                        FormRole.role_id.in_(user_roles_subq),
                                    )
                                )
                            )
                            |
                            # App access: check app_roles
                            (
                                (WorkflowAccess.entity_type == "app")
                                & exists(
                                    select(AppRole.app_id).where(
                                        AppRole.app_id == WorkflowAccess.entity_id,
                                        AppRole.role_id.in_(user_roles_subq),
                                    )
                                )
                            )
                        )
                    ),
                )
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or False

    async def _has_integration_access(self, workflow_id: str) -> bool:
        """
        Check if workflow is tied to an integration.

        Data providers linked to integrations are accessible to any authenticated user.
        This is a special case for integration entity providers (e.g., list_entities_data_provider_id).

        Returns:
            True if workflow is linked to an active integration
        """
        try:
            workflow_uuid = UUID(workflow_id)
        except ValueError:
            return False

        # Check if this workflow/data provider is tied to an integration
        query = select(
            exists(
                select(Integration.id).where(
                    Integration.list_entities_data_provider_id == workflow_uuid,
                    Integration.is_deleted.is_(False),
                )
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or False


async def check_workflow_execution_access(
    db: AsyncSession,
    workflow_id: str,
    user_id: UUID | None,
    user_org_id: UUID | None,
    is_superuser: bool,
    is_api_key: bool = False,
) -> bool:
    """
    Convenience function to check workflow execution access.

    This is a thin wrapper around ExecutionAuthService for simple use cases.
    """
    service = ExecutionAuthService(db)
    return await service.can_execute_workflow(
        workflow_id=workflow_id,
        user_id=user_id,
        user_org_id=user_org_id,
        is_superuser=is_superuser,
        is_api_key=is_api_key,
    )
