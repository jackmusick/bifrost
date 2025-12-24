"""
Workflows SDK for Bifrost.

Provides Python API for workflow operations (list, get status).

All methods are async and must be awaited.
"""

from __future__ import annotations

import logging

from src.models.contracts.executions import WorkflowExecution
from src.models.contracts.workflows import WorkflowMetadata

from ._internal import get_context
from .executions import executions

logger = logging.getLogger(__name__)


class workflows:
    """
    Workflow operations.

    Allows workflows to query available workflows and execution status.

    All methods are async - await is required.
    """

    @staticmethod
    async def list() -> list[WorkflowMetadata]:
        """
        List all available workflows.

        Returns:
            list[WorkflowMetadata]: List of workflow metadata with attributes:
                - id: str - Workflow UUID
                - name: str - Workflow name (snake_case)
                - description: str | None - Human-readable description
                - category: str - Category for organization
                - tags: list[str] - Tags for categorization
                - parameters: list[WorkflowParameter] - Workflow parameters
                - execution_mode: Literal["sync", "async"] - Execution mode
                - timeout_seconds: int - Max execution time
                - retry_policy: RetryPolicy | None - Retry configuration
                - schedule: str | None - Cron expression
                - endpoint_enabled: bool - Whether exposed as HTTP endpoint
                - allowed_methods: list[str] - Allowed HTTP methods
                - disable_global_key: bool - Whether global API key is disabled
                - public_endpoint: bool - Whether endpoint is public
                - is_tool: bool - Whether available as AI tool
                - tool_description: str | None - AI tool description
                - time_saved: int - Minutes saved per execution
                - value: float - Value metric for reporting
                - source_file_path: str | None - Full file path
                - relative_file_path: str | None - Workspace-relative path

        Raises:
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import workflows
            >>> wf_list = await workflows.list()
            >>> for wf in wf_list:
            ...     print(f"{wf.name}: {wf.description}")
        """
        context = get_context()

        logger.info(f"User {context.user_id} listing workflows")

        if not context._db:
            logger.warning("No database session in context, returning empty workflow list")
            return []

        from src.repositories.workflows import WorkflowRepository

        repo = WorkflowRepository(context._db)
        db_workflows = await repo.get_all_active()

        # Convert to WorkflowMetadata models
        # Use getattr for fields that may not exist on the ORM
        workflow_list = [
            WorkflowMetadata(
                id=str(wf.id),
                name=wf.name,
                description=wf.description,
                category=wf.category or "General",
                tags=wf.tags or [],
                parameters=wf.parameters_schema or [],
                execution_mode=wf.execution_mode or "sync",  # type: ignore[arg-type]
                timeout_seconds=getattr(wf, "timeout_seconds", None) or 1800,
                retry_policy=getattr(wf, "retry_policy", None),
                schedule=wf.schedule,
                endpoint_enabled=wf.endpoint_enabled or False,
                allowed_methods=wf.allowed_methods or ["POST"],
                disable_global_key=getattr(wf, "disable_global_key", False) or False,
                public_endpoint=getattr(wf, "public_endpoint", False) or False,
                is_tool=wf.is_tool or False,
                tool_description=wf.tool_description,
                time_saved=wf.time_saved or 0,
                value=float(wf.value) if wf.value else 0.0,
                source_file_path=getattr(wf, "source_file_path", None) or wf.file_path,
                relative_file_path=getattr(wf, "relative_file_path", None),
            )
            for wf in db_workflows
        ]

        logger.info(f"Returning {len(workflow_list)} workflows for user {context.user_id}")

        return workflow_list

    @staticmethod
    async def get(execution_id: str) -> WorkflowExecution:
        """
        Get execution details for a workflow.

        Args:
            execution_id: Execution ID

        Returns:
            WorkflowExecution: Execution details including status, result, logs

        Raises:
            ValueError: If execution not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import workflows
            >>> execution = await workflows.get("exec-123")
            >>> print(execution.status)
        """
        # Use the async executions SDK
        return await executions.get(execution_id)
