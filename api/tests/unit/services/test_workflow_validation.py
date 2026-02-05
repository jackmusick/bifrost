"""
Unit tests for workflow validation service.

Tests the validate_workflow_file function which validates workflow files
for syntax errors, decorator issues, and Pydantic validation.
"""

import pytest

from src.services.workflow_validation import (
    validate_workflow_file,
    _convert_workflow_metadata_to_model,
    _extract_relative_path,
)
from src.services.execution.module_loader import WorkflowMetadata, WorkflowParameter


class TestExtractRelativePath:
    """Test _extract_relative_path helper function

    NOTE: As of the virtual module loading migration, paths are now stored
    as relative paths in the database and used directly. The function just
    returns the path as-is without any transformation.
    """

    def test_returns_path_as_is(self):
        """Test that paths are returned as-is"""
        result = _extract_relative_path("workflows/my_workflow.py")
        assert result == "workflows/my_workflow.py"

    def test_returns_nested_path_as_is(self):
        """Test that nested paths are returned as-is"""
        result = _extract_relative_path("features/ticketing/workflows/create_ticket.py")
        assert result == "features/ticketing/workflows/create_ticket.py"

    def test_returns_absolute_path_as_is(self):
        """Test that even absolute paths are returned as-is (for backwards compat)"""
        result = _extract_relative_path("/some/absolute/path.py")
        assert result == "/some/absolute/path.py"

    def test_none_input(self):
        """Test None input returns None"""
        result = _extract_relative_path(None)
        assert result is None

    def test_empty_string(self):
        """Test empty string returns None"""
        result = _extract_relative_path("")
        assert result is None


class TestConvertWorkflowMetadataToModel:
    """Test _convert_workflow_metadata_to_model conversion function"""

    def test_basic_conversion(self):
        """Test basic metadata conversion without parameters"""
        metadata = WorkflowMetadata(
            name="test_workflow",
            description="Test workflow description",
            category="Testing",
            tags=["test"],
            execution_mode="sync",
            timeout_seconds=300,
            source_file_path="/home/test/workflows/test.py"
        )

        result = _convert_workflow_metadata_to_model(metadata)

        # ID is generated as pending-{name} for validation
        assert result.id == "pending-test_workflow"
        assert result.name == "test_workflow"
        assert result.description == "Test workflow description"
        assert result.category == "Testing"
        assert result.tags == ["test"]
        assert result.execution_mode == "sync"
        assert result.timeout_seconds == 300

    def test_conversion_with_parameters(self):
        """Test conversion includes workflow parameters correctly"""
        metadata = WorkflowMetadata(
            name="test_workflow",
            description="Test",
            parameters=[
                WorkflowParameter(
                    name="name",
                    type="string",
                    required=True,
                    label="Name",
                    default_value=None
                ),
                WorkflowParameter(
                    name="count",
                    type="int",
                    required=False,
                    label="Count",
                    default_value=1
                ),
            ]
        )

        result = _convert_workflow_metadata_to_model(metadata)

        assert len(result.parameters) == 2

        name_param = result.parameters[0]
        assert name_param.name == "name"
        assert name_param.type == "string"
        assert name_param.required is True
        assert name_param.label == "Name"

        count_param = result.parameters[1]
        assert count_param.name == "count"
        assert count_param.type == "int"
        assert count_param.required is False
        assert count_param.default_value == 1

    def test_conversion_handles_missing_optional_fields(self):
        """Test conversion handles parameters with only required fields.

        This test verifies the fix for the AttributeError when workflow parameters
        don't have form-specific fields like data_provider, help_text, validation.
        """
        # WorkflowParameter dataclass only has: name, type, label, required, default_value
        # It does NOT have: data_provider, help_text, validation, options
        # The conversion function should handle this gracefully
        metadata = WorkflowMetadata(
            name="test_workflow",
            description="Test",
            parameters=[
                WorkflowParameter(
                    name="simple_param",
                    type="string",
                    required=True,
                )
            ]
        )

        # This should NOT raise AttributeError
        result = _convert_workflow_metadata_to_model(metadata)

        assert len(result.parameters) == 1
        assert result.parameters[0].name == "simple_param"


