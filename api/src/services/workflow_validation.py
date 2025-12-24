"""
Workflow Validation Service

Validates workflow files for syntax errors, decorator issues, and Pydantic validation.
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.models import WorkflowMetadata as WorkflowMetadataModel

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

    # Hardcoded workspace path - kept in sync with S3 by WorkspaceSyncService
    workspace_path = Path("/tmp/bifrost/workspace")
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
            # Note: data_provider, help_text, validation, options are form concerns,
            # not workflow concerns. Workflow parameters come from function signatures.
            if p.label is not None:
                param_dict["label"] = p.label
            if p.default_value is not None:
                param_dict["default_value"] = p.default_value
            parameters.append(param_dict)

    # Extract the relative path for display
    relative_path = _extract_relative_path(workflow_metadata.source_file_path)

    # Generate a placeholder ID for validation if not present
    # (workflows get real IDs when saved to the database)
    workflow_id = workflow_metadata.id or f"pending-{workflow_metadata.name}"

    return WorkflowMetadataModel(
        id=workflow_id,
        name=workflow_metadata.name,
        description=workflow_metadata.description,
        category=workflow_metadata.category,
        tags=workflow_metadata.tags or [],
        parameters=parameters,
        execution_mode=workflow_metadata.execution_mode,
        timeout_seconds=workflow_metadata.timeout_seconds or 1800,
        retry_policy=None,
        schedule=None,
        endpoint_enabled=False,
        disable_global_key=False,
        public_endpoint=False,
        time_saved=workflow_metadata.time_saved or 0,
        value=workflow_metadata.value or 0.0,
        source_file_path=workflow_metadata.source_file_path,
        relative_file_path=relative_path,
    )


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
    from src.models import WorkflowValidationResponse, ValidationIssue
    from src.services.execution.module_loader import import_module_fresh, WorkflowMetadata
    from src.services.execution.type_inference import VALID_PARAM_TYPES

    issues = []
    valid = True
    metadata = None

    # Determine the absolute file path
    # Primary location is /tmp/bifrost/workspace (hardcoded, kept in sync with S3)
    workspace_roots = ["/tmp/bifrost/workspace", "/home", "/platform", "/workspace"]

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
