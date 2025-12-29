"""
Unit tests for MCP tool implementations.

Tests the actual tool implementation functions that handle
file operations, workflow validation, and execution tracking.
"""

from uuid import uuid4

import pytest

from src.services.mcp.server import MCPContext


# ==================== Fixtures ====================


@pytest.fixture
def context():
    """Create an MCPContext for testing."""
    return MCPContext(
        user_id=str(uuid4()),
        org_id=str(uuid4()),
        is_platform_admin=False,
        user_email="test@example.com",
        user_name="Test User",
    )


@pytest.fixture
def admin_context():
    """Create an admin MCPContext for testing."""
    return MCPContext(
        user_id=str(uuid4()),
        org_id=str(uuid4()),
        is_platform_admin=True,
        user_email="admin@example.com",
        user_name="Admin User",
    )


# ==================== File Operation Tool Tests ====================


class TestReadFileImpl:
    """Tests for _read_file_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when path is empty."""
        from src.services.mcp.server import _read_file_impl

        result = await _read_file_impl(context, "")
        assert "Error: path is required" in result


class TestWriteFileImpl:
    """Tests for _write_file_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when path is empty."""
        from src.services.mcp.server import _write_file_impl

        result = await _write_file_impl(context, "", "content")
        assert "Error: path is required" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_content_none(self, context):
        """Should return error message when content is None."""
        from src.services.mcp.server import _write_file_impl

        result = await _write_file_impl(context, "test.txt", None)
        assert "Error: content is required" in result


class TestDeleteFileImpl:
    """Tests for _delete_file_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when path is empty."""
        from src.services.mcp.server import _delete_file_impl

        result = await _delete_file_impl(context, "")
        assert "Error: path is required" in result


class TestSearchFilesImpl:
    """Tests for _search_files_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_query_empty(self, context):
        """Should return error message when query is empty."""
        from src.services.mcp.server import _search_files_impl

        result = await _search_files_impl(context, "")
        assert "Error: query is required" in result


class TestSearchKnowledgeImpl:
    """Tests for _search_knowledge_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_query_empty(self, context):
        """Should return error message when query is empty."""
        from src.services.mcp.server import _search_knowledge_impl

        result = await _search_knowledge_impl(context, "")
        assert "Error: query is required" in result

    @pytest.mark.asyncio
    async def test_returns_error_when_no_namespaces_accessible(self, context):
        """Should return error when user has no accessible namespaces."""
        from src.services.mcp.server import _search_knowledge_impl

        # Context has empty accessible_namespaces by default
        result = await _search_knowledge_impl(context, "test query")
        assert "No knowledge sources available" in result

    @pytest.mark.asyncio
    async def test_returns_access_denied_for_unauthorized_namespace(self, context):
        """Should deny access to namespace not in accessible list."""
        from src.services.mcp.server import _search_knowledge_impl

        context.accessible_namespaces = ["allowed-ns"]
        result = await _search_knowledge_impl(context, "test query", namespace="forbidden-ns")
        assert "Access denied" in result
        assert "forbidden-ns" in result


class TestCreateFolderImpl:
    """Tests for _create_folder_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when path is empty."""
        from src.services.mcp.server import _create_folder_impl

        result = await _create_folder_impl(context, "")
        assert "Error: path is required" in result


# ==================== Workflow Tool Tests ====================


class TestValidateWorkflowImpl:
    """Tests for _validate_workflow_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when file_path is empty."""
        from src.services.mcp.server import _validate_workflow_impl

        result = await _validate_workflow_impl(context, "")
        assert "Error: file_path is required" in result


class TestGetWorkflowSchemaImpl:
    """Tests for _get_workflow_schema_impl()."""

    @pytest.mark.asyncio
    async def test_returns_schema_documentation(self, context):
        """Should return comprehensive schema documentation."""
        from src.services.mcp.server import _get_workflow_schema_impl

        result = await _get_workflow_schema_impl(context)

        # Check for key sections
        assert "# Workflow Schema Documentation" in result
        assert "@workflow" in result
        assert "from bifrost import workflow" in result
        assert "AI Module" in result
        assert "HTTP Module" in result


