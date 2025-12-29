"""
Module Loader
Pure functions for loading workflows, data providers, and forms at runtime.

Note: Metadata discovery (for DB sync) is handled by FileStorageService at write time.
This module is only for runtime loading of Python code for execution.

Since all workflow/data provider executions run in fresh subprocess workers,
we don't need any module cache clearing - sys.modules starts empty.
"""

import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)


# ==================== WORKSPACE INITIALIZATION ====================
# Add workspace to sys.path at module load time
# This ensures all processes (API, worker, consumer) can import workspace modules

WORKSPACE_PATH = Path("/tmp/bifrost/workspace")
WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)

if str(WORKSPACE_PATH) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_PATH))
    logger.debug(f"Added workspace to sys.path: {WORKSPACE_PATH}")


# ==================== METADATA DATACLASSES ====================
# These are the same as in registry.py but defined here to avoid circular imports


@dataclass
class WorkflowParameter:
    """Workflow parameter metadata - derived from function signature."""
    name: str
    type: str  # string, int, bool, float, json, list
    label: str | None = None
    required: bool = False
    default_value: Any | None = None
    options: list[dict[str, str]] | None = None  # For Literal types - [{label, value}, ...]


@dataclass
class WorkflowMetadata:
    """Workflow metadata from @workflow decorator"""
    # Identity
    id: str | None = None  # Persistent UUID (written by discovery watcher to Python file)
    name: str = ""
    description: str = ""
    category: str = "General"
    tags: list[str] = field(default_factory=list)

    # Execution
    execution_mode: Literal["sync", "async"] = "async"
    timeout_seconds: int = 1800  # Default 30 minutes

    # Retry (for future use)
    retry_policy: dict[str, Any] | None = None

    # Scheduling (for future use)
    schedule: str | None = None

    # HTTP Endpoint Configuration
    endpoint_enabled: bool = False
    allowed_methods: list[str] = field(default_factory=lambda: ["POST"])
    disable_global_key: bool = False
    public_endpoint: bool = False

    # Tool configuration (for AI agent tool calling)
    tool: bool = False  # Whether this workflow is available as an agent tool
    tool_description: str | None = None  # LLM-friendly description for tool calling

    # Economics - value metrics for reporting
    time_saved: int = 0  # Minutes saved per execution
    value: float = 0.0  # Flexible value unit (e.g., cost savings, revenue)

    # Source tracking
    source_file_path: str | None = None

    # Parameters and function
    parameters: list[WorkflowParameter] = field(default_factory=list)
    function: Any = None


@dataclass
class DataProviderMetadata:
    """Data provider metadata from @data_provider decorator"""
    name: str
    description: str
    category: str = "General"
    cache_ttl_seconds: int = 300  # Default 5 minutes
    function: Any = None  # The actual Python function
    parameters: list[WorkflowParameter] = field(default_factory=list)

    # Identity - persistent UUID (written by discovery watcher)
    id: str | None = None

    # Source tracking (home, platform, workspace)
    source: Literal["home", "platform", "workspace"] | None = None
    source_file_path: str | None = None


@dataclass
class FormMetadata:
    """Lightweight form metadata for listing"""
    id: str
    name: str
    workflow_id: str | None
    org_id: str
    is_active: bool
    is_global: bool
    access_level: str | None
    file_path: str
    created_at: datetime
    updated_at: datetime
    launch_workflow_id: str | None = None


# ==================== WORKSPACE HELPERS ====================


def get_workspace_paths() -> list[Path]:
    """
    Get all workspace directories.

    Returns:
        List of Path objects for existing workspace directories
    """
    paths: list[Path] = []
    base_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent

    # Hardcoded workspace path - kept in sync with S3 by WorkspaceSyncService
    workspace_path = Path("/tmp/bifrost/workspace")
    workspace_path.mkdir(parents=True, exist_ok=True)
    paths.append(workspace_path)

    # Platform code directory (always relative to project root)
    platform_path = base_dir / 'platform'
    if platform_path.exists():
        paths.append(platform_path)

    return paths