class TestValidateWorkflowFile:
    """Test validate_workflow_file function

    NOTE: validate_workflow_file now requires content to be passed directly.
    It no longer reads from the filesystem - all workflows are stored in the database.
    Tests should pass content directly via the content parameter.
    """

    @pytest.mark.asyncio
    async def test_valid_workflow_passes_validation(self):
        """Test that a valid workflow file passes validation"""
        workflow_content = '''
"""Test workflow"""

from bifrost import workflow

@workflow(
    category="testing",
    tags=["test"],
)
async def test_valid_workflow(name: str) -> dict:
    """A simple test workflow."""
    return {"greeting": f"Hello, {name}!"}
'''
        result = await validate_workflow_file("test_workflow.py", content=workflow_content)

        assert result.valid is True
        assert result.metadata is not None
        assert result.metadata.name == "test_valid_workflow"
        # Should have warnings about category and tags being default, but not errors
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_syntax_error_fails_validation(self):
        """Test that syntax errors are caught"""
        workflow_content = '''
"""Invalid syntax"""

def test_workflow(
    # Missing closing paren
'''
        result = await validate_workflow_file("invalid_syntax.py", content=workflow_content)

        assert result.valid is False
        assert any("Syntax error" in i.message for i in result.issues)

    @pytest.mark.asyncio
    async def test_missing_decorator_fails_validation(self):
        """Test that missing @workflow decorator is caught"""
        workflow_content = '''
"""No decorator"""

async def test_workflow(name: str) -> dict:
    """A test workflow without decorator."""
    return {"name": name}
'''
        result = await validate_workflow_file("no_decorator.py", content=workflow_content)

        assert result.valid is False
        assert any("No @workflow decorator found" in i.message for i in result.issues)

    @pytest.mark.asyncio
    async def test_invalid_workflow_name_fails_validation(self):
        """Test that invalid workflow names (not snake_case) are caught"""
        workflow_content = '''
"""Invalid name"""

from bifrost import workflow

@workflow(
    name="InvalidCamelCase",
    category="testing",
)
async def invalid_workflow(name: str) -> dict:
    """Test workflow with invalid name."""
    return {"name": name}
'''
        result = await validate_workflow_file("invalid_name.py", content=workflow_content)

        assert result.valid is False
        assert any("Invalid workflow name" in i.message for i in result.issues)

    @pytest.mark.asyncio
    async def test_validation_with_content_parameter(self):
        """Test validation using content parameter instead of reading from disk"""
        workflow_content = '''
"""Test workflow"""

from bifrost import workflow

@workflow(
    category="testing",
    tags=["test"],
)
async def content_test_workflow(value: int = 1) -> dict:
    """A workflow validated via content parameter."""
    return {"doubled": value * 2}
'''
        # Pass content directly, path is just for display
        result = await validate_workflow_file(
            "fake_path.py",
            content=workflow_content
        )

        assert result.valid is True
        assert result.metadata is not None
        assert result.metadata.name == "content_test_workflow"

    @pytest.mark.asyncio
    async def test_file_not_found_fails_validation(self):
        """Test that non-existent file fails validation when no content provided

        NOTE: This test validates that when no content is passed, the function
        tries to read from the database and returns an appropriate error.
        """
        from unittest.mock import patch, AsyncMock, MagicMock

        # Mock the database context
        mock_db = MagicMock()
        mock_db_context = MagicMock()
        mock_db_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_context.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.read_file = AsyncMock(side_effect=FileNotFoundError("Not found"))

        with patch("src.core.database.get_db_context", return_value=mock_db_context):
            with patch("src.services.file_storage.FileStorageService", return_value=mock_service):
                result = await validate_workflow_file("nonexistent_workflow.py")

        assert result.valid is False
        assert any("File not found" in i.message for i in result.issues)

    @pytest.mark.asyncio
    async def test_invalid_execution_mode_silently_defaults(self):
        """Test that invalid execution_mode in decorator is silently ignored (defaults to async)."""
        workflow_content = '''
"""Invalid execution mode"""

from bifrost import workflow

@workflow(
    execution_mode="invalid_mode",
    category="testing",
)
async def test_workflow(name: str) -> dict:
    """Test workflow."""
    return {"name": name}
'''
        result = await validate_workflow_file(
            "test.py",
            content=workflow_content
        )

        # execution_mode is no longer a decorator param; unknown kwargs are silently ignored
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_missing_description_warning(self):
        """Test that missing description generates an error"""
        workflow_content = '''
"""Module docstring"""

from bifrost import workflow

@workflow(
    category="testing",
)
async def no_description_workflow(name: str):
    # No docstring on function
    return {"name": name}
'''
        result = await validate_workflow_file(
            "test.py",
            content=workflow_content
        )

        # The decorator extracts description from docstring first line
        # If no docstring, description will be empty which is an error
        assert result.valid is False
        assert any("description is required" in i.message.lower() for i in result.issues)
