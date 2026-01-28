# MCP Tool Result Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize all Bifrost MCP tool outputs to use `CallToolResult` with proper `content` (human-readable) and `structuredContent` (machine-parseable) fields, enabling proper display in Claude Code and other MCP clients.

**Architecture:** All tools return `CallToolResult` instead of JSON strings. Built-in code tools use CLI-style output formats (grep, diff) that Claude Code auto-colors. Custom workflow tools auto-wrap their results. Frontend detects `CallToolResult` structure and renders `content` with pattern-based syntax highlighting.

**Tech Stack:** Python (FastMCP, mcp.types), TypeScript/React (frontend components), pytest (testing)

---

## Task 1: Create Tool Result Helper Module

**Files:**
- Create: `api/src/services/mcp_server/tool_result.py`
- Test: `api/tests/unit/services/mcp_server/test_tool_result.py`

**Step 1: Write the failing test for success_result**

Create test file:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.mcp_server.tool_result'`

**Step 3: Write minimal implementation for success_result**

```python
# api/src/services/mcp_server/tool_result.py
"""
MCP Tool Result Helpers

Standard helpers for building CallToolResult objects with proper
content (human-readable) and structuredContent (machine-parseable).
"""

from typing import Any

from mcp.types import CallToolResult, TextContent


def success_result(display_text: str, data: dict[str, Any]) -> CallToolResult:
    """
    Create a successful tool result with display text and structured data.

    Args:
        display_text: Human-readable text for display in CLI/UI
        data: Structured data dict for LLM parsing

    Returns:
        CallToolResult with content and structuredContent
    """
    return CallToolResult(
        content=[TextContent(type="text", text=display_text)],
        structuredContent=data,
        isError=False,
    )
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestSuccessResult -v`

Expected: PASS (4 tests)

**Step 5: Write failing test for error_result**

Add to test file:

```python
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
```

**Step 6: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestErrorResult -v`

Expected: FAIL with `ImportError` (error_result not defined)

**Step 7: Implement error_result**

Add to `tool_result.py`:

```python
def error_result(error_message: str, extra_data: dict[str, Any] | None = None) -> CallToolResult:
    """
    Create an error tool result.

    Args:
        error_message: Human-readable error description
        extra_data: Optional additional data to include in structuredContent

    Returns:
        CallToolResult with isError=True
    """
    data = {"error": error_message}
    if extra_data:
        data.update(extra_data)

    return CallToolResult(
        content=[TextContent(type="text", text=f"Error: {error_message}")],
        structuredContent=data,
        isError=True,
    )
```

**Step 8: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestErrorResult -v`

Expected: PASS (5 tests)

**Step 9: Commit**

```bash
git add api/src/services/mcp_server/tool_result.py api/tests/unit/services/mcp_server/test_tool_result.py
git commit -m "feat(mcp): add tool result helpers for CallToolResult standardization"
```

---

## Task 2: Add Display Formatting Helpers

**Files:**
- Modify: `api/src/services/mcp_server/tool_result.py`
- Test: `api/tests/unit/services/mcp_server/test_tool_result.py`

**Step 1: Write failing test for format_grep_matches**

Add to test file:

```python
class TestFormatGrepMatches:
    """Tests for format_grep_matches helper."""

    def test_empty_matches_returns_not_found_message(self):
        """Should return 'No matches' for empty list."""
        from src.services.mcp_server.tool_result import format_grep_matches

        result = format_grep_matches([], "def foo")

        assert "No matches found" in result
        assert "def foo" in result

    def test_single_match_format(self):
        """Should format single match in grep style."""
        from src.services.mcp_server.tool_result import format_grep_matches

        matches = [{"path": "src/auth.py", "line_number": 45, "match": "def get_user(id):"}]
        result = format_grep_matches(matches, "get_user")

        assert "Found 1 match" in result
        assert "src/auth.py:45:" in result
        assert "def get_user(id):" in result

    def test_multiple_matches_format(self):
        """Should format multiple matches in grep style."""
        from src.services.mcp_server.tool_result import format_grep_matches

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
        from src.services.mcp_server.tool_result import format_grep_matches

        matches = [{"path": "test.py", "line_number": 1, "match": "    indented code    "}]
        result = format_grep_matches(matches, "code")

        assert "indented code" in result
        assert "    indented code    " not in result
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatGrepMatches -v`

Expected: FAIL with `ImportError`