def import_module(file_path: Path) -> ModuleType:
    """
    Import a Python module from a file path.

    Since workflow executions run in fresh subprocess workers, sys.modules
    starts empty - no cache clearing needed. Python's import machinery
    handles .pyc files correctly (regenerates if stale).

    Args:
        file_path: Path to the Python file to import

    Returns:
        The imported module

    Raises:
        ImportError: If module cannot be imported
    """
    workspace_paths = get_workspace_paths()

    # Calculate module name from workspace-relative path
    module_name = None
    for workspace_path in workspace_paths:
        try:
            relative_path = file_path.relative_to(workspace_path)
            module_parts = list(relative_path.parts[:-1]) + [file_path.stem]
            module_name = '.'.join(module_parts) if module_parts else file_path.stem
            break
        except ValueError:
            continue

    if not module_name:
        module_name = file_path.stem

    # Ensure workspace paths are in sys.path for relative imports
    # (e.g., from modules.helpers import foo)
    for wp in workspace_paths:
        wp_str = str(wp)
        if wp_str not in sys.path:
            sys.path.insert(0, wp_str)

    # Import the module
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not create module spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        # Clean up on failure
        if module_name in sys.modules:
            del sys.modules[module_name]
        raise ImportError(f"Failed to import {file_path}: {e}") from e

    return module


# Aliases for backward compatibility
reload_module = import_module
import_module_fresh = import_module
reload_single_module = import_module


# ==================== WORKFLOW DISCOVERY ====================


def scan_all_workflows() -> list[WorkflowMetadata]:
    """
    Scan all workspace directories and return workflow metadata.

    Imports each Python file and extracts workflows with
    the _workflow_metadata attribute set by @workflow decorator.

    Returns:
        List of WorkflowMetadata objects
    """
    workflows: list[WorkflowMetadata] = []
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        logger.warning("No workspace paths found")
        return workflows

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            # Skip __init__.py and private files
            if py_file.name.startswith("_"):
                continue
            # Skip .packages directory
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module(py_file)

                # Scan module for decorated functions
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_workflow_metadata'):
                        metadata = getattr(attr, '_workflow_metadata', None)
                        if metadata is None:
                            continue
                        if isinstance(metadata, WorkflowMetadata):
                            workflows.append(metadata)
                        else:
                            # Convert from old registry type if needed
                            workflows.append(_convert_workflow_metadata(metadata))

            except Exception as e:
                logger.warning(f"Failed to scan {py_file}: {e}")

    logger.info(f"Scanned {len(workflows)} workflows from {len(workspace_paths)} workspace(s)")
    return workflows


def load_workflow(name: str) -> tuple[Callable, WorkflowMetadata] | None:
    """
    Find and load a specific workflow by name.

    Scans workspace directories, imports, and returns the
    function and metadata for the named workflow.

    Args:
        name: Workflow name to find

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        return None

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_workflow_metadata'):
                        metadata = getattr(attr, '_workflow_metadata', None)
                        if metadata and hasattr(metadata, 'name') and metadata.name == name:
                            if isinstance(metadata, WorkflowMetadata):
                                return (attr, metadata)
                            else:
                                return (attr, _convert_workflow_metadata(metadata))

            except Exception as e:
                logger.debug(f"Error scanning {py_file} for workflow '{name}': {e}")

    return None


# ==================== DATA PROVIDER DISCOVERY ====================


def scan_all_data_providers() -> list[DataProviderMetadata]:
    """
    Scan all workspace directories and return data provider metadata.

    Returns:
        List of DataProviderMetadata objects
    """
    providers: list[DataProviderMetadata] = []
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        return providers

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_data_provider_metadata'):
                        metadata = getattr(attr, '_data_provider_metadata', None)
                        if metadata is None:
                            continue
                        if isinstance(metadata, DataProviderMetadata):
                            providers.append(metadata)
                        else:
                            providers.append(_convert_data_provider_metadata(metadata))

            except Exception as e:
                logger.warning(f"Failed to scan {py_file}: {e}")

    logger.info(f"Scanned {len(providers)} data providers from {len(workspace_paths)} workspace(s)")
    return providers


def load_data_provider(name: str) -> tuple[Callable, DataProviderMetadata] | None:
    """
    Find and load a specific data provider by name.

    Args:
        name: Data provider name to find

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        return None

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_data_provider_metadata'):
                        metadata = getattr(attr, '_data_provider_metadata', None)
                        if metadata and hasattr(metadata, 'name') and metadata.name == name:
                            if isinstance(metadata, DataProviderMetadata):
                                return (attr, metadata)
                            else:
                                return (attr, _convert_data_provider_metadata(metadata))

            except Exception as e:
                logger.debug(f"Error scanning {py_file} for data provider '{name}': {e}")

    return None


# ==================== FORM DISCOVERY ====================


