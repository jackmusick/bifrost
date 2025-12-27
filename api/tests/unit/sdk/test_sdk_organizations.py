"""
Unit tests for Bifrost Organizations SDK module.

Tests platform mode (inside workflows) operations.
Organizations module is admin-only and does not support external mode.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from uuid import uuid4



@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


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
def non_admin_context(test_org_id):
    """Create non-admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="regular-user",
        email="user@example.com",
        name="Regular User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="user-exec-789",
    )
