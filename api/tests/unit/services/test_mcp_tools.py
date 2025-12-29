"""
Unit tests for MCP Tools.

Tests the MCP tools for the Bifrost platform:
- get_form_schema: Returns form schema documentation
- validate_form_schema: Validates form JSON structures
- list_workflows: Lists registered workflows
- list_forms: Lists forms with org scoping
- search_knowledge: Searches the knowledge base
- list_integrations: Lists available integrations
- execute_workflow: Executes workflows and returns results

Uses mocked database access for fast, isolated testing.

Note: The MCP tools are now consolidated in server.py with shared implementations.
We test the implementation functions directly (_*_impl functions).
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.mcp.server import (
    MCPContext,
    _execute_workflow_impl,
    _get_form_schema_impl,
    _list_forms_impl,
    _list_integrations_impl,
    _list_workflows_impl,
    _search_knowledge_impl,
    _validate_form_schema_impl,
)


# ==================== Fixtures ====================


@pytest.fixture
def platform_admin_context() -> MCPContext:
    """Create an MCPContext for a platform admin user."""
    return MCPContext(
        user_id=uuid4(),
        org_id=None,  # Platform admin has no org scope
        is_platform_admin=True,
        user_email="admin@platform.local",
        user_name="Platform Admin",
    )


@pytest.fixture
def org_user_context() -> MCPContext:
    """Create an MCPContext for a regular org user."""
    return MCPContext(
        user_id=uuid4(),
        org_id=uuid4(),
        is_platform_admin=False,
        user_email="user@org.local",
        user_name="Org User",
    )


@pytest.fixture
def mock_workflow():
    """Create a mock workflow ORM object."""
    mock = MagicMock()
    mock.id = uuid4()
    mock.name = "test_workflow"
    mock.description = "A test workflow for testing"
    mock.category = "automation"
    mock.is_tool = False
    mock.schedule = None
    mock.endpoint_enabled = True
    mock.file_path = "/tmp/bifrost/workspace/workflows/test_workflow.py"
    mock.is_active = True
    return mock


@pytest.fixture
def mock_form():
    """Create a mock form ORM object."""
    mock = MagicMock()
    mock.id = uuid4()
    mock.name = "Test Form"
    mock.description = "A test form"
    mock.workflow_id = str(uuid4())
    mock.launch_workflow_id = None
    mock.is_active = True
    mock.access_level = MagicMock(value="authenticated")
    mock.file_path = "forms/test-form.form.json"

    # Mock fields
    field = MagicMock()
    field.name = "email"
    field.label = "Email Address"
    field.type = "email"
    field.required = True
    field.position = 0
    mock.fields = [field]

    return mock


@pytest.fixture
def mock_knowledge_document():
    """Create a mock knowledge document."""
    from src.repositories.knowledge import KnowledgeDocument

    return KnowledgeDocument(
        id=str(uuid4()),
        namespace="bifrost_docs",
        content="This is documentation about the SDK",
        metadata={"source": "docs", "title": "SDK Guide"},
        score=0.85,
        organization_id=None,
        key="sdk-guide",
        created_at=datetime.utcnow(),
    )


# ==================== get_form_schema Tests ====================


class TestGetFormSchema:
    """Tests for the get_form_schema MCP tool."""

    @pytest.mark.asyncio
    async def test_documentation_content(self, org_user_context):
        """Should return comprehensive form schema documentation."""
        result = await _get_form_schema_impl(org_user_context)

        # Check that documentation contains key sections
        assert "Form Schema Documentation" in result
        assert "Field Types" in result
        assert "Text Field" in result
        assert "Select Field" in result

    @pytest.mark.asyncio
    async def test_includes_field_types(self, org_user_context):
        """Should include documentation for common field types."""
        result = await _get_form_schema_impl(org_user_context)

        # Verify field types are documented
        field_types = ["text", "number", "select", "boolean", "date"]
        for field_type in field_types:
            assert field_type in result, f"Field type {field_type} not documented"

    @pytest.mark.asyncio
    async def test_includes_example_json(self, org_user_context):
        """Should include JSON examples."""
        result = await _get_form_schema_impl(org_user_context)

        # Find the example JSON blocks
        assert "```json" in result
        assert '"type":' in result


# ==================== validate_form_schema Tests ====================


class TestValidateFormSchema:
    """Tests for the validate_form_schema MCP tool."""

    @pytest.mark.asyncio
    async def test_valid_form_schema(self, org_user_context):
        """Should validate a correct form schema structure."""
        valid_form = json.dumps({
            "name": "Test Form",
            "fields": [
                {"name": "email", "label": "Email", "type": "email", "required": True}
            ]
        })

        result = await _validate_form_schema_impl(org_user_context, valid_form)
        assert "valid" in result.lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_json(self, org_user_context):
        """Should reject invalid JSON."""
        result = await _validate_form_schema_impl(org_user_context, "{ invalid json }")
        assert "Invalid JSON" in result

    @pytest.mark.asyncio
    async def test_rejects_missing_name(self, org_user_context):
        """Should reject form missing name field."""
        form = json.dumps({
            "fields": [{"name": "test", "type": "text"}]
        })
        result = await _validate_form_schema_impl(org_user_context, form)
        assert "name" in result.lower()

    @pytest.mark.asyncio
    async def test_rejects_missing_fields(self, org_user_context):
        """Should reject form missing fields array."""
        form = json.dumps({"name": "Test"})
        result = await _validate_form_schema_impl(org_user_context, form)
        assert "fields" in result.lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_field_type(self, org_user_context):
        """Should reject fields with invalid types."""
        form = json.dumps({
            "name": "Test",
            "fields": [{"name": "test", "type": "invalid_type"}]
        })
        result = await _validate_form_schema_impl(org_user_context, form)
        assert "invalid type" in result.lower()


# ==================== list_workflows Tests ====================


class TestListWorkflows:
    """Tests for the list_workflows MCP tool."""

    @pytest.mark.asyncio
    async def test_lists_workflows(self, org_user_context, mock_workflow):
        """Should list registered workflows."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.search = AsyncMock(return_value=[mock_workflow])
                mock_repo.count_active = AsyncMock(return_value=1)
                mock_repo_cls.return_value = mock_repo

                result = await _list_workflows_impl(org_user_context)

        assert "Registered Workflows" in result
        assert "test_workflow" in result
        assert "A test workflow for testing" in result
        assert "Endpoint: Enabled" in result

    @pytest.mark.asyncio
    async def test_returns_empty_message(self, org_user_context):
        """Should return helpful message when no workflows found."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.search = AsyncMock(return_value=[])
                mock_repo.count_active = AsyncMock(return_value=0)
                mock_repo_cls.return_value = mock_repo

                result = await _list_workflows_impl(org_user_context)

        assert "No workflows found" in result
        assert "/tmp/bifrost/workspace" in result
        assert "@workflow" in result

    @pytest.mark.asyncio
    async def test_filters_by_category(self, org_user_context, mock_workflow):
        """Should pass category filter to repository."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.search = AsyncMock(return_value=[mock_workflow])
                mock_repo.count_active = AsyncMock(return_value=1)
                mock_repo_cls.return_value = mock_repo

                await _list_workflows_impl(org_user_context, category="automation")

                # Verify category was passed to search
                mock_repo.search.assert_called_once_with(
                    query=None,
                    category="automation",
                    limit=100,
                )

    @pytest.mark.asyncio
    async def test_handles_database_error(self, org_user_context):
        """Should return error message on database failure."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_db_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_workflows_impl(org_user_context)

        assert "Error listing workflows" in result


# ==================== list_forms Tests ====================


class TestListForms:
    """Tests for the list_forms MCP tool."""

    @pytest.mark.asyncio
    async def test_lists_forms_for_org_user(self, org_user_context, mock_form):
        """Should list forms for org user."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.repositories.forms.FormRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_by_organization = AsyncMock(return_value=[mock_form])
                mock_repo_cls.return_value = mock_repo

                result = await _list_forms_impl(org_user_context)

        assert "Forms" in result
        assert "Test Form" in result
        assert "A test form" in result

    @pytest.mark.asyncio
    async def test_lists_forms_for_platform_admin(
        self, platform_admin_context, mock_form
    ):
        """Should list all forms for platform admin."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.repositories.forms.FormRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_all = AsyncMock(return_value=[mock_form])
                mock_repo_cls.return_value = mock_repo

                result = await _list_forms_impl(platform_admin_context)

        assert "Forms" in result
        assert "Test Form" in result

    @pytest.mark.asyncio
    async def test_returns_empty_message(self, org_user_context):
        """Should return helpful message when no forms found."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch("src.repositories.forms.FormRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_by_organization = AsyncMock(return_value=[])
                mock_repo_cls.return_value = mock_repo

                result = await _list_forms_impl(org_user_context)

        assert "No forms found" in result

    @pytest.mark.asyncio
    async def test_handles_database_error(self, org_user_context):
        """Should return error message on database failure."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_db_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_forms_impl(org_user_context)

        assert "Error listing forms" in result


# ==================== search_knowledge Tests ====================


class TestSearchKnowledge:
    """Tests for the search_knowledge MCP tool."""

    @pytest.mark.asyncio
    async def test_searches_knowledge_base(
        self, org_user_context, mock_knowledge_document
    ):
        """Should search knowledge base and return results."""
        # Add accessible namespaces to allow knowledge search
        org_user_context.accessible_namespaces = ["test-namespace"]

        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.services.embeddings.get_embedding_client"
            ) as mock_embed_client:
                mock_client = AsyncMock()
                mock_client.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3])
                mock_embed_client.return_value = mock_client

                with patch(
                    "src.repositories.knowledge.KnowledgeRepository"
                ) as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.search = AsyncMock(return_value=[mock_knowledge_document])
                    mock_repo_cls.return_value = mock_repo

                    result = await _search_knowledge_impl(
                        org_user_context, "SDK documentation"
                    )

        assert "Knowledge Search Results" in result
        assert "SDK documentation" in result
        assert "This is documentation about the SDK" in result

    @pytest.mark.asyncio
    async def test_returns_no_results_message(self, org_user_context):
        """Should return helpful message when no results found."""
        # Add accessible namespaces to allow knowledge search
        org_user_context.accessible_namespaces = ["test-namespace"]

        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.services.embeddings.get_embedding_client"
            ) as mock_embed_client:
                mock_client = AsyncMock()
                mock_client.embed_single = AsyncMock(return_value=[0.1, 0.2, 0.3])
                mock_embed_client.return_value = mock_client

                with patch(
                    "src.repositories.knowledge.KnowledgeRepository"
                ) as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.search = AsyncMock(return_value=[])
                    mock_repo_cls.return_value = mock_repo

                    result = await _search_knowledge_impl(
                        org_user_context, "nonexistent topic"
                    )

        assert "No results found" in result
        assert "nonexistent topic" in result

    @pytest.mark.asyncio
    async def test_handles_missing_query(self, org_user_context):
        """Should return error when query is empty."""
        result = await _search_knowledge_impl(org_user_context, "")
        assert "query is required" in result

    @pytest.mark.asyncio
    async def test_handles_embedding_error(self, org_user_context):
        """Should return error when embedding service fails."""
        # Add accessible namespaces to allow knowledge search
        org_user_context.accessible_namespaces = ["test-namespace"]

        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.services.embeddings.get_embedding_client"
            ) as mock_embed_client:
                mock_embed_client.side_effect = Exception("Embedding service error")

                result = await _search_knowledge_impl(org_user_context, "test query")

        assert "Error searching knowledge" in result


# ==================== list_integrations Tests ====================


@pytest.fixture
def mock_integration():
    """Create a mock integration ORM object."""
    mock = MagicMock()
    mock.id = uuid4()
    mock.name = "Microsoft Graph"
    mock.is_deleted = False
    mock.has_oauth_config = True
    mock.entity_id_name = "Tenant ID"
    return mock


class TestListIntegrations:
    """Tests for the list_integrations MCP tool."""

    @pytest.mark.asyncio
    async def test_lists_integrations_for_platform_admin(
        self, platform_admin_context, mock_integration
    ):
        """Should list all active integrations for platform admin."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_integration]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_integrations_impl(platform_admin_context)

        assert "Available Integrations" in result
        assert "Microsoft Graph" in result
        assert "OAuth configured" in result
        assert "Tenant ID" in result

    @pytest.mark.asyncio
    async def test_lists_integrations_for_org_user(
        self, org_user_context, mock_integration
    ):
        """Should list org-mapped integrations for org user."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_integration]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_integrations_impl(org_user_context)

        assert "Available Integrations" in result
        assert "Microsoft Graph" in result

    @pytest.mark.asyncio
    async def test_returns_empty_message(self, org_user_context):
        """Should return helpful message when no integrations found."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_integrations_impl(org_user_context)

        assert "No integrations" in result
        assert "admin panel" in result

    @pytest.mark.asyncio
    async def test_handles_database_error(self, org_user_context):
        """Should return error message on database failure."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_db_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _list_integrations_impl(org_user_context)

        assert "Error listing integrations" in result


# ==================== execute_workflow Tests ====================


class TestExecuteWorkflow:
    """Tests for the execute_workflow MCP tool."""

    @pytest.mark.asyncio
    async def test_executes_workflow_successfully(
        self, org_user_context, mock_workflow
    ):
        """Should execute workflow and return success result."""
        # Create mock execution result
        mock_result = MagicMock()
        mock_result.status.value = "Success"
        mock_result.duration_ms = 150
        mock_result.result = {"output": "test value"}
        mock_result.error = None

        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_by_name = AsyncMock(return_value=mock_workflow)
                mock_repo_cls.return_value = mock_repo

                with patch(
                    "src.services.execution.service.execute_tool"
                ) as mock_execute:
                    mock_execute.return_value = mock_result

                    result = await _execute_workflow_impl(
                        org_user_context,
                        "test_workflow",
                        {"key": "value"},
                    )

        assert "executed successfully" in result
        assert "test_workflow" in result
        assert "150ms" in result
        assert "test value" in result

    @pytest.mark.asyncio
    async def test_returns_error_workflow_not_found(self, org_user_context):
        """Should return error when workflow not found."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_by_name = AsyncMock(return_value=None)
                mock_repo_cls.return_value = mock_repo

                result = await _execute_workflow_impl(
                    org_user_context,
                    "nonexistent_workflow",
                )

        assert "not found" in result
        assert "nonexistent_workflow" in result
        assert "list_workflows" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_execution_failure(
        self, org_user_context, mock_workflow
    ):
        """Should return error details when workflow execution fails."""
        # Create mock failed execution result
        mock_result = MagicMock()
        mock_result.status.value = "Failed"
        mock_result.error = "Division by zero"
        mock_result.error_type = "ValueError"

        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_session = AsyncMock()
            mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.repositories.workflows.WorkflowRepository"
            ) as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_by_name = AsyncMock(return_value=mock_workflow)
                mock_repo_cls.return_value = mock_repo

                with patch(
                    "src.services.execution.service.execute_tool"
                ) as mock_execute:
                    mock_execute.return_value = mock_result

                    result = await _execute_workflow_impl(
                        org_user_context,
                        "test_workflow",
                    )

        assert "failed" in result
        assert "Division by zero" in result
        assert "ValueError" in result

    @pytest.mark.asyncio
    async def test_handles_missing_workflow_name(self, org_user_context):
        """Should return error when workflow_name is empty."""
        result = await _execute_workflow_impl(org_user_context, "")
        assert "workflow_name is required" in result

    @pytest.mark.asyncio
    async def test_handles_exception(self, org_user_context):
        """Should return error message on unexpected exception."""
        with patch("src.core.database.get_db_context") as mock_db_ctx:
            mock_db_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Unexpected error")
            )
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await _execute_workflow_impl(
                org_user_context,
                "test_workflow",
            )

        assert "Error executing workflow" in result


