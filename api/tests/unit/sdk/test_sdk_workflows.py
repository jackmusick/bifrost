"""
Unit tests for Bifrost Workflows SDK module.

Tests platform mode (inside workflows) only - workflows module doesn't support external mode.
Uses mocked dependencies for fast, isolated testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


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


class TestWorkflowsPlatformMode:
    """Test workflows SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_list_returns_workflows_from_database(self, test_context):
        """Test that workflows.list() returns workflow data from database."""
        from bifrost import workflows

        set_execution_context(test_context)

        # Mock workflow objects
        mock_workflow_1 = MagicMock()
        mock_workflow_1.name = "CreateCustomer"
        mock_workflow_1.description = "Creates a new customer record"
        mock_workflow_1.parameters_schema = [
            {"name": "customer_name", "type": "string", "required": True}
        ]
        mock_workflow_1.execution_mode = "sync"
        mock_workflow_1.endpoint_enabled = True

        mock_workflow_2 = MagicMock()
        mock_workflow_2.name = "UpdateInventory"
        mock_workflow_2.description = None
        mock_workflow_2.parameters_schema = []
        mock_workflow_2.execution_mode = "async"
        mock_workflow_2.endpoint_enabled = False

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(
            return_value=[mock_workflow_1, mock_workflow_2]
        )

        # Mock database context
        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "CreateCustomer"
        assert result[0]["description"] == "Creates a new customer record"
        assert result[0]["parameters"] == [
            {"name": "customer_name", "type": "string", "required": True}
        ]
        assert result[0]["executionMode"] == "sync"
        assert result[0]["endpointEnabled"] is True
        assert result[1]["name"] == "UpdateInventory"
        assert result[1]["description"] == ""
        assert result[1]["parameters"] == []
        assert result[1]["executionMode"] == "async"
        assert result[1]["endpointEnabled"] is False

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_database_session(self, test_context):
        """Test that workflows.list() returns empty list when no database session."""
        from bifrost import workflows

        set_execution_context(test_context)

        # Context without database session
        test_context._db = None

        result = await workflows.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_workflows(self, test_context):
        """Test that workflows.list() returns empty list when no workflows exist."""
        from bifrost import workflows

        set_execution_context(test_context)

        # Mock repository with empty result
        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[])

        # Mock database context
        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_formats_workflow_data_correctly(self, test_context):
        """Test that workflows.list() formats workflow data with all fields."""
        from bifrost import workflows

        set_execution_context(test_context)

        # Mock workflow with all fields populated
        mock_workflow = MagicMock()
        mock_workflow.name = "ProcessOrder"
        mock_workflow.description = "Process customer order"
        mock_workflow.parameters_schema = [
            {"name": "order_id", "type": "string", "required": True},
            {"name": "priority", "type": "string", "required": False, "default": "normal"},
        ]
        mock_workflow.execution_mode = "async"
        mock_workflow.endpoint_enabled = True

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert len(result) == 1
        workflow = result[0]
        assert workflow["name"] == "ProcessOrder"
        assert workflow["description"] == "Process customer order"
        assert len(workflow["parameters"]) == 2
        assert workflow["parameters"][0]["name"] == "order_id"
        assert workflow["parameters"][1]["default"] == "normal"
        assert workflow["executionMode"] == "async"
        assert workflow["endpointEnabled"] is True

    @pytest.mark.asyncio
    async def test_list_handles_null_description(self, test_context):
        """Test that workflows.list() handles null description gracefully."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_workflow = MagicMock()
        mock_workflow.name = "TestWorkflow"
        mock_workflow.description = None
        mock_workflow.parameters_schema = []
        mock_workflow.execution_mode = "sync"
        mock_workflow.endpoint_enabled = False

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result[0]["description"] == ""

    @pytest.mark.asyncio
    async def test_list_handles_null_parameters_schema(self, test_context):
        """Test that workflows.list() handles null parameters_schema gracefully."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_workflow = MagicMock()
        mock_workflow.name = "TestWorkflow"
        mock_workflow.description = "Test"
        mock_workflow.parameters_schema = None
        mock_workflow.execution_mode = "sync"
        mock_workflow.endpoint_enabled = False

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result[0]["parameters"] == []

    @pytest.mark.asyncio
    async def test_list_handles_null_execution_mode(self, test_context):
        """Test that workflows.list() handles null execution_mode gracefully."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_workflow = MagicMock()
        mock_workflow.name = "TestWorkflow"
        mock_workflow.description = "Test"
        mock_workflow.parameters_schema = []
        mock_workflow.execution_mode = None
        mock_workflow.endpoint_enabled = False

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result[0]["executionMode"] == "sync"

    @pytest.mark.asyncio
    async def test_list_handles_null_endpoint_enabled(self, test_context):
        """Test that workflows.list() handles null endpoint_enabled gracefully."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_workflow = MagicMock()
        mock_workflow.name = "TestWorkflow"
        mock_workflow.description = "Test"
        mock_workflow.parameters_schema = []
        mock_workflow.execution_mode = "sync"
        mock_workflow.endpoint_enabled = None

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            result = await workflows.list()

        assert result[0]["endpointEnabled"] is False

    @pytest.mark.asyncio
    async def test_list_requires_platform_context(self):
        """Test that workflows.list() requires platform execution context."""
        from bifrost import workflows

        # No context set
        clear_execution_context()

        with pytest.raises(RuntimeError, match="execution context"):
            await workflows.list()

    @pytest.mark.asyncio
    async def test_get_returns_execution_details(self, test_context):
        """Test that workflows.get() returns execution details via executions.get()."""
        from bifrost import workflows

        set_execution_context(test_context)

        execution_id = str(uuid4())
        mock_execution_data = {
            "id": execution_id,
            "workflow_name": "CreateCustomer",
            "workflow_version": "1.0.0",
            "status": "Completed",
            "executed_by": "test-user",
            "executed_by_name": "Test User",
            "parameters": {"customer_name": "Acme Corp"},
            "result": {"customer_id": "cust-123"},
            "error_message": None,
            "created_at": "2025-01-01T00:00:00",
            "started_at": "2025-01-01T00:00:01",
            "completed_at": "2025-01-01T00:00:05",
            "duration_ms": 4000,
            "logs": [],
        }

        with patch("bifrost.executions.executions.get", new=AsyncMock(return_value=mock_execution_data)):
            result = await workflows.get(execution_id)

        assert result["id"] == execution_id
        assert result["workflow_name"] == "CreateCustomer"
        assert result["status"] == "Completed"
        assert result["result"] == {"customer_id": "cust-123"}

    @pytest.mark.asyncio
    async def test_get_raises_value_error_when_execution_not_found(self, test_context):
        """Test that workflows.get() raises ValueError when execution not found."""
        from bifrost import workflows

        set_execution_context(test_context)

        execution_id = str(uuid4())

        with patch("bifrost.executions.executions.get", new=AsyncMock(side_effect=ValueError("Execution not found"))):
            with pytest.raises(ValueError, match="Execution not found"):
                await workflows.get(execution_id)

    @pytest.mark.asyncio
    async def test_get_raises_permission_error_when_access_denied(self, test_context):
        """Test that workflows.get() raises PermissionError when access denied."""
        from bifrost import workflows

        set_execution_context(test_context)

        execution_id = str(uuid4())

        with patch("bifrost.executions.executions.get", new=AsyncMock(side_effect=PermissionError("Access denied"))):
            with pytest.raises(PermissionError, match="Access denied"):
                await workflows.get(execution_id)

    @pytest.mark.asyncio
    async def test_get_requires_platform_context(self):
        """Test that workflows.get() requires platform execution context."""
        from bifrost import workflows

        # No context set
        clear_execution_context()

        execution_id = str(uuid4())

        with pytest.raises(RuntimeError, match="execution context"):
            await workflows.get(execution_id)

    @pytest.mark.asyncio
    async def test_list_calls_repository_with_db_session(self, test_context):
        """Test that workflows.list() calls repository with database session."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_db = MagicMock()
        test_context._db = mock_db

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[])

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ) as mock_repo_class:
            await workflows.list()

            # Verify repository was instantiated with db session
            mock_repo_class.assert_called_once_with(mock_db)
            mock_repo.get_all_active.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_delegates_to_executions_sdk(self, test_context):
        """Test that workflows.get() properly delegates to executions.get()."""
        from bifrost import workflows

        set_execution_context(test_context)

        execution_id = str(uuid4())
        expected_data = {
            "id": execution_id,
            "workflow_name": "test",
            "status": "Running",
        }

        with patch("bifrost.executions.executions.get", new=AsyncMock(return_value=expected_data)) as mock_get:
            result = await workflows.get(execution_id)

            # Verify executions.get was called with execution_id
            mock_get.assert_called_once_with(execution_id)
            assert result == expected_data

    @pytest.mark.asyncio
    async def test_list_logs_workflow_count(self, test_context):
        """Test that workflows.list() logs the number of workflows returned."""
        from bifrost import workflows

        set_execution_context(test_context)

        mock_workflow = MagicMock()
        mock_workflow.name = "TestWorkflow"
        mock_workflow.description = "Test"
        mock_workflow.parameters_schema = []
        mock_workflow.execution_mode = "sync"
        mock_workflow.endpoint_enabled = False

        mock_repo = MagicMock()
        mock_repo.get_all_active = AsyncMock(return_value=[mock_workflow])

        test_context._db = MagicMock()

        with patch(
            "src.repositories.workflows.WorkflowRepository", return_value=mock_repo
        ):
            with patch("bifrost.workflows.logger") as mock_logger:
                await workflows.list()

                # Verify logging
                mock_logger.info.assert_any_call(
                    f"User {test_context.user_id} listing workflows"
                )
                mock_logger.info.assert_any_call(
                    f"Returning 1 workflows for user {test_context.user_id}"
                )

    @pytest.mark.asyncio
    async def test_list_logs_warning_when_no_db_session(self, test_context):
        """Test that workflows.list() logs warning when no database session."""
        from bifrost import workflows

        set_execution_context(test_context)

        # Context without database session
        test_context._db = None

        with patch("bifrost.workflows.logger") as mock_logger:
            result = await workflows.list()

            mock_logger.warning.assert_called_once_with(
                "No database session in context, returning empty workflow list"
            )
            assert result == []
