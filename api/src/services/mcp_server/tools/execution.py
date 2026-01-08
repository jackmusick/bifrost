"""
Execution MCP Tools

Tools for listing and viewing workflow execution history.
"""

import json
import logging
from typing import Any

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="list_executions",
    name="List Executions",
    description="List recent workflow executions.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "workflow_name": {
                "type": "string",
                "description": "Optional workflow name to filter by",
            },
            "status": {
                "type": "string",
                "description": "Optional status to filter by (Success, Failed, Running, Pending)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of executions to return (default: 20)",
                "default": 20,
            },
        },
        "required": [],
    },
)
async def list_executions(
    context: Any,
    workflow_name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List recent workflow executions."""
    from src.core.database import get_db_context
    from src.repositories.executions import ExecutionRepository

    logger.info(f"MCP list_executions called with workflow={workflow_name}, status={status}")

    try:
        async with get_db_context() as db:
            repo = ExecutionRepository(db)

            # Build filters
            filters: dict[str, Any] = {}
            if workflow_name:
                filters["workflow_name"] = workflow_name
            if status:
                filters["status"] = status

            executions = await repo.list_executions(
                filters=filters,
                limit=limit,
                user_id=str(context.user_id) if not context.is_platform_admin else None,
                org_id=str(context.org_id) if context.org_id else None,
            )

            if not executions:
                return json.dumps({"executions": [], "count": 0})

            execution_list = []
            for ex in executions:
                execution_data = {
                    "id": str(ex.id),
                    "workflow_name": ex.workflow_name or "Unknown",
                    "status": ex.status.value,
                    "duration_ms": ex.duration_ms,
                    "created_at": ex.created_at.isoformat() if ex.created_at else None,
                    "error": ex.error[:100] + "..." if ex.error and len(ex.error) > 100 else ex.error,
                }
                execution_list.append(execution_data)

            return json.dumps({"executions": execution_list, "count": len(execution_list)})

    except Exception as e:
        logger.exception(f"Error listing executions via MCP: {e}")
        return json.dumps({"error": f"Error listing executions: {str(e)}"})


@system_tool(
    id="get_execution",
    name="Get Execution",
    description="Get details and logs for a specific workflow execution.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "Execution UUID",
            },
        },
        "required": ["execution_id"],
    },
)
async def get_execution(context: Any, execution_id: str) -> str:
    """Get details and logs for a specific workflow execution."""
    from src.core.database import get_db_context
    from src.repositories.executions import ExecutionRepository

    logger.info(f"MCP get_execution called with id={execution_id}")

    if not execution_id:
        return json.dumps({"error": "execution_id is required"})

    try:
        async with get_db_context() as db:
            repo = ExecutionRepository(db)
            execution = await repo.get_execution(execution_id)

            if not execution:
                return json.dumps({"error": f"Execution not found: {execution_id}"})

            # Check access
            if not context.is_platform_admin and str(execution.user_id) != str(context.user_id):
                return json.dumps({"error": "Access denied"})

            # Build execution data
            execution_data: dict[str, Any] = {
                "id": str(execution.id),
                "workflow_name": execution.workflow_name or "Unknown",
                "status": execution.status.value,
                "duration_ms": execution.duration_ms,
                "created_at": execution.created_at.isoformat() if execution.created_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "error": execution.error,
                "result": execution.result,
            }

            # Get logs
            logs = await repo.get_execution_logs(execution_id)
            if logs:
                execution_data["logs"] = [
                    {"level": log.level, "message": log.message}
                    for log in logs[-20:]  # Last 20 logs
                ]
            else:
                execution_data["logs"] = []

            return json.dumps(execution_data, default=str)

    except Exception as e:
        logger.exception(f"Error getting execution via MCP: {e}")
        return json.dumps({"error": f"Error getting execution: {str(e)}"})
