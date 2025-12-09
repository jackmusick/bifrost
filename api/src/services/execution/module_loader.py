"""
Module Loader
Pure functions for loading workflows, data providers, and forms at runtime.
No singletons, no caching - always fresh imports.

Note: Metadata discovery (for DB sync) is handled by FileStorageService at write time.
This module is only for runtime loading of Python code for execution.
"""

import importlib
import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Literal, Sequence

logger = logging.getLogger(__name__)


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
    execution_mode: Literal["sync", "async"] = "sync"
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

    # Source tracking (home, platform, workspace)
    source: Literal["home", "platform", "workspace"] | None = None
    source_file_path: str | None = None


@dataclass
class FormMetadata:
    """Lightweight form metadata for listing"""
    id: str
    name: str
    linked_workflow: str
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

    # User workspace from environment variable or default to /tmp/bifrost/workspace
    # The workspace sync service downloads from S3 to /tmp/bifrost/workspace
    workspace_loc = os.getenv("BIFROST_WORKSPACE_LOCATION")
    if workspace_loc:
        workspace_path = Path(workspace_loc)
        if workspace_path.exists():
            paths.append(workspace_path)
    else:
        # Default workspace location for S3-synced files
        default_workspace = Path("/tmp/bifrost/workspace")
        if default_workspace.exists():
            paths.append(default_workspace)

    # Platform code directory (always relative to project root)
    platform_path = base_dir / 'platform'
    if platform_path.exists():
        paths.append(platform_path)

    return paths


def _is_in_workspace(file_path: str, workspace_paths: Sequence[Path | str]) -> bool:
    """Check if a file path is within any workspace directory."""
    file_path_resolved = str(Path(file_path).resolve())
    for wp in workspace_paths:
        # Handle both Path objects and strings
        wp_resolved = str(Path(wp).resolve()) if isinstance(wp, str) else str(wp.resolve())
        if file_path_resolved.startswith(wp_resolved):
            return True
    return False


def _clear_all_workspace_pyc(workspace_paths: Sequence[Path | str]) -> int:
    """
    Delete ALL .pyc files in workspace directories.

    This is critical for ensuring new functions in helper modules are found.
    Unlike the old approach that only deleted .pyc for loaded modules,
    this deletes ALL .pyc files to handle the case of a new function
    in a module that wasn't previously imported.

    Returns:
        Number of .pyc files deleted
    """
    deleted_count = 0
    for workspace_path in workspace_paths:
        # Handle both Path objects and strings
        wp = Path(workspace_path) if isinstance(workspace_path, str) else workspace_path
        for pycache_dir in wp.rglob('__pycache__'):
            for pyc_file in pycache_dir.glob('*.pyc'):
                try:
                    pyc_file.unlink()
                    deleted_count += 1
                except OSError:
                    pass  # Ignore permission errors
    return deleted_count


def _clear_workspace_modules(workspace_paths: Sequence[Path | str]) -> int:
    """
    Clear all workspace modules from sys.modules.

    Returns:
        Number of modules cleared
    """
    cleared_count = 0
    for mod_name in list(sys.modules.keys()):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if not hasattr(mod, '__file__') or mod.__file__ is None:
            continue

        try:
            mod_file = str(Path(mod.__file__).resolve())
            # Check if module is in any workspace path
            if _is_in_workspace(mod_file, workspace_paths):
                # Skip .packages directory (user-installed third-party packages)
                if '.packages' in mod_file:
                    continue
                del sys.modules[mod_name]
                cleared_count += 1
        except (OSError, ValueError):
            continue

    return cleared_count


def import_module_fresh(file_path: Path) -> ModuleType:
    """
    Import a module guaranteeing fresh code.

    This function:
    1. Clears ALL workspace modules from sys.modules
    2. Deletes ALL .pyc files in workspace directories
    3. Invalidates import caches
    4. Imports the module fresh

    Args:
        file_path: Path to the Python file to import

    Returns:
        The imported module

    Raises:
        ImportError: If module cannot be imported
    """
    workspace_paths = get_workspace_paths()

    # 1. Clear all workspace modules from sys.modules
    modules_cleared = _clear_workspace_modules(workspace_paths)

    # 2. Delete ALL .pyc files in workspace directories
    pyc_deleted = _clear_all_workspace_pyc(workspace_paths)

    # 3. Invalidate Python's import caches
    importlib.invalidate_caches()

    if modules_cleared > 0 or pyc_deleted > 0:
        logger.debug(f"Fresh import prep: cleared {modules_cleared} modules, {pyc_deleted} .pyc files")

    # 4. Calculate module name
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

    # 5. Add workspace paths to sys.path for relative imports (e.g., from modules.rewst import ...)
    # NOTE: We keep these paths in sys.path permanently (like function_app.py did on Azure)
    # because workflows need them during execution, not just during import
    for wp in workspace_paths:
        wp_str = str(wp)
        if wp_str not in sys.path:
            sys.path.insert(0, wp_str)

    # 6. Fresh import
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