class TestGetWorkflowImpl:
    """Tests for _get_workflow_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_no_id_or_name(self, context):
        """Should return error when neither ID nor name provided."""
        from src.services.mcp.server import _get_workflow_impl

        result = await _get_workflow_impl(context, None, None)
        assert "Error" in result
        assert "workflow_id or workflow_name" in result


class TestGetExecutionImpl:
    """Tests for _get_execution_impl()."""

    @pytest.mark.asyncio
    async def test_returns_error_when_id_empty(self, context):
        """Should return error when execution_id is empty."""
        from src.services.mcp.server import _get_execution_impl

        result = await _get_execution_impl(context, "")
        assert "Error: execution_id is required" in result


# ==================== Integration Test Models ====================


class TestIntegrationTestModels:
    """Tests for integration test request/response models."""

    def test_integration_test_request_model(self):
        """Should have proper request model structure."""
        from src.models.contracts.integrations import IntegrationTestRequest

        request = IntegrationTestRequest(organization_id=uuid4())
        assert request.organization_id is not None

    def test_integration_test_response_model(self):
        """Should have proper response model structure."""
        from src.models.contracts.integrations import IntegrationTestResponse

        response = IntegrationTestResponse(
            success=True,
            message="Connection successful",
            method_called="list_users",
            duration_ms=150,
        )
        assert response.success is True
        assert response.message == "Connection successful"
        assert response.method_called == "list_users"
        assert response.duration_ms == 150

    def test_integration_test_response_with_error(self):
        """Should handle error details."""
        from src.models.contracts.integrations import IntegrationTestResponse

        response = IntegrationTestResponse(
            success=False,
            message="Connection failed",
            error_details="HTTP 401: Unauthorized",
        )
        assert response.success is False
        assert response.error_details == "HTTP 401: Unauthorized"


# ==================== SYSTEM_TOOLS Registry Tests ====================


class TestSystemToolsRegistry:
    """Tests for SYSTEM_TOOLS registry."""

    def test_all_tools_registered(self):
        """All 18 system tools should be registered."""
        from src.routers.tools import SYSTEM_TOOLS

        tool_ids = {t.id for t in SYSTEM_TOOLS}

        # Original 7
        assert "execute_workflow" in tool_ids
        assert "list_workflows" in tool_ids
        assert "list_integrations" in tool_ids
        assert "list_forms" in tool_ids
        assert "get_form_schema" in tool_ids
        assert "validate_form_schema" in tool_ids
        assert "search_knowledge" in tool_ids

        # File operations (6)
        assert "read_file" in tool_ids
        assert "write_file" in tool_ids
        assert "list_files" in tool_ids
        assert "delete_file" in tool_ids
        assert "search_files" in tool_ids
        assert "create_folder" in tool_ids

        # Workflow/execution (5)
        assert "validate_workflow" in tool_ids
        assert "get_workflow_schema" in tool_ids
        assert "get_workflow" in tool_ids
        assert "list_executions" in tool_ids
        assert "get_execution" in tool_ids

    def test_file_operations_disabled_for_coding_agent(self):
        """File operation tools should be disabled by default for coding agent."""
        from src.routers.tools import SYSTEM_TOOLS

        file_tools = ["read_file", "write_file", "list_files", "delete_file", "search_files", "create_folder"]
        for tool in SYSTEM_TOOLS:
            if tool.id in file_tools:
                assert tool.default_enabled_for_coding_agent is False, f"{tool.id} should be disabled for coding agent"

    def test_workflow_execution_tools_enabled_for_coding_agent(self):
        """Workflow and execution tools should be enabled by default for coding agent."""
        from src.routers.tools import SYSTEM_TOOLS

        workflow_tools = ["validate_workflow", "get_workflow_schema", "get_workflow", "list_executions", "get_execution"]
        for tool in SYSTEM_TOOLS:
            if tool.id in workflow_tools:
                assert tool.default_enabled_for_coding_agent is True, f"{tool.id} should be enabled for coding agent"

    def test_all_tools_have_required_fields(self):
        """All tools should have id, name, description, and type."""
        from src.routers.tools import SYSTEM_TOOLS

        for tool in SYSTEM_TOOLS:
            assert tool.id, f"Tool missing id"
            assert tool.name, f"Tool {tool.id} missing name"
            assert tool.description, f"Tool {tool.id} missing description"
            assert tool.type == "system", f"Tool {tool.id} has wrong type"


# ==================== BifrostMCPServer Tests ====================


class TestBifrostMCPServer:
    """Tests for BifrostMCPServer class."""

    def test_get_tool_names_includes_all_tools(self, context):
        """get_tool_names() should include all 18 tools when no filter."""
        from src.services.mcp.server import BifrostMCPServer

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Should have 18 tools prefixed with mcp__bifrost__
        assert len(tool_names) == 18

        # Check a few are properly prefixed
        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__read_file" in tool_names
        assert "mcp__bifrost__validate_workflow" in tool_names

    def test_get_tool_names_filters_by_enabled(self, context):
        """get_tool_names() should filter based on enabled_system_tools."""
        from src.services.mcp.server import BifrostMCPServer

        context.enabled_system_tools = ["execute_workflow", "list_workflows"]
        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert len(tool_names) == 2
        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__read_file" not in tool_names
