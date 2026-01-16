"""
Workflow MCP Tools

Tools for executing, listing, validating, and creating workflows.
"""

import logging
from typing import Any

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="execute_workflow",
    name="Execute Workflow",
    description="Execute a Bifrost workflow by ID and return the results. Use list_workflows to get workflow IDs.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    import json
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    if not workflow_id:
        return json.dumps({"error": "workflow_id is required"})

    try:
        workflow_uuid = UUID(workflow_id)
    except ValueError:
        return json.dumps({"error": f"'{workflow_id}' is not a valid UUID. Use list_workflows to get workflow IDs."})

    params = params or {}
    logger.info(f"MCP execute_workflow: {workflow_id} with params: {params}")

    try:
        async with get_db_context() as db:
            ctx_org_id = UUID(str(context.org_id)) if context.org_id else None
            ctx_user_id = UUID(str(context.user_id)) if context.user_id else None
            repo = WorkflowRepository(
                db,
                org_id=ctx_org_id,
                user_id=ctx_user_id,
                is_superuser=context.is_platform_admin,
            )
            workflow = await repo.get(id=workflow_uuid)

            if not workflow:
                return json.dumps({"error": f"Workflow with ID '{workflow_id}' not found. Use list_workflows to see available workflows."})

            result = await execute_tool(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                parameters=params,
                user_id=str(context.user_id),
                user_email=context.user_email,
                user_name=context.user_name or "MCP User",
                org_id=str(context.org_id) if context.org_id else None,
                is_platform_admin=context.is_platform_admin,
            )

            return json.dumps({
                "success": result.status.value == "Success",
                "execution_id": result.execution_id,
                "workflow_id": str(workflow.id),
                "workflow_name": workflow.name,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "result": result.result,
                "error": result.error,
                "error_type": result.error_type,
            }, default=str)

    except Exception as e:
        logger.exception(f"Error executing workflow via MCP: {e}")
        return json.dumps({"error": f"Error executing workflow: {str(e)}"})


