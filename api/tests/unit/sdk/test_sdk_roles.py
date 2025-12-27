"""
Unit tests for Bifrost Roles SDK module.

Tests platform mode (inside workflows) operations.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4



@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_context(test_org_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


@pytest.fixture
def admin_context(test_org_id):
    """Create platform admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


@pytest.fixture
def mock_role():
    """Create a mock role database object."""
    mock = MagicMock()
    mock.id = uuid4()
    mock.organization_id = uuid4()
    mock.name = "test_role"
    mock.display_name = "Test Role"
    mock.description = "A test role"
    mock.permissions = ["read:workflows", "execute:workflows"]
    mock.is_system_role = False
    mock.created_at = "2025-01-01T00:00:00"
    mock.updated_at = "2025-01-01T00:00:00"
    return mock
