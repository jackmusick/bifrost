"""
Unit tests for Code Editor MCP Tools.

Tests the precision editing tools:
- list_content: List files by entity type
- search_content: Regex search with context
- read_content_lines: Line range reading
- get_content: Full content read
- patch_content: Surgical edits
- replace_content: Full content write
- delete_content: Delete files
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from src.services.mcp_server.server import MCPContext


def get_result_data(result: ToolResult) -> dict:
    """Extract structured data from a ToolResult."""
    return result.structured_content or {}


def get_result_text(result: ToolResult) -> str:
    """Extract display text from a ToolResult."""
    if not result.content:
        return ""
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    return "\n".join(texts)


def is_error_result(result: ToolResult) -> bool:
    """Check if a ToolResult represents an error."""
    if result.structured_content and "error" in result.structured_content:
        return True
    if result.content and isinstance(result.content, str) and result.content.startswith("Error:"):
        return True
    return False


@pytest.fixture
def platform_admin_context() -> MCPContext:
    """Create an MCPContext for a platform admin user."""
    return MCPContext(
        user_id=uuid4(),
        org_id=None,
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


class TestListContent:
    """Tests for the list_content MCP tool."""

    @pytest.mark.asyncio
    async def test_list_workflows(self, platform_admin_context):
        """Should list workflow paths."""
        from src.services.mcp_server.tools.code_editor import list_content

        mock_wf1 = MagicMock()
        mock_wf1.path = "workflows/sync_tickets.py"
        mock_wf1.organization_id = None

        mock_wf2 = MagicMock()
        mock_wf2.path = "workflows/sync_users.py"
        mock_wf2.organization_id = None

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_wf1, mock_wf2]
            mock_session.execute.return_value = mock_result

            result = await list_content(
                context=platform_admin_context,
                entity_type="workflow",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert "files" in data
            assert len(data["files"]) == 2
            assert data["files"][0]["path"] == "workflows/sync_tickets.py"

    @pytest.mark.asyncio
    async def test_list_requires_app_id_for_app_files(self, platform_admin_context):
        """Should return error if app_id not provided for app_file."""
        from src.services.mcp_server.tools.code_editor import list_content

        result = await list_content(
            context=platform_admin_context,
            entity_type="app_file",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "app_id" in data["error"]

    @pytest.mark.asyncio
    async def test_list_invalid_entity_type(self, platform_admin_context):
        """Should return error for invalid entity_type."""
        from src.services.mcp_server.tools.code_editor import list_content

        result = await list_content(
            context=platform_admin_context,
            entity_type="invalid",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "Invalid entity_type" in data["error"]

    @pytest.mark.asyncio
    async def test_list_modules(self, platform_admin_context):
        """Should list module paths."""
        from src.services.mcp_server.tools.code_editor import list_content

        mock_mod1 = MagicMock()
        mock_mod1.path = "modules/helpers.py"

        mock_mod2 = MagicMock()
        mock_mod2.path = "modules/utils.py"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_mod1, mock_mod2]
            mock_session.execute.return_value = mock_result

            result = await list_content(
                context=platform_admin_context,
                entity_type="module",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert "files" in data
            assert len(data["files"]) == 2
            assert data["files"][0]["path"] == "modules/helpers.py"

    @pytest.mark.asyncio
    async def test_list_app_files(self, platform_admin_context):
        """Should list app files for an application."""
        from src.services.mcp_server.tools.code_editor import list_content

        app_id = str(uuid4())

        mock_app = MagicMock()
        mock_app.draft_version_id = uuid4()
        mock_app.organization_id = None

        mock_file1 = MagicMock()
        mock_file1.path = "components/Header.tsx"

        mock_file2 = MagicMock()
        mock_file2.path = "pages/index.tsx"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_session.get.return_value = mock_app

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_file1, mock_file2]
            mock_session.execute.return_value = mock_result

            result = await list_content(
                context=platform_admin_context,
                entity_type="app_file",
                app_id=app_id,
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert "files" in data
            assert len(data["files"]) == 2
            assert data["files"][0]["path"] == "components/Header.tsx"
            assert data["files"][0]["app_id"] == app_id

    @pytest.mark.asyncio
    async def test_list_with_path_prefix(self, platform_admin_context):
        """Should filter by path_prefix when provided."""
        from src.services.mcp_server.tools.code_editor import list_content

        mock_wf = MagicMock()
        mock_wf.path = "workflows/sync_tickets.py"
        mock_wf.organization_id = None

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_wf]
            mock_session.execute.return_value = mock_result

            result = await list_content(
                context=platform_admin_context,
                entity_type="workflow",
                path_prefix="workflows/",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_list_workflows_org_scoped(self, org_user_context):
        """Should filter workflows by organization for non-admin users."""
        from src.services.mcp_server.tools.code_editor import list_content

        mock_wf = MagicMock()
        mock_wf.path = "workflows/sync_tickets.py"
        mock_wf.organization_id = org_user_context.org_id

        # Mock organization for scope name lookup
        mock_org = MagicMock()
        mock_org.id = org_user_context.org_id
        mock_org.name = "Test Org"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # First call returns workflows, second returns organizations
            mock_wf_result = MagicMock()
            mock_wf_result.scalars.return_value.all.return_value = [mock_wf]

            mock_org_result = MagicMock()
            mock_org_result.scalars.return_value.all.return_value = [mock_org]

            mock_session.execute.side_effect = [mock_wf_result, mock_org_result]

            result = await list_content(
                context=org_user_context,
                entity_type="workflow",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert "files" in data
            assert len(data["files"]) == 1
            # Should have scopes array with org name
            assert data["files"][0]["scopes"] == ["Test Org"]
            # Should be called twice: once for workflows, once for organizations
            assert mock_session.execute.call_count == 2


class TestSearchContent:
    """Tests for the search_content MCP tool."""

    @pytest.mark.asyncio
    async def test_search_workflow_content(self, platform_admin_context):
        """Should find matches in workflow code with context."""
        from src.services.mcp_server.tools.code_editor import search_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync_tickets.py"
        mock_workflow.organization_id = None
        mock_workflow.code = '''from bifrost import workflow

@workflow(name="Sync Tickets")
async def sync_tickets(client_id: str) -> dict:
    """Sync tickets from HaloPSA."""
    return {"synced": True}
'''

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_workflow]
            mock_session.execute.return_value = mock_result

            result = await search_content(
                context=platform_admin_context,
                pattern="async def",
                entity_type="workflow",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert "matches" in data
            assert len(data["matches"]) == 1
            assert data["matches"][0]["line_number"] == 4
            assert "sync_tickets" in data["matches"][0]["match"]

    @pytest.mark.asyncio
    async def test_search_requires_valid_entity_type(self, platform_admin_context):
        """Should return error if entity_type is invalid."""
        from src.services.mcp_server.tools.code_editor import search_content

        result = await search_content(
            context=platform_admin_context,
            pattern="test",
            entity_type="",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_search_invalid_regex(self, platform_admin_context):
        """Should return error for invalid regex pattern."""
        from src.services.mcp_server.tools.code_editor import search_content

        result = await search_content(
            context=platform_admin_context,
            pattern="[invalid",
            entity_type="workflow",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "Invalid regex" in data["error"]


class TestReadContentLines:
    """Tests for the read_content_lines MCP tool."""

    @pytest.mark.asyncio
    async def test_read_line_range(self, platform_admin_context):
        """Should read specific line range from workflow."""
        from src.services.mcp_server.tools.code_editor import read_content_lines

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = """line 1
line 2
line 3
line 4
line 5
line 6
line 7
line 8
line 9
line 10"""

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            result = await read_content_lines(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/sync.py",
                start_line=3,
                end_line=6,
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["start_line"] == 3
            assert data["end_line"] == 6
            assert data["total_lines"] == 10
            assert "3: line 3" in data["content"]
            assert "6: line 6" in data["content"]
            assert "line 2" not in data["content"]

    @pytest.mark.asyncio
    async def test_read_requires_path(self, platform_admin_context):
        """Should return error if path not provided."""
        from src.services.mcp_server.tools.code_editor import read_content_lines

        result = await read_content_lines(
            context=platform_admin_context,
            entity_type="workflow",
            path="",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "path" in data["error"]


class TestGetContent:
    """Tests for the get_content MCP tool."""

    @pytest.mark.asyncio
    async def test_get_full_content(self, platform_admin_context):
        """Should return full file content with metadata."""
        from src.services.mcp_server.tools.code_editor import get_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = "line 1\nline 2\nline 3"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            result = await get_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/sync.py",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["path"] == "workflows/sync.py"
            assert data["total_lines"] == 3
            assert "line 1" in data["content"]
            assert "line 3" in data["content"]

    @pytest.mark.asyncio
    async def test_get_content_not_found(self, platform_admin_context):
        """Should return error if file not found."""
        from src.services.mcp_server.tools.code_editor import get_content

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_session.execute.return_value = mock_result

            result = await get_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/nonexistent.py",
            )

            assert isinstance(result, ToolResult)
            assert is_error_result(result)
            data = get_result_data(result)
            assert "error" in data
            assert "not found" in data["error"].lower()


class TestPatchContent:
    """Tests for the patch_content MCP tool."""

    @pytest.mark.asyncio
    async def test_patch_unique_string(self, platform_admin_context):
        """Should replace unique string successfully."""
        from src.services.mcp_server.tools.code_editor import patch_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = '''async def sync_tickets():
    return {"status": "old"}
'''

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            # Mock FileStorageService for validation
            with patch(
                "src.services.mcp_server.tools.code_editor.FileStorageService"
            ) as mock_fs:
                mock_fs_instance = MagicMock()
                mock_fs_instance.write_file = AsyncMock()
                mock_fs.return_value = mock_fs_instance

                result = await patch_content(
                    context=platform_admin_context,
                    entity_type="workflow",
                    path="workflows/sync.py",
                    old_string='return {"status": "old"}',
                    new_string='return {"status": "new"}',
                )

                assert isinstance(result, ToolResult)
                data = get_result_data(result)
                assert data["success"] is True

    @pytest.mark.asyncio
    async def test_patch_non_unique_string_fails(self, platform_admin_context):
        """Should fail when old_string matches multiple locations."""
        from src.services.mcp_server.tools.code_editor import patch_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = '''def func1():
    return "duplicate"

def func2():
    return "duplicate"
'''

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            result = await patch_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/sync.py",
                old_string='return "duplicate"',
                new_string='return "new_value"',
            )

            assert isinstance(result, ToolResult)
            assert is_error_result(result)
            data = get_result_data(result)
            assert "match_locations" in data or "matches" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_patch_string_not_found(self, platform_admin_context):
        """Should fail when old_string not found."""
        from src.services.mcp_server.tools.code_editor import patch_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = "some code here"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            result = await patch_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/sync.py",
                old_string="nonexistent string",
                new_string="replacement",
            )

            assert isinstance(result, ToolResult)
            assert is_error_result(result)
            data = get_result_data(result)
            assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_patch_requires_old_string(self, platform_admin_context):
        """Should return error if old_string not provided."""
        from src.services.mcp_server.tools.code_editor import patch_content

        result = await patch_content(
            context=platform_admin_context,
            entity_type="workflow",
            path="workflows/sync.py",
            old_string="",
            new_string="replacement",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "old_string" in data["error"]

    @pytest.mark.asyncio
    async def test_patch_requires_app_id_for_app_files(self, platform_admin_context):
        """Should return error if app_id not provided for app_file."""
        from src.services.mcp_server.tools.code_editor import patch_content

        result = await patch_content(
            context=platform_admin_context,
            entity_type="app_file",
            path="components/Button.tsx",
            old_string="old code",
            new_string="new code",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "app_id" in data["error"]


class TestReplaceContent:
    """Tests for the replace_content MCP tool."""

    @pytest.mark.asyncio
    async def test_replace_existing_workflow(self, platform_admin_context):
        """Should replace entire file content."""
        from src.services.mcp_server.tools.code_editor import replace_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/sync.py"
        mock_workflow.organization_id = None
        mock_workflow.code = "old content"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_workflow
            mock_session.execute.return_value = mock_result

            with patch(
                "src.services.mcp_server.tools.code_editor.FileStorageService"
            ) as mock_fs:
                mock_fs_instance = MagicMock()
                mock_fs_instance.read_file = AsyncMock(return_value=(b"old", None))
                mock_fs_instance.write_file = AsyncMock()
                mock_fs.return_value = mock_fs_instance

                result = await replace_content(
                    context=platform_admin_context,
                    entity_type="workflow",
                    path="workflows/sync.py",
                    content='''from bifrost import workflow

@workflow(name="Sync")
async def sync():
    return {"done": True}
''',
                )

                assert isinstance(result, ToolResult)
                data = get_result_data(result)
                assert data["success"] is True
                assert data["entity_type"] == "workflow"

    @pytest.mark.asyncio
    async def test_replace_validates_entity_type_mismatch(self, platform_admin_context):
        """Should error if declared entity_type doesn't match content."""
        from src.services.mcp_server.tools.code_editor import replace_content

        # Trying to create a "module" with @workflow decorator should fail
        result = await replace_content(
            context=platform_admin_context,
            entity_type="module",
            path="modules/helpers.py",
            content='''from bifrost import workflow

@workflow(name="Should Be Module")
async def oops():
    return {}
''',
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "mismatch" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_replace_requires_content(self, platform_admin_context):
        """Should return error if content not provided."""
        from src.services.mcp_server.tools.code_editor import replace_content

        result = await replace_content(
            context=platform_admin_context,
            entity_type="workflow",
            path="workflows/sync.py",
            content="",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "content" in data["error"]

    @pytest.mark.asyncio
    async def test_replace_requires_path(self, platform_admin_context):
        """Should return error if path not provided."""
        from src.services.mcp_server.tools.code_editor import replace_content

        result = await replace_content(
            context=platform_admin_context,
            entity_type="workflow",
            path="",
            content="some content",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "path" in data["error"]

    @pytest.mark.asyncio
    async def test_replace_requires_app_id_for_app_files(self, platform_admin_context):
        """Should return error if app_id not provided for app_file."""
        from src.services.mcp_server.tools.code_editor import replace_content

        result = await replace_content(
            context=platform_admin_context,
            entity_type="app_file",
            path="components/Button.tsx",
            content="export default function Button() { return <button>Click</button>; }",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "app_id" in data["error"]

    @pytest.mark.asyncio
    async def test_replace_invalid_entity_type(self, platform_admin_context):
        """Should return error for invalid entity_type."""
        from src.services.mcp_server.tools.code_editor import replace_content

        result = await replace_content(
            context=platform_admin_context,
            entity_type="invalid",
            path="some/path.py",
            content="content",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "Invalid entity_type" in data["error"]

    @pytest.mark.asyncio
    async def test_replace_workflow_missing_decorator(self, platform_admin_context):
        """Should error if workflow content lacks @workflow decorator."""
        from src.services.mcp_server.tools.code_editor import replace_content

        # Trying to create a "workflow" without @workflow decorator should fail
        result = await replace_content(
            context=platform_admin_context,
            entity_type="workflow",
            path="workflows/sync.py",
            content='''def regular_function():
    return {"done": True}
''',
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "mismatch" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_replace_app_file_creates_new(self, platform_admin_context):
        """Should create new app file if it doesn't exist."""
        from src.services.mcp_server.tools.code_editor import replace_content

        app_id = str(uuid4())

        mock_app = MagicMock()
        mock_app.draft_version_id = uuid4()
        mock_app.organization_id = None

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_session.get.return_value = mock_app

            # File doesn't exist
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            with patch(
                "src.core.pubsub.publish_app_code_file_update"
            ) as mock_publish:
                mock_publish.return_value = None

                result = await replace_content(
                    context=platform_admin_context,
                    entity_type="app_file",
                    app_id=app_id,
                    path="components/NewComponent.tsx",
                    content="export default function NewComponent() { return <div>New</div>; }",
                )

                assert isinstance(result, ToolResult)
                data = get_result_data(result)
                assert data["success"] is True
                assert data["created"] is True
                assert data["app_id"] == app_id


class TestDeleteContent:
    """Tests for the delete_content MCP tool."""

    @pytest.mark.asyncio
    async def test_delete_workflow(self, platform_admin_context):
        """Should delete a workflow by deactivating it."""
        from src.services.mcp_server.tools.code_editor import delete_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/old_sync.py"
        mock_workflow.organization_id = None
        mock_workflow.is_active = True

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_workflow]
            mock_session.execute.return_value = mock_result

            result = await delete_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/old_sync.py",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["success"] is True
            assert data["path"] == "workflows/old_sync.py"
            assert data["entity_type"] == "workflow"
            # Verify workflow was marked inactive
            assert mock_workflow.is_active is False

    @pytest.mark.asyncio
    async def test_delete_module(self, platform_admin_context):
        """Should delete a module by marking it as deleted."""
        from src.services.mcp_server.tools.code_editor import delete_content

        mock_module = MagicMock()
        mock_module.id = uuid4()
        mock_module.path = "modules/old_helpers.py"
        mock_module.entity_type = "module"
        mock_module.is_deleted = False

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_module
            mock_session.execute.return_value = mock_result

            result = await delete_content(
                context=platform_admin_context,
                entity_type="module",
                path="modules/old_helpers.py",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["success"] is True
            assert data["path"] == "modules/old_helpers.py"
            assert data["entity_type"] == "module"
            # Verify module was marked deleted
            assert mock_module.is_deleted is True

    @pytest.mark.asyncio
    async def test_delete_app_file(self, platform_admin_context):
        """Should delete an app file from the draft version."""
        from src.services.mcp_server.tools.code_editor import delete_content

        app_id = str(uuid4())

        mock_app = MagicMock()
        mock_app.draft_version_id = uuid4()
        mock_app.organization_id = None

        mock_file = MagicMock()
        mock_file.id = uuid4()
        mock_file.path = "components/OldButton.tsx"

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_session.get.return_value = mock_app

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_file
            mock_session.execute.return_value = mock_result

            # Patch where it's imported (inside _delete_app_file)
            with patch(
                "src.core.pubsub.publish_app_code_file_update"
            ) as mock_publish:
                mock_publish.return_value = None

                result = await delete_content(
                    context=platform_admin_context,
                    entity_type="app_file",
                    app_id=app_id,
                    path="components/OldButton.tsx",
                )

                assert isinstance(result, ToolResult)
                data = get_result_data(result)
                assert data["success"] is True
                assert data["path"] == "components/OldButton.tsx"
                assert data["entity_type"] == "app_file"

                # Verify delete was called
                mock_session.delete.assert_called_once_with(mock_file)

                # Verify pubsub was called with delete action
                mock_publish.assert_called_once()
                call_kwargs = mock_publish.call_args.kwargs
                assert call_kwargs["action"] == "delete"
                assert call_kwargs["path"] == "components/OldButton.tsx"

    @pytest.mark.asyncio
    async def test_delete_not_found(self, platform_admin_context):
        """Should return error if file not found."""
        from src.services.mcp_server.tools.code_editor import delete_content

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            result = await delete_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/nonexistent.py",
            )

            assert isinstance(result, ToolResult)
            assert is_error_result(result)
            data = get_result_data(result)
            assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_requires_path(self, platform_admin_context):
        """Should return error if path not provided."""
        from src.services.mcp_server.tools.code_editor import delete_content

        result = await delete_content(
            context=platform_admin_context,
            entity_type="workflow",
            path="",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "path" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_requires_app_id_for_app_files(self, platform_admin_context):
        """Should return error if app_id not provided for app_file."""
        from src.services.mcp_server.tools.code_editor import delete_content

        result = await delete_content(
            context=platform_admin_context,
            entity_type="app_file",
            path="components/Button.tsx",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "app_id" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_invalid_entity_type(self, platform_admin_context):
        """Should return error for invalid entity_type."""
        from src.services.mcp_server.tools.code_editor import delete_content

        result = await delete_content(
            context=platform_admin_context,
            entity_type="invalid",
            path="some/path.py",
        )

        assert isinstance(result, ToolResult)
        assert is_error_result(result)
        data = get_result_data(result)
        assert "error" in data
        assert "Invalid entity_type" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_workflow_with_org_filter(self, org_user_context):
        """Should filter workflows by organization for non-admin users."""
        from src.services.mcp_server.tools.code_editor import delete_content

        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.path = "workflows/org_sync.py"
        mock_workflow.organization_id = org_user_context.org_id
        mock_workflow.is_active = True

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_workflow]
            mock_session.execute.return_value = mock_result

            result = await delete_content(
                context=org_user_context,
                entity_type="workflow",
                path="workflows/org_sync.py",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["success"] is True
            # Query should have been filtered by org_id
            mock_session.execute.assert_called_once()


class TestMultiFunctionWorkflows:
    """Tests for multi-function workflow file handling."""

    @pytest.mark.asyncio
    async def test_get_content_multi_function_file(self, platform_admin_context):
        """Should return content when multiple workflow rows share the same path."""
        from src.services.mcp_server.tools.code_editor import get_content

        code = '''from bifrost import workflow, tool

@workflow(name="Sync Tickets")
async def sync_tickets():
    return {"synced": True}

@tool(name="Get Ticket")
async def get_ticket(ticket_id: str):
    return {"id": ticket_id}
'''

        mock_wf1 = MagicMock()
        mock_wf1.id = uuid4()
        mock_wf1.path = "workflows/multi.py"
        mock_wf1.organization_id = None
        mock_wf1.code = code

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            # scalars().first() returns the first row — works even with multiple rows
            mock_result.scalars.return_value.first.return_value = mock_wf1
            mock_session.execute.return_value = mock_result

            result = await get_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/multi.py",
            )

            assert isinstance(result, ToolResult)
            assert not is_error_result(result)
            data = get_result_data(result)
            assert data["path"] == "workflows/multi.py"
            assert "sync_tickets" in data["content"]
            assert "get_ticket" in data["content"]

    @pytest.mark.asyncio
    async def test_delete_multi_function_file(self, platform_admin_context):
        """Should deactivate ALL workflows at the same path."""
        from src.services.mcp_server.tools.code_editor import delete_content

        mock_wf1 = MagicMock()
        mock_wf1.id = uuid4()
        mock_wf1.path = "workflows/multi.py"
        mock_wf1.organization_id = None
        mock_wf1.is_active = True

        mock_wf2 = MagicMock()
        mock_wf2.id = uuid4()
        mock_wf2.path = "workflows/multi.py"
        mock_wf2.organization_id = None
        mock_wf2.is_active = True

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_wf1, mock_wf2]
            mock_session.execute.return_value = mock_result

            result = await delete_content(
                context=platform_admin_context,
                entity_type="workflow",
                path="workflows/multi.py",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            assert data["success"] is True
            # Both workflows should be deactivated
            assert mock_wf1.is_active is False
            assert mock_wf2.is_active is False

    @pytest.mark.asyncio
    async def test_search_deduplicates_multi_function_results(self, platform_admin_context):
        """Should not produce duplicate search results from multi-function files."""
        from src.services.mcp_server.tools.code_editor import search_content

        code = '''from bifrost import workflow

@workflow(name="Sync")
async def sync():
    return {"done": True}

@workflow(name="Cleanup")
async def cleanup():
    return {"done": True}
'''
        # Two rows with same path and identical code (multi-function file)
        mock_wf1 = MagicMock()
        mock_wf1.id = uuid4()
        mock_wf1.path = "workflows/multi.py"
        mock_wf1.organization_id = None
        mock_wf1.code = code

        mock_wf2 = MagicMock()
        mock_wf2.id = uuid4()
        mock_wf2.path = "workflows/multi.py"
        mock_wf2.organization_id = None
        mock_wf2.code = code

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_wf1, mock_wf2]
            mock_session.execute.return_value = mock_result

            result = await search_content(
                context=platform_admin_context,
                pattern="return",
                entity_type="workflow",
            )

            assert isinstance(result, ToolResult)
            data = get_result_data(result)
            # Should have exactly 2 matches (one per "return" line), NOT 4
            assert data["total_matches"] == 2


class TestFormatDeactivationResult:
    """Tests for _format_deactivation_result."""

    def _get_text(self, result: ToolResult) -> str:
        """Extract text from ToolResult content (handles TextContent list)."""
        content = result.content
        if isinstance(content, str):
            return content
        if isinstance(content, list) and len(content) > 0:
            return content[0].text
        return ""

    def test_format_without_schedule_key(self):
        """Should not crash when pending deactivation dict lacks 'schedule' key."""
        from src.services.mcp_server.tools.code_editor import _format_deactivation_result

        pending = [
            {
                "function_name": "sync_tickets",
                "decorator_type": "workflow",
                "has_executions": False,
                "last_execution_at": None,
                "endpoint_enabled": False,
                "affected_entities": [],
            }
        ]

        result = _format_deactivation_result(
            path="workflows/sync.py",
            pending_deactivations=pending,
            available_replacements=None,
        )

        assert isinstance(result, ToolResult)
        text = self._get_text(result)
        assert "sync_tickets" in text
        assert "workflow" in text

    def test_format_with_affected_entities(self):
        """Should list affected entities in deactivation result."""
        from src.services.mcp_server.tools.code_editor import _format_deactivation_result

        pending = [
            {
                "function_name": "sync_tickets",
                "decorator_type": "workflow",
                "has_executions": True,
                "last_execution_at": "2026-01-15T12:00:00Z",
                "endpoint_enabled": True,
                "affected_entities": [
                    {
                        "entity_type": "form",
                        "name": "Ticket Sync Form",
                        "reference_type": "workflow_id",
                    }
                ],
            }
        ]

        result = _format_deactivation_result(
            path="workflows/sync.py",
            pending_deactivations=pending,
            available_replacements=None,
        )

        text = self._get_text(result)
        assert "execution history" in text
        assert "API endpoint" in text
        assert "Ticket Sync Form" in text