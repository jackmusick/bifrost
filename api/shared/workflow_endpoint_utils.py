"""
Workflow Endpoint Utilities
Reusable business logic for workflow endpoint execution
"""

import logging
from datetime import datetime
from typing import Any

from shared.context import ExecutionContext
from shared.module_loader import WorkflowMetadata
from shared.execution_logger import ExecutionLogger
from shared.models import ExecutionStatus, WorkflowExecutionResponse

logger = logging.getLogger(__name__)


def coerce_parameter_types(
    input_data: dict[str, Any],
    param_metadata: dict[str, Any]
) -> dict[str, Any]:
    """
    Convert string query parameters to their proper types based on metadata.

    Args:
        input_data: Raw input data (query params + body)
        param_metadata: Dictionary mapping parameter names to their metadata

    Returns:
        Dictionary with type-coerced values
    """
    coerced_params = {}

    for key, value in input_data.items():
        if key in param_metadata:
            param = param_metadata[key]
            try:
                # Convert string values from query params to proper types
                if param.type in ['int', 'integer'] and isinstance(value, str):
                    value = int(value)
                elif param.type == 'float' and isinstance(value, str):
                    value = float(value)
                elif param.type in ['bool', 'boolean'] and isinstance(value, str):
                    # Handle common boolean string representations
                    value = value.lower() in ('true', '1', 'yes', 'on')
                # string type needs no conversion
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to convert parameter '{key}' to {param.type}: {e}",
                    extra={"key": key, "value": value, "expected_type": param.type}
                )
                # Keep original value if conversion fails

            coerced_params[key] = value
        else:
            # Pass through non-workflow parameters unchanged
            coerced_params[key] = value

    return coerced_params


async def record_workflow_execution_result(
    exec_logger: ExecutionLogger,
    execution_id: str,
    context: ExecutionContext,
    status: ExecutionStatus,
    start_time: datetime,
    result: Any | None = None,
    error: Exception | None = None
) -> WorkflowExecutionResponse:
    """
    Record workflow execution result and build response.

    Args:
        exec_logger: Execution logger instance
        execution_id: Execution ID
        context: Organization context
        status: Execution status (SUCCESS or FAILED)
        start_time: Execution start time
        result: Workflow result (for success)
        error: Exception (for failure)

    Returns:
        WorkflowExecutionResponse model
    """
    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # Prepare update kwargs
    update_kwargs = {
        "execution_id": execution_id,
        "org_id": context.org_id,
        "user_id": context.user_id,
        "status": status,
        "duration_ms": duration_ms
    }

    # Add result or error
    if status == ExecutionStatus.SUCCESS:
        update_kwargs["result"] = result
    elif error:
        update_kwargs["error_message"] = str(error)
        update_kwargs["error_type"] = type(error).__name__

    # Update execution record
    await exec_logger.update_execution(**update_kwargs)

    # Build response
    response_data = {
        "executionId": execution_id,
        "status": status.value,  # Convert enum to string
        "durationMs": duration_ms,
        "startedAt": start_time.isoformat(),
        "completedAt": end_time.isoformat()
    }

    if status == ExecutionStatus.SUCCESS:
        response_data["result"] = result
    elif error:
        response_data["error"] = str(error)
        response_data["errorType"] = type(error).__name__

    return WorkflowExecutionResponse(**response_data)


def separate_workflow_params(
    input_data: dict[str, Any],
    workflow_metadata: WorkflowMetadata
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Separate workflow parameters from extra variables.

    Args:
        input_data: All input data
        workflow_metadata: Workflow metadata with parameter definitions

    Returns:
        Tuple of (workflow_params, extra_variables)
    """
    defined_params = {param.name for param in workflow_metadata.parameters}

    workflow_params = {}
    extra_variables = {}

    for key, value in input_data.items():
        if key in defined_params:
            workflow_params[key] = value
        else:
            extra_variables[key] = value

    return workflow_params, extra_variables
