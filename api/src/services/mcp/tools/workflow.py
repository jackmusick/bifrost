"""
Workflow MCP Tools

Tools for executing, listing, validating, and creating workflows.
"""

import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="execute_workflow",
    name="Execute Workflow",
    description="Execute a Bifrost workflow by ID and return the results. Use list_workflows to get workflow IDs.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the workflow to execute",
            },
            "params": {
                "type": "object",
                "description": "Input parameters for the workflow",
            },
        },
        "required": ["workflow_id"],
    },
)
async def execute_workflow(
    context: Any, workflow_id: str, params: dict[str, Any] | None = None
) -> str:
    """Execute a workflow by ID and return results."""
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    if not workflow_id:
        return "Error: workflow_id is required"

    try:
        workflow_uuid = UUID(workflow_id)
    except ValueError:
        return f"Error: '{workflow_id}' is not a valid UUID. Use list_workflows to get workflow IDs."

    params = params or {}
    logger.info(f"MCP execute_workflow: {workflow_id} with params: {params}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflow = await repo.get_by_id(workflow_uuid)

            if not workflow:
                return f"Error: Workflow with ID '{workflow_id}' not found. Use list_workflows to see available workflows."

            result = await execute_tool(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                parameters=params,
                user_id=str(context.user_id),
                user_email=context.user_email or "mcp@bifrost.local",
                user_name=context.user_name or "MCP User",
                org_id=str(context.org_id) if context.org_id else None,
                is_platform_admin=context.is_platform_admin,
            )

            if result.status.value == "Success":
                import json

                result_str = (
                    json.dumps(result.result, indent=2, default=str)
                    if result.result
                    else "null"
                )
                return (
                    f"✓ Workflow '{workflow.name}' executed successfully!\n\n"
                    f"**Duration:** {result.duration_ms}ms\n\n"
                    f"**Result:**\n```json\n{result_str}\n```"
                )
            else:
                return (
                    f"✗ Workflow '{workflow.name}' failed!\n\n"
                    f"**Status:** {result.status.value}\n"
                    f"**Error:** {result.error or 'Unknown error'}\n\n"
                    f"**Error Type:** {result.error_type or 'Unknown'}"
                )

    except Exception as e:
        logger.exception(f"Error executing workflow via MCP: {e}")
        return f"Error executing workflow: {str(e)}"


@system_tool(
    id="list_workflows",
    name="List Workflows",
    description="List workflows registered in Bifrost.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search query to filter workflows",
            },
            "category": {
                "type": "string",
                "description": "Optional category to filter workflows",
            },
        },
        "required": [],
    },
)
async def list_workflows(
    context: Any, query: str | None = None, category: str | None = None
) -> str:
    """List all registered workflows."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP list_workflows called with query={query}, category={category}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflows = await repo.search(query=query, category=category, limit=100)
            total_count = await repo.count_active()

            if not workflows:
                return (
                    "No workflows found.\n\n"
                    "If you've created a workflow file in `/tmp/bifrost/workspace`, "
                    "wait a moment for the file watcher to detect and register it.\n\n"
                    "Workflows are Python files with the `.workflow.py` extension that "
                    "use the `@workflow` decorator."
                )

            lines = ["# Registered Workflows\n"]
            lines.append(f"Showing {len(workflows)} of {total_count} total workflows\n")

            for workflow in workflows:
                lines.append(f"## {workflow.name}")
                lines.append(f"- ID: `{workflow.id}`")
                if workflow.description:
                    lines.append(f"{workflow.description}")

                meta_parts = []
                if workflow.category:
                    meta_parts.append(f"Category: {workflow.category}")
                if workflow.type == "tool":
                    meta_parts.append("Tool: Yes")
                if workflow.schedule:
                    meta_parts.append(f"Schedule: {workflow.schedule}")
                if workflow.endpoint_enabled:
                    meta_parts.append("Endpoint: Enabled")

                if meta_parts:
                    lines.append(f"- {' | '.join(meta_parts)}")
                if workflow.path:
                    lines.append(f"- File: `{workflow.path}`")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing workflows via MCP: {e}")
        return f"Error listing workflows: {str(e)}"


@system_tool(
    id="validate_workflow",
    name="Validate Workflow",
    description="Validate a workflow Python file for syntax and decorator issues.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the workflow file to validate",
            },
        },
        "required": ["file_path"],
    },
)
async def validate_workflow(context: Any, file_path: str) -> str:
    """Validate a workflow Python file for syntax and decorator issues."""
    import ast
    import re

    from src.services.file_storage_service import FileStorageService

    logger.info(f"MCP validate_workflow called with file_path={file_path}")

    try:
        service = FileStorageService()
        content = await service.read_file(file_path)

        errors: list[str] = []
        warnings: list[str] = []

        # Check Python syntax
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"**Syntax Error** at line {e.lineno}:\n```\n{e.msg}\n```"

        # Check for @workflow decorator
        has_workflow_decorator = False
        workflow_funcs: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    decorator_name = ""
                    if isinstance(decorator, ast.Name):
                        decorator_name = decorator.id
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name):
                            decorator_name = decorator.func.id
                        elif isinstance(decorator.func, ast.Attribute):
                            decorator_name = decorator.func.attr

                    if decorator_name == "workflow":
                        has_workflow_decorator = True
                        workflow_funcs.append(node.name)

        if not has_workflow_decorator:
            errors.append("No `@workflow` decorator found. Add `@workflow` to your main function.")

        # Check for bifrost import
        has_bifrost_import = "from bifrost" in content or "import bifrost" in content
        if not has_bifrost_import:
            warnings.append("No bifrost import found. You may need `from bifrost import workflow`.")

        # Check file extension
        if not file_path.endswith(".workflow.py"):
            warnings.append(
                f"File should end with `.workflow.py` for auto-discovery. "
                f"Current: `{file_path.split('/')[-1]}`"
            )

        # Build result
        if errors:
            result = "**Validation Failed**\n\n"
            result += "### Errors\n"
            for err in errors:
                result += f"- {err}\n"
            if warnings:
                result += "\n### Warnings\n"
                for warn in warnings:
                    result += f"- {warn}\n"
            return result

        result = "**Validation Passed** ✓\n\n"
        if workflow_funcs:
            result += f"Found workflow function(s): `{', '.join(workflow_funcs)}`\n"
        if warnings:
            result += "\n### Warnings\n"
            for warn in warnings:
                result += f"- {warn}\n"

        return result

    except FileNotFoundError:
        return f"File not found: `{file_path}`"
    except Exception as e:
        logger.exception(f"Error validating workflow via MCP: {e}")
        return f"Error validating workflow: {str(e)}"


@system_tool(
    id="create_workflow",
    name="Create Workflow",
    description="Create a new workflow by validating Python code and writing to workspace.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path for the new workflow file (should end with .workflow.py)",
            },
            "code": {
                "type": "string",
                "description": "Python code for the workflow",
            },
        },
        "required": ["file_path", "code"],
    },
)
async def create_workflow(context: Any, file_path: str, code: str) -> str:
    """Create a new workflow file after validation."""
    import ast

    from src.services.file_storage_service import FileStorageService

    logger.info(f"MCP create_workflow called with file_path={file_path}")

    if not file_path:
        return "Error: file_path is required"
    if not code:
        return "Error: code is required"

    # Validate syntax first
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"**Syntax Error** at line {e.lineno}:\n```\n{e.msg}\n```\n\nFix the syntax error and try again."

    # Check for workflow decorator
    if "@workflow" not in code:
        return (
            "**Missing @workflow decorator**\n\n"
            "Your code must include a function decorated with `@workflow`. Example:\n\n"
            "```python\n"
            "from bifrost import workflow\n\n"
            "@workflow\n"
            "async def my_workflow():\n"
            "    return {'result': 'success'}\n"
            "```"
        )

    # Suggest .workflow.py extension
    if not file_path.endswith(".workflow.py"):
        suggested = file_path.replace(".py", ".workflow.py") if file_path.endswith(".py") else f"{file_path}.workflow.py"
        return (
            f"**File Extension Warning**\n\n"
            f"Workflow files should end with `.workflow.py` for auto-discovery.\n\n"
            f"Suggested path: `{suggested}`\n\n"
            f"Use that path or proceed with `{file_path}` if intentional."
        )

    try:
        service = FileStorageService()

        # Check if file exists
        try:
            existing = await service.read_file(file_path)
            if existing:
                return (
                    f"**File Already Exists**\n\n"
                    f"File `{file_path}` already exists. Use the file tools to update it, "
                    f"or choose a different path."
                )
        except FileNotFoundError:
            pass  # Good - file doesn't exist

        # Write the file
        await service.write_file(file_path, code)

        return (
            f"✓ Workflow created at `{file_path}`\n\n"
            f"The file watcher will detect it shortly and register the workflow.\n"
            f"Use `list_workflows` to verify it was discovered."
        )

    except Exception as e:
        logger.exception(f"Error creating workflow via MCP: {e}")
        return f"Error creating workflow: {str(e)}"


@system_tool(
    id="get_workflow_schema",
    name="Get Workflow Schema",
    description="Get documentation about workflow structure, decorators, and SDK features.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_workflow_schema(context: Any) -> str:
    """Get workflow schema documentation."""
    return '''# Bifrost Workflow Schema

## File Structure

Workflows are Python files with the `.workflow.py` extension:
```
workflows/
├── my_task.workflow.py
├── data_sync.workflow.py
└── reports/
    └── daily_report.workflow.py
```

## Basic Workflow

```python
from bifrost import workflow

@workflow
async def my_workflow(param1: str, param2: int = 10):
    """Workflow description shown in UI."""
    # Your logic here
    return {"result": "success", "count": param2}
```

## Decorator Options

```python
@workflow(
    name="Human Readable Name",      # Display name (default: function name)
    description="What it does",       # Shown in workflow list
    category="automation",            # For organizing workflows
    schedule="0 9 * * *",            # Cron schedule (optional)
    endpoint=True,                    # Expose as HTTP endpoint
    tool=True,                        # Make available as MCP tool
    tool_description="For LLMs",     # Description for AI tools
)
async def my_workflow():
    ...
```

## Using Integrations

```python
from bifrost import workflow, integrations

@workflow
async def sync_data():
    # Get configured integration
    ms365 = await integrations.get("Microsoft 365")

    if ms365 and ms365.oauth:
        # Use OAuth token
        token = ms365.oauth.access_token
        # Make API calls...

    return {"synced": True}
```

## Data Providers

```python
from bifrost import data_provider

@data_provider(
    name="Get Users",
    description="Fetch users from database",
)
async def get_users(search: str = "", limit: int = 100):
    # Query your data source
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
```

## Logging

```python
from bifrost import workflow, log

@workflow
async def my_workflow():
    log.info("Starting workflow")
    log.debug("Debug details", extra={"key": "value"})
    log.warning("Something to note")
    log.error("Something went wrong")
    return {"done": True}
```

## Error Handling

```python
from bifrost import workflow, BifrostError

@workflow
async def my_workflow():
    try:
        # risky operation
        pass
    except SomeError as e:
        raise BifrostError(f"Failed: {e}", error_type="VALIDATION_ERROR")
```

## Return Values

Workflows should return JSON-serializable data:
- `dict` - Most common, shown as JSON
- `list` - Arrays of results
- `str` - Plain text
- `None` - No output

## Best Practices

1. **Use async/await** - All workflows should be async
2. **Type hints** - Add type hints for parameters
3. **Descriptions** - Add docstrings for UI display
4. **Error handling** - Catch and handle exceptions gracefully
5. **Logging** - Use bifrost.log for visibility
6. **Idempotency** - Design workflows to be safely re-runnable
'''


@system_tool(
    id="get_workflow",
    name="Get Workflow",
    description="Get detailed metadata for a specific workflow by ID or name.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the workflow",
            },
            "workflow_name": {
                "type": "string",
                "description": "Name of the workflow (alternative to ID)",
            },
        },
        "required": [],
    },
)
async def get_workflow(
    context: Any,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
) -> str:
    """Get detailed workflow metadata."""
    import json
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP get_workflow called with id={workflow_id}, name={workflow_name}")

    if not workflow_id and not workflow_name:
        return "Error: Either workflow_id or workflow_name is required"

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)

            if workflow_id:
                try:
                    workflow = await repo.get_by_id(UUID(workflow_id))
                except ValueError:
                    return f"Error: Invalid workflow_id format: {workflow_id}"
            else:
                workflow = await repo.get_by_name(workflow_name)  # type: ignore

            if not workflow:
                return f"Workflow not found: {workflow_id or workflow_name}"

            lines = [f"# {workflow.name}\n"]
            lines.append(f"**ID:** `{workflow.id}`")
            if workflow.description:
                lines.append(f"**Description:** {workflow.description}")
            lines.append(f"**Type:** {workflow.type}")
            if workflow.category:
                lines.append(f"**Category:** {workflow.category}")
            lines.append(f"**Active:** {'Yes' if workflow.is_active else 'No'}")

            if workflow.path:
                lines.append(f"**File:** `{workflow.path}`")

            if workflow.schedule:
                lines.append(f"**Schedule:** `{workflow.schedule}`")

            if workflow.endpoint_enabled:
                lines.append(f"**Endpoint:** Enabled")

            if workflow.type == "tool" and workflow.tool_description:
                lines.append(f"**Tool Description:** {workflow.tool_description}")

            if workflow.parameters:
                lines.append("\n## Parameters")
                lines.append("```json")
                lines.append(json.dumps(workflow.parameters, indent=2))
                lines.append("```")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting workflow via MCP: {e}")
        return f"Error getting workflow: {str(e)}"
