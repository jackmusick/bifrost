"""
Contract Tests for Workflow Execution API
Tests request/response models for workflow execution endpoint
"""


import pytest
from pydantic import ValidationError

from src.models import ErrorResponse, WorkflowExecutionRequest, WorkflowExecutionResponse
from src.models.enums import ExecutionStatus


# Note: Models use snake_case (e.g., workflow_id, input_data, execution_id)
# This matches the OpenAPI/TypeScript schema


class TestWorkflowExecutionRequest:
    """Test WorkflowExecutionRequest validation"""

    def test_valid_execution_request(self):
        """Test valid execution request with all fields"""
        request = WorkflowExecutionRequest(
            workflow_id="550e8400-e29b-41d4-a716-446655440000",
            form_id="form-123",
            input_data={
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User"
            }
        )

        assert request.workflow_id == "550e8400-e29b-41d4-a716-446655440000"
        assert request.form_id == "form-123"
        assert request.input_data["email"] == "test@example.com"

    def test_execution_request_minimal(self):
        """Test execution request with minimal fields"""
        request = WorkflowExecutionRequest(
            workflow_id="550e8400-e29b-41d4-a716-446655440001",
            input_data={"key": "value"}
        )

        assert request.workflow_id == "550e8400-e29b-41d4-a716-446655440001"
        assert request.form_id is None
        assert request.input_data == {"key": "value"}

    def test_execution_request_missing_workflow_id(self):
        """Test that either workflow_id or code is required"""
        with pytest.raises(ValidationError) as exc_info:
            WorkflowExecutionRequest()

        errors = exc_info.value.errors()
        assert any("Either 'workflow_id' or 'code' must be provided" in str(e) for e in errors)

    def test_execution_request_missing_input_data(self):
        """Test that input_data has default factory"""
        request = WorkflowExecutionRequest(
            workflow_id="550e8400-e29b-41d4-a716-446655440002",
            form_id="form-123"
        )

        assert request.input_data == {}
        assert request.form_id == "form-123"
        assert request.workflow_id == "550e8400-e29b-41d4-a716-446655440002"


class TestWorkflowExecutionResponse:
    """Test WorkflowExecutionResponse validation"""

    def test_success_response(self):
        """Test successful execution response"""
        response = WorkflowExecutionResponse(
            execution_id="exec-123",
            status=ExecutionStatus.SUCCESS,
            result={"message": "Workflow executed successfully"}
        )

        assert response.execution_id == "exec-123"
        assert response.status == ExecutionStatus.SUCCESS
        assert response.result == {"message": "Workflow executed successfully"}
        assert response.error is None

    def test_failed_response(self):
        """Test failed execution response"""
        response = WorkflowExecutionResponse(
            execution_id="exec-789",
            status=ExecutionStatus.FAILED,
            error="Validation failed",
            error_type="ValidationError"
        )

        assert response.execution_id == "exec-789"
        assert response.status == ExecutionStatus.FAILED
        assert response.error == "Validation failed"
        assert response.error_type == "ValidationError"

    def test_running_response(self):
        """Test running/pending response"""
        response = WorkflowExecutionResponse(
            execution_id="exec-999",
            status=ExecutionStatus.RUNNING
        )

        assert response.execution_id == "exec-999"
        assert response.status == ExecutionStatus.RUNNING
        assert response.result is None
        assert response.error is None

    def test_response_required_fields(self):
        """Test that execution_id and status are required"""
        with pytest.raises(ValidationError) as exc_info:
            WorkflowExecutionResponse(
                execution_id="exec-123"
            )

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('status',) for e in errors)


class TestErrorResponse:
    """Test ErrorResponse model"""

    def test_error_response_basic(self):
        """Test basic error response"""
        error = ErrorResponse(
            error="NotFound",
            message="Workflow not found"
        )

        assert error.error == "NotFound"
        assert error.message == "Workflow not found"
        assert error.details is None

    def test_error_response_with_details(self):
        """Test error response with details"""
        error = ErrorResponse(
            error="ValidationError",
            message="Invalid input parameters",
            details={
                "field": "email",
                "issue": "Invalid email format"
            }
        )

        assert error.error == "ValidationError"
        assert error.details["field"] == "email"

    def test_error_response_required_fields(self):
        """Test that error and message are required"""
        with pytest.raises(ValidationError) as exc_info:
            ErrorResponse(error="NotFound")

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('message',) for e in errors)


class TestExecutionStatus:
    """Test ExecutionStatus enum"""

    def test_execution_status_values(self):
        """Test all execution status values"""
        assert ExecutionStatus.PENDING == "Pending"
        assert ExecutionStatus.RUNNING == "Running"
        assert ExecutionStatus.SUCCESS == "Success"
        assert ExecutionStatus.FAILED == "Failed"

    def test_execution_status_in_response(self):
        """Test using ExecutionStatus in response"""
        response = WorkflowExecutionResponse(
            execution_id="exec-123",
            status=ExecutionStatus.SUCCESS,
            result={"status": "Success"}
        )

        assert response.status == "Success"
        assert isinstance(response.status, ExecutionStatus)