@system_tool(
    id="list_workflows",
    name="List Workflows",
    description="List workflows registered in Bifrost.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    import json

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP list_workflows called with query={query}, category={category}")

    try:
        async with get_db_context() as db:
            from uuid import UUID
            ctx_org_id = UUID(str(context.org_id)) if context.org_id else None
            ctx_user_id = UUID(str(context.user_id)) if context.user_id else None
            repo = WorkflowRepository(
                db,
                org_id=ctx_org_id,
                user_id=ctx_user_id,
                is_superuser=context.is_platform_admin,
            )
            workflows = await repo.search(query=query, category=category, limit=100)
            total_count = await repo.count_active()

            return json.dumps({
                "workflows": [
                    {
                        "id": str(w.id),
                        "name": w.name,
                        "description": w.description,
                        "type": w.type,
                        "category": w.category,
                        "schedule": w.schedule,
                        "endpoint_enabled": w.endpoint_enabled,
                        "path": w.path,
                    }
                    for w in workflows
                ],
                "count": len(workflows),
                "total_count": total_count,
            })

    except Exception as e:
        logger.exception(f"Error listing workflows via MCP: {e}")
        return json.dumps({"error": f"Error listing workflows: {str(e)}"})


@system_tool(
    id="validate_workflow",
    name="Validate Workflow",
    description="Validate a workflow Python file for syntax and decorator issues.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    import json

    from src.core.database import get_db_context
    from src.services.file_storage import FileStorageService

    logger.info(f"MCP validate_workflow called with file_path={file_path}")

    try:
        async with get_db_context() as db:
            service = FileStorageService(db)
            content = await service.read_file(file_path)

            errors: list[str] = []
            warnings: list[str] = []

            # Check Python syntax
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return json.dumps({
                    "valid": False,
                    "errors": [{"type": "syntax", "line": e.lineno, "message": e.msg}],
                    "warnings": [],
                    "workflow_functions": [],
                })

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
                errors.append("No @workflow decorator found. Add @workflow to your main function.")

            # Check for bifrost import
            has_bifrost_import = "from bifrost" in content or "import bifrost" in content
            if not has_bifrost_import:
                warnings.append("No bifrost import found. You may need `from bifrost import workflow`.")

            return json.dumps({
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "workflow_functions": workflow_funcs,
            })

    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {file_path}"})
    except Exception as e:
        logger.exception(f"Error validating workflow via MCP: {e}")
        return json.dumps({"error": f"Error validating workflow: {str(e)}"})


@system_tool(
    id="create_workflow",
    name="Create Workflow",
    description="Create a new workflow by validating Python code and writing to workspace.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path for the new workflow file (e.g., 'workflows/my_task.py')",
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
    import json

    from src.core.database import get_db_context
    from src.services.file_storage import FileStorageService

    logger.info(f"MCP create_workflow called with file_path={file_path}")

    if not file_path:
        return json.dumps({"error": "file_path is required"})
    if not code:
        return json.dumps({"error": "code is required"})

    # Validate syntax first
    try:
        ast.parse(code)
    except SyntaxError as e:
        return json.dumps({
            "error": "Syntax error in code",
            "line": e.lineno,
            "message": e.msg,
        })

    # Check for workflow decorator
    if "@workflow" not in code:
        return json.dumps({
            "error": "Missing @workflow decorator. Your code must include a function decorated with @workflow."
        })

    # Ensure .py extension
    if not file_path.endswith(".py"):
        file_path = f"{file_path}.py"

    try:
        async with get_db_context() as db:
            service = FileStorageService(db)

            # Check if file exists
            try:
                existing = await service.read_file(file_path)
                if existing:
                    return json.dumps({
                        "error": f"File already exists: {file_path}. Use file tools to update it or choose a different path."
                    })
            except FileNotFoundError:
                pass  # Good - file doesn't exist

            # Write the file (encode string to bytes)
            await service.write_file(file_path, code.encode('utf-8'))

            return json.dumps({
                "success": True,
                "file_path": file_path,
                "message": "Workflow created and registered.",
            })

    except Exception as e:
        logger.exception(f"Error creating workflow via MCP: {e}")
        return json.dumps({"error": f"Error creating workflow: {str(e)}"})


@system_tool(
    id="get_workflow_schema",
    name="Get Workflow Schema",
    description="Get documentation about workflow structure, decorators, and SDK features.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_workflow_schema(context: Any) -> str:  # noqa: ARG001
    """Get workflow schema documentation generated from Pydantic models."""
    from src.models.contracts.workflows import WorkflowMetadata, WorkflowParameter
    from src.services.mcp_server.schema_utils import models_to_markdown

    # Generate model documentation
    model_docs = models_to_markdown([
        (WorkflowMetadata, "WorkflowMetadata (API response)"),
        (WorkflowParameter, "WorkflowParameter (parameter definition)"),
    ], "Workflow Schema Documentation")

    # Reference to SDK documentation
    sdk_reference = """
## SDK Documentation

For complete SDK documentation including decorators, modules, and examples, use `get_sdk_schema`.

## MCP Tools for Workflows

- `list_workflows` - List all accessible workflows
- `get_workflow` - Get workflow details by ID or name
- `execute_workflow` - Execute a workflow with parameters
- `validate_workflow` - Validate Python file syntax
- `create_workflow` - Create a new workflow file
- `get_sdk_schema` - Get full SDK documentation
"""

    return model_docs + sdk_reference


@system_tool(
    id="get_workflow",
    name="Get Workflow",
    description="Get detailed metadata for a specific workflow by ID or name.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
        return json.dumps({"error": "Either workflow_id or workflow_name is required"})

    try:
        async with get_db_context() as db:
            ctx_org_id = UUID(str(context.org_id)) if context.org_id else None
            ctx_user_id = UUID(str(context.user_id)) if context.user_id else None
            repo = WorkflowRepository(
                db,
                org_id=ctx_org_id,
                user_id=ctx_user_id,
                is_superuser=context.is_platform_admin,
            )

            if workflow_id:
                try:
                    workflow = await repo.get(id=UUID(workflow_id))
                except ValueError:
                    return json.dumps({"error": f"Invalid workflow_id format: {workflow_id}"})
            else:
                workflow = await repo.get_by_name(workflow_name)  # type: ignore

            if not workflow:
                return json.dumps({"error": f"Workflow not found: {workflow_id or workflow_name}"})

            return json.dumps({
                "id": str(workflow.id),
                "name": workflow.name,
                "description": workflow.description,
                "type": workflow.type,
                "category": workflow.category,
                "is_active": workflow.is_active,
                "path": workflow.path,
                "schedule": workflow.schedule,
                "endpoint_enabled": workflow.endpoint_enabled,
                "tool_description": workflow.tool_description if workflow.type == "tool" else None,
                "parameters": workflow.parameters_schema,
            })

    except Exception as e:
        logger.exception(f"Error getting workflow via MCP: {e}")
        return json.dumps({"error": f"Error getting workflow: {str(e)}"})
