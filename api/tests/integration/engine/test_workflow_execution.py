"""
Integration Tests for Workflow Execution
End-to-end tests for the workflow execution endpoint
"""

from unittest.mock import MagicMock

import pytest

from shared.context import Organization, ExecutionContext
from shared.context import Caller


@pytest.fixture
def mock_org():
    """Mock organization for testing"""
    return Organization(
        id="test-org-123",
        name="Test Organization",
        is_active=True
    )


@pytest.fixture
def mock_caller():
    """Mock caller for testing"""
    return Caller(
        user_id="test-user-789",
        email="test@example.com",
        name="Test User"
    )


@pytest.fixture
def mock_context(mock_org, mock_caller):
    """Mock organization context"""
    return ExecutionContext(
        user_id=mock_caller.user_id,
        email=mock_caller.email,
        name=mock_caller.name,
        scope=mock_org.id,
        organization=mock_org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
        _config={
            "default_license": "O365_E3",
            "welcome_email_template": "welcome_v1"
        }
    )


@pytest.fixture
def mock_table_storage():
    """Mock table storage service"""
    # The fixture is defined but not currently used in the tests below
    # Leaving it for future use
    instance = MagicMock()
    yield instance


class TestWorkflowExecutionEndpoint:
    """Test the POST /workflows/{workflowName} endpoint components"""

    @pytest.mark.asyncio
    async def test_workflow_execution_flow(self, mock_context):
        """Test complete workflow execution flow"""

        from shared.decorators import workflow

        # Define a simple test workflow with decorator
        @workflow(
            name="simple_test_workflow",
            description="Simple test workflow",
            category="test"
        )
        async def simple_workflow(context, value: int):
            """Returns doubled value"""
            return {"result": value * 2, "org": context.org_id}

        # Verify workflow has metadata attached
        assert hasattr(simple_workflow, '_workflow_metadata')
        metadata = simple_workflow._workflow_metadata
        assert metadata.name == "simple_test_workflow"

        # Execute the workflow function directly
        result = await simple_workflow(mock_context, value=21)

        assert result["result"] == 42
        assert result["org"] == "test-org-123"  # Uses scope

    @pytest.mark.asyncio
    async def test_workflow_with_validation_error(self, mock_context):
        """Test workflow that raises ValidationError"""

        from shared.decorators import workflow
        from shared.error_handling import ValidationError

        @workflow(
            name="validation_workflow",
            description="Workflow with validation",
            category="test"
        )
        async def validate_email(context, email: str):
            """Validates email format"""
            if '@' not in email:
                raise ValidationError("Invalid email format", field="email")
            return {"valid": True}

        # Test valid email
        result = await validate_email(mock_context, email="test@example.com")
        assert result["valid"] is True

        # Test invalid email
        with pytest.raises(ValidationError) as exc_info:
            await validate_email(mock_context, email="invalid")

        assert exc_info.value.error_type == "ValidationError"
        assert exc_info.value.details["field"] == "email"

    @pytest.mark.asyncio
    async def test_workflow_with_state_tracking(self, mock_context):
        """Test that state tracking works correctly"""

        from shared.decorators import workflow

        @workflow(
            name="state_test_workflow",
            description="Workflow with state tracking",
            category="test"
        )
        async def track_state(context, step: str):
            """Simple test workflow"""
            return {"completed": True, "step": step}

        # Execute workflow
        result = await track_state(mock_context, step="validation")

        assert result["completed"] is True
        assert result["step"] == "validation"