**Step 3: Implement format_grep_matches**

Add to `tool_result.py`:

```python
def format_grep_matches(matches: list[dict[str, Any]], pattern: str) -> str:
    """
    Format search results in grep style (file:line: match).

    This format is recognized by Claude Code for automatic syntax highlighting.

    Args:
        matches: List of match dicts with path, line_number, match keys
        pattern: The search pattern (for display in header)

    Returns:
        Grep-style formatted string
    """
    if not matches:
        return f"No matches found for pattern: {pattern}"

    count_word = "match" if len(matches) == 1 else "matches"
    lines = [f"Found {len(matches)} {count_word} for '{pattern}'", ""]

    for m in matches:
        # Format: path:line: match_content (grep style)
        match_text = m.get("match", "").strip()
        lines.append(f"{m['path']}:{m['line_number']}: {match_text}")

    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatGrepMatches -v`

Expected: PASS (4 tests)

**Step 5: Write failing test for format_diff**

Add to test file:

```python
class TestFormatDiff:
    """Tests for format_diff helper."""

    def test_shows_path_header(self):
        """Should start with 'Updated path'."""
        from src.services.mcp_server.tool_result import format_diff

        result = format_diff("src/auth.py", ["old"], ["new"])

        assert result.startswith("Updated src/auth.py")

    def test_old_lines_prefixed_with_minus(self):
        """Should prefix removed lines with '-'."""
        from src.services.mcp_server.tool_result import format_diff

        result = format_diff("test.py", ["return None"], ["return value"])

        assert "-  return None" in result

    def test_new_lines_prefixed_with_plus(self):
        """Should prefix added lines with '+'."""
        from src.services.mcp_server.tool_result import format_diff

        result = format_diff("test.py", ["return None"], ["return value"])

        assert "+  return value" in result

    def test_multiple_lines(self):
        """Should handle multiple old and new lines."""
        from src.services.mcp_server.tool_result import format_diff

        old = ["def foo():", "    pass"]
        new = ["def foo(x):", "    return x"]
        result = format_diff("test.py", old, new)

        assert "-  def foo():" in result
        assert "-  pass" in result
        assert "+  def foo(x):" in result
        assert "+  return x" in result
```

**Step 6: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatDiff -v`

Expected: FAIL with `ImportError`

**Step 7: Implement format_diff**

Add to `tool_result.py`:

```python
def format_diff(path: str, old_lines: list[str], new_lines: list[str]) -> str:
    """
    Format changes in diff style.

    Uses +/- prefixes recognized by Claude Code for automatic coloring.

    Args:
        path: File path that was modified
        old_lines: Lines that were removed
        new_lines: Lines that were added

    Returns:
        Diff-style formatted string
    """
    lines = [f"Updated {path}", ""]

    for line in old_lines:
        lines.append(f"-  {line}")

    for line in new_lines:
        lines.append(f"+  {line}")

    return "\n".join(lines)
```

**Step 8: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatDiff -v`

Expected: PASS (4 tests)

**Step 9: Write failing test for format_file_content**

Add to test file:

```python
class TestFormatFileContent:
    """Tests for format_file_content helper."""

    def test_shows_path_header(self):
        """Should show path at top."""
        from src.services.mcp_server.tool_result import format_file_content

        result = format_file_content("src/main.py", "print('hello')")

        assert result.startswith("src/main.py")

    def test_adds_line_numbers(self):
        """Should add line numbers to each line."""
        from src.services.mcp_server.tool_result import format_file_content

        result = format_file_content("test.py", "line1\nline2\nline3")

        assert "   1: line1" in result
        assert "   2: line2" in result
        assert "   3: line3" in result

    def test_custom_start_line(self):
        """Should support custom start line number."""
        from src.services.mcp_server.tool_result import format_file_content

        result = format_file_content("test.py", "code here", start_line=45)

        assert "  45: code here" in result

    def test_pads_line_numbers(self):
        """Should right-align line numbers."""
        from src.services.mcp_server.tool_result import format_file_content

        content = "\n".join(["line"] * 100)
        result = format_file_content("test.py", content)

        # Line 1 should be padded, line 100 should not need padding
        assert "   1: line" in result
        assert " 100: line" in result
```