def scan_all_forms() -> list[FormMetadata]:
    """
    Scan all workspace directories for *.form.json files.

    Returns:
        List of FormMetadata objects
    """
    forms: list[FormMetadata] = []
    workspace_paths = get_workspace_paths()

    for workspace_path in workspace_paths:
        # Find all *.form.json and form.json files
        form_files = list(workspace_path.rglob("*.form.json")) + list(workspace_path.rglob("form.json"))

        for form_file in form_files:
            try:
                with open(form_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Parse datetime fields (support both snake_case and camelCase)
                now = datetime.utcnow()
                created_at = now
                updated_at = now
                created_at_str = data.get('created_at') or data.get('createdAt')
                if created_at_str:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                updated_at_str = data.get('updated_at') or data.get('updatedAt')
                if updated_at_str:
                    updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))

                # Parse accessLevel (support both formats)
                access_level = data.get('access_level') or data.get('accessLevel')

                # Generate ID from file path if not provided
                form_id = data.get('id') or f"workspace-{form_file.stem}"

                is_global = data.get('is_global', False)
                org_id = data.get('org_id', 'GLOBAL' if is_global else '')

                # Prefer workflow_id, fall back to linked_workflow for legacy files
                workflow_id = data.get('workflow_id') or data.get('linked_workflow')

                forms.append(FormMetadata(
                    id=form_id,
                    name=data['name'],
                    workflow_id=workflow_id,
                    org_id=org_id,
                    is_active=data.get('is_active', True),
                    is_global=is_global,
                    access_level=access_level,
                    file_path=str(form_file),
                    created_at=created_at,
                    updated_at=updated_at,
                    launch_workflow_id=data.get('launch_workflow_id')
                ))

            except Exception as e:
                logger.warning(f"Failed to load form from {form_file}: {e}")

    logger.info(f"Scanned {len(forms)} forms from {len(workspace_paths)} workspace(s)")
    return forms