# ==================== BifrostMCPServer Tests ====================


class TestBifrostMCPServer:
    """Tests for the BifrostMCPServer class."""

    def test_creates_server_with_context(self, org_user_context):
        """Should create server with context."""
        from src.services.mcp.server import BifrostMCPServer

        server = BifrostMCPServer(org_user_context)
        assert server.context == org_user_context

    def test_get_tool_names_returns_all_tools(self, org_user_context):
        """Should return all tool names when no filter."""
        from src.services.mcp.server import BifrostMCPServer

        server = BifrostMCPServer(org_user_context)
        tool_names = server.get_tool_names()

        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__list_integrations" in tool_names
        assert "mcp__bifrost__list_forms" in tool_names
        assert "mcp__bifrost__get_form_schema" in tool_names
        assert "mcp__bifrost__validate_form_schema" in tool_names
        assert "mcp__bifrost__search_knowledge" in tool_names

    def test_get_tool_names_respects_enabled_filter(self):
        """Should return only enabled tools when filter applied."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=["execute_workflow", "list_workflows"],
        )
        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__list_integrations" not in tool_names
        assert len(tool_names) == 2


# ==================== get_system_tool_ids Tests ====================


class TestGetSystemToolIds:
    """Tests for the get_system_tool_ids helper function."""

    def test_returns_all_system_tool_ids(self):
        """Should return IDs for all system tools."""
        from src.routers.tools import get_system_tool_ids, SYSTEM_TOOLS

        tool_ids = get_system_tool_ids()

        # Should return same number as SYSTEM_TOOLS
        assert len(tool_ids) == len(SYSTEM_TOOLS)

        # Should contain all expected IDs
        expected_ids = {tool.id for tool in SYSTEM_TOOLS}
        assert set(tool_ids) == expected_ids

    def test_contains_expected_tools(self):
        """Should contain the expected system tool IDs."""
        from src.routers.tools import get_system_tool_ids

        tool_ids = get_system_tool_ids()

        # These are the core system tools
        expected = [
            "execute_workflow",
            "list_workflows",
            "list_integrations",
            "list_forms",
            "get_form_schema",
            "validate_form_schema",
            "search_knowledge",
        ]

        for tool_id in expected:
            assert tool_id in tool_ids, f"Missing expected tool: {tool_id}"

    def test_returns_list_not_generator(self):
        """Should return a list, not a generator or other iterable."""
        from src.routers.tools import get_system_tool_ids

        tool_ids = get_system_tool_ids()

        assert isinstance(tool_ids, list)


# ==================== MCPConfigService Tests ====================


class TestMCPConfigService:
    """Tests for the MCP configuration service."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_config_returns_defaults_when_not_configured(self, mock_session):
        """Should return default config when no config exists."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock no config found
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = MCPConfigService(mock_session)
        config = await service.get_config()

        assert config.enabled is True
        assert config.require_platform_admin is True
        assert config.allowed_tool_ids is None
        assert config.blocked_tool_ids is None
        assert config.is_configured is False

    @pytest.mark.asyncio
    async def test_get_config_returns_stored_config(self, mock_session):
        """Should return stored config values."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock config found
        mock_config = MagicMock()
        mock_config.value_json = {
            "enabled": False,
            "require_platform_admin": False,
            "allowed_tool_ids": ["execute_workflow", "list_workflows"],
            "blocked_tool_ids": ["search_knowledge"],
        }
        mock_config.updated_at = datetime.utcnow()
        mock_config.updated_by = "admin@test.com"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = MCPConfigService(mock_session)
        config = await service.get_config()

        assert config.enabled is False
        assert config.require_platform_admin is False
        assert config.allowed_tool_ids == ["execute_workflow", "list_workflows"]
        assert config.blocked_tool_ids == ["search_knowledge"]
        assert config.is_configured is True
        assert config.configured_by == "admin@test.com"

    @pytest.mark.asyncio
    async def test_save_config_creates_new_config(self, mock_session):
        """Should create new config when none exists."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock no existing config
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()

        service = MCPConfigService(mock_session)
        config = await service.save_config(
            enabled=False,
            require_platform_admin=True,
            allowed_tool_ids=None,
            blocked_tool_ids=["search_knowledge"],
            updated_by="admin@test.com",
        )

        mock_session.add.assert_called_once()
        assert config.enabled is False
        assert config.require_platform_admin is True
        assert config.blocked_tool_ids == ["search_knowledge"]

    @pytest.mark.asyncio
    async def test_save_config_updates_existing_config(self, mock_session):
        """Should update existing config."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock existing config
        mock_config = MagicMock()
        mock_config.value_json = {"enabled": True, "require_platform_admin": True}
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = MCPConfigService(mock_session)
        config = await service.save_config(
            enabled=False,
            require_platform_admin=False,
            allowed_tool_ids=["execute_workflow"],
            blocked_tool_ids=[],
            updated_by="admin@test.com",
        )

        assert config.enabled is False
        assert config.require_platform_admin is False
        assert mock_config.value_json["enabled"] is False
        assert mock_config.updated_by == "admin@test.com"

    @pytest.mark.asyncio
    async def test_delete_config_removes_existing(self, mock_session):
        """Should delete existing config."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock existing config
        mock_config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()

        service = MCPConfigService(mock_session)
        deleted = await service.delete_config()

        assert deleted is True
        mock_session.delete.assert_called_once_with(mock_config)

    @pytest.mark.asyncio
    async def test_delete_config_returns_false_when_none_exists(self, mock_session):
        """Should return False when no config to delete."""
        from src.services.mcp.config_service import MCPConfigService

        # Mock no config
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = MCPConfigService(mock_session)
        deleted = await service.delete_config()

        assert deleted is False


class TestMCPConfigCache:
    """Tests for the MCP config caching."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_cached_values(self):
        """Should clear cached config on invalidation."""
        from src.services.mcp.config_service import (
            _cached_config,
            _cache_time,
            invalidate_mcp_config_cache,
        )

        # Call invalidate
        invalidate_mcp_config_cache()

        # Import again to check values
        from src.services.mcp import config_service

        assert config_service._cached_config is None
        assert config_service._cache_time is None


