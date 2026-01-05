"""
Data Provider MCP Tools

Tools for listing, validating, and getting schema documentation for data providers.
"""

import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="list_data_providers",
    name="List Data Providers",
    description="List all available data providers with their parameters.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search query to filter data providers",
            },
        },
        "required": [],
    },
)
async def list_data_providers(context: Any, query: str | None = None) -> str:
    """List all available data providers."""
    from src.core.database import get_db_context
    from src.repositories.data_providers import DataProviderRepository

    logger.info(f"MCP list_data_providers called with query={query}")

    try:
        async with get_db_context() as db:
            repo = DataProviderRepository(db)
            providers = await repo.search(query=query, limit=100)
            total_count = await repo.count_active()

            if not providers:
                return (
                    "No data providers found.\n\n"
                    "Data providers are Python functions decorated with `@data_provider` "
                    "that supply dynamic options for form select fields.\n\n"
                    "Create a data provider by adding a Python file with the "
                    "`@data_provider` decorator in your workspace."
                )

            lines = ["# Available Data Providers\n"]
            lines.append(f"Showing {len(providers)} of {total_count} total providers\n")

            for provider in providers:
                lines.append(f"## {provider.name}")
                lines.append(f"- ID: `{provider.id}`")
                if provider.description:
                    lines.append(f"{provider.description}")
                if provider.path:
                    lines.append(f"- File: `{provider.path}`")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing data providers via MCP: {e}")
        return f"Error listing data providers: {str(e)}"


@system_tool(
    id="get_data_provider_schema",
    name="Get Data Provider Schema",
    description="Get documentation about data provider structure, decorators, and examples.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_data_provider_schema(context: Any) -> str:
    """Get documentation about data provider structure and decorators."""
    return """# Data Provider Schema Documentation

Data providers are Python functions that supply dynamic options for form select fields.

## Basic Structure

```python
from bifrost import data_provider

@data_provider(
    name="Customer List",
    description="Returns list of customers",
    cache_ttl_seconds=300,  # Cache for 5 minutes
)
async def get_customers() -> list[dict]:
    '''Return list of customers for dropdown.'''
    return [
        {"label": "Acme Corp", "value": "acme-123"},
        {"label": "TechCo", "value": "tech-456"},
    ]
```

## Decorator Properties

- `name`: Display name for the data provider (defaults to function name)
- `description`: Human-readable description (defaults to docstring)
- `cache_ttl_seconds`: How long to cache results (default: 300, 0 = no caching)
- `category`: Group related providers (default: "General")

## With Parameters

Parameters are automatically derived from the function signature:

```python
from bifrost import data_provider

@data_provider
async def get_users_by_dept(
    department_id: str,
    include_inactive: bool = False
) -> list[dict]:
    '''Get users filtered by department.'''
    users = await fetch_users(department_id, include_inactive)
    return [
        {"label": user.name, "value": str(user.id)}
        for user in users
    ]
```

## Return Format

Data providers must return a list of objects with `label` and `value`:

```python
[
    {"label": "Display Text", "value": "unique_value"},
    {"label": "Another Option", "value": "another_value", "metadata": {"extra": "info"}},
]
```

- `label`: Text shown to the user in the dropdown
- `value`: The actual value stored when selected
- `metadata`: Optional extra data (not displayed, but available to workflows)

## Using in Forms

Reference a data provider in form field definitions:

```json
{
  "name": "customer",
  "type": "select",
  "label": "Select Customer",
  "data_provider_id": "uuid-of-provider",
  "data_provider_inputs": {
    "department_id": "{{department}}"
  }
}
```

## Parameter Types

Supported parameter types (derived from function signature):
- `str` - Text input
- `int` - Integer value
- `float` - Decimal value
- `bool` - True/false
- `dict` - Complex object (as JSON)
- `Optional[T]` - Optional parameter with None default
"""


@system_tool(
    id="validate_data_provider",
    name="Validate Data Provider",
    description="Validate a data provider Python file for syntax and decorator issues.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the data provider file to validate",
            },
        },
        "required": ["file_path"],
    },
)
async def validate_data_provider(context: Any, file_path: str) -> str:
    """Validate a data provider Python file."""
    import ast
    from pathlib import Path

    logger.info(f"MCP validate_data_provider called with file_path={file_path}")

    if not file_path:
        return "Error: file_path is required"

    try:
        workspace_path = Path("/tmp/bifrost/workspace")
        full_path = workspace_path / file_path.lstrip("/")

        if not full_path.exists():
            return f"Error: File not found: {file_path}"

        content = full_path.read_text()
        errors = []

        # Check syntax
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append(f"Syntax error on line {e.lineno}: {e.msg}")
            return "# Validation Failed\n\n" + "\n".join(f"- {e}" for e in errors)

        # Check for @data_provider decorator
        if "@data_provider" not in content:
            errors.append("Missing @data_provider decorator")

        # Check for bifrost import
        if "from bifrost" not in content and "import bifrost" not in content:
            errors.append("Missing bifrost import (e.g., from bifrost import data_provider)")

        # Check for async def (data providers should be async)
        if "async def" not in content and "def " in content:
            # Only warn if there's a non-async function - could still be valid
            errors.append(
                "Warning: Data provider functions should be async (use 'async def'). "
                "Sync functions will work but may block the event loop."
            )

        if errors:
            return "# Validation Issues\n\n" + "\n".join(f"- {e}" for e in errors)

        return "Validation passed! Data provider syntax is valid."

    except Exception as e:
        logger.exception(f"Error validating data provider via MCP: {e}")
        return f"Error validating data provider: {str(e)}"
