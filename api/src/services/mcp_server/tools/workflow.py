"""
Workflow MCP Tools

Tools for executing, listing, validating, and creating workflows.
"""

import logging
from typing import Any

from fastmcp.tools.tool import ToolResult

from src.services.mcp_server.tool_result import error_result, success_result

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


async def execute_workflow(
    context: Any, workflow_id: str, params: dict[str, Any] | None = None
) -> ToolResult:
    """Execute a workflow by ID or name and return results."""
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    if not workflow_id:
        return error_result("workflow_id is required")

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
            workflow = await repo.resolve(workflow_id)

            if not workflow:
                return error_result(f"Workflow '{workflow_id}' not found. Use list_workflows to see available workflows.")

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

            success = result.status.value == "Success"
            data = {
                "success": success,
                "execution_id": result.execution_id,
                "workflow_id": str(workflow.id),
                "workflow_name": workflow.name,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "result": result.result,
                "error": result.error,
                "error_type": result.error_type,
            }

            if success:
                display_text = f"Workflow '{workflow.name}' completed successfully ({result.duration_ms}ms)"
                return success_result(display_text, data)
            else:
                display_text = f"Workflow '{workflow.name}' failed: {result.error}"
                return error_result(display_text, data)

    except Exception as e:
        logger.exception(f"Error executing workflow via MCP: {e}")
        return error_result(f"Error executing workflow: {str(e)}")


async def list_workflows(
    context: Any, query: str | None = None, category: str | None = None
) -> ToolResult:
    """List all registered workflows."""
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP list_workflows called with query={query}, category={category}")

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
            workflows = await repo.search(query=query, category=category, limit=100)
            total_count = await repo.count_active()

            workflow_list = [
                {
                    "id": str(w.id),
                    "name": w.name,
                    "description": w.description,
                    "type": w.type,
                    "category": w.category,
                    "endpoint_enabled": w.endpoint_enabled,
                    "path": w.path,
                }
                for w in workflows
            ]

            data = {
                "workflows": workflow_list,
                "count": len(workflows),
                "total_count": total_count,
            }

            if not workflows:
                return success_result("No workflows found", data)

            # Build display text showing first 10 workflows
            display_lines = [f"Found {len(workflows)} workflow(s):"]
            for w in workflows[:10]:
                desc = f" - {w.description}" if w.description else ""
                display_lines.append(f"  - {w.name} ({w.type}){desc}")
            if len(workflows) > 10:
                display_lines.append(f"  ... and {len(workflows) - 10} more")

            return success_result("\n".join(display_lines), data)

    except Exception as e:
        logger.exception(f"Error listing workflows via MCP: {e}")
        return error_result(f"Error listing workflows: {str(e)}")


async def validate_workflow(context: Any, file_path: str) -> ToolResult:
    """Validate a workflow Python file for syntax and decorator issues."""
    import ast

    from src.core.database import get_db_context
    from src.services.file_storage import FileStorageService

    logger.info(f"MCP validate_workflow called with file_path={file_path}")

    try:
        async with get_db_context() as db:
            service = FileStorageService(db)
            content_bytes, _ = await service.read_file(file_path)
            content = content_bytes.decode("utf-8")

            errors: list[str | dict[str, Any]] = []
            warnings: list[str] = []

            # Check Python syntax
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                data = {
                    "valid": False,
                    "errors": [{"type": "syntax", "line": e.lineno, "message": e.msg}],
                    "warnings": [],
                    "workflow_functions": [],
                }
                return error_result(f"Syntax error at line {e.lineno}: {e.msg}", data)

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

            is_valid = len(errors) == 0
            data = {
                "valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "workflow_functions": workflow_funcs,
            }

            if is_valid:
                funcs_str = ", ".join(workflow_funcs) if workflow_funcs else "none"
                warning_str = f" ({len(warnings)} warning(s))" if warnings else ""
                display_text = f"Workflow '{file_path}' is valid{warning_str}. Functions: {funcs_str}"
                return success_result(display_text, data)
            else:
                error_msgs = "; ".join(str(e) for e in errors)
                return error_result(f"Workflow '{file_path}' has errors: {error_msgs}", data)

    except FileNotFoundError:
        return error_result(f"File not found: {file_path}")
    except Exception as e:
        logger.exception(f"Error validating workflow via MCP: {e}")
        return error_result(f"Error validating workflow: {str(e)}")


