# api/tests/unit/services/mcp_server/test_tool_result.py
"""Unit tests for MCP tool result helpers."""

from mcp.types import CallToolResult, TextContent

from src.services.mcp_server.tool_result import (
    error_result,
    format_diff,
    format_file_content,
    format_grep_matches,
    success_result,
)


class TestSuccessResult:
    """Tests for success_result helper."""

    def test_returns_call_tool_result(self):
        """Should return a CallToolResult instance."""
        result = success_result("Test message", {"key": "value"})

        assert isinstance(result, CallToolResult)

    def test_content_is_text_content_list(self):
        """Should have content as list of TextContent."""
        result = success_result("Hello world", {"data": 123})

        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].type == "text"
        assert result.content[0].text == "Hello world"

    def test_structured_content_preserved(self):
        """Should preserve structuredContent dict."""
        data = {"success": True, "count": 42, "items": ["a", "b"]}
        result = success_result("Display text", data)

        assert result.structuredContent == data

    def test_is_error_false(self):
        """Should have isError=False for success."""
        result = success_result("OK", {})

        assert result.isError is False


class TestErrorResult:
    """Tests for error_result helper."""

    def test_returns_call_tool_result(self):
        """Should return a CallToolResult instance."""
        result = error_result("Something went wrong")

        assert isinstance(result, CallToolResult)

    def test_content_prefixed_with_error(self):
        """Should prefix content with 'Error:'."""
        result = error_result("File not found")

        assert result.content[0].text == "Error: File not found"

    def test_structured_content_with_error_key(self):
        """Should include error in structuredContent."""
        result = error_result("Invalid input")

        assert result.structuredContent == {"error": "Invalid input"}

    def test_structured_content_with_extra_data(self):
        """Should merge extra data into structuredContent."""
        result = error_result("Not unique", {"match_count": 3, "locations": [1, 5, 9]})

        assert result.structuredContent["error"] == "Not unique"
        assert result.structuredContent["match_count"] == 3
        assert result.structuredContent["locations"] == [1, 5, 9]

    def test_is_error_true(self):
        """Should have isError=True for errors."""
        result = error_result("Oops")

        assert result.isError is True


class TestFormatGrepMatches:
    """Tests for format_grep_matches helper."""

    def test_empty_matches_returns_not_found_message(self):
        """Should return 'No matches' for empty list."""
        result = format_grep_matches([], "def foo")

        assert "No matches found" in result
        assert "def foo" in result

    def test_single_match_format(self):
        """Should format single match in grep style."""
        matches = [{"path": "src/auth.py", "line_number": 45, "match": "def get_user(id):"}]
        result = format_grep_matches(matches, "get_user")

        assert "Found 1 match" in result
        assert "src/auth.py:45:" in result
        assert "def get_user(id):" in result

    def test_multiple_matches_format(self):
        """Should format multiple matches in grep style."""
        matches = [
            {"path": "src/auth.py", "line_number": 45, "match": "def get_user(id):"},
            {"path": "src/models.py", "line_number": 12, "match": "  user = get_user(uid)"},
        ]
        result = format_grep_matches(matches, "get_user")

        assert "Found 2 match" in result
        assert "src/auth.py:45:" in result
        assert "src/models.py:12:" in result

    def test_strips_match_whitespace(self):
        """Should strip leading/trailing whitespace from match."""
        matches = [{"path": "test.py", "line_number": 1, "match": "    indented code    "}]
        result = format_grep_matches(matches, "code")

        assert "indented code" in result
        assert "    indented code    " not in result


class TestFormatDiff:
    """Tests for format_diff helper."""

    def test_shows_path_header(self):
        """Should start with 'Updated path'."""
        result = format_diff("src/auth.py", ["old"], ["new"])

        assert result.startswith("Updated src/auth.py")

    def test_old_lines_prefixed_with_minus(self):
        """Should prefix removed lines with '-'."""
        result = format_diff("test.py", ["return None"], ["return value"])

        assert "-  return None" in result

    def test_new_lines_prefixed_with_plus(self):
        """Should prefix added lines with '+'."""
        result = format_diff("test.py", ["return None"], ["return value"])

        assert "+  return value" in result

    def test_multiple_lines(self):
        """Should handle multiple old and new lines."""
        old = ["def foo():", "    pass"]
        new = ["def foo(x):", "    return x"]
        result = format_diff("test.py", old, new)

        assert "-  def foo():" in result
        assert "-      pass" in result
        assert "+  def foo(x):" in result
        assert "+      return x" in result


class TestFormatFileContent:
    """Tests for format_file_content helper."""

    def test_shows_path_header(self):
        """Should show path at top."""
        result = format_file_content("src/main.py", "print('hello')")

        assert result.startswith("src/main.py")

    def test_adds_line_numbers(self):
        """Should add line numbers to each line."""
        result = format_file_content("test.py", "line1\nline2\nline3")

        assert "1: line1" in result
        assert "2: line2" in result
        assert "3: line3" in result

    def test_custom_start_line(self):
        """Should support custom start line number."""
        result = format_file_content("test.py", "code here", start_line=45)

        assert "45: code here" in result

    def test_pads_line_numbers(self):
        """Should right-align line numbers."""
        content = "\n".join(["line"] * 100)
        result = format_file_content("test.py", content)

        # Line 1 should be padded, line 100 should not need padding
        assert "  1: line" in result
        assert "100: line" in result


