"""
Execution context management for Bifrost SDK.

Provides ContextVar-based context propagation from workflow engine to SDK calls.

Usage in workflows:
    from bifrost import context

    @workflow
    async def my_workflow(name: str) -> dict:
        # Access context directly - no need to pass as parameter
        user = context.user_id
        org = context.org_id
        config_value = await context.get_config("my_key")
        return {"greeting": f"Hello {name} from {user}"}
"""

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.context import ExecutionContext

# Context variable for current execution context
# Set by workflow engine before executing user code
_execution_context: ContextVar["ExecutionContext | None"] = ContextVar(
    "bifrost_execution_context", default=None
)


class _ContextProxy:
    """
    Proxy object that retrieves ExecutionContext from the contextvar.

    This allows workflows to access the execution context without
    having it passed as a parameter. The proxy forwards all attribute
    access to the underlying ExecutionContext.

    Example:
        from bifrost import context

        @workflow
        async def my_workflow() -> dict:
            return {"user": context.user_id, "org": context.org_id}
    """

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the underlying ExecutionContext."""
        ctx = _execution_context.get()
        if ctx is None:
            # Raise AttributeError so hasattr() returns False correctly
            # (hasattr only catches AttributeError, not RuntimeError)
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}' - "
                "No active execution context. "
                "This usually means you're trying to access 'context' outside of a workflow execution. "
                "Make sure you're inside a @workflow decorated function."
            )
        return getattr(ctx, name)

    def __repr__(self) -> str:
        ctx = _execution_context.get()
        if ctx is None:
            return "<ExecutionContext: not active>"
        return f"<ExecutionContext: user={ctx.user_id}, scope={ctx.scope}, execution={ctx.execution_id}>"


# The proxy object that workflows will import via `from bifrost import context`
context: "ExecutionContext" = _ContextProxy()  # type: ignore[assignment]


def set_execution_context(ctx: "ExecutionContext") -> None:
    """
    Set the execution context for the current workflow execution.

    Called by the workflow engine before executing user code.

    Args:
        ctx: ExecutionContext with user, org, and permission info
    """
    _execution_context.set(ctx)


def get_execution_context() -> "ExecutionContext":
    """
    Get the current execution context.

    Returns:
        ExecutionContext for the current execution

    Raises:
        RuntimeError: If called outside of a workflow execution context
    """
    ctx = _execution_context.get()
    if ctx is None:
        raise RuntimeError(
            "No execution context found. "
            "The bifrost SDK can only be used within workflow executions."
        )
    return ctx


def clear_execution_context() -> None:
    """
    Clear the execution context.

    Called by the workflow engine after user code execution completes.
    """
    _execution_context.set(None)