async def create_workflow(context: Any, file_path: str, code: str) -> ToolResult:
    """Create a new workflow file after validation."""
    import ast

    from src.core.database import get_db_context
    from src.services.file_storage import FileStorageService

    logger.info(f"MCP create_workflow called with file_path={file_path}")

    if not file_path:
        return error_result("file_path is required")
    if not code:
        return error_result("code is required")

    # Validate syntax first
    try:
        ast.parse(code)
    except SyntaxError as e:
        return error_result(
            f"Syntax error in code at line {e.lineno}: {e.msg}",
            {"line": e.lineno, "message": e.msg},
        )

    # Check for workflow/tool/data_provider decorator
    has_decorator = "@workflow" in code or "@data_provider" in code or "@tool" in code
    if not has_decorator:
        return error_result("Missing decorator. Your code must include a function decorated with @workflow, @data_provider, or @tool.")

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
                    return error_result(f"File already exists: {file_path}. Use file tools to update it or choose a different path.")
            except FileNotFoundError:
                pass  # Good - file doesn't exist

            # Write the file (encode string to bytes)
            await service.write_file(file_path, code.encode('utf-8'))

            data = {
                "success": True,
                "file_path": file_path,
                "message": "Workflow file created. Use register_workflow to register the function.",
            }
            return success_result(f"Workflow created at '{file_path}'", data)

    except Exception as e:
        logger.exception(f"Error creating workflow via MCP: {e}")
        return error_result(f"Error creating workflow: {str(e)}")