# =============================================================================
# Integration Tests for Code Editor Tools
# =============================================================================

import pytest


class TestDeleteContentResult:
    """Tests for delete_content tool returning CallToolResult."""

    @pytest.mark.asyncio
    async def test_success_returns_call_tool_result(self):
        """delete_content should return CallToolResult on success."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import delete_content

        context = MCPContext(
            user_id=uuid4(),
            org_id=None,
            is_platform_admin=True,
            user_email="test@test.com",
            user_name="Test",
        )

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.services.mcp_server.tools.code_editor._delete_workflow"
            ) as mock_delete:
                mock_delete.return_value = True

                result = await delete_content(
                    context=context,
                    entity_type="workflow",
                    path="features/test.py",
                )

        assert isinstance(result, CallToolResult)
        assert result.isError is False
        # Type narrow to TextContent for .text access
        content = result.content[0]
        assert hasattr(content, "text")
        assert "Deleted features/test.py" in content.text  # type: ignore[union-attr]
        assert result.structuredContent is not None
        assert result.structuredContent["success"] is True
        assert result.structuredContent["path"] == "features/test.py"

    @pytest.mark.asyncio
    async def test_not_found_returns_error_result(self):
        """delete_content should return error CallToolResult when file not found."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import delete_content

        context = MCPContext(
            user_id=uuid4(),
            org_id=None,
            is_platform_admin=True,
            user_email="test@test.com",
            user_name="Test",
        )

        with patch("src.services.mcp_server.tools.code_editor.get_db_context") as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "src.services.mcp_server.tools.code_editor._delete_workflow"
            ) as mock_delete:
                mock_delete.return_value = False

                result = await delete_content(
                    context=context,
                    entity_type="workflow",
                    path="features/nonexistent.py",
                )

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        # Type narrow to TextContent for .text access
        content = result.content[0]
        assert hasattr(content, "text")
        assert "Error:" in content.text  # type: ignore[union-attr]
        assert "not found" in content.text.lower()  # type: ignore[union-attr]


class TestPatchContentResult:
    """Tests for patch_content tool returning CallToolResult."""

    @pytest.mark.asyncio
    async def test_success_returns_diff_format(self):
        """patch_content should return diff-style display on success."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import patch_content

        context = MCPContext(
            user_id=uuid4(),
            org_id=None,
            is_platform_admin=True,
            user_email="test@test.com",
            user_name="Test",
        )

        with patch(
            "src.services.mcp_server.tools.code_editor._get_content_by_entity"
        ) as mock_get:
            mock_get.return_value = (
                "def hello():\n    return 'hello'\n",
                {"path": "test.py"},
                None,
            )

            with patch(
                "src.services.mcp_server.tools.code_editor._persist_content"
            ) as mock_persist:
                mock_persist.return_value = None

                result = await patch_content(
                    context=context,
                    entity_type="workflow",
                    path="test.py",
                    old_string="return 'hello'",
                    new_string="return 'world'",
                )

        assert isinstance(result, CallToolResult)
        assert result.isError is False
        # Type narrow to TextContent for .text access
        content = result.content[0]
        assert hasattr(content, "text")
        assert "Updated test.py" in content.text  # type: ignore[union-attr]
        assert "-  return 'hello'" in content.text  # type: ignore[union-attr]
        assert "+  return 'world'" in content.text  # type: ignore[union-attr]
        assert result.structuredContent is not None
        assert result.structuredContent["success"] is True

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        """patch_content should return error when old_string not found."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import patch_content

        context = MCPContext(
            user_id=uuid4(),
            org_id=None,
            is_platform_admin=True,
            user_email="test@test.com",
            user_name="Test",
        )

        with patch(
            "src.services.mcp_server.tools.code_editor._get_content_by_entity"
        ) as mock_get:
            mock_get.return_value = (
                "completely different content",
                {"path": "test.py"},
                None,
            )

            result = await patch_content(
                context=context,
                entity_type="workflow",
                path="test.py",
                old_string="this does not exist",
                new_string="replacement",
            )

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        # Type narrow to TextContent for .text access
        content = result.content[0]
        assert hasattr(content, "text")
        assert "not found" in content.text.lower()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_multiple_matches_returns_error_with_locations(self):
        """patch_content should return error with locations when multiple matches."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import patch_content

        context = MCPContext(
            user_id=uuid4(),
            org_id=None,
            is_platform_admin=True,
            user_email="test@test.com",
            user_name="Test",
        )

        with patch(
            "src.services.mcp_server.tools.code_editor._get_content_by_entity"
        ) as mock_get:
            # Content with 'return' appearing twice
            mock_get.return_value = (
                "def a():\n    return 1\ndef b():\n    return 2\n",
                {"path": "test.py"},
                None,
            )

            result = await patch_content(
                context=context,
                entity_type="workflow",
                path="test.py",
                old_string="return",
                new_string="yield",
            )

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        # Type narrow to TextContent for .text access
        content = result.content[0]
        assert hasattr(content, "text")
        assert "2 locations" in content.text or "matches" in content.text.lower()  # type: ignore[union-attr]
        assert result.structuredContent is not None
        assert "match_locations" in result.structuredContent