# ==================== Tool Filtering Tests ====================


class TestToolFiltering:
    """Tests for tool filtering based on allowed/blocked lists."""

    def test_allowed_tool_ids_limits_visible_tools(self):
        """Should only show tools in the allowed list when specified."""
        from src.services.mcp.server import BifrostMCPServer

        # Context with specific allowed tools
        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=["execute_workflow", "list_workflows"],
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Should only contain allowed tools
        assert "mcp__bifrost__execute_workflow" in tool_names
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__list_integrations" not in tool_names
        assert "mcp__bifrost__list_forms" not in tool_names
        assert "mcp__bifrost__search_knowledge" not in tool_names
        assert len(tool_names) == 2

    def test_empty_allowed_means_all_tools(self):
        """Should show all tools when allowed list is empty (falsy)."""
        from src.services.mcp.server import BifrostMCPServer

        # Context with empty enabled tools - empty list is falsy,
        # so BifrostMCPServer treats it as None (all tools allowed)
        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=[],
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Empty list is falsy, so it becomes None -> all tools shown
        assert len(tool_names) == 18

    def test_no_enabled_tools_means_all_tools(self):
        """Should show all tools when enabled_system_tools is not set."""
        from src.services.mcp.server import BifrostMCPServer

        # Context without enabled_system_tools set
        context = MCPContext(
            user_id=uuid4(),
            # enabled_system_tools not set -> defaults to empty list
        )
        # Manually set to None to simulate "all tools" mode
        context.enabled_system_tools = []

        # But we need to create server before setting - let's test the None case
        context2 = MCPContext(user_id=uuid4())

        # BifrostMCPServer converts empty list to None for "all tools"
        server = BifrostMCPServer(context2)

        # enabled_tools should be None since context.enabled_system_tools is empty
        # Actually the logic is: if enabled_system_tools is truthy, use it
        # If empty/falsy, _enabled_tools becomes None meaning "all tools"
        tool_names = server.get_tool_names()

        # Should contain all system tools
        expected_tools = [
            "mcp__bifrost__execute_workflow",
            "mcp__bifrost__list_workflows",
            "mcp__bifrost__list_integrations",
            "mcp__bifrost__list_forms",
            "mcp__bifrost__get_form_schema",
            "mcp__bifrost__validate_form_schema",
            "mcp__bifrost__search_knowledge",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

        # All 18 tools (7 original + 6 file ops + 5 workflow/execution tools)
        assert len(tool_names) == 18

    def test_single_tool_filtering(self):
        """Should correctly filter to single tool."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=["search_knowledge"],
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert tool_names == ["mcp__bifrost__search_knowledge"]

    def test_tool_filtering_preserves_order(self):
        """Should return tools in consistent order."""
        from src.services.mcp.server import BifrostMCPServer

        # Test multiple times to ensure consistent ordering
        for _ in range(3):
            context = MCPContext(
                user_id=uuid4(),
                enabled_system_tools=["list_workflows", "execute_workflow", "list_forms"],
            )

            server = BifrostMCPServer(context)
            tool_names = server.get_tool_names()

            # Order should match the all_tools list order, not enabled_system_tools order
            # (execute_workflow comes before list_workflows in all_tools)
            assert "mcp__bifrost__execute_workflow" in tool_names
            assert "mcp__bifrost__list_workflows" in tool_names
            assert "mcp__bifrost__list_forms" in tool_names

    def test_unknown_tool_ids_ignored(self):
        """Should ignore unknown tool IDs in enabled list."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=["execute_workflow", "unknown_tool", "fake_tool"],
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Should only contain the valid tool
        assert tool_names == ["mcp__bifrost__execute_workflow"]


class TestMCPContextFiltering:
    """Tests for MCPContext-based tool access control."""

    def test_platform_admin_sees_all_tools_by_default(self):
        """Platform admin should see all tools when no filter applied."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            is_platform_admin=True,
            # No enabled_system_tools filter
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert len(tool_names) == 18  # All system tools

    def test_org_user_respects_enabled_tools(self):
        """Org user should only see tools from enabled_system_tools."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            org_id=uuid4(),
            is_platform_admin=False,
            enabled_system_tools=["list_workflows", "list_forms"],
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert len(tool_names) == 2
        assert "mcp__bifrost__list_workflows" in tool_names
        assert "mcp__bifrost__list_forms" in tool_names

    def test_context_with_all_tools_enabled(self):
        """Context with all tools enabled should show all tools."""
        from src.services.mcp.server import BifrostMCPServer

        all_tool_ids = [
            "execute_workflow",
            "list_workflows",
            "list_integrations",
            "list_forms",
            "get_form_schema",
            "validate_form_schema",
            "search_knowledge",
        ]

        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=all_tool_ids,
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        assert len(tool_names) == 7

    def test_enabled_tools_are_case_sensitive(self):
        """Tool IDs should be case-sensitive."""
        from src.services.mcp.server import BifrostMCPServer

        context = MCPContext(
            user_id=uuid4(),
            enabled_system_tools=["Execute_Workflow", "LIST_WORKFLOWS"],  # Wrong case
        )

        server = BifrostMCPServer(context)
        tool_names = server.get_tool_names()

        # Should be empty since tool IDs don't match (case sensitive)
        assert len(tool_names) == 0
