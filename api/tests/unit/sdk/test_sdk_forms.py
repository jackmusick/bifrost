"""
Unit tests for Bifrost Forms SDK module.

Tests platform mode (inside workflows) operations.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from datetime import datetime, timezone
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
def mock_form():
    """Create a mock form database object."""
    form_id = uuid4()
    org_id = uuid4()

    mock = MagicMock()
    mock.id = form_id
    mock.organization_id = org_id
    mock.name = "test_form"
    mock.display_name = "Test Form"
    mock.description = "A test form"
    mock.schema_json = {
        "fields": [
            {"name": "email", "type": "email", "required": True},
            {"name": "message", "type": "textarea", "required": False},
        ]
    }
    mock.is_active = True
    mock.allow_anonymous = False
    mock.created_by = "user-123"
    mock.created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock.updated_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    return mock


@pytest.fixture
def mock_submission():
    """Create a mock form submission database object."""
    submission_id = uuid4()
    form_id = uuid4()

    mock = MagicMock()
    mock.id = submission_id
    mock.form_id = form_id
    mock.submitted_data = {"email": "test@example.com", "message": "Hello world"}
    mock.submitted_by = "user-456"
    mock.submitted_by_name = "Test User"
    mock.submitted_at = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
    mock.ip_address = "192.168.1.100"
    mock.user_agent = "Mozilla/5.0"

    return mock
