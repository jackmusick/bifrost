"""
Execute Workflow MCP Tool

Allows Claude Agent SDK to execute Bifrost workflows and get results.
This is the primary tool for testing workflows during coding mode.
"""

import logging
from typing import Any

from src.services.mcp.server import MCPContext

logger = logging.getLogger(__name__)

# Claude Agent SDK is optional - will be installed when using coding mode
try:
    from claude_agent_sdk import tool  # type: ignore

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    def tool(**kwargs: Any) -> Any:
        """Stub decorator when SDK not installed."""

        def decorator(func: Any) -> Any:
            return func

        return decorator


def execute_workflow_tool(context: MCPContext) -> Any:
    """
    Create an execute_workflow tool bound to the given context.

    Args:
        context: MCP context with user/org information

    Returns:
        Tool function for Claude Agent SDK
    """

    @tool(
        name="execute_workflow",
        description="Execute a Bifrost workflow by name and return the results. Use this to test workflows you've written.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_name": {
                    "type": "string",
                    "description": "Name of the workflow to execute",
                },
                "inputs": {
                    "type": "object",
                    "description": "Input parameters for the workflow",
                },
            },
            "required": ["workflow_name"],
        },
    )
    async def _execute_workflow(args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a workflow and return results.

        Args:
            args: Tool arguments containing:
                - workflow_name: Name of the workflow to execute
                - inputs: Dictionary of input parameters for the workflow

        Returns:
            Dict with execution results or error information
        """
        from src.core.database import get_db_context
        from src.repositories.workflows import WorkflowRepository
        from src.services.execution.service import execute_tool

        workflow_name = args.get("workflow_name")
        inputs = args.get("inputs", {})

        if not workflow_name:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: workflow_name is required",
                    }
                ]
            }

        logger.info(f"MCP execute_workflow: {workflow_name} with inputs: {inputs}")

        try:
            async with get_db_context() as db:
                # Look up workflow by name
                repo = WorkflowRepository(db)
                workflow = await repo.get_by_name(workflow_name)

                if not workflow:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: Workflow '{workflow_name}' not found. Use list_workflows to see available workflows.",
                            }
                        ]
                    }

                # Execute the workflow
                # Note: We need user details from context
                # For coding mode, this runs as the platform admin
                result = await execute_tool(
                    workflow_id=str(workflow.id),
                    workflow_name=workflow.name,
                    parameters=inputs,
                    user_id=str(context.user_id),
                    user_email="coding-mode@bifrost.local",  # TODO: Get from context
                    user_name="Coding Mode",
                    org_id=str(context.org_id) if context.org_id else None,
                    is_platform_admin=context.is_platform_admin,
                )

                # Format result for Claude
                if result.status.value == "Success":
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"✓ Workflow '{workflow_name}' executed successfully!\n\n"
                                f"**Duration:** {result.duration_ms}ms\n\n"
                                f"**Result:**\n```json\n{_format_result(result.result)}\n```",
                            }
                        ]
                    }
                else:
                    error_msg = result.error or "Unknown error"
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"✗ Workflow '{workflow_name}' failed!\n\n"
                                f"**Status:** {result.status.value}\n"
                                f"**Error:** {error_msg}\n\n"
                                f"**Error Type:** {result.error_type or 'Unknown'}",
                            }
                        ]
                    }

        except Exception as e:
            logger.exception(f"Error executing workflow via MCP: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing workflow: {str(e)}",
                    }
                ]
            }

    return _execute_workflow


def _format_result(result: Any) -> str:
    """Format workflow result as JSON string."""
    import json

    if result is None:
        return "null"
    try:
        return json.dumps(result, indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)
