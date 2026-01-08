"""
Unit tests for MCP tool implementations.

Tests the actual tool implementation functions that handle
file operations, workflow validation, and execution tracking.
"""

from uuid import uuid4

import pytest

from src.services.mcp_server.server import MCPContext


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
    """Tests for read_file tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return JSON error when path is empty."""
        import json

        from src.services.mcp_server.tools.files import read_file

        result = await read_file(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "path is required"


class TestWriteFileImpl:
    """Tests for write_file tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return JSON error when path is empty."""
        import json

        from src.services.mcp_server.tools.files import write_file

        result = await write_file(context, "", "content")
        parsed = json.loads(result)
        assert parsed["error"] == "path is required"

    @pytest.mark.asyncio
    async def test_returns_error_when_content_none(self, context):
        """Should return JSON error when content is None."""
        import json

        from src.services.mcp_server.tools.files import write_file

        result = await write_file(context, "test.txt", None)  # type: ignore[arg-type]
        parsed = json.loads(result)
        assert parsed["error"] == "content is required"


class TestDeleteFileImpl:
    """Tests for delete_file tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return JSON error when path is empty."""
        import json

        from src.services.mcp_server.tools.files import delete_file

        result = await delete_file(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "path is required"


class TestSearchFilesImpl:
    """Tests for search_files tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_query_empty(self, context):
        """Should return JSON error when query is empty."""
        import json

        from src.services.mcp_server.tools.files import search_files

        result = await search_files(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "query is required"


class TestSearchKnowledgeImpl:
    """Tests for search_knowledge tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_query_empty(self, context):
        """Should return JSON error when query is empty."""
        import json

        from src.services.mcp_server.tools.knowledge import search_knowledge

        result = await search_knowledge(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "query is required"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_namespaces_accessible(self, context):
        """Should return empty results when user has no accessible namespaces."""
        import json

        from src.services.mcp_server.tools.knowledge import search_knowledge

        # Context has empty accessible_namespaces by default
        result = await search_knowledge(context, "test query")
        parsed = json.loads(result)
        assert parsed["results"] == []
        assert parsed["count"] == 0
        assert "No knowledge sources available" in parsed["message"]

    @pytest.mark.asyncio
    async def test_returns_access_denied_for_unauthorized_namespace(self, context):
        """Should deny access to namespace not in accessible list."""
        import json

        from src.services.mcp_server.tools.knowledge import search_knowledge

        context.accessible_namespaces = ["allowed-ns"]
        result = await search_knowledge(context, "test query", namespace="forbidden-ns")
        parsed = json.loads(result)
        assert "Access denied" in parsed["error"]
        assert "forbidden-ns" in parsed["error"]


class TestCreateFolderImpl:
    """Tests for create_folder tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return JSON error when path is empty."""
        import json

        from src.services.mcp_server.tools.files import create_folder

        result = await create_folder(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "path is required"


# ==================== Workflow Tool Tests ====================


class TestValidateWorkflowImpl:
    """Tests for validate_workflow tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_path_empty(self, context):
        """Should return error message when file_path is empty."""
        from src.services.mcp_server.tools.workflow import validate_workflow

        result = await validate_workflow(context, "")
        # The implementation returns an error when path is empty
        assert "Error" in result or "error" in result.lower()


class TestGetWorkflowSchemaImpl:
    """Tests for get_workflow_schema tool."""

    @pytest.mark.asyncio
    async def test_returns_schema_documentation(self, context):
        """Should return comprehensive schema documentation."""
        from src.services.mcp_server.tools.workflow import get_workflow_schema

        result = await get_workflow_schema(context)

        # Check for key sections
        assert "# Bifrost Workflow Schema" in result
        assert "@workflow" in result
        assert "from bifrost import workflow" in result
        assert "Data Providers" in result
        assert "Best Practices" in result


class TestGetWorkflowImpl:
    """Tests for get_workflow tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_no_id_or_name(self, context):
        """Should return JSON error when neither ID nor name provided."""
        import json

        from src.services.mcp_server.tools.workflow import get_workflow

        result = await get_workflow(context, None, None)
        parsed = json.loads(result)
        assert "error" in parsed
        assert "workflow_id or workflow_name" in parsed["error"]


class TestGetExecutionImpl:
    """Tests for get_execution tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_id_empty(self, context):
        """Should return JSON error when execution_id is empty."""
        import json

        from src.services.mcp_server.tools.execution import get_execution

        result = await get_execution(context, "")
        parsed = json.loads(result)
        assert parsed["error"] == "execution_id is required"


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
        """All 38 system tools should be registered via @system_tool decorator."""
        from src.routers.tools import SYSTEM_TOOLS

        tool_ids = {t.id for t in SYSTEM_TOOLS}

        # Core workflow tools
        assert "execute_workflow" in tool_ids
        assert "list_workflows" in tool_ids
        assert "validate_workflow" in tool_ids
        assert "get_workflow_schema" in tool_ids
        assert "get_workflow" in tool_ids
        assert "create_workflow" in tool_ids

        # Form tools
        assert "list_forms" in tool_ids
        assert "get_form_schema" in tool_ids
        assert "create_form" in tool_ids
        assert "get_form" in tool_ids
        assert "update_form" in tool_ids

        # File operations
        assert "read_file" in tool_ids
        assert "write_file" in tool_ids
        assert "list_files" in tool_ids
        assert "delete_file" in tool_ids
        assert "search_files" in tool_ids
        assert "create_folder" in tool_ids

        # Execution tools
        assert "list_executions" in tool_ids
        assert "get_execution" in tool_ids

        # App builder tools
        assert "list_apps" in tool_ids
        assert "create_app" in tool_ids
        assert "get_app" in tool_ids
        assert "update_app" in tool_ids
        assert "publish_app" in tool_ids
        assert "get_app_schema" in tool_ids
        assert "get_page" in tool_ids
        assert "create_page" in tool_ids
        assert "update_page" in tool_ids
        assert "delete_page" in tool_ids
        assert "list_components" in tool_ids
        assert "get_component" in tool_ids
        assert "create_component" in tool_ids
        assert "update_component" in tool_ids
        assert "delete_component" in tool_ids
        assert "move_component" in tool_ids

        # Other tools
        assert "list_integrations" in tool_ids
        assert "search_knowledge" in tool_ids
        assert "get_data_provider_schema" in tool_ids

        # Total count (46 tools including app builder, component, page, table, and organization tools)
        assert len(tool_ids) == 46, f"Expected 46 tools, got {len(tool_ids)}: {sorted(tool_ids)}"

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
            assert tool.id, "Tool missing id"
            assert tool.name, f"Tool {tool.id} missing name"
            assert tool.description, f"Tool {tool.id} missing description"
            assert tool.type == "system", f"Tool {tool.id} has wrong type"


# ==================== BifrostMCPServer Tests ====================


class TestBifrostMCPServer:
    """Tests for BifrostMCPServer class."""

    def test_get_tool_names_includes_all_tools(self, context):
        """get_tool_names() should include all system tools when no filter."""
        from src.services.mcp_server.server import BifrostMCPServer

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Should have at least 18 tools prefixed with mcp__bifrost__
        # (forms, workflows, data providers, apps, file ops, etc.)
        assert len(tool_names) >= 18

        # Check a few are properly prefixed
        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__read_file" in tool_names
        assert "mcp__bifrost__validate_workflow" in tool_names

    def test_get_tool_names_filters_by_enabled(self, context):
        """get_tool_names() should filter based on enabled_system_tools."""
        from src.services.mcp_server.server import BifrostMCPServer

        context.enabled_system_tools = ["execute_workflow", "list_workflows"]
        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert len(tool_names) == 2
        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__read_file" not in tool_names