**Step 10: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatFileContent -v`

Expected: FAIL with `ImportError`

**Step 11: Implement format_file_content**

Add to `tool_result.py`:

```python
def format_file_content(path: str, content: str, start_line: int = 1) -> str:
    """
    Format file content with line numbers.

    Uses the same numbered format as Claude Code's Read tool.

    Args:
        path: File path
        content: File content
        start_line: Starting line number (default 1)

    Returns:
        Content with line numbers
    """
    lines = content.split("\n")
    total_lines = start_line + len(lines) - 1
    width = len(str(total_lines))

    numbered = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        numbered.append(f"{line_num:>{width}}: {line}")

    return f"{path}\n" + "\n".join(numbered)
```

**Step 12: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestFormatFileContent -v`

Expected: PASS (4 tests)

**Step 13: Run all tool_result tests**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py -v`

Expected: PASS (all 21 tests)

**Step 14: Commit**

```bash
git add api/src/services/mcp_server/tool_result.py api/tests/unit/services/mcp_server/test_tool_result.py
git commit -m "feat(mcp): add display formatting helpers (grep, diff, file content)"
```

---

## Task 3: Update delete_content Tool

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`
- Test: `api/tests/unit/services/mcp_server/test_tool_result.py` (add integration test)

**Step 1: Write failing test for delete_content returning CallToolResult**

Add to test file:

```python
class TestDeleteContentResult:
    """Tests for delete_content tool returning CallToolResult."""

    @pytest.mark.asyncio
    async def test_success_returns_call_tool_result(self):
        """delete_content should return CallToolResult on success."""
        from unittest.mock import AsyncMock, MagicMock, patch
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
        assert "Deleted features/test.py" in result.content[0].text
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
        assert "Error:" in result.content[0].text
        assert "not found" in result.content[0].text.lower()
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestDeleteContentResult -v`

Expected: FAIL with `AssertionError` (returns str, not CallToolResult)

**Step 3: Update delete_content to return CallToolResult**

Modify `api/src/services/mcp_server/tools/code_editor.py`:

1. Add import at top:
```python
from mcp.types import CallToolResult

from src.services.mcp_server.tool_result import error_result, success_result
```

2. Update return type and implementation of `delete_content`:
```python
@system_tool(
    id="delete_content",
    name="Delete Content",
    description="Delete a file. For workflows, this deactivates the workflow. For modules, marks as deleted. For app files, removes from the draft version.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity to delete",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path to delete (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional). Not applicable to modules.",
            },
        },
        "required": ["entity_type", "path"],
    },
)
async def delete_content(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> CallToolResult:
    """Delete a file."""
    logger.info(f"MCP delete_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return error_result(f"Invalid entity_type: {entity_type}")
    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    try:
        async with get_db_context() as db:
            if entity_type == "app_file":
                assert app_id is not None
                deleted = await _delete_app_file(db, context, app_id, path)
            elif entity_type == "workflow":
                deleted = await _delete_workflow(db, context, path, organization_id)
            elif entity_type == "module":
                deleted = await _delete_module(db, context, path)
            elif entity_type == "text":
                deleted = await _delete_text_file(db, context, path)
            else:
                deleted = False

            if not deleted:
                return error_result(f"File not found: {path}")

            await db.commit()

        return success_result(
            f"Deleted {path}",
            {
                "success": True,
                "path": path,
                "entity_type": entity_type,
            },
        )

    except Exception as e:
        logger.exception(f"Error in delete_content: {e}")
        return error_result(str(e))
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestDeleteContentResult -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py api/tests/unit/services/mcp_server/test_tool_result.py
git commit -m "feat(mcp): update delete_content to return CallToolResult"
```

---

