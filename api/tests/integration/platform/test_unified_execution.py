"""
Integration tests for unified execution authorization.

Note: The ExecutionAuthService is comprehensively tested in unit tests
(tests/unit/services/test_execution_auth.py) with mocked database queries.

This file contains integration tests for edge cases that require real
database connections, such as testing the actual SQL queries work correctly.

Most authorization logic is validated by the unit tests which cover:
- Platform admin and API key access bypass
- Form-based workflow access (workflow_id, launch_workflow_id, data_provider_id)
- App-based workflow access (page launch, data sources, component workflows)
- Role-based access control
- Organization scoping
- Published vs draft page handling
"""

import pytest
from uuid import uuid4

from src.services.execution_auth import ExecutionAuthService


class TestExecutionAuthServiceBasic:
    """Basic tests that don't require complex fixture setup."""

    @pytest.mark.asyncio
    async def test_superuser_always_allowed(self, db_session):
        """Platform admin should always be able to execute any workflow."""
        service = ExecutionAuthService(db_session)

        # Non-existent workflow ID - superuser should still be allowed
        result = await service.can_execute_workflow(
            workflow_id=str(uuid4()),
            user_id=uuid4(),
            user_org_id=uuid4(),
            is_superuser=True,
            is_api_key=False,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_api_key_always_allowed(self, db_session):
        """API key requests should always be allowed."""
        service = ExecutionAuthService(db_session)

        result = await service.can_execute_workflow(
            workflow_id=str(uuid4()),
            user_id=None,
            user_org_id=uuid4(),
            is_superuser=False,
            is_api_key=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_no_user_id_denied(self, db_session):
        """Non-admin, non-API-key request without user_id should be denied."""
        service = ExecutionAuthService(db_session)

        result = await service.can_execute_workflow(
            workflow_id=str(uuid4()),
            user_id=None,
            user_org_id=uuid4(),
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_nonexistent_workflow_denied(self, db_session):
        """Workflow that doesn't exist in any form/app should be denied."""
        service = ExecutionAuthService(db_session)

        result = await service.can_execute_workflow(
            workflow_id=str(uuid4()),
            user_id=uuid4(),
            user_org_id=uuid4(),
            is_superuser=False,
            is_api_key=False,
        )
        assert result is False
