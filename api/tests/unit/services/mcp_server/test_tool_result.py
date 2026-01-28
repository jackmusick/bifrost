# api/tests/unit/services/mcp_server/test_tool_result.py
"""Unit tests for MCP tool result helpers."""

import pytest
from mcp.types import CallToolResult, TextContent


class TestSuccessResult:
    """Tests for success_result helper."""

    def test_returns_call_tool_result(self):
        """Should return a CallToolResult instance."""
        from src.services.mcp_server.tool_result import success_result

        result = success_result("Test message", {"key": "value"})

        assert isinstance(result, CallToolResult)

    def test_content_is_text_content_list(self):
        """Should have content as list of TextContent."""
        from src.services.mcp_server.tool_result import success_result

        result = success_result("Hello world", {"data": 123})

        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].type == "text"
        assert result.content[0].text == "Hello world"

    def test_structured_content_preserved(self):
        """Should preserve structuredContent dict."""
        from src.services.mcp_server.tool_result import success_result

        data = {"success": True, "count": 42, "items": ["a", "b"]}
        result = success_result("Display text", data)

        assert result.structuredContent == data

    def test_is_error_false(self):
        """Should have isError=False for success."""
        from src.services.mcp_server.tool_result import success_result

        result = success_result("OK", {})

        assert result.isError is False


class TestErrorResult:
    """Tests for error_result helper."""

    def test_returns_call_tool_result(self):
        """Should return a CallToolResult instance."""
        from src.services.mcp_server.tool_result import error_result

        result = error_result("Something went wrong")

        assert isinstance(result, CallToolResult)

    def test_content_prefixed_with_error(self):
        """Should prefix content with 'Error:'."""
        from src.services.mcp_server.tool_result import error_result

        result = error_result("File not found")

        assert result.content[0].text == "Error: File not found"

    def test_structured_content_with_error_key(self):
        """Should include error in structuredContent."""
        from src.services.mcp_server.tool_result import error_result

        result = error_result("Invalid input")

        assert result.structuredContent == {"error": "Invalid input"}

    def test_structured_content_with_extra_data(self):
        """Should merge extra data into structuredContent."""
        from src.services.mcp_server.tool_result import error_result

        result = error_result("Not unique", {"match_count": 3, "locations": [1, 5, 9]})

        assert result.structuredContent["error"] == "Not unique"
        assert result.structuredContent["match_count"] == 3
        assert result.structuredContent["locations"] == [1, 5, 9]

    def test_is_error_true(self):
        """Should have isError=True for errors."""
        from src.services.mcp_server.tool_result import error_result

        result = error_result("Oops")

        assert result.isError is True