def load_form(form_id: str) -> dict | None:
    """
    Load a form by ID, reading fresh from file.

    Args:
        form_id: Form ID to find

    Returns:
        Full form dict or None if not found
    """
    workspace_paths = get_workspace_paths()

    for workspace_path in workspace_paths:
        form_files = list(workspace_path.rglob("*.form.json")) + list(workspace_path.rglob("form.json"))

        for form_file in form_files:
            try:
                with open(form_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check if this is the form we're looking for
                file_form_id = data.get('id') or f"workspace-{form_file.stem}"
                if file_form_id == form_id:
                    # Ensure id is in the returned data (may be derived from filename)
                    data['id'] = file_form_id
                    return data

            except Exception as e:
                logger.debug(f"Error reading {form_file}: {e}")

    return None


def load_form_by_file_path(file_path: str) -> dict | None:
    """
    Load a form directly by its file path.

    Args:
        file_path: Full path to the form.json file

    Returns:
        Full form dict or None if not found
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load form from {file_path}: {e}")
        return None


def get_form_metadata(form_id: str) -> FormMetadata | None:
    """
    Get form metadata by ID.

    Args:
        form_id: Form ID to find

    Returns:
        FormMetadata or None if not found
    """
    all_forms = scan_all_forms()
    for form in all_forms:
        if form.id == form_id:
            return form
    return None


def get_forms_by_workflow(workflow_id_or_name: str) -> list[FormMetadata]:
    """
    Get all forms that use a specific workflow.

    Args:
        workflow_id_or_name: Workflow ID (UUID) or name to filter by

    Returns:
        List of FormMetadata for forms using this workflow
    """
    all_forms = scan_all_forms()
    # Match by workflow_id (for UUID-based lookups) or legacy name-based lookups
    return [f for f in all_forms if f.workflow_id == workflow_id_or_name]


# ==================== METADATA CONVERSION HELPERS ====================
# These handle compatibility with existing decorator output format


def _convert_workflow_metadata(old_metadata: Any) -> WorkflowMetadata:
    """Convert old registry WorkflowMetadata to discovery WorkflowMetadata."""
    return WorkflowMetadata(
        id=getattr(old_metadata, 'id', None),
        name=old_metadata.name,
        description=old_metadata.description,
        category=getattr(old_metadata, 'category', 'General'),
        tags=getattr(old_metadata, 'tags', []),
        execution_mode=getattr(old_metadata, 'execution_mode', 'sync'),
        timeout_seconds=getattr(old_metadata, 'timeout_seconds', 1800),
        retry_policy=getattr(old_metadata, 'retry_policy', None),
        schedule=getattr(old_metadata, 'schedule', None),
        endpoint_enabled=getattr(old_metadata, 'endpoint_enabled', False),
        allowed_methods=getattr(old_metadata, 'allowed_methods', ['POST']),
        disable_global_key=getattr(old_metadata, 'disable_global_key', False),
        public_endpoint=getattr(old_metadata, 'public_endpoint', False),
        tool=getattr(old_metadata, 'tool', False),
        tool_description=getattr(old_metadata, 'tool_description', None),
        time_saved=getattr(old_metadata, 'time_saved', 0),
        value=getattr(old_metadata, 'value', 0.0),
        source_file_path=getattr(old_metadata, 'source_file_path', None),
        parameters=_convert_parameters(getattr(old_metadata, 'parameters', [])),
        function=getattr(old_metadata, 'function', None)
    )


def _convert_data_provider_metadata(old_metadata: Any) -> DataProviderMetadata:
    """Convert old registry DataProviderMetadata to discovery DataProviderMetadata."""
    return DataProviderMetadata(
        name=old_metadata.name,
        description=old_metadata.description,
        category=getattr(old_metadata, 'category', 'General'),
        cache_ttl_seconds=getattr(old_metadata, 'cache_ttl_seconds', 300),
        function=getattr(old_metadata, 'function', None),
        parameters=_convert_parameters(getattr(old_metadata, 'parameters', [])),
        source=getattr(old_metadata, 'source', None),
        source_file_path=getattr(old_metadata, 'source_file_path', None)
    )


def _convert_parameters(params: list) -> list[WorkflowParameter]:
    """Convert parameter list to WorkflowParameter list."""
    result = []
    for p in params:
        if isinstance(p, WorkflowParameter):
            result.append(p)
        else:
            result.append(WorkflowParameter(
                name=p.name,
                type=p.type,
                label=getattr(p, 'label', None),
                required=getattr(p, 'required', False),
                default_value=getattr(p, 'default_value', None),
            ))
    return result


# ==================== DIRECT FILE LOADING ====================


def load_workflow_by_file_path(
    file_path: str | Path,
    workflow_name: str,
) -> tuple[Callable, WorkflowMetadata] | None:
    """
    Load a specific workflow from a known file path.

    Use this when you already know the file path (from database or cache)
    to skip the filesystem scan that load_workflow() does.

    Args:
        file_path: Path to the workflow Python file (relative or absolute)
        workflow_name: Expected workflow name to find

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    # Resolve to absolute path if relative
    if isinstance(file_path, str):
        file_path = Path(file_path)

    if not file_path.is_absolute():
        # Assume relative to workspace root
        file_path = WORKSPACE_PATH / file_path

    if not file_path.exists():
        logger.warning(f"Workflow file not found: {file_path}")
        return None

    try:
        module = import_module(file_path)

        # Find the workflow function by name
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, '_workflow_metadata'):
                metadata = getattr(attr, '_workflow_metadata', None)
                if metadata and hasattr(metadata, 'name') and metadata.name == workflow_name:
                    if isinstance(metadata, WorkflowMetadata):
                        return (attr, metadata)
                    else:
                        return (attr, _convert_workflow_metadata(metadata))

        logger.warning(f"Workflow '{workflow_name}' not found in {file_path}")
        return None

    except Exception as e:
        logger.error(f"Error loading workflow '{workflow_name}' from {file_path}: {e}")
        return None


def get_workflow(name: str) -> tuple[Callable, WorkflowMetadata] | None:
    """
    Get a workflow by name.

    Uses the same import logic as load_workflow() to ensure correct
    module paths and __file__ resolution.

    Args:
        name: Workflow name

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    # Use load_workflow which properly handles module imports
    # This ensures __file__ and sys.path are set correctly
    return load_workflow(name)


def get_data_provider(name: str) -> tuple[Callable, DataProviderMetadata] | None:
    """
    Get a data provider by name.

    Uses the same import logic as load_data_provider() to ensure correct
    module paths and __file__ resolution.

    Args:
        name: Data provider name

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    # Use load_data_provider which properly handles module imports
    return load_data_provider(name)


def get_form(form_id: str) -> dict | None:
    """
    Get a form by ID.

    Args:
        form_id: Form ID

    Returns:
        Form dict or None if not found
    """
    return load_form(form_id)
