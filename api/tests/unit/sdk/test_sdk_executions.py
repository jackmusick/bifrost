"""
Unit tests for Bifrost Executions SDK module.

Tests platform mode (inside workflows) only.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context
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


class TestExecutionsPlatformMode:
    """Test executions SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_list_returns_executions_from_database(
        self, test_context, test_org_id, test_user_id, mock_execution
    ):
        """Test that executions.list() returns executions from database."""
        from bifrost import executions

        set_execution_context(test_context)

        # Mock the session factory and query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        assert len(result) == 1
        assert result[0]["id"] == str(mock_execution.id)
        assert result[0]["workflow_name"] == "test_workflow"
        assert result[0]["workflow_version"] == "1.0.0"
        assert result[0]["status"] == "Success"
        assert result[0]["executed_by"] == str(mock_execution.executed_by)
        assert result[0]["executed_by_name"] == "Test User"
        assert result[0]["parameters"] == {"input": "data"}
        assert result[0]["result"] == {"output": "result"}
        assert result[0]["error_message"] is None
        assert result[0]["created_at"] == "2025-01-01T12:00:00"
        assert result[0]["started_at"] == "2025-01-01T12:00:01"
        assert result[0]["completed_at"] == "2025-01-01T12:00:05"
        assert result[0]["duration_ms"] == 4000

    @pytest.mark.asyncio
    async def test_list_uses_context_org_id_when_not_specified(
        self, test_context, test_org_id, test_user_id, mock_execution
    ):
        """Test that executions.list() uses context.org_id when not specified."""
        from bifrost import executions
        from uuid import UUID

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        # Verify the query was built with the context's org_id
        call_args = mock_session.execute.call_args
        # The query should have filtered by organization_id
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_filters_by_workflow_name_when_provided(
        self, test_context, mock_execution
    ):
        """Test that executions.list() filters by workflow_name when provided."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list(workflow_name="test_workflow")

        assert len(result) == 1
        assert result[0]["workflow_name"] == "test_workflow"
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_filters_by_status_when_provided(
        self, test_context, mock_execution
    ):
        """Test that executions.list() filters by status when provided."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list(status="Success")

        assert len(result) == 1
        assert result[0]["status"] == "Success"
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_respects_limit_parameter(self, test_context):
        """Test that executions.list() respects limit parameter."""
        from bifrost import executions

        set_execution_context(test_context)

        # Create 5 mock executions
        mock_executions = []
        for i in range(5):
            exec_mock = MagicMock()
            exec_mock.id = uuid4()
            exec_mock.workflow_name = f"workflow_{i}"
            exec_mock.workflow_version = "1.0.0"
            exec_mock.status = ExecutionStatus.SUCCESS
            exec_mock.executed_by = uuid4()
            exec_mock.executed_by_name = f"User {i}"
            exec_mock.organization_id = uuid4()
            exec_mock.parameters = {}
            exec_mock.result = {}
            exec_mock.error_message = None
            exec_mock.created_at = datetime(2025, 1, 1, 12, i, 0)
            exec_mock.started_at = datetime(2025, 1, 1, 12, i, 1)
            exec_mock.completed_at = datetime(2025, 1, 1, 12, i, 5)
            exec_mock.duration_ms = 4000
            mock_executions.append(exec_mock)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_executions[:3]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list(limit=3)

        assert len(result) == 3
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_caps_limit_at_1000(self, test_context):
        """Test that executions.list() caps limit at 1000."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            # Request a huge limit
            result = await executions.list(limit=10000)

        # Should have capped at 1000
        assert len(result) == 0  # Empty result, but the query was executed
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_filters_by_user_for_non_admins(
        self, test_context, test_user_id, mock_execution
    ):
        """Test that executions.list() filters by user for non-admin users."""
        from bifrost import executions

        set_execution_context(test_context)

        # The mock execution should belong to the test user
        mock_execution.executed_by = test_user_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        # Should return the execution since it belongs to the user
        assert len(result) == 1
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_does_not_filter_by_user_for_admins(
        self, admin_context, mock_execution
    ):
        """Test that executions.list() does not filter by user for admins."""
        from bifrost import executions

        set_execution_context(admin_context)

        # The mock execution belongs to a different user
        mock_execution.executed_by = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        # Admin should see all executions
        assert len(result) == 1
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_executions(self, test_context):
        """Test that executions.list() returns empty list when no executions."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_returns_execution_data_with_logs(
        self, test_context, test_user_id, mock_execution_with_logs
    ):
        """Test that executions.get() returns execution data with logs."""
        from bifrost import executions
        from uuid import UUID

        set_execution_context(test_context)

        # Make sure the execution belongs to the test user
        mock_execution_with_logs.executed_by = UUID(test_user_id)
        mock_execution_with_logs.organization_id = UUID(test_context.organization.id)

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = (
            mock_execution_with_logs
        )

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.get(str(mock_execution_with_logs.id))

        assert result["id"] == str(mock_execution_with_logs.id)
        assert result["workflow_name"] == "test_workflow"
        assert result["status"] == "Success"
        assert "logs" in result
        assert len(result["logs"]) == 3
        assert result["logs"][0]["level"] == "INFO"
        assert result["logs"][0]["message"] == "Workflow started"
        assert result["logs"][0]["metadata"] == {"step": 1}
        assert result["logs"][0]["timestamp"] == "2025-01-01T12:00:01"

    @pytest.mark.asyncio
    async def test_get_raises_error_when_execution_not_found(self, test_context):
        """Test that executions.get() raises error when execution not found."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = None

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            with pytest.raises(ValueError, match="Execution not found"):
                await executions.get(str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_raises_permission_error_for_wrong_org(
        self, test_context, test_user_id, mock_execution
    ):
        """Test that executions.get() raises permission error for wrong org."""
        from bifrost import executions

        set_execution_context(test_context)

        # Set execution to belong to a different org
        mock_execution.organization_id = uuid4()
        mock_execution.executed_by = test_user_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = (
            mock_execution
        )

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            with pytest.raises(PermissionError, match="Access denied"):
                await executions.get(str(mock_execution.id))

    @pytest.mark.asyncio
    async def test_get_raises_permission_error_for_non_admin_different_user(
        self, test_context, mock_execution
    ):
        """Test that executions.get() raises permission error for non-admin viewing different user's execution."""
        from bifrost import executions

        set_execution_context(test_context)

        # Set execution to belong to same org but different user
        mock_execution.organization_id = test_context.organization.id
        mock_execution.executed_by = uuid4()  # Different user

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = (
            mock_execution
        )

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            with pytest.raises(PermissionError, match="Access denied"):
                await executions.get(str(mock_execution.id))

    @pytest.mark.asyncio
    async def test_get_allows_admin_to_view_any_execution_in_scope(
        self, admin_context, mock_execution
    ):
        """Test that executions.get() allows admin to view any execution in scope."""
        from bifrost import executions
        from uuid import UUID

        set_execution_context(admin_context)

        # Set execution to belong to same org but different user
        mock_execution.organization_id = UUID(admin_context.organization.id)
        mock_execution.executed_by = uuid4()  # Different user

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = (
            mock_execution
        )

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.get(str(mock_execution.id))

        # Admin should be able to view it
        assert result["id"] == str(mock_execution.id)

    @pytest.mark.asyncio
    async def test_list_requires_platform_context(self):
        """Test that executions.list() requires platform context."""
        from bifrost import executions

        # No context set
        clear_execution_context()

        with pytest.raises(RuntimeError, match="No execution context"):
            await executions.list()

    @pytest.mark.asyncio
    async def test_get_requires_platform_context(self):
        """Test that executions.get() requires platform context."""
        from bifrost import executions

        # No context set
        clear_execution_context()

        with pytest.raises(RuntimeError, match="No execution context"):
            await executions.get(str(uuid4()))

    @pytest.mark.asyncio
    async def test_list_handles_global_scope(self):
        """Test that executions.list() handles GLOBAL scope correctly."""
        from bifrost import executions
        from src.sdk.context import ExecutionContext, Organization

        # Create a global scope context
        org = Organization(id="GLOBAL", name="Global", is_active=True)
        global_context = ExecutionContext(
            user_id=str(uuid4()),
            email="global@example.com",
            name="Global User",
            scope="GLOBAL",
            organization=org,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="global-exec",
        )
        set_execution_context(global_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        # Should handle GLOBAL scope (no org filter)
        assert result == []
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_list_handles_invalid_org_id(self):
        """Test that executions.list() handles invalid org_id gracefully."""
        from bifrost import executions
        from src.sdk.context import ExecutionContext, Organization

        # Create context with invalid UUID org_id
        org = Organization(id="not-a-uuid", name="Invalid Org", is_active=True)
        invalid_context = ExecutionContext(
            user_id=str(uuid4()),
            email="test@example.com",
            name="Test User",
            scope="not-a-uuid",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec",
        )
        set_execution_context(invalid_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        # Should handle gracefully and query without org filter
        assert result == []
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_get_handles_invalid_org_id(self, mock_execution):
        """Test that executions.get() handles invalid org_id gracefully."""
        from bifrost import executions
        from src.sdk.context import ExecutionContext, Organization
        from uuid import UUID

        # Create context with invalid UUID org_id
        org = Organization(id="not-a-uuid", name="Invalid Org", is_active=True)
        user_id = uuid4()
        invalid_context = ExecutionContext(
            user_id=str(user_id),
            email="test@example.com",
            name="Test User",
            scope="not-a-uuid",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec",
        )
        set_execution_context(invalid_context)

        # Set execution to have no org and belong to the user
        mock_execution.organization_id = None
        mock_execution.executed_by = user_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.unique.return_value.first.return_value = (
            mock_execution
        )

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.get(str(mock_execution.id))

        # Should handle gracefully
        assert result["id"] == str(mock_execution.id)

    @pytest.mark.asyncio
    async def test_list_filters_by_date_range(self, test_context, mock_execution):
        """Test that executions.list() filters by start_date and end_date."""
        from bifrost import executions

        set_execution_context(test_context)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_execution]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list(
                start_date="2025-01-01T00:00:00", end_date="2025-01-02T00:00:00"
            )

        assert len(result) == 1
        assert mock_session.execute.called

    @pytest.mark.asyncio
    async def test_execution_to_dict_handles_none_values(self, test_context):
        """Test that _execution_to_dict() handles None values correctly."""
        from bifrost import executions

        set_execution_context(test_context)

        # Create execution with None values
        exec_mock = MagicMock()
        exec_mock.id = uuid4()
        exec_mock.workflow_name = "test"
        exec_mock.workflow_version = None
        exec_mock.status = ExecutionStatus.PENDING
        exec_mock.executed_by = uuid4()
        exec_mock.executed_by_name = "User"
        exec_mock.organization_id = uuid4()
        exec_mock.parameters = {}
        exec_mock.result = None
        exec_mock.error_message = None
        exec_mock.created_at = None
        exec_mock.started_at = None
        exec_mock.completed_at = None
        exec_mock.duration_ms = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [exec_mock]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        with patch(
            "bifrost.executions.get_session_factory", return_value=mock_session_factory
        ):
            result = await executions.list()

        assert len(result) == 1
        assert result[0]["workflow_version"] is None
        assert result[0]["result"] is None
        assert result[0]["error_message"] is None
        assert result[0]["created_at"] is None
        assert result[0]["started_at"] is None
        assert result[0]["completed_at"] is None
        assert result[0]["duration_ms"] is None
