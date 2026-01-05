"""
Execution MCP Tools

Tools for listing and viewing workflow execution history.
"""

import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="list_executions",
    name="List Executions",
    description="List recent workflow executions.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
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
                return "No executions found."

            lines = ["# Recent Executions\n"]
            for ex in executions:
                status_icon = "✓" if ex.status.value == "Success" else "✗" if ex.status.value == "Failed" else "⏳"
                lines.append(f"## {status_icon} {ex.workflow_name or 'Unknown'}")
                lines.append(f"- **ID:** `{ex.id}`")
                lines.append(f"- **Status:** {ex.status.value}")
                if ex.duration_ms:
                    lines.append(f"- **Duration:** {ex.duration_ms}ms")
                if ex.created_at:
                    lines.append(f"- **Started:** {ex.created_at.isoformat()}")
                if ex.error:
                    lines.append(f"- **Error:** {ex.error[:100]}...")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing executions via MCP: {e}")
        return f"Error listing executions: {str(e)}"


@system_tool(
    id="get_execution",
    name="Get Execution",
    description="Get details and logs for a specific workflow execution.",
    category=ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent=True,
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
    import json as json_module

    from src.core.database import get_db_context
    from src.repositories.executions import ExecutionRepository

    logger.info(f"MCP get_execution called with id={execution_id}")

    if not execution_id:
        return "Error: execution_id is required"

    try:
        async with get_db_context() as db:
            repo = ExecutionRepository(db)
            execution = await repo.get_execution(execution_id)

            if not execution:
                return f"Error: Execution not found: {execution_id}"

            # Check access
            if not context.is_platform_admin and str(execution.user_id) != str(context.user_id):
                return "Error: Access denied"

            lines = [f"# Execution: {execution.workflow_name or 'Unknown'}\n"]

            status_icon = "✓" if execution.status.value == "Success" else "✗" if execution.status.value == "Failed" else "⏳"
            lines.append(f"## Status: {status_icon} {execution.status.value}\n")

            lines.append("## Details\n")
            lines.append(f"- **ID:** `{execution.id}`")
            if execution.duration_ms:
                lines.append(f"- **Duration:** {execution.duration_ms}ms")
            if execution.created_at:
                lines.append(f"- **Started:** {execution.created_at.isoformat()}")
            if execution.completed_at:
                lines.append(f"- **Completed:** {execution.completed_at.isoformat()}")

            if execution.error:
                lines.append(f"\n## Error\n```\n{execution.error}\n```")

            if execution.result:
                result_str = json_module.dumps(execution.result, indent=2, default=str)
                lines.append(f"\n## Result\n```json\n{result_str}\n```")

            # Get logs
            logs = await repo.get_execution_logs(execution_id)
            if logs:
                lines.append("\n## Logs\n")
                for log in logs[-20:]:  # Last 20 logs
                    lines.append(f"[{log.level}] {log.message}")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting execution via MCP: {e}")
        return f"Error getting execution: {str(e)}"
