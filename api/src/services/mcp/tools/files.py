"""
File MCP Tools

Tools for reading, writing, listing, deleting, and searching files in the workspace.
"""

import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="read_file",
    name="Read File",
    description="Read a file from the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
            },
        },
        "required": ["path"],
    },
)
async def read_file(context: Any, path: str) -> str:
    """Read a file from the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP read_file called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        result = await file_operations.read_file(path)
        if result.encoding == "base64":
            return f"Binary file ({result.size} bytes). Base64 content available but too large to display."
        return result.content or ""
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error reading file via MCP: {e}")
        return f"Error reading file: {str(e)}"


@system_tool(
    id="write_file",
    name="Write File",
    description="Write content to a file in the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
)
async def write_file(context: Any, path: str, content: str) -> str:
    """Write content to a file in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP write_file called with path={path}")

    if not path:
        return "Error: path is required"
    if content is None:
        return "Error: content is required"

    try:
        result = await file_operations.write_file(path, content)
        return f"File written successfully: {path} ({result.size} bytes)"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error writing file via MCP: {e}")
        return f"Error writing file: {str(e)}"


@system_tool(
    id="list_files",
    name="List Files",
    description="List files and directories in the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory path to list (defaults to workspace root)",
                "default": "",
            },
        },
        "required": [],
    },
)
async def list_files(context: Any, directory: str = "") -> str:
    """List files and directories in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP list_files called with directory={directory}")

    try:
        items = file_operations.list_directory(directory or "")

        if not items:
            return f"No files found in: {directory or '/'}"

        lines = [f"# Files in {directory or '/'}\n"]
        for item in items:
            icon = "folder" if item.type.value == "folder" else "file"
            size_str = f" ({item.size} bytes)" if item.type.value == "file" and item.size else ""
            lines.append(f"- [{icon}] `{item.name}`{size_str}")

        return "\n".join(lines)
    except FileNotFoundError:
        return f"Error: Directory not found: {directory}"
    except Exception as e:
        logger.exception(f"Error listing files via MCP: {e}")
        return f"Error listing files: {str(e)}"


@system_tool(
    id="delete_file",
    name="Delete File",
    description="Delete a file or directory from the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file or directory to delete",
            },
        },
        "required": ["path"],
    },
)
async def delete_file(context: Any, path: str) -> str:
    """Delete a file or directory from the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP delete_file called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        file_operations.delete_path(path)
        return f"Deleted: {path}"
    except FileNotFoundError:
        return f"Error: Path not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error deleting file via MCP: {e}")
        return f"Error deleting file: {str(e)}"


@system_tool(
    id="search_files",
    name="Search Files",
    description="Search for text patterns across files in the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text pattern to search for",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g., '**/*.py')",
                "default": "**/*",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether to match case sensitively",
                "default": False,
            },
        },
        "required": ["query"],
    },
)
async def search_files(
    context: Any,
    query: str,
    pattern: str = "**/*",
    case_sensitive: bool = False,
) -> str:
    """Search for text patterns across files in the workspace."""
    from src.services.editor import search as search_module
    from src.services.editor.search import SearchRequest

    logger.info(f"MCP search_files called with query={query}, pattern={pattern}")

    if not query:
        return "Error: query is required"

    try:
        request = SearchRequest(
            query=query,
            include_pattern=pattern,
            case_sensitive=case_sensitive,
            max_results=50,
        )
        response = search_module.search_files(request)
        results = response.results

        if not results:
            return f"No matches found for: '{query}'"

        lines = [f"# Search Results for '{query}'\n"]
        lines.append(f"Found {len(results)} matches\n")

        for result in results[:20]:  # Limit to 20 results in output
            lines.append(f"## {result.file_path}:{result.line}")
            lines.append("```")
            lines.append(result.match_text.strip())
            lines.append("```\n")

        if len(results) > 20:
            lines.append(f"... and {len(results) - 20} more matches")

        return "\n".join(lines)
    except Exception as e:
        logger.exception(f"Error searching files via MCP: {e}")
        return f"Error searching files: {str(e)}"


@system_tool(
    id="create_folder",
    name="Create Folder",
    description="Create a new folder in the Bifrost workspace.",
    category=ToolCategory.FILE,
    default_enabled_for_coding_agent=False,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path for the new folder",
            },
        },
        "required": ["path"],
    },
)
async def create_folder(context: Any, path: str) -> str:
    """Create a new folder in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP create_folder called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        file_operations.create_folder(path)
        return f"Folder created: {path}"
    except FileExistsError:
        return f"Folder already exists: {path}"
    except Exception as e:
        logger.exception(f"Error creating folder via MCP: {e}")
        return f"Error creating folder: {str(e)}"
