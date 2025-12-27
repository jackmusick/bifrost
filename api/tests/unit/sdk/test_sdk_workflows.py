"""
Unit tests for Bifrost Workflows SDK module.

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
def mock_workflow():
    """Create a mock workflow database object."""
    mock = MagicMock()
    mock.id = uuid4()
    mock.organization_id = uuid4()
    mock.name = "test_workflow"
    mock.display_name = "Test Workflow"
    mock.description = "A test workflow"
    mock.version = "1.0.0"
    mock.is_active = True
    mock.is_latest = True
    mock.created_by = "user-123"
    mock.created_by_name = "Test User"
    mock.created_at = "2025-01-01T00:00:00"
    mock.updated_at = "2025-01-01T00:00:00"
    mock.workflow_type = "automation"
    mock.tags = ["test", "demo"]
    mock.metadata_ = {"category": "testing"}
    return mock


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
