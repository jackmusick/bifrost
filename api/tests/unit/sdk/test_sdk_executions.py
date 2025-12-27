"""
Unit tests for Bifrost Executions SDK module.

Tests platform mode (inside workflows) only.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.models.enums import ExecutionStatus


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_user_id():
    """Return a test user ID."""
    return str(uuid4())


@pytest.fixture
def test_context(test_org_id, test_user_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id=test_user_id,
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
        user_id=str(uuid4()),
        email="admin@example.com",
        name="Admin User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


@pytest.fixture
def mock_execution():
    """Create a mock execution object."""
    exec_id = uuid4()
    user_id = uuid4()
    org_id = uuid4()

    execution = MagicMock()
    execution.id = exec_id
    execution.workflow_name = "test_workflow"
    execution.workflow_version = "1.0.0"
    execution.status = ExecutionStatus.SUCCESS
    execution.executed_by = user_id
    execution.executed_by_name = "Test User"
    execution.organization_id = org_id
    execution.parameters = {"input": "data"}
    execution.result = {"output": "result"}
    execution.result_type = "dict"
    execution.variables = {}
    execution.error_message = None
    execution.created_at = datetime(2025, 1, 1, 12, 0, 0)
    execution.started_at = datetime(2025, 1, 1, 12, 0, 1)
    execution.completed_at = datetime(2025, 1, 1, 12, 0, 5)
    execution.duration_ms = 4000
    execution.logs = []

    return execution


@pytest.fixture
def mock_execution_with_logs(mock_execution):
    """Create a mock execution with logs."""
    log1 = MagicMock()
    log1.id = 1
    log1.level = "INFO"
    log1.message = "Workflow started"
    log1.log_metadata = {"step": 1}
    log1.timestamp = datetime(2025, 1, 1, 12, 0, 1)

    log2 = MagicMock()
    log2.id = 2
    log2.level = "INFO"
    log2.message = "Processing data"
    log2.log_metadata = {"step": 2}
    log2.timestamp = datetime(2025, 1, 1, 12, 0, 3)

    log3 = MagicMock()
    log3.id = 3
    log3.level = "INFO"
    log3.message = "Workflow completed"
    log3.log_metadata = {"step": 3}
    log3.timestamp = datetime(2025, 1, 1, 12, 0, 5)

    mock_execution.logs = [log1, log2, log3]
    return mock_execution