## Task 4: Update patch_content Tool

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`
- Test: `api/tests/unit/services/mcp_server/test_tool_result.py`

**Step 1: Write failing test for patch_content returning CallToolResult**

Add to test file:

```python
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
        assert "Updated test.py" in result.content[0].text
        assert "-  return 'hello'" in result.content[0].text
        assert "+  return 'world'" in result.content[0].text
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
        assert "not found" in result.content[0].text.lower()

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
        assert "2 locations" in result.content[0].text or "matches" in result.content[0].text.lower()
        assert "match_locations" in result.structuredContent
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestPatchContentResult -v`

Expected: FAIL with `AssertionError` (returns str, not CallToolResult)

**Step 3: Update patch_content to return CallToolResult**

Update the `patch_content` function in `code_editor.py`:

```python
@system_tool(
    id="patch_content",
    name="Patch Content",
    description="Surgical edit: replace old_string with new_string. The old_string must be unique in the file. Include enough context to ensure uniqueness. Use replace_content if patch fails due to syntax issues.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional for global). Not applicable to modules.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact string to find and replace (must be unique in file)",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement string",
            },
        },
        "required": ["entity_type", "path", "old_string", "new_string"],
    },
)
async def patch_content(
    context: Any,
    entity_type: str,
    path: str,
    old_string: str,
    new_string: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> CallToolResult:
    """Make a surgical edit by replacing a unique string."""
    logger.info(f"MCP patch_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")
    if not old_string:
        return error_result("old_string is required")
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return error_result(f"Invalid entity_type: {entity_type}")
    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    content_result, metadata_result, error = await _get_content_by_entity(
        entity_type, path, app_id, organization_id, context
    )

    if error:
        return error_result(error)
    if content_result is None or metadata_result is None:
        return error_result("Failed to retrieve content")

    content_str = _normalize_line_endings(content_result)
    old_string = _normalize_line_endings(old_string)
    new_string = _normalize_line_endings(new_string)

    # Check uniqueness
    match_count = content_str.count(old_string)

    if match_count == 0:
        return error_result("old_string not found in file")

    if match_count > 1:
        locations = _find_match_locations(content_str, old_string)
        return error_result(
            f"old_string matches {match_count} locations. Include more context to make it unique.",
            {"match_locations": locations},
        )

    # Perform replacement
    new_content = content_str.replace(old_string, new_string, 1)

    # Count lines changed
    old_lines = old_string.count("\n") + 1
    new_lines = new_string.count("\n") + 1
    lines_changed = max(old_lines, new_lines)

    # Persist the change
    try:
        await _persist_content(
            entity_type, path, new_content, app_id, organization_id, context
        )

        # Format diff-style display
        display = format_diff(
            metadata_result["path"],
            old_string.split("\n"),
            new_string.split("\n"),
        )

        return success_result(
            display,
            {
                "success": True,
                "path": metadata_result["path"],
                "lines_changed": lines_changed,
            },
        )

    except Exception as e:
        logger.exception(f"Error persisting patch: {e}")
        return error_result(f"Failed to save changes: {str(e)}")
```

Also add the import for `format_diff`:
```python
from src.services.mcp_server.tool_result import error_result, format_diff, success_result
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestPatchContentResult -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py api/tests/unit/services/mcp_server/test_tool_result.py
git commit -m "feat(mcp): update patch_content to return CallToolResult with diff display"
```

---

## Task 5: Update search_content Tool

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`
- Test: `api/tests/unit/services/mcp_server/test_tool_result.py`

**Step 1: Write failing test for search_content returning CallToolResult**

Add to test file:

```python
class TestSearchContentResult:
    """Tests for search_content tool returning CallToolResult."""

    @pytest.mark.asyncio
    async def test_matches_return_grep_format(self):
        """search_content should return grep-style format for matches."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import search_content

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
                "src.services.mcp_server.tools.code_editor._search_workflows"
            ) as mock_search:
                mock_search.return_value = [
                    {
                        "path": "features/auth.py",
                        "line_number": 42,
                        "match": "def get_user(id):",
                        "context_before": ["41: # Get user by ID"],
                        "context_after": ["43:     return db.get(id)"],
                    }
                ]

                result = await search_content(
                    context=context,
                    pattern="get_user",
                    entity_type="workflow",
                )

        assert isinstance(result, CallToolResult)
        assert result.isError is False
        assert "Found 1 match" in result.content[0].text
        assert "features/auth.py:42:" in result.content[0].text
        assert result.structuredContent["total_matches"] == 1

    @pytest.mark.asyncio
    async def test_no_matches_returns_not_found(self):
        """search_content should return 'No matches' message when nothing found."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from mcp.types import CallToolResult

        from src.services.mcp_server.server import MCPContext
        from src.services.mcp_server.tools.code_editor import search_content

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
                "src.services.mcp_server.tools.code_editor._search_workflows"
            ) as mock_search:
                mock_search.return_value = []

                result = await search_content(
                    context=context,
                    pattern="nonexistent_function",
                    entity_type="workflow",
                )

        assert isinstance(result, CallToolResult)
        assert result.isError is False  # No matches is not an error
        assert "No matches found" in result.content[0].text
```

**Step 2: Run test to verify it fails**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestSearchContentResult -v`

Expected: FAIL with `AssertionError` (returns str, not CallToolResult)

**Step 3: Update search_content to return CallToolResult**

Update the `search_content` function in `code_editor.py`:

```python
from src.services.mcp_server.tool_result import (
    error_result,
    format_diff,
    format_grep_matches,
    success_result,
)

# ... (update the function)

@system_tool(
    id="search_content",
    name="Search Content",
    description="Search for patterns in code files. Returns matching lines with context. Use to find functions, imports, or usages before making edits.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for (e.g., 'def get_.*agent', 'useWorkflow')",
            },
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity to search. Optional - omit to search all types (except app_file which requires app_id)",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required for app_file, optional for others)",
            },
            "path": {
                "type": "string",
                "description": "Filter to a specific file path (optional - searches all if omitted)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: limit to this organization (optional). Not applicable to modules or text.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of lines to show before and after each match (default: 3)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 20)",
            },
        },
        "required": ["pattern"],
    },
)
async def search_content(
    context: Any,
    pattern: str,
    entity_type: str | None = None,
    app_id: str | None = None,
    path: str | None = None,
    organization_id: str | None = None,
    context_lines: int = 3,
    max_results: int = 20,
) -> CallToolResult:
    """Search for regex patterns in code content."""
    logger.info(f"MCP search_content: pattern={pattern}, entity_type={entity_type}")

    if not pattern:
        return error_result("pattern is required")

    # Validate entity_type if provided
    valid_types = ("app_file", "workflow", "module", "text")
    if entity_type is not None and entity_type not in valid_types:
        return error_result(
            f"Invalid entity_type: {entity_type}. Must be one of: app_file, workflow, module, text"
        )

    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return error_result(f"Invalid regex pattern: {e}")

    matches: list[dict[str, Any]] = []
    truncated = False

    try:
        async with get_db_context() as db:
            # Determine which types to search
            if entity_type:
                types_to_search = [entity_type]
            else:
                types_to_search = ["workflow", "module", "text"]
                if app_id:
                    types_to_search.append("app_file")

            remaining = max_results
            for etype in types_to_search:
                if remaining <= 0:
                    break

                if etype == "app_file" and app_id:
                    type_matches = await _search_app_files(
                        db, context, app_id, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "app_file"
                    matches.extend(type_matches)
                elif etype == "workflow":
                    type_matches = await _search_workflows(
                        db, context, path, organization_id, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "workflow"
                    matches.extend(type_matches)
                elif etype == "module":
                    type_matches = await _search_modules(
                        db, context, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "module"
                    matches.extend(type_matches)
                elif etype == "text":
                    type_matches = await _search_text_files(
                        db, context, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "text"
                    matches.extend(type_matches)

                remaining = max_results - len(matches)

            if len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True

        # Format grep-style display
        display = format_grep_matches(matches, pattern)

        return success_result(
            display,
            {
                "matches": matches,
                "total_matches": len(matches),
                "truncated": truncated,
            },
        )

    except Exception as e:
        logger.exception(f"Error in search_content: {e}")
        return error_result(f"Search failed: {str(e)}")
```

**Step 4: Run test to verify it passes**

Run: `./test.sh api/tests/unit/services/mcp_server/test_tool_result.py::TestSearchContentResult -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py api/tests/unit/services/mcp_server/test_tool_result.py
git commit -m "feat(mcp): update search_content to return CallToolResult with grep display"
```

---

## Task 6: Update Remaining code_editor Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`

This task updates the remaining tools: `list_content`, `read_content_lines`, `get_content`, `replace_content`.

**Step 1: Update list_content**

Change return type to `CallToolResult` and use helpers:

```python
async def list_content(...) -> CallToolResult:
    # ... validation ...

    # ... existing query logic ...

    # Format display
    if not all_files:
        display = "No files found"
    else:
        lines = [f"Found {len(all_files)} file(s):", ""]
        for f in all_files:
            lines.append(f"  {f['path']} ({f.get('entity_type', 'unknown')})")
        display = "\n".join(lines)

    result_data: dict[str, Any] = {
        "files": all_files,
        "count": len(all_files),
    }
    if entity_type:
        result_data["entity_type"] = entity_type

    return success_result(display, result_data)
```

**Step 2: Update read_content_lines**

```python
async def read_content_lines(...) -> CallToolResult:
    # ... validation and content retrieval ...

    # Format with line numbers
    display = format_file_content(
        metadata_result["path"],
        "\n".join(selected_lines_raw),  # raw lines without numbers for display func
        start_line,
    )

    return success_result(
        display,
        {
            "path": metadata_result["path"],
            "organization_id": metadata_result.get("organization_id"),
            "app_id": metadata_result.get("app_id"),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "content": "\n".join(selected_lines),
        },
    )
```

Note: Need to adjust the logic slightly - store raw lines separately for formatting.

**Step 3: Update get_content**

```python
async def get_content(...) -> CallToolResult:
    # ... validation and content retrieval ...

    display = format_file_content(metadata_result["path"], content_str)

    result_data: dict[str, Any] = {
        "path": metadata_result["path"],
        "organization_id": metadata_result.get("organization_id"),
        "app_id": metadata_result.get("app_id"),
        "entity_id": metadata_result.get("entity_id"),
        "total_lines": total_lines,
        "content": content_str,
    }

    if truncated:
        result_data["truncated"] = True
        result_data["warning"] = warning
        display = f"{warning}\n\n{display}"

    return success_result(display, result_data)
```

**Step 4: Update replace_content**

```python
async def replace_content(...) -> CallToolResult:
    # ... validation ...

    try:
        # ... existing creation logic ...

        action = "Created" if created else "Updated"
        return success_result(
            f"{action} {path}",
            {
                "success": True,
                "path": path,
                "entity_type": entity_type,
                "organization_id": organization_id,
                "app_id": app_id,
                "created": created,
            },
        )

    except Exception as e:
        logger.exception(f"Error in replace_content: {e}")
        return error_result(str(e))
```

**Step 5: Add format_file_content to imports**

```python
from src.services.mcp_server.tool_result import (
    error_result,
    format_diff,
    format_file_content,
    format_grep_matches,
    success_result,
)
```

**Step 6: Run all code_editor tests**

Run: `./test.sh api/tests/unit/services/mcp_server/ -v -k "tool_result or code_editor"`

Expected: All tests pass

**Step 7: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py
git commit -m "feat(mcp): update all code_editor tools to return CallToolResult"
```

---

## Task 7: Update workflow.py Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/workflow.py`

**Step 1: Update imports**

Add at top of file:
```python
from mcp.types import CallToolResult

from src.services.mcp_server.tool_result import error_result, success_result
```

**Step 2: Update execute_workflow**

```python
async def execute_workflow(...) -> CallToolResult:
    # ... existing logic ...

    if not workflow_id:
        return error_result("workflow_id is required")

    try:
        workflow_uuid = UUID(workflow_id)
    except ValueError:
        return error_result(f"'{workflow_id}' is not a valid UUID. Use list_workflows to get workflow IDs.")

    # ... rest of logic ...

    result_data = {
        "success": result.status.value == "Success",
        "execution_id": result.execution_id,
        "workflow_id": str(workflow.id),
        "workflow_name": workflow.name,
        "status": result.status.value,
        "duration_ms": result.duration_ms,
        "result": result.result,
        "error": result.error,
        "error_type": result.error_type,
    }

    if result_data["success"]:
        display = f"✓ Workflow '{workflow.name}' completed successfully ({result.duration_ms}ms)"
    else:
        display = f"✗ Workflow '{workflow.name}' failed: {result.error}"

    return success_result(display, result_data)
```

**Step 3: Update list_workflows**

```python
async def list_workflows(...) -> CallToolResult:
    # ... existing logic ...

    workflow_list = [
        {
            "id": str(wf.id),
            "name": wf.name,
            "description": wf.description,
            # ... other fields
        }
        for wf in workflows
    ]

    if not workflow_list:
        display = "No workflows found"
    else:
        lines = [f"Found {len(workflow_list)} workflow(s):", ""]
        for wf in workflow_list[:10]:  # Show first 10
            lines.append(f"  {wf['name']} ({wf['id'][:8]}...)")
        if len(workflow_list) > 10:
            lines.append(f"  ... and {len(workflow_list) - 10} more")
        display = "\n".join(lines)

    return success_result(
        display,
        {
            "workflows": workflow_list,
            "count": len(workflow_list),
            "total_count": total_count,
        },
    )
```

**Step 4: Commit**

```bash
git add api/src/services/mcp_server/tools/workflow.py
git commit -m "feat(mcp): update workflow tools to return CallToolResult"
```

---

## Task 8: Update Remaining Backend Tool Files

Apply the same pattern to remaining tool files. For each file:

1. Add imports for `CallToolResult`, `error_result`, `success_result`
2. Change return type from `str` to `CallToolResult`
3. Replace `json.dumps({"error": ...})` with `error_result(...)`
4. Replace success returns with `success_result(display_text, data)`

**Files to update:**
- `api/src/services/mcp_server/tools/execution.py`
- `api/src/services/mcp_server/tools/knowledge.py`
- `api/src/services/mcp_server/tools/organizations.py`
- `api/src/services/mcp_server/tools/agents.py`
- `api/src/services/mcp_server/tools/forms.py`
- `api/src/services/mcp_server/tools/apps.py`
- `api/src/services/mcp_server/tools/tables.py`
- `api/src/services/mcp_server/tools/integrations.py`
- `api/src/services/mcp_server/tools/data_providers.py`
- `api/src/services/mcp_server/tools/sdk.py`

**Commit after each file or batch:**

```bash
git add api/src/services/mcp_server/tools/
git commit -m "feat(mcp): update all tool files to return CallToolResult"
```

---

## Task 9: Update Workflow Tool Wrapper

**Files:**
- Modify: `api/src/services/mcp_server/server.py`

**Step 1: Find and update WorkflowTool.run() method**

The `WorkflowTool` class wraps custom workflow tools. Update it to auto-wrap non-CallToolResult returns:

```python
from mcp.types import CallToolResult, TextContent

from src.services.mcp_server.tool_result import error_result, success_result

# In WorkflowTool class:
async def run(self, arguments: dict[str, Any], context: Any = None) -> CallToolResult:
    """Execute the workflow tool and wrap result in CallToolResult."""
    try:
        result = await _execute_workflow_tool_impl(
            workflow_id=self.workflow_id,
            arguments=arguments,
            context=context or _get_context_from_token(),
        )

        # If user returned CallToolResult, pass through
        if isinstance(result, CallToolResult):
            return result

        # Parse result if it's a JSON string (legacy)
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                # Plain string result
                return success_result(result, {"result": result})

        # Auto-wrap dict results
        if isinstance(result, dict):
            if result.get("error"):
                return error_result(result["error"], result)

            # Format as pretty JSON for display
            display = json.dumps(result, indent=2, default=str)
            return success_result(display, result)

        # Fallback for other types
        display = str(result)
        return success_result(display, {"result": result})

    except Exception as e:
        logger.exception(f"Error executing workflow tool: {e}")
        return error_result(str(e))
```

**Step 2: Commit**

```bash
git add api/src/services/mcp_server/server.py
git commit -m "feat(mcp): auto-wrap workflow tool results in CallToolResult"
```

---

## Task 10: Create Frontend ToolOutputDisplay Component

**Files:**
- Create: `client/src/components/chat/ToolOutputDisplay.tsx`

**Step 1: Create the component**

```typescript
// client/src/components/chat/ToolOutputDisplay.tsx
/**
 * ToolOutputDisplay Component
 *
 * Renders tool output text with pattern-based syntax highlighting.
 * Recognizes standard formats:
 * - Diff lines: +/- prefixes get green/red coloring
 * - Grep format: file:line: gets cyan coloring
 * - Status messages: Updated/Deleted/Created get blue coloring
 * - Errors: Error: prefix gets red coloring
 */

import { cn } from "@/lib/utils";

interface ToolOutputDisplayProps {
	text: string;
	className?: string;
}

/**
 * Determine CSS class for a line based on its content pattern.
 */
function getLineClass(line: string): string {
	// Diff format: added lines
	if (line.startsWith("+")) {
		return "text-green-600 dark:text-green-400";
	}

	// Diff format: removed lines
	if (line.startsWith("-")) {
		return "text-red-600 dark:text-red-400";
	}

	// Grep format: file:line: match
	if (/^[\w./]+:\d+:/.test(line)) {
		return "text-cyan-600 dark:text-cyan-400";
	}

	// Status messages
	if (/^(Updated|Deleted|Created|Found)\s/.test(line)) {
		return "text-blue-600 dark:text-blue-400";
	}

	// Error messages
	if (line.startsWith("Error:") || line.startsWith("✗")) {
		return "text-red-600 dark:text-red-400";
	}

	// Success indicators
	if (line.startsWith("✓")) {
		return "text-green-600 dark:text-green-400";
	}

	return "";
}

export function ToolOutputDisplay({
	text,
	className,
}: ToolOutputDisplayProps) {
	const lines = text.split("\n");

	return (
		<pre
			className={cn(
				"font-mono text-sm whitespace-pre-wrap overflow-x-auto",
				className
			)}
		>
			{lines.map((line, i) => (
				<div key={i} className={getLineClass(line)}>
					{line || "\u00A0"} {/* Non-breaking space for empty lines */}
				</div>
			))}
		</pre>
	);
}
```

**Step 2: Commit**

```bash
git add client/src/components/chat/ToolOutputDisplay.tsx
git commit -m "feat(ui): add ToolOutputDisplay component with pattern-based coloring"
```

---

## Task 11: Update ToolExecutionCard to Handle CallToolResult

**Files:**
- Modify: `client/src/components/chat/ToolExecutionCard.tsx`

**Step 1: Add import for ToolOutputDisplay**

```typescript
import { ToolOutputDisplay } from "@/components/chat/ToolOutputDisplay";
```

**Step 2: Create helper to detect and render CallToolResult**

Add this helper function before the component:

```typescript
/**
 * Check if result is a CallToolResult structure and extract content.
 */
function extractMcpContent(
	result: unknown
): { text: string; structured: unknown } | null {
	if (!result || typeof result !== "object") {
		return null;
	}

	const mcpResult = result as {
		content?: Array<{ type: string; text?: string }>;
		structuredContent?: unknown;
	};

	// Check for CallToolResult structure
	if (!mcpResult.content || !Array.isArray(mcpResult.content)) {
		return null;
	}

	// Extract text from TextContent blocks
	const textContent = mcpResult.content
		.filter((c) => c.type === "text" && typeof c.text === "string")
		.map((c) => c.text)
		.join("\n");

	if (!textContent) {
		return null;
	}

	return {
		text: textContent,
		structured: mcpResult.structuredContent,
	};
}
```

**Step 3: Update result rendering in the component**

Find where `PrettyInputDisplay` is used for result rendering and update:

```typescript
// In the result rendering section, replace:
{result && (
  <PrettyInputDisplay value={result} />
)}

// With:
{result && (() => {
  const mcpContent = extractMcpContent(result);
  if (mcpContent) {
    return (
      <div className="space-y-2">
        <ToolOutputDisplay text={mcpContent.text} />
        {mcpContent.structured && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              View raw data
            </summary>
            <PrettyInputDisplay value={mcpContent.structured} />
          </details>
        )}
      </div>
    );
  }
  // Legacy: render as before
  return <PrettyInputDisplay value={result} />;
})()}
```

**Step 4: Commit**

```bash
git add client/src/components/chat/ToolExecutionCard.tsx
git commit -m "feat(ui): handle CallToolResult in ToolExecutionCard"
```

---

## Task 12: Run Full Test Suite and Verify

**Step 1: Run backend tests**

```bash
./test.sh
```

Expected: All tests pass

**Step 2: Run frontend type check**

```bash
cd client && npm run tsc
```

Expected: No type errors

**Step 3: Run frontend lint**

```bash
cd client && npm run lint
```

Expected: No lint errors

**Step 4: Manual verification**

1. Start dev stack: `./debug.sh`
2. Open web client at localhost:3000
3. Test a tool call (e.g., search for code)
4. Verify:
   - Display shows formatted text (not raw JSON)
   - Colors apply correctly (green for +, red for -)
   - "View raw data" shows structuredContent

**Step 5: Final commit**

```bash
git add .
git commit -m "feat(mcp): complete CallToolResult standardization

- All backend tools return CallToolResult with content + structuredContent
- Built-in tools use CLI-style formats (grep, diff) for auto-coloring
- Workflow tools auto-wrap non-CallToolResult returns
- Frontend handles CallToolResult with pattern-based syntax highlighting"
```

---

## Verification Checklist

- [ ] All backend tools return `CallToolResult` (not `str`)
- [ ] `content` field has human-readable `TextContent`
- [ ] `structuredContent` field has raw dict data
- [ ] Error cases have `isError: True`
- [ ] Code editor tools use CLI formats (grep, diff)
- [ ] Workflow tool wrapper auto-wraps results
- [ ] Frontend detects `CallToolResult` structure
- [ ] Frontend applies pattern-based coloring
- [ ] All tests pass
- [ ] Type checking passes (Python + TypeScript)
- [ ] Linting passes

---

Plan complete and saved to `docs/plans/2026-01-28-mcp-tool-result-standardization.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
