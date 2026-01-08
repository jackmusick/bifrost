"""
Data Provider MCP Tools

Tools for getting schema documentation for data providers.
Note: Data providers are now stored in the workflows table with type='data_provider'.
Use list_workflows to see data providers.
"""

import logging
from typing import Any

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="get_data_provider_schema",
    name="Get Data Provider Schema",
    description="Get documentation about data provider structure, decorators, and examples.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_data_provider_schema(context: Any) -> str:
    """Get documentation about data provider structure and decorators."""
    return """# Data Provider Schema Documentation

Data providers are Python functions that supply dynamic options for form select fields.
They are stored as workflows with type='data_provider'. Use list_workflows to see available data providers.

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

## Viewing Data Providers

Data providers are stored as workflows with type='data_provider'.
Use the list_workflows tool to see all available data providers.
"""
