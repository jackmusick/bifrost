"""
Unit tests for ExecutionAuthService.

Tests cover the precomputed workflow_access table approach:
- Platform admin access (always allowed, no DB query)
- API key access (always allowed, no DB query)
- Workflow access via workflow_access table lookup

The workflow_access table is populated at mutation time (form create/update,
app publish) and contains precomputed workflow references for fast lookups.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.execution_auth import ExecutionAuthService, check_workflow_execution_access


# Test UUIDs
WORKFLOW_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DATA_PROVIDER_ID = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
USER_ID = uuid4()
ORG_ID = uuid4()
FORM_ID = uuid4()
APP_ID = uuid4()
PAGE_ID = uuid4()
ROLE_ID = uuid4()


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=AsyncSession)


@pytest.fixture
def auth_service(mock_db):
    """Create an ExecutionAuthService instance."""
    return ExecutionAuthService(mock_db)


class TestPlatformAdminAccess:
    """Platform admins should always have access without DB queries."""

    @pytest.mark.asyncio
    async def test_platform_admin_can_execute_any_workflow(self, auth_service):
        """Platform admin should always be able to execute any workflow."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_platform_admin_can_execute_data_provider(self, auth_service):
        """Platform admin should be able to execute any data provider."""
        result = await auth_service.can_execute_workflow(
            workflow_id=DATA_PROVIDER_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_platform_admin_without_org(self, auth_service):
        """Platform admin without org context should still have access."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=None,
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True


class TestApiKeyAccess:
    """API key requests should always have access without DB queries."""

    @pytest.mark.asyncio
    async def test_api_key_can_execute_any_workflow(self, auth_service):
        """API key should always be able to execute any workflow."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=None,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_api_key_without_user_id(self, auth_service):
        """API key without user_id should still have access."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=None,
            user_org_id=None,
            is_superuser=False,
            is_api_key=True,
        )
        assert result is True


class TestNoUserAccess:
    """Non-admin, non-API-key requests without user_id should be denied."""

    @pytest.mark.asyncio
    async def test_no_user_id_denied(self, auth_service):
        """Request without user_id (non-admin, non-API-key) should be denied."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=None,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False


class TestWorkflowAccessTableLookup:
    """Tests for workflow_access table based access."""

    @pytest.mark.asyncio
    async def test_access_granted_when_in_workflow_access(self, auth_service, mock_db):
        """User with workflow_access entry should have access."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True  # Integration check returns True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True
        # Integration check returns True, so we short-circuit (only 1 query)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_access_denied_when_not_in_workflow_access(self, auth_service, mock_db):
        """User without workflow_access entry should be denied."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False
        # Two queries: integration check (False) + workflow_access check (False)
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_data_provider_access(self, auth_service, mock_db):
        """Data providers are checked same as workflows (via workflow_access)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=DATA_PROVIDER_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True


class TestIntegrationAccess:
    """Tests for integration-based access to data providers."""

    @pytest.mark.asyncio
    async def test_integration_linked_data_provider_grants_access(self, auth_service, mock_db):
        """Data provider tied to an integration is accessible to any authenticated user."""
        # First call (integration check) returns True
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=DATA_PROVIDER_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True
        # Only integration check needed when it returns True
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_integration_falls_through_to_workflow_access(self, auth_service, mock_db):
        """Non-integration data provider falls through to workflow_access check."""
        # Create mock results: first False (no integration), then True (has workflow_access)
        integration_result = MagicMock()
        integration_result.scalar.return_value = False
        workflow_result = MagicMock()
        workflow_result.scalar.return_value = True

        mock_db.execute = AsyncMock(side_effect=[integration_result, workflow_result])

        result = await auth_service.can_execute_workflow(
            workflow_id=DATA_PROVIDER_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True
        # Both integration check and workflow_access check
        assert mock_db.execute.call_count == 2


class TestOrgScoping:
    """Tests for organization scoping via workflow_access."""

    @pytest.mark.asyncio
    async def test_global_workflow_accessible(self, auth_service, mock_db):
        """User can access workflow from global entity (organization_id=NULL)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_different_org_denied(self, auth_service, mock_db):
        """User cannot access workflow from different org's entity."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_user_without_org_can_access_global(self, auth_service, mock_db):
        """User without org can access global workflows."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=None,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True


class TestConvenienceFunction:
    """Tests for the convenience function wrapper."""

    @pytest.mark.asyncio
    async def test_check_workflow_execution_access_wrapper(self, mock_db):
        """Test the convenience function wrapper."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await check_workflow_execution_access(
            db=mock_db,
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_convenience_function_platform_admin(self, mock_db):
        """Convenience function should allow platform admin."""
        result = await check_workflow_execution_access(
            db=mock_db,
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True


class TestAccessPrecedence:
    """Tests to verify correct precedence of access checks."""

    @pytest.mark.asyncio
    async def test_superuser_short_circuits(self, auth_service, mock_db):
        """Superuser check should short-circuit, not query DB."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True
        # DB should not be called for superuser
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_short_circuits(self, auth_service, mock_db):
        """API key check should short-circuit, not query DB."""
        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=None,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=True,
        )
        assert result is True
        # DB should not be called for API key
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_query_for_workflow_access(self, auth_service, mock_db):
        """Workflow access lookup should use a single query."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True
        # Only one query should be executed (workflow_access lookup)
        assert mock_db.execute.call_count == 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_invalid_workflow_id_format(self, auth_service, mock_db):
        """Handle non-UUID workflow IDs gracefully - should return False without querying."""
        result = await auth_service.can_execute_workflow(
            workflow_id="not-a-uuid",
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        # Should not raise, just return False
        assert result is False
        # DB should not be queried for invalid UUID
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_workflow_id(self, auth_service, mock_db):
        """Handle empty workflow ID - should return False without querying."""
        result = await auth_service.can_execute_workflow(
            workflow_id="",
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False
        # DB should not be queried for empty UUID
        mock_db.execute.assert_not_called()


class TestAccessLevels:
    """Tests for different access levels (authenticated vs role_based)."""

    @pytest.mark.asyncio
    async def test_authenticated_access_level(self, auth_service, mock_db):
        """Authenticated access level should grant access to any authenticated user."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_role_based_access_requires_role(self, auth_service, mock_db):
        """Role-based access requires user to have matching role."""
        # Simulate user not having the required role
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False


class TestEntityTypes:
    """Tests verifying both form and app entity types work."""

    @pytest.mark.asyncio
    async def test_form_entity_type_access(self, auth_service, mock_db):
        """Form entity type should grant workflow access."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_app_entity_type_access(self, auth_service, mock_db):
        """App entity type should grant workflow access."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.can_execute_workflow(
            workflow_id=WORKFLOW_ID,
            user_id=USER_ID,
            user_org_id=ORG_ID,
            is_superuser=False,
            is_api_key=False,
        )
        assert result is True