async def get_workflow_schema(context: Any) -> ToolResult:  # noqa: ARG001
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
- `register_workflow` - Register a function from an existing file
- `get_sdk_schema` - Get full SDK documentation
"""

    full_docs = model_docs + sdk_reference
    data = {
        "documentation": full_docs,
        "models": ["WorkflowMetadata", "WorkflowParameter"],
    }
    return success_result(full_docs, data)


async def get_workflow(
    context: Any,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
) -> ToolResult:
    """Get detailed workflow metadata."""
    from uuid import UUID

    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP get_workflow called with id={workflow_id}, name={workflow_name}")

    if not workflow_id and not workflow_name:
        return error_result("Either workflow_id or workflow_name is required")

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
                    return error_result(f"Invalid workflow_id format: {workflow_id}")
            else:
                workflow = await repo.get_by_name(workflow_name)  # type: ignore

            if not workflow:
                return error_result(f"Workflow not found: {workflow_id or workflow_name}")

            data = {
                "id": str(workflow.id),
                "name": workflow.name,
                "description": workflow.description,
                "type": workflow.type,
                "category": workflow.category,
                "is_active": workflow.is_active,
                "path": workflow.path,
                "endpoint_enabled": workflow.endpoint_enabled,
                "tool_description": workflow.tool_description if workflow.type == "tool" else None,
                "parameters": workflow.parameters_schema,
            }

            desc = f" - {workflow.description}" if workflow.description else ""
            display_text = f"Workflow: {workflow.name} ({workflow.type}){desc}"
            return success_result(display_text, data)

    except Exception as e:
        logger.exception(f"Error getting workflow via MCP: {e}")
        return error_result(f"Error getting workflow: {str(e)}")


async def register_workflow(context: Any, path: str, function_name: str) -> ToolResult:
    """Register a decorated Python function as a workflow.

    Takes a file path and function name, validates the function has a
    @workflow/@tool/@data_provider decorator, and registers it in the system.
    """
    import ast
    from uuid import uuid4

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.workflows import Workflow as WorkflowORM
    from src.services.file_storage import FileStorageService
    from src.services.file_storage.indexers.workflow import WorkflowIndexer

    if not path:
        return error_result("path is required")
    if not function_name:
        return error_result("function_name is required")
    if not path.endswith(".py"):
        return error_result("path must be a .py file")

    try:
        async with get_db_context() as db:
            service = FileStorageService(db)

            # Read file
            try:
                content, _ = await service.read_file(path)
            except FileNotFoundError:
                return error_result(f"File not found: {path}")

            # AST parse and find decorated function
            content_str = content.decode("utf-8", errors="replace")
            try:
                tree = ast.parse(content_str, filename=path)
            except SyntaxError as e:
                return error_result(f"Syntax error in {path}: {e}")

            found = False
            decorator_type = None
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != function_name:
                    continue
                for dec in node.decorator_list:
                    dec_name = None
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                        dec_name = dec.func.id
                    if dec_name in ("workflow", "tool", "data_provider"):
                        found = True
                        decorator_type = dec_name
                        break
                if found:
                    break

            if not found:
                return error_result(
                    f"No @workflow/@tool/@data_provider decorated function '{function_name}' found in {path}"
                )

            # Check already registered
            existing = await db.execute(
                select(WorkflowORM).where(
                    WorkflowORM.path == path,
                    WorkflowORM.function_name == function_name,
                    WorkflowORM.is_active.is_(True),
                )
            )
            if existing.scalar_one_or_none():
                return error_result(f"Workflow '{function_name}' in {path} is already registered")

            # Create record
            wf_type = "data_provider" if decorator_type == "data_provider" else (
                "tool" if decorator_type == "tool" else "workflow"
            )
            workflow_id = uuid4()
            new_wf = WorkflowORM(
                id=workflow_id,
                name=function_name,
                function_name=function_name,
                path=path,
                type=wf_type,
                is_active=True,
            )
            db.add(new_wf)
            await db.flush()

            # Enrich with decorator metadata
            indexer = WorkflowIndexer(db)
            await indexer.index_python_file(path, content)

            # Re-fetch enriched record
            result = await db.execute(
                select(WorkflowORM).where(WorkflowORM.id == workflow_id)
            )
            workflow = result.scalar_one()

            return success_result(
                f"Registered {wf_type} '{workflow.name}' from {path}::{function_name}",
                {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "function_name": workflow.function_name,
                    "path": workflow.path,
                    "type": workflow.type,
                },
            )
    except Exception as e:
        logger.error(f"register_workflow failed: {e}", exc_info=True)
        return error_result(str(e))


# Tool metadata for registration
TOOLS = [
    ("execute_workflow", "Execute Workflow", "Execute a Bifrost workflow by ID or name and return the results. Use list_workflows to get workflow IDs."),
    ("list_workflows", "List Workflows", "List workflows registered in Bifrost."),
    ("validate_workflow", "Validate Workflow", "Validate a workflow Python file for syntax and decorator issues."),
    ("create_workflow", "Create Workflow", "Create a new workflow by validating Python code and writing to workspace."),
    ("get_workflow_schema", "Get Workflow Schema", "Get documentation about workflow structure, decorators, and SDK features."),
    ("get_workflow", "Get Workflow", "Get detailed metadata for a specific workflow by ID or name."),
    ("register_workflow", "Register Workflow", "Register a decorated Python function as a workflow. Takes a file path and function name."),
]


def register_tools(mcp: Any, get_context_fn: Any) -> None:
    """Register all workflow tools with FastMCP."""
    from src.services.mcp_server.generators.fastmcp_generator import register_tool_with_context

    tool_funcs = {
        "execute_workflow": execute_workflow,
        "list_workflows": list_workflows,
        "validate_workflow": validate_workflow,
        "create_workflow": create_workflow,
        "get_workflow_schema": get_workflow_schema,
        "get_workflow": get_workflow,
        "register_workflow": register_workflow,
    }

    for tool_id, name, description in TOOLS:
        register_tool_with_context(mcp, tool_funcs[tool_id], tool_id, description, get_context_fn)
