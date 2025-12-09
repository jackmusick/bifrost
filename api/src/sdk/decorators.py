"""
Workflow and Data Provider Decorators

Decorators for attaching metadata to workflows and data providers.
No registration - metadata is stored on the function and discovered dynamically.

Parameter information is derived from function signatures - no @param decorator needed.
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

from src.services.execution.module_loader import DataProviderMetadata, WorkflowMetadata, WorkflowParameter
from src.services.execution.type_inference import extract_parameters_from_signature

logger = logging.getLogger(__name__)


def workflow(
    _func: Callable | None = None,
    *,
    # Identity
    id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    category: str = "General",
    tags: list[str] | None = None,

    # Execution
    execution_mode: Literal["sync", "async"] | None = None,
    timeout_seconds: int = 1800,  # Default 30 minutes

    # Retry
    retry_policy: dict[str, Any] | None = None,

    # Scheduling
    schedule: str | None = None,

    # HTTP Endpoint Configuration
    endpoint_enabled: bool = False,
    allowed_methods: list[str] | None = None,
    disable_global_key: bool = False,
    public_endpoint: bool = False
):
    """
    Decorator for registering workflow functions.

    Parameters are automatically derived from function signatures - no @param needed.

    Usage:
        @workflow
        async def greet_user(name: str, count: int = 1) -> dict:
            '''Greet a user multiple times.'''
            return {"greetings": [f"Hello {name}!" for _ in range(count)]}

        @workflow(category="Admin", tags=["user", "m365"])
        async def onboard_user(email: str, license_type: str = "E3") -> dict:
            '''Onboard a new M365 user.'''
            ...

    Args:
        id: Persistent UUID (written by discovery watcher)
        name: Workflow name (defaults to function name)
        description: Description (defaults to first line of docstring)
        category: Category for organization (default: "General")
        tags: Optional list of tags for filtering
        execution_mode: "sync" | "async" | None (auto-select based on endpoint_enabled)
        timeout_seconds: Max execution time in seconds (default: 1800, max: 7200)
        retry_policy: Dict with retry config
        schedule: Cron expression for scheduled workflows
        endpoint_enabled: Whether to expose as HTTP endpoint
        allowed_methods: HTTP methods allowed for endpoint (default: ["POST"])
        disable_global_key: If True, only workflow-specific API keys work
        public_endpoint: If True, skip authentication for webhooks

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        # Derive name from function name if not provided
        workflow_name = name or func.__name__

        # Derive description from docstring if not provided
        workflow_description = description
        if workflow_description is None and func.__doc__:
            # Use first line of docstring
            workflow_description = func.__doc__.strip().split('\n')[0].strip()
        workflow_description = workflow_description or ""

        # Get tags with default
        workflow_tags = tags if tags is not None else []

        # Get allowed methods with default
        workflow_allowed_methods = allowed_methods if allowed_methods is not None else ["POST"]

        # Apply execution mode defaults
        workflow_execution_mode = execution_mode
        if workflow_execution_mode is None:
            # Endpoints default to sync, regular workflows to async
            workflow_execution_mode = "sync" if endpoint_enabled else "async"

        # Extract parameters from function signature
        param_dicts = extract_parameters_from_signature(func)
        parameters = [
            WorkflowParameter(
                name=p["name"],
                type=p["type"],
                label=p.get("label"),
                required=p["required"],
                default_value=p.get("default_value"),
            )
            for p in param_dicts
        ]

        # Get source file path
        source_file_path = None
        if hasattr(func, '__code__'):
            source_file_path = func.__code__.co_filename

        # Initialize metadata
        metadata = WorkflowMetadata(
            id=id,
            name=workflow_name,
            description=workflow_description,
            category=category,
            tags=workflow_tags,
            execution_mode=workflow_execution_mode,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            schedule=schedule,
            endpoint_enabled=endpoint_enabled,
            allowed_methods=workflow_allowed_methods,
            disable_global_key=disable_global_key,
            public_endpoint=public_endpoint,
            source_file_path=source_file_path,
            parameters=parameters,
            function=func
        )

        # Store metadata on function for dynamic discovery
        func._workflow_metadata = metadata

        logger.debug(
            f"Workflow decorator applied: {workflow_name} "
            f"({len(parameters)} params, execution_mode={workflow_execution_mode})"
        )

        # Return function unchanged (for normal Python execution)
        return func

    # Support both @workflow and @workflow(...) syntax
    if _func is not None:
        # Called as @workflow without parentheses
        return decorator(_func)
    else:
        # Called as @workflow(...) with arguments
        return decorator


def data_provider(
    name: str,
    description: str,
    category: str = "General",
    cache_ttl_seconds: int = 300
):
    """
    Decorator for registering data provider functions.

    Data providers return dynamic options for form fields.
    Parameters are automatically derived from function signatures.

    Usage:
        @data_provider(
            name="get_available_licenses",
            description="Returns available M365 licenses",
            category="m365",
            cache_ttl_seconds=300
        )
        async def get_available_licenses() -> list[dict]:
            ...

    Args:
        name: Unique data provider identifier (snake_case)
        description: Human-readable description
        category: Category for organization (default: "General")
        cache_ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes)

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        # Extract parameters from function signature
        param_dicts = extract_parameters_from_signature(func)
        parameters = [
            WorkflowParameter(
                name=p["name"],
                type=p["type"],
                label=p.get("label"),
                required=p["required"],
                default_value=p.get("default_value"),
            )
            for p in param_dicts
        ]

        # Detect source based on file path
        source = None
        source_file_path = None
        if hasattr(func, '__code__'):
            file_path = func.__code__.co_filename
            source_file_path = file_path
            if '/platform/' in file_path or '\\platform\\' in file_path:
                source = 'platform'
            elif '/home/' in file_path or '\\home\\' in file_path:
                source = 'home'
            elif '/workspace/' in file_path or '\\workspace\\' in file_path:
                source = 'workspace'

        # Create metadata
        metadata = DataProviderMetadata(
            name=name,
            description=description,
            category=category,
            cache_ttl_seconds=cache_ttl_seconds,
            parameters=parameters,
            function=func,
            source=source,
            source_file_path=source_file_path
        )

        # Store metadata on function for dynamic discovery
        func._data_provider_metadata = metadata

        logger.debug(
            f"Data provider decorator applied: {name} "
            f"(cache_ttl={cache_ttl_seconds}s)"
        )

        # Return function unchanged
        return func

    return decorator
