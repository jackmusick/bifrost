"""
Bifrost SDK Decorators

Workflow and data provider decorators for SDK usage.
These are compatible with the main Bifrost decorators.
"""

from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def workflow(
    name: str | None = None,
    description: str | None = None,
    category: str = "General",
    schedule: str | None = None,
    tags: list[str] | None = None,
    parameters: list[dict] | None = None,
    timeout_seconds: int = 1800,
    endpoint_enabled: bool = False,
    allowed_methods: list[str] | None = None,
    execution_mode: str = "sync",
) -> Callable[[F], F]:
    """
    Decorator to define a workflow function.

    Args:
        name: Workflow name (defaults to function name)
        description: Workflow description
        category: Category for grouping workflows
        schedule: Cron expression for scheduled execution
        tags: Tags for filtering
        parameters: Parameter schema for UI/CLI prompting
        timeout_seconds: Execution timeout
        endpoint_enabled: Enable HTTP endpoint
        allowed_methods: HTTP methods for endpoint
        execution_mode: sync or async

    Example:
        @workflow(
            name="my-workflow",
            description="Does something useful",
            parameters=[
                {"name": "input", "type": "string", "required": True}
            ]
        )
        async def my_workflow(input: str):
            return f"Processed: {input}"
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Attach metadata for discovery
        setattr(wrapper, "_workflow_metadata", {
            "name": name or func.__name__.replace("_", "-"),
            "description": description or func.__doc__ or "",
            "category": category,
            "schedule": schedule,
            "tags": tags or [],
            "parameters": parameters or [],
            "timeout_seconds": timeout_seconds,
            "endpoint_enabled": endpoint_enabled,
            "allowed_methods": allowed_methods or ["POST"],
            "execution_mode": execution_mode,
        })

        return wrapper  # type: ignore

    return decorator


def data_provider(
    name: str | None = None,
    description: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator to define a data provider function.

    Data providers are used by form fields to populate dynamic options.

    Args:
        name: Provider name (defaults to function name)
        description: Provider description

    Example:
        @data_provider(name="get-users")
        async def get_users():
            return [
                {"value": "1", "label": "User 1"},
                {"value": "2", "label": "User 2"},
            ]
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        setattr(wrapper, "_data_provider_metadata", {
            "name": name or func.__name__.replace("_", "-"),
            "description": description or func.__doc__ or "",
        })

        return wrapper  # type: ignore

    return decorator
