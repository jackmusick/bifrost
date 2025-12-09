"""
Workflows Handlers V2 - Refactored to use unified engine
Business logic for workflow execution using subprocess isolation.

Note: HTTP handlers have been removed - see FastAPI routers in src/routers/
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from shared.module_loader import get_workflow
from shared.models import ErrorResponse, ExecutionStatus, WorkflowMetadata as WorkflowMetadataModel

# Lazy imports to avoid unnecessary dependencies for validation-only use cases
if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _extract_relative_path(source_file_path: str | None) -> str | None:
    """
    Extract workspace-relative file path from absolute path.
    Returns path with /workspace/ prefix for consistency with editor paths.

    Args:
        source_file_path: Absolute file path (e.g., /path/to/workspace/repo/workflows/my_workflow.py)

    Returns:
        Path with /workspace/ prefix (e.g., /workspace/workflows/my_workflow.py)
        Returns None if source_file_path is None or no marker found
    """
    if not source_file_path:
        return None

    # Get workspace location from environment
    workspace_location = os.getenv("BIFROST_WORKSPACE_LOCATION")
    if workspace_location:
        workspace_path = Path(workspace_location)
        source_path = Path(source_file_path)

        # Check if source_path is relative to workspace
        try:
            relative = source_path.relative_to(workspace_path)
            # Return with /workspace/ prefix for consistency
            return f"/workspace/{relative}"
        except ValueError:
            # Not relative to workspace, fall through to marker check
            pass

    # Fallback: Extract everything after markers and prepend /workspace/
    for marker in ['/home/', '/platform/']:
        if marker in source_file_path:
            relative = source_file_path.split(marker, 1)[1]
            return f"/workspace/{relative}"

    # If already has /workspace/ prefix, return as-is
    if '/workspace/' in source_file_path:
        return '/workspace/' + source_file_path.split('/workspace/', 1)[1]

    return None


def _convert_workflow_metadata_to_model(
    workflow_metadata: Any,
) -> WorkflowMetadataModel:
    """
    Convert a discovery WorkflowMetadata dataclass to a Pydantic model.

    Args:
        workflow_metadata: Workflow metadata from discovery (dataclass)

    Returns:
        WorkflowMetadata Pydantic model for API response
    """
    # Convert parameters from dataclass to dict with proper field mapping
    parameters = []
    if workflow_metadata.parameters:
        for p in workflow_metadata.parameters:
            param_dict = {
                "name": p.name,
                "type": p.type,
                "required": p.required,
            }
            # Add optional fields only if they're not None
            if p.label is not None:
                param_dict["label"] = p.label
            if p.data_provider is not None:
                param_dict["dataProvider"] = p.data_provider
            if p.default_value is not None:
                param_dict["defaultValue"] = p.default_value
            if p.help_text is not None:
                param_dict["helpText"] = p.help_text
            if p.validation is not None:
                param_dict["validation"] = p.validation
            if hasattr(p, 'description') and p.description is not None:
                param_dict["description"] = p.description
            parameters.append(param_dict)

    # Get or generate workflow ID
    # Use existing id if available, otherwise generate deterministic UUID from name
    workflow_id = workflow_metadata.id
    if not workflow_id:
        # Generate deterministic UUID from workflow name for consistency
        workflow_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"bifrost.workflow.{workflow_metadata.name}"))

    return WorkflowMetadataModel(
        id=workflow_id,
        name=workflow_metadata.name,
        description=workflow_metadata.description,
        category=workflow_metadata.category,
        tags=workflow_metadata.tags,
        parameters=parameters,
        execution_mode=workflow_metadata.execution_mode,
        timeout_seconds=workflow_metadata.timeout_seconds,
        retry_policy=workflow_metadata.retry_policy,
        schedule=workflow_metadata.schedule,
        endpoint_enabled=workflow_metadata.endpoint_enabled,
        allowed_methods=workflow_metadata.allowed_methods,
        disable_global_key=workflow_metadata.disable_global_key,
        public_endpoint=workflow_metadata.public_endpoint,
        source_file_path=workflow_metadata.source_file_path,
        relative_file_path=_extract_relative_path(workflow_metadata.source_file_path),
    )


async def execute_workflow_internal(
    context,
    workflow_name: str,
    parameters: dict,
    form_id: str | None = None,
    transient: bool = False,
    code_base64: str | None = None
) -> tuple[dict, int]:
    """
    Internal workflow execution logic shared by forms and workflow execute endpoint.

    Args:
        context: ExecutionContext with org scope and user info
        workflow_name: Name of workflow to execute
        parameters: Workflow parameters
        form_id: Optional form ID if triggered by form
        transient: If True, don't write to database
        code_base64: Optional base64-encoded inline script

    Returns:
        tuple of (response_dict, status_code)
    """
    user_id = context.user_id

    # Determine execution mode
    is_script = bool(code_base64)

    # Determine if async execution is required
    execution_mode = "async"  # Default for scripts

    # Variables to hold loaded workflow data
    workflow_func = None
    workflow_metadata = None

    if not is_script:
        # Dynamically load workflow (always fresh import)
        try:
            result = get_workflow(workflow_name)
            if not result:
                logger.warning(f"Workflow not found: {workflow_name}")
                return {
                    "error": "NotFound",
                    "message": f"Workflow '{workflow_name}' not found"
                }, 404

            workflow_func, workflow_metadata = result
            logger.debug(f"Loaded workflow fresh: {workflow_name}")
        except Exception as e:
            # Load failed (likely syntax error)
            logger.error(f"Failed to load workflow {workflow_name}: {e}", exc_info=True)
            error_response = ErrorResponse(
                error="WorkflowLoadError",
                message=f"Failed to load workflow '{workflow_name}': {str(e)}"
            )
            return error_response.model_dump(), 500

        # Get execution mode from workflow metadata
        execution_mode = workflow_metadata.execution_mode

    # Queue for async execution if required
    if execution_mode == "async":
        from shared.async_executor import enqueue_workflow_execution

        execution_id = await enqueue_workflow_execution(
            context=context,
            workflow_name=workflow_name,
            parameters=parameters,
            form_id=form_id,
            code_base64=code_base64  # Pass script code if present
        )

        return {
            "executionId": execution_id,
            "status": "Pending",
            "message": "Workflow queued for async execution" if not is_script else "Script queued for async execution"
        }, 202

    # Synchronous execution path - execute in isolated subprocess
    execution_id = str(uuid.uuid4())

    # Runtime imports to avoid unnecessary dependencies at module load
    from shared.execution import get_execution_pool
    from shared.execution_logger import get_execution_logger
    from shared.webpubsub_broadcaster import WebPubSubBroadcaster

    exec_logger = get_execution_logger()
    start_time = datetime.utcnow()
    timeout_seconds = workflow_metadata.timeout_seconds if workflow_metadata else 1800

    # Initialize Web PubSub broadcaster for real-time updates
    broadcaster = WebPubSubBroadcaster()

    try:
        # Create execution record - skip if transient
        if not transient:
            await exec_logger.create_execution(
                execution_id=execution_id,
                org_id=context.org_id,
                user_id=user_id,
                user_name=context.name,
                workflow_name=workflow_name,
                input_data=parameters,
                form_id=form_id,
                webpubsub_broadcaster=broadcaster
            )

        logger.info(
            f"Starting sync workflow execution: {workflow_name}",
            extra={
                "execution_id": execution_id,
                "org_id": context.org_id,
                "user_id": user_id
            }
        )

        # Build context data for subprocess
        org_data = None
        if context.organization:
            org_data = {
                "id": context.organization.id,
                "name": context.organization.name,
                "is_active": context.organization.is_active,
            }

        context_data = {
            "execution_id": execution_id,
            "name": workflow_name,
            "code": code_base64 if is_script else None,
            "parameters": parameters,
            "caller": {
                "user_id": context.user_id,
                "email": context.email,
                "name": context.name,
            },
            "organization": org_data,
            "config": context._config,
            "tags": ["workflow"] if not is_script else [],
            "timeout_seconds": timeout_seconds,
            "transient": transient,
            "is_platform_admin": context.is_platform_admin,
        }

        # Execute in isolated subprocess
        pool = get_execution_pool()
        result = await pool.execute(
            execution_id=execution_id,
            context_data=context_data,
            timeout_seconds=timeout_seconds,
        )

        # Map result status
        status_str = result.get("status", "Failed")
        status = ExecutionStatus(status_str) if status_str in [s.value for s in ExecutionStatus] else ExecutionStatus.FAILED

        # Update execution record - skip if transient
        if not transient:
            await exec_logger.update_execution(
                execution_id=execution_id,
                org_id=context.org_id,
                user_id=user_id,
                status=status,
                result=result.get("result"),
                error_message=result.get("error_message"),
                error_type=result.get("error_type"),
                duration_ms=result.get("duration_ms", 0),
                integration_calls=result.get("integration_calls"),
                logs=result.get("logs"),
                variables=result.get("variables"),
                webpubsub_broadcaster=broadcaster
            )

        # Build response
        end_time = datetime.utcnow()

        response_dict = {
            "executionId": execution_id,
            "status": status.value,
            "durationMs": result.get("duration_ms", 0),
            "startedAt": start_time.isoformat(),
            "completedAt": end_time.isoformat(),
            "isTransient": transient
        }

        if status == ExecutionStatus.SUCCESS:
            response_dict["result"] = result.get("result")
        elif result.get("error_message"):
            # Filter error details based on user role and error type
            if context.is_platform_admin:
                # Admins see full technical details
                response_dict["error"] = result.get("error_message")
                response_dict["errorType"] = result.get("error_type")
            else:
                # Regular users: Check if it's a UserError (show message) or generic error (hide details)
                if result.get("error_type") == "UserError":
                    response_dict["error"] = result.get("error_message")
                else:
                    response_dict["error"] = "An error occurred during execution"

        # Include logs/variables for platform admins
        if context.is_platform_admin:
            if result.get("logs"):
                response_dict["logs"] = result.get("logs")
            if result.get("variables"):
                response_dict["variables"] = result.get("variables")
        else:
            # Regular users: Filter logs to exclude DEBUG and TRACEBACK levels
            if result.get("logs"):
                filtered_logs = [
                    log for log in result.get("logs", [])
                    if log.get('level') not in ['debug', 'traceback']
                ]
                response_dict["logs"] = filtered_logs

        return response_dict, 200

    except asyncio.CancelledError:
        # Execution was cancelled
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=user_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution cancelled by user",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(f"Failed to update execution record: {update_error}")

        return {
            "executionId": execution_id,
            "status": "Cancelled",
            "error": "Execution cancelled by user",
            "durationMs": duration_ms,
            "startedAt": start_time.isoformat(),
            "completedAt": end_time.isoformat(),
            "isTransient": transient
        }, 200

    except TimeoutError as e:
        # Execution timed out
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=user_id,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=str(e),
                    error_type="TimeoutError",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(f"Failed to update execution record: {update_error}")

        return {
            "executionId": execution_id,
            "status": "Timeout",
            "error": str(e),
            "errorType": "TimeoutError",
            "durationMs": duration_ms,
            "startedAt": start_time.isoformat(),
            "completedAt": end_time.isoformat(),
            "isTransient": transient
        }, 200

    except Exception as e:
        # CRITICAL: Catch-all to prevent stuck executions
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.error(
            f"Unexpected error in workflow execution: {workflow_name}",
            extra={"execution_id": execution_id, "error": str(e)},
            exc_info=True
        )

        # Try to update execution record
        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=user_id,
                    status=ExecutionStatus.FAILED,
                    error_message=f"Unexpected error: {str(e)}",
                    error_type="InternalError",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(
                    f"Failed to update execution record: {update_error}")

        # Return error response
        return {
            "executionId": execution_id,
            "status": "Failed",
            "error": str(e),
            "errorType": "InternalError",
            "durationMs": duration_ms,
            "startedAt": start_time.isoformat(),
            "completedAt": end_time.isoformat(),
            "isTransient": transient
        }, 200


# Note: HTTP handlers are implemented in FastAPI routers.
# See src/routers/workflows.py for the HTTP endpoint implementation.


async def validate_workflow_file(path: str, content: str | None = None):
    """
    Validate a workflow file for syntax errors, decorator issues, and Pydantic validation.

    Args:
        path: Relative workspace path to the workflow file
        content: Optional file content (if not provided, reads from disk)

    Returns:
        WorkflowValidationResponse with validation results
    """
    import tempfile
    import re
    from pydantic import ValidationError
    from shared.models import WorkflowValidationResponse, ValidationIssue
    from shared.module_loader import import_module_fresh, WorkflowMetadata
    from shared.type_inference import VALID_PARAM_TYPES

    issues = []
    valid = True
    metadata = None

    # Determine the absolute file path
    workspace_roots = ["/home", "/platform", "/workspace"]
    workspace_location = os.environ.get("BIFROST_WORKSPACE_LOCATION")
    if workspace_location:
        workspace_roots.insert(0, workspace_location)

    abs_path = None
    for root in workspace_roots:
        candidate = Path(root) / path
        if candidate.exists():
            abs_path = candidate
            break

    # If content provided, use temporary file; otherwise use actual file
    if content is not None:
        # Create a temporary file with the content
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        try:
            temp_file.write(content)
            temp_file.close()
            file_to_validate = Path(temp_file.name)
            file_content = content
        except Exception as e:
            issues.append(ValidationIssue(
                line=None,
                message=f"Failed to write temporary file: {str(e)}",
                severity="error"
            ))
            return WorkflowValidationResponse(valid=False, issues=issues, metadata=None)
    else:
        if abs_path is None or not abs_path.exists():
            issues.append(ValidationIssue(
                line=None,
                message=f"File not found: {path}",
                severity="error"
            ))
            return WorkflowValidationResponse(valid=False, issues=issues, metadata=None)
        file_to_validate = abs_path
        file_content = abs_path.read_text()

    try:
        # Step 1: Check for Python syntax errors
        try:
            compile(file_content, str(file_to_validate), 'exec')
        except SyntaxError as e:
            issues.append(ValidationIssue(
                line=e.lineno,
                message=f"Syntax error: {e.msg}",
                severity="error"
            ))
            valid = False
            return WorkflowValidationResponse(valid=valid, issues=issues, metadata=None)

        # Step 2: Check for import errors by attempting to load the module
        try:
            module = import_module_fresh(file_to_validate)
        except Exception as e:
            # Import error - could be missing dependencies or runtime errors
            issues.append(ValidationIssue(
                line=None,
                message=f"Import error: {str(e)}",
                severity="error"
            ))
            valid = False
            return WorkflowValidationResponse(valid=valid, issues=issues, metadata=None)

        # Step 3: Check if @workflow decorator was found by scanning module
        discovered_workflows: list[WorkflowMetadata] = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, '_workflow_metadata'):
                metadata_obj = attr._workflow_metadata
                if isinstance(metadata_obj, WorkflowMetadata):
                    discovered_workflows.append(metadata_obj)

        if not discovered_workflows:
            issues.append(ValidationIssue(
                line=None,
                message="No @workflow decorator found. Functions must use @workflow(...) to be discoverable.",
                severity="error"
            ))
            valid = False
            return WorkflowValidationResponse(valid=valid, issues=issues, metadata=None)

        # Use the first matching workflow for validation
        # (most files will have just one workflow, but we support multiple)
        workflow_metadata = discovered_workflows[0]

        # Step 4: Validate workflow name pattern
        name_pattern = r"^[a-z0-9_]+$"
        if not re.match(name_pattern, workflow_metadata.name):
            issues.append(ValidationIssue(
                line=None,
                message=f"Invalid workflow name '{workflow_metadata.name}'. Name must be lowercase snake_case (only letters, numbers, underscores).",
                severity="error"
            ))
            valid = False

        # Step 5: Validate required fields
        if not workflow_metadata.description or len(workflow_metadata.description.strip()) == 0:
            issues.append(ValidationIssue(
                line=None,
                message="Workflow description is required and cannot be empty.",
                severity="error"
            ))
            valid = False

        # Step 6: Validate execution mode
        if workflow_metadata.execution_mode not in ["sync", "async"]:
            issues.append(ValidationIssue(
                line=None,
                message=f"Invalid execution mode '{workflow_metadata.execution_mode}'. Must be 'sync' or 'async'.",
                severity="error"
            ))
            valid = False

        # Step 7: Validate timeout
        if workflow_metadata.timeout_seconds is not None:
            if workflow_metadata.timeout_seconds < 1 or workflow_metadata.timeout_seconds > 7200:
                issues.append(ValidationIssue(
                    line=None,
                    message=f"Invalid timeout {workflow_metadata.timeout_seconds}s. Must be between 1 and 7200 seconds.",
                    severity="error"
                ))
                valid = False

        # Step 8: Validate parameter types
        if workflow_metadata.parameters:
            for param in workflow_metadata.parameters:
                if param.type not in VALID_PARAM_TYPES:
                    issues.append(ValidationIssue(
                        line=None,
                        message=f"Invalid parameter type '{param.type}' for parameter '{param.name}'. Must be one of: {', '.join(VALID_PARAM_TYPES)}",
                        severity="error"
                    ))
                    valid = False

        # Step 9: Validate Pydantic model conversion (this is what discovery endpoint does)
        try:
            metadata = _convert_workflow_metadata_to_model(workflow_metadata)
        except ValidationError as e:
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                issues.append(ValidationIssue(
                    line=None,
                    message=f"Validation error in field '{field}': {error['msg']}",
                    severity="error"
                ))
            valid = False

        # Step 10: Warnings for best practices
        if workflow_metadata.category == "General":
            issues.append(ValidationIssue(
                line=None,
                message="Consider specifying a category other than 'General' for better organization.",
                severity="warning"
            ))

        if not workflow_metadata.tags or len(workflow_metadata.tags) == 0:
            issues.append(ValidationIssue(
                line=None,
                message="Consider adding tags to make your workflow more discoverable.",
                severity="warning"
            ))

    finally:
        # Clean up temporary file if created
        if content is not None:
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass

    return WorkflowValidationResponse(valid=valid, issues=issues, metadata=metadata)