# Alias for backward compatibility
reload_single_module = import_module_fresh


# ==================== WORKFLOW DISCOVERY ====================


def scan_all_workflows() -> list[WorkflowMetadata]:
    """
    Scan all workspace directories and return workflow metadata.

    Imports each Python file fresh and extracts workflows with
    the _workflow_metadata attribute set by @workflow decorator.

    Returns:
        List of WorkflowMetadata objects
    """
    workflows: list[WorkflowMetadata] = []
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        logger.warning("No workspace paths found")
        return workflows

    # First clear everything for a clean slate
    _clear_workspace_modules(workspace_paths)
    _clear_all_workspace_pyc(workspace_paths)
    importlib.invalidate_caches()

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            # Skip __init__.py and private files
            if py_file.name.startswith("_"):
                continue
            # Skip .packages directory
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module_fresh(py_file)

                # Scan module for decorated functions
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_workflow_metadata'):
                        metadata = attr._workflow_metadata
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

    Scans workspace directories, imports fresh, and returns the
    function and metadata for the named workflow.

    Args:
        name: Workflow name to find

    Returns:
        Tuple of (function, metadata) or None if not found
    """
    workspace_paths = get_workspace_paths()

    if not workspace_paths:
        return None

    # Clear everything for fresh imports
    _clear_workspace_modules(workspace_paths)
    _clear_all_workspace_pyc(workspace_paths)
    importlib.invalidate_caches()

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module_fresh(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_workflow_metadata'):
                        metadata = attr._workflow_metadata
                        if hasattr(metadata, 'name') and metadata.name == name:
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

    # Clear everything for a clean slate
    _clear_workspace_modules(workspace_paths)
    _clear_all_workspace_pyc(workspace_paths)
    importlib.invalidate_caches()

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module_fresh(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_data_provider_metadata'):
                        metadata = attr._data_provider_metadata
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

    # Clear everything for fresh imports
    _clear_workspace_modules(workspace_paths)
    _clear_all_workspace_pyc(workspace_paths)
    importlib.invalidate_caches()

    for workspace_path in workspace_paths:
        for py_file in workspace_path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if ".packages" in py_file.parts:
                continue

            try:
                module = import_module_fresh(py_file)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_data_provider_metadata'):
                        metadata = attr._data_provider_metadata
                        if hasattr(metadata, 'name') and metadata.name == name:
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

                forms.append(FormMetadata(
                    id=form_id,
                    name=data['name'],
                    linked_workflow=data.get('linked_workflow', ''),
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


def get_forms_by_workflow(workflow_name: str) -> list[FormMetadata]:
    """
    Get all forms that use a specific workflow.

    Args:
        workflow_name: Workflow name to filter by

    Returns:
        List of FormMetadata for forms using this workflow
    """
    all_forms = scan_all_forms()
    return [f for f in all_forms if f.linked_workflow == workflow_name]


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


# ==================== EFFICIENT SINGLE-FILE LOADING ====================
# These use the watchdog index for O(1) lookup, then import just one file


def _import_file_fresh(file_path: Path) -> ModuleType:
    """
    Import a single file fresh with proper cache clearing.

    This function ensures the latest code is always executed by:
    1. Clearing ALL workspace modules from sys.modules (not just the target file)
    2. Deleting .pyc files for the target module
    3. Adding workspace paths to sys.path for relative imports
    4. Invalidating import caches

    Args:
        file_path: Path to the Python file to import

    Returns:
        The imported module
    """
    workspace_paths = get_workspace_paths()

    # Clear ALL workspace modules to ensure dependent modules are also reloaded
    # This is critical for workflows that import from helper modules
    _clear_workspace_modules(workspace_paths)

    module_name = file_path.stem

    # Delete this file's .pyc files
    pycache = file_path.parent / '__pycache__'
    if pycache.exists():
        for pyc in pycache.glob(f'{module_name}.*.pyc'):
            try:
                pyc.unlink()
            except OSError:
                pass

    importlib.invalidate_caches()

    # Add workspace paths to sys.path for relative imports (e.g., from modules.rewst import ...)
    paths_added: list[str] = []
    for wp in workspace_paths:
        wp_str = str(wp)
        if wp_str not in sys.path:
            sys.path.insert(0, wp_str)
            paths_added.append(wp_str)

    try:
        # Fresh import
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not create module spec for {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            if module_name in sys.modules:
                del sys.modules[module_name]
            raise ImportError(f"Failed to import {file_path}: {e}") from e

        return module
    finally:
        # Clean up: remove workspace paths we added to sys.path
        for p in paths_added:
            if p in sys.path:
                sys.path.remove(p)


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
