"""
Workflows SDK for Bifrost.

Provides Python API for workflow operations (list, get status).

All methods are async and must be awaited.
"""

from __future__ import annotations

import logging
from typing import Any

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
    async def list() -> list[dict[str, Any]]:
        """
        List all available workflows.

        Returns:
            list[dict]: List of workflow metadata

        Raises:
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import workflows
            >>> wf_list = await workflows.list()
            >>> for wf in wf_list:
            ...     print(f"{wf['name']}: {wf['description']}")
        """
        context = get_context()

        logger.info(f"User {context.user_id} listing workflows")

        if not context._db:
            logger.warning("No database session in context, returning empty workflow list")
            return []

        from src.repositories.workflows import WorkflowRepository

        repo = WorkflowRepository(context._db)
        db_workflows = await repo.get_all_active()

        # Convert to dicts for serialization
        workflow_list = [
            {
                "name": wf.name,
                "description": wf.description or "",
                "parameters": wf.parameters_schema or [],
                "executionMode": wf.execution_mode or "sync",
                "endpointEnabled": wf.endpoint_enabled or False
            }
            for wf in db_workflows
        ]

        logger.info(f"Returning {len(workflow_list)} workflows for user {context.user_id}")

        return workflow_list

    @staticmethod
    async def get(execution_id: str) -> dict[str, Any]:
        """
        Get execution details for a workflow.

        Args:
            execution_id: Execution ID

        Returns:
            dict: Execution details including status, result, logs

        Raises:
            ValueError: If execution not found
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import workflows
            >>> execution = await workflows.get("exec-123")
            >>> print(execution["status"])
        """
        # Use the async executions SDK
        return await executions.get(execution_id)
