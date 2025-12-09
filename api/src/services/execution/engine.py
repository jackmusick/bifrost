"""
Unified Execution Engine
Single source of truth for all code execution (workflows, scripts, data providers)
"""

import asyncio
import inspect
import logging
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

from src.sdk.context import Caller, ExecutionContext, Organization
from src.sdk.error_handling import WorkflowError
from src.sdk.errors import UserError, WorkflowExecutionException
from src.models.enums import ExecutionStatus
from src.repositories.execution_logs import get_execution_logs_repository
from src.core.cache import prewarm_sdk_cache, cleanup_execution_cache, get_cached_data_provider, cache_data_provider_result

logger = logging.getLogger(__name__)

# Import unified log streaming (Redis Stream + PubSub)
try:
    from bifrost._logging import log_and_broadcast, flush_logs_to_postgres
    STREAM_LOGGING_AVAILABLE = True
except ImportError:
    STREAM_LOGGING_AVAILABLE = False
    log_and_broadcast = None  # type: ignore
    flush_logs_to_postgres = None  # type: ignore

# Import bifrost context management for SDK support
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from bifrost._context import set_execution_context, clear_execution_context
    BIFROST_CONTEXT_AVAILABLE = True
except ImportError:
    logger.warning(
        "Bifrost SDK not available - user workflows cannot use bifrost SDK")
    BIFROST_CONTEXT_AVAILABLE = False

# Import write buffer for SDK writes
try:
    from bifrost._write_buffer import WriteBuffer, set_write_buffer, clear_write_buffer
    WRITE_BUFFER_AVAILABLE = True
except ImportError:
    WRITE_BUFFER_AVAILABLE = False
    WriteBuffer = None  # type: ignore
    set_write_buffer = None  # type: ignore
    clear_write_buffer = None  # type: ignore

# Import cache warming and flush
try:
    from bifrost._sync import flush_pending_changes
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    flush_pending_changes = None  # type: ignore

# Data provider cache is now available via import at top
DATA_PROVIDER_CACHE_AVAILABLE = True


@dataclass
class ExecutionRequest:
    """Request to execute code or a function"""
    execution_id: str
    caller: Caller
    organization: Organization | None
    config: dict[str, Any]

    # Function to execute (preferred - passed directly from discovery)
    func: Any = None                     # The actual callable function

    # Alternative: inline code (mutually exclusive with func)
    code: str | None = None              # Base64 Python code

    # Function name (for display/logging purposes)
    name: str | None = None              # Function name (from metadata)

    # Tags for execution type (e.g., ["workflow"], ["data_provider"])
    tags: list[str] = field(default_factory=list)

    # Execution settings
    timeout_seconds: int = 1800          # Default 30 minutes
    cache_ttl_seconds: int = 300         # For data providers

    # Parameters
    parameters: dict[str, Any] = field(default_factory=dict)

    # Flags
    transient: bool = False              # Don't write to DB
    no_cache: bool = False               # For data providers
    is_platform_admin: bool = False       # For platform admin executions

    # Real-time updates
    broadcaster: Any = None              # WebPubSubBroadcaster for streaming logs


@dataclass
class ExecutionResult:
    """Result of code/function execution"""
    execution_id: str
    status: ExecutionStatus
    result: Any
    duration_ms: int

    # Captured data
    logs: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] | None = None  # Only for inline scripts
    integration_calls: list[dict[str, Any]] = field(default_factory=list)

    # Error details
    error_message: str | None = None
    error_type: str | None = None

    # Data provider specific
    cached: bool = False
    cache_expires_at: str | None = None


async def execute(request: ExecutionRequest) -> ExecutionResult:
    """
    Unified execution engine for all code execution.

    Handles:
    - Direct function execution (request.func set)
    - Inline Python scripts (request.code set)

    Args:
        request: ExecutionRequest with execution details

    Returns:
        ExecutionResult with execution outcome

    Raises:
        ValueError: If neither func nor code provided
    """
    start_time = datetime.utcnow()

    # Resolve what we're executing
    func = None
    is_script = False
    is_data_provider = "data_provider" in request.tags

    if request.func and request.code:
        raise ValueError(
            "Cannot provide both func and code - they are mutually exclusive")

    if request.func:
        # Direct function execution (from discovery)
        func = request.func
        is_script = False
    elif request.code:
        # Executing inline script
        is_script = True
        func = None
    else:
        raise ValueError("Must provide either func or code")

    # Create execution context
    context = ExecutionContext(
        user_id=request.caller.user_id,
        email=request.caller.email,
        name=request.caller.name,
        scope=request.organization.id if request.organization else "GLOBAL",
        organization=request.organization,
        is_platform_admin=request.is_platform_admin,
        is_function_key=False,  # Engine executions are not function key based
        execution_id=request.execution_id,
        _config=request.config
    )

    # Set bifrost SDK context if available
    if BIFROST_CONTEXT_AVAILABLE:
        set_execution_context(context)
        logger.debug(
            f"Set bifrost execution context for execution {request.execution_id}")

    # Pre-warm SDK cache (reads config, oauth, forms, roles from Postgres into Redis)
    if CACHE_AVAILABLE and prewarm_sdk_cache:
        try:
            org_id = request.organization.id if request.organization else None
            await prewarm_sdk_cache(
                execution_id=request.execution_id,
                org_id=org_id,
                user_id=request.caller.user_id,
                is_admin=request.is_platform_admin,
            )
            logger.debug(f"Pre-warmed SDK cache for execution {request.execution_id}")
        except Exception as e:
            # Log but don't fail - SDK will fall back gracefully
            logger.warning(f"Failed to pre-warm SDK cache: {e}")

    # Set up stdout/stderr capture
    # Python's logging writes to stderr by default, so we'll capture it naturally
    logger_output: list[dict[str, Any]] = []
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    # For captured logging (scripts and workflows)
    captured_logs: list[str] = []
    captured_variables: dict[str, Any] = {}  # Initialize to empty dict
    cache_expires_at_str: str | None = None  # For data providers

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Check Redis cache for data providers
            if is_data_provider and not request.no_cache and DATA_PROVIDER_CACHE_AVAILABLE and get_cached_data_provider:
                org_id = request.organization.id if request.organization else None
                cached_result = await get_cached_data_provider(
                    org_id,
                    request.name or "",
                    request.parameters
                )
                if cached_result:
                    return _build_cached_result(
                        request.execution_id,
                        cached_result,
                        start_time
                    )

            # Convert scripts to callables for unified execution
            if is_script:
                assert request.code is not None
                func = _script_to_callable(request.code, request.name or "script")

            # Unified execution path for both workflows and scripts
            assert func is not None

            # Always capture logs AND variables for all executions
            # Filtering based on permissions happens at API response level
            result, captured_variables, captured_logs = await _execute_workflow_with_trace(
                func,
                context,
                request.parameters,
                execution_id=request.execution_id,
                broadcaster=request.broadcaster
            )

            # Cache result to Redis if data provider
            if is_data_provider and DATA_PROVIDER_CACHE_AVAILABLE and cache_data_provider_result:
                org_id = request.organization.id if request.organization else None
                expires_at = await cache_data_provider_result(
                    org_id,
                    request.name or "",
                    request.parameters,
                    result,
                    request.cache_ttl_seconds
                )
                cache_expires_at_str = expires_at.isoformat()

        # Process captured logs (from scripts or workflows with platform admin)
        logger.info(
            f"Processing {len(captured_logs)} captured logs for execution {request.execution_id}")
        for log_line in captured_logs:
            # Parse format: [LEVEL] message
            level = 'info'
            message = log_line

            if log_line.startswith('[INFO]'):
                level = 'info'
                message = log_line[6:].strip()
            elif log_line.startswith('[WARNING]') or log_line.startswith('[WARN]'):
                level = 'warning'
                message = log_line[log_line.index(']')+1:].strip()
            elif log_line.startswith('[ERROR]'):
                level = 'error'
                message = log_line[7:].strip()
            elif log_line.startswith('[DEBUG]'):
                level = 'debug'
                message = log_line[7:].strip()
            elif log_line.startswith('[TRACEBACK]'):
                level = 'traceback'
                message = log_line[11:].strip()

            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message,
                'source': 'script' if is_script else 'workflow'
            })

        # Calculate duration
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Determine execution status based on result
        # If result is a dict with success=false (explicitly false), mark as COMPLETED_WITH_ERRORS
        status = ExecutionStatus.SUCCESS
        if isinstance(result, dict) and result.get('success') is False:
            status = ExecutionStatus.COMPLETED_WITH_ERRORS

        return ExecutionResult(
            execution_id=request.execution_id,
            status=status,
            result=result,
            duration_ms=duration_ms,
            logs=logger_output,
            variables=captured_variables,
            integration_calls=context._integration_calls,
            cached=False,
            cache_expires_at=cache_expires_at_str
        )

    except WorkflowExecutionException as e:
        # Workflow exception with captured variables
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract variables and logs from the wrapper exception
        captured_variables = e.captured_vars
        captured_logs = e.logs

        # Process captured logs
        for log_line in captured_logs:
            level = 'info'
            message = log_line

            if log_line.startswith('[INFO]'):
                level = 'info'
                message = log_line[6:].strip()
            elif log_line.startswith('[WARNING]') or log_line.startswith('[WARN]'):
                level = 'warning'
                message = log_line[log_line.index(']')+1:].strip()
            elif log_line.startswith('[ERROR]'):
                level = 'error'
                message = log_line[7:].strip()
            elif log_line.startswith('[DEBUG]'):
                level = 'debug'
                message = log_line[7:].strip()

            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message,
                'source': 'workflow'
            })

        # Determine error type from original exception
        original_exc = e.original_exception
        error_type = type(original_exc).__name__
        error_message = str(original_exc)

        # Add traceback to logs
        import traceback
        if isinstance(original_exc, UserError):
            # UserError: Show message only (user-facing)
            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'error',
                'message': str(original_exc),
                'source': 'workflow'
            })
        else:
            # Other exceptions: Add full traceback
            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'error',
                'message': f"Execution error: {request.name or 'workflow'}",
                'source': 'workflow'
            })
            tb_lines = traceback.format_exception(type(original_exc), original_exc, original_exc.__traceback__)
            for line in ''.join(tb_lines).split('\n'):
                if line.strip():
                    logger_output.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'level': 'error',
                        'message': line,
                        'source': 'workflow'
                    })

        # Check if it's a WorkflowError
        if isinstance(original_exc, WorkflowError):
            status = ExecutionStatus.FAILED
        else:
            status = ExecutionStatus.FAILED

        return ExecutionResult(
            execution_id=request.execution_id,
            status=status,
            result=None,
            duration_ms=duration_ms,
            logs=logger_output,
            variables=captured_variables,
            integration_calls=context._integration_calls,
            error_message=error_message,
            error_type=error_type
        )

    except WorkflowError as e:
        # Expected workflow error (without variable capture)
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Add traceback to logs
        import traceback
        logger_output.append({
            'timestamp': datetime.utcnow().isoformat(),
            'level': 'error',
            'message': f"Workflow error: {request.name or 'workflow'}",
            'source': 'workflow'
        })
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        for line in ''.join(tb_lines).split('\n'):
            if line.strip():
                logger_output.append({
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': 'error',
                    'message': line,
                    'source': 'workflow'
                })

        return ExecutionResult(
            execution_id=request.execution_id,
            status=ExecutionStatus.FAILED,
            result=None,
            duration_ms=duration_ms,
            logs=logger_output,
            variables=captured_variables,  # Return captured variables even on error
            integration_calls=context._integration_calls,
            error_message=str(e),
            error_type=type(e).__name__
        )

    except Exception as e:
        # Unexpected error
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.error(
            f"Execution error: {request.name or 'script'}",
            extra={
                "execution_id": request.execution_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        # Add traceback to logs
        import traceback
        if isinstance(e, UserError):
            # UserError: Show message only (user-facing)
            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'error',
                'message': str(e),
                'source': 'script' if request.code else 'workflow'
            })
        else:
            # Other exceptions: Add full traceback
            logger_output.append({
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'error',
                'message': f"Execution error: {request.name or 'script'}",
                'source': 'script' if request.code else 'workflow'
            })
            tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
            for line in ''.join(tb_lines).split('\n'):
                if line.strip():
                    logger_output.append({
                        'timestamp': datetime.utcnow().isoformat(),
                        'level': 'error',
                        'message': line,
                        'source': 'script' if request.code else 'workflow'
                    })

        return ExecutionResult(
            execution_id=request.execution_id,
            status=ExecutionStatus.FAILED,
            result=None,
            duration_ms=duration_ms,
            logs=logger_output,
            variables=captured_variables,  # Return captured variables even on error
            integration_calls=context._integration_calls,
            error_message=str(e),
            error_type=type(e).__name__
        )

    finally:
        # Flush pending changes from write buffer to Postgres
        if CACHE_AVAILABLE and flush_pending_changes:
            try:
                changes_count = await flush_pending_changes(request.execution_id)
                if changes_count > 0:
                    logger.info(f"Flushed {changes_count} pending changes for execution {request.execution_id}")
            except Exception as e:
                logger.error(f"Failed to flush pending changes: {e}", exc_info=True)

        # Flush logs from Redis Stream to Postgres
        if STREAM_LOGGING_AVAILABLE and flush_logs_to_postgres:
            try:
                logs_count = await flush_logs_to_postgres(request.execution_id)
                if logs_count > 0:
                    logger.debug(f"Flushed {logs_count} logs to Postgres for execution {request.execution_id}")
            except Exception as e:
                logger.warning(f"Failed to flush logs to Postgres: {e}")

        # Cleanup execution cache (remove temporary Redis keys)
        if CACHE_AVAILABLE and cleanup_execution_cache:
            try:
                await cleanup_execution_cache(request.execution_id)
                logger.debug(f"Cleaned up execution cache for {request.execution_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup execution cache: {e}")

        # Clear bifrost SDK context
        if BIFROST_CONTEXT_AVAILABLE:
            clear_execution_context()
            logger.debug(
                f"Cleared bifrost execution context for execution {request.execution_id}")

        # Clear write buffer context
        if WRITE_BUFFER_AVAILABLE and clear_write_buffer:
            clear_write_buffer()

        # Close broadcaster to prevent resource leaks
        if request.broadcaster is not None:
            try:
                request.broadcaster.close()
                logger.debug(f"Closed broadcaster for execution {request.execution_id}")
            except Exception as e:
                logger.warning(f"Error closing broadcaster: {e}")


def _script_to_callable(code: str, name: str):
    """
    Convert base64-encoded script code to an async callable function.

    This allows scripts to be executed through the same unified execution path
    as workflows, enabling consistent logging, variable capture, and real-time
    streaming.

    The script code is wrapped in an async main() function to enable:
    - Proper variable capture via sys.settrace()
    - Function-level logging that can be filtered
    - Support for both sync and async code

    Args:
        code: Base64-encoded Python code
        name: Script name for logging and error messages

    Returns:
        Async callable function with signature: async def(context, **parameters)
    """
    import base64
    import textwrap

    # Decode base64 code
    script_code = base64.b64decode(code).decode('utf-8')

    # Wrap script code in an async main() function
    # This allows sys.settrace() to capture variables properly
    wrapped_code = f"""async def main():
{textwrap.indent(script_code, '    ')}
"""

    # Compile wrapped script
    compiled_code = compile(wrapped_code, f'<script:{name}>', 'exec')

    async def script_wrapper(context: ExecutionContext, **parameters):
        """
        Async wrapper that executes the script code.

        The script code runs inside an async main() function, allowing:
        - sys.settrace() to capture variables from main's frame
        - await to work in user scripts
        - Proper logging with script-specific logger
        """
        import sys
        import types

        # Create script-specific logger
        script_logger = logging.getLogger(f'script.{name}')
        script_logger.setLevel(logging.DEBUG)
        script_logger.propagate = True

        # Create a custom logging module wrapper that uses our script logger
        # This allows scripts to use logging.info() and have it route to script.{name} logger
        script_logging = types.ModuleType('logging')

        # Copy all attributes from real logging module
        for attr in dir(logging):
            if not attr.startswith('_'):
                setattr(script_logging, attr, getattr(logging, attr))

        # Override the module-level logging functions to use our script logger
        # Using setattr for type-checker compatibility with ModuleType
        setattr(script_logging, 'debug', script_logger.debug)
        setattr(script_logging, 'info', script_logger.info)
        setattr(script_logging, 'warning', script_logger.warning)
        setattr(script_logging, 'error', script_logger.error)
        setattr(script_logging, 'critical', script_logger.critical)
        setattr(script_logging, 'exception', script_logger.exception)
        setattr(script_logging, 'log', script_logger.log)
        setattr(script_logging, 'getLogger', lambda name=None: script_logger)  # Return our logger for any getLogger calls

        # Temporarily replace logging in sys.modules so imports get our wrapper
        original_logging = sys.modules.get('logging')
        sys.modules['logging'] = script_logging

        try:
            # Create execution namespace with bifrost SDK access
            exec_globals = {
                '__name__': '__main__',
                '__file__': f'<script:{name}>',
                'context': context,
                'logging': script_logging,  # Provide wrapped logging module
                'logger': script_logger,  # Also provide logger instance for direct use
                **parameters  # Make parameters available as globals
            }

            # Execute wrapped script (defines main() function)
            exec(compiled_code, exec_globals)

            # Call main() from async context
            await exec_globals['main']()

            return {"status": "completed", "message": "Script executed successfully"}
        finally:
            # Restore original logging module
            if original_logging is not None:
                sys.modules['logging'] = original_logging
            else:
                sys.modules.pop('logging', None)

    # Set function metadata for trace filtering
    script_wrapper.__name__ = name
    script_wrapper.__module__ = f'<script:{name}>'

    return script_wrapper


async def _execute_workflow_with_trace(
    func: Any,
    context: ExecutionContext,
    parameters: dict[str, Any],
    execution_id: str | None = None,
    broadcaster: Any = None
) -> tuple[Any, dict[str, Any], list[str]]:
    """
    Execute a workflow function with variable capture using sys.settrace().

    This is the same approach used for scripts, ensuring consistency.
    Captures all local variables from the function as it executes.
    Streams logs in real-time via SignalR if broadcaster is provided.

    Args:
        func: Workflow function to execute
        context: ExecutionContext
        parameters: Function parameters
        execution_id: Execution ID for Web PubSub broadcasts
        broadcaster: WebPubSubBroadcaster for real-time log streaming

    Returns:
        Tuple of (result, captured_variables, logs)
    """
    captured_vars: dict[str, Any] = {}
    workflow_logs: list[str] = []
    func_name = func.__name__
    log_buffer: list[dict[str, Any]] = []  # Buffer for SignalR broadcasts

    # Thread-safe sequence counter for log ordering in WebPubSub broadcasts
    # Each execution gets its own counter starting at 0
    import threading
    broadcast_sequence_lock = threading.Lock()
    broadcast_sequence_counter = 0

    # Get the workflow's module file path for filtering
    workflow_module_file = func.__code__.co_filename

    # Set up logging capture for the workflow
    class WorkflowLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Always capture TRACEBACK level (admin-only error details)
            is_traceback = record.levelname == "TRACEBACK"

            # Check if this is a script logger (logger name starts with 'script.')
            is_script_log = record.name.startswith('script.')

            # Only capture logs that originate from the workflow's file or workspace
            # This prevents capturing third-party SDK, aiohttp, and infrastructure logs
            # Use basename comparison since dynamically loaded modules may have different path formats
            workflow_basename = os.path.basename(workflow_module_file)
            record_basename = os.path.basename(record.pathname)

            # Also check if it's from workspace directory (for user workflows)
            is_workspace_log = 'workspace' in record.pathname or '/repo/' in record.pathname
            is_workflow_file = record_basename == workflow_basename

            # Don't log from inside the handler to avoid infinite recursion
            # Just filter and process

            if not (is_traceback or is_script_log or is_workflow_file or is_workspace_log):
                return

            # Format: [LEVEL] message
            log_entry = f"[{record.levelname}] {record.getMessage()}"
            workflow_logs.append(log_entry)

            # Real-time log processing - stream to Redis pub/sub for WebSocket delivery
            if execution_id:
                import uuid
                log_id = str(uuid.uuid4())
                timestamp = datetime.utcnow().isoformat() + "Z"

                # Atomically get next sequence number BEFORE spawning thread
                # This ensures sequence assignment order matches log order
                nonlocal broadcast_sequence_counter
                with broadcast_sequence_lock:
                    broadcast_sequence_counter += 1
                    sequence = broadcast_sequence_counter

                log_dict = {
                    "executionLogId": log_id,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "timestamp": timestamp,
                    "sequence": sequence
                }
                log_buffer.append(log_dict)

                # Unified log streaming: Write to Redis Stream + publish to PubSub
                # Redis Stream is the single source of truth for logs
                # - PubSub delivers immediately to WebSocket clients
                # - Background worker persists from Stream to Postgres
                try:
                    if STREAM_LOGGING_AVAILABLE and log_and_broadcast:
                        log_and_broadcast(
                            execution_id=execution_id,
                            level=record.levelname,
                            message=record.getMessage(),
                        )
                    # Fallback: logs are still captured in log_buffer for batch save at end
                except Exception as e:
                    # Log errors but don't fail workflow execution
                    # Real-time updates are non-critical
                    logger.error(
                        f"Failed to stream log (non-fatal): {str(e)}",
                        exc_info=True,
                        extra={"execution_id": execution_id}
                    )

    # Configure logging for workflows
    handler = WorkflowLogHandler()
    handler.setLevel(logging.DEBUG)  # Capture all levels

    # Attach to root logger since workflows use logging.info() which goes to root
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set logger level to capture DEBUG messages
    root_logger.addHandler(handler)

    def remove_circular_refs(obj, seen=None):
        """
        Remove circular references from objects to make them JSON serializable.

        Recursively walks through dicts/lists/tuples and replaces circular references
        with a string marker. Non-serializable objects are converted to string repr.
        """
        if seen is None:
            seen = set()

        obj_id = id(obj)
        if obj_id in seen:
            return "[Circular Reference]"

        seen = seen.copy()  # Copy seen set for this branch
        seen.add(obj_id)

        try:
            if isinstance(obj, dict):
                return {k: remove_circular_refs(v, seen) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                cleaned = [remove_circular_refs(item, seen) for item in obj]
                return cleaned if isinstance(obj, list) else tuple(cleaned)
            elif isinstance(obj, set):
                return [remove_circular_refs(item, seen) for item in obj]
            else:
                # Test if primitive type is JSON serializable
                import json
                json.dumps(obj)
                return obj
        except (TypeError, ValueError):
            # Not serializable - return type name
            return f"<{type(obj).__name__}>"

    # Helper to capture variables from locals
    def capture_variables_from_locals(local_vars: dict[str, Any]) -> None:
        """Capture variables from a frame's local variables, excluding params and internals."""
        param_names = set(parameters.keys()) | {'context', 'self'}

        for k, v in local_vars.items():
            # Skip parameters, private vars, callables, and modules
            if (not k.startswith('_')
                and k not in param_names
                and not callable(v)
                and not isinstance(v, type(sys))):
                # Remove circular references to make JSON serializable
                cleaned_value = remove_circular_refs(v)
                captured_vars[k] = cleaned_value

    exception_to_raise = None

    # Set up trace function to capture variables on return or exception
    def trace_func(frame, event, arg):
        # Trace the workflow function OR script's main() function
        # Scripts wrap their code in an async main() function
        if frame.f_code.co_name not in (func_name, 'main'):
            return None

        # Capture variables when returning or raising exception
        if event in ('return', 'exception'):
            capture_variables_from_locals(frame.f_locals)

        return trace_func

    # Build trace function chain (with existing trace if present, e.g., debugpy)
    existing_trace = sys.gettrace()

    def chained_trace_func(frame, event, arg):
        # Call our trace function first
        trace_func(frame, event, arg)

        # Then call the existing trace function (e.g., debugpy)
        if existing_trace:
            return existing_trace(frame, event, arg)
        return chained_trace_func

    try:
        # Inspect function signature to determine if it expects context parameter
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        # Get accepted parameter names from the function signature
        # This allows us to split form fields into accepted params vs extra params
        accepted_param_names = {p.name for p in params}

        # Check if function accepts **kwargs (VAR_KEYWORD) - if so, all params are accepted
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params
        )

        if has_var_keyword:
            # Function accepts **kwargs, pass everything
            accepted_params = parameters
            extra_params: dict[str, Any] = {}
        else:
            # Split parameters into accepted (match function signature) and extra
            accepted_params = {
                k: v for k, v in parameters.items() if k in accepted_param_names
            }
            extra_params = {
                k: v for k, v in parameters.items() if k not in accepted_param_names
            }

        # Store extra params in context.parameters instead of injecting into globals
        # This avoids race conditions when concurrent workflows share the same module
        # Workflows can access via: context.parameters.get('param_name')
        if extra_params:
            context.parameters = extra_params
            # Also add to captured_vars so they appear in execution details
            for key, value in extra_params.items():
                captured_vars[key] = remove_circular_refs(value)

        # Check if first parameter is for context (by type annotation OR by name as fallback)
        first_param_is_context = False
        if params:
            first_param = params[0]
            annotation = first_param.annotation

            # Check type annotation first (preferred - supports any parameter name)
            if annotation is not inspect.Parameter.empty:
                if annotation is ExecutionContext:
                    first_param_is_context = True
                elif isinstance(annotation, str) and 'ExecutionContext' in annotation:
                    first_param_is_context = True

            # Fallback: check if parameter is named 'context' (for untyped legacy workflows)
            if not first_param_is_context and first_param.name == 'context':
                first_param_is_context = True

        # Define the workflow execution function
        async def _run_workflow_async():
            if first_param_is_context:
                return await func(context, **accepted_params)
            else:
                return await func(**accepted_params)

        # Set up execution context for SDK support
        if BIFROST_CONTEXT_AVAILABLE:
            set_execution_context(context)

        # Initialize write buffer for SDK writes
        if WRITE_BUFFER_AVAILABLE and WriteBuffer and set_write_buffer:
            org_id = context.org_id if context.org_id != "GLOBAL" else None
            buffer = WriteBuffer(
                execution_id=execution_id or "",
                org_id=org_id,
                user_id=context.user_id,
            )
            set_write_buffer(buffer)

        # Set up trace function for variable capture
        sys.settrace(chained_trace_func if existing_trace else trace_func)
        try:
            # Run the workflow directly - isolation is provided by subprocess
            result = await _run_workflow_async()
        finally:
            # Clear trace function
            sys.settrace(None)
            # Clear context
            if BIFROST_CONTEXT_AVAILABLE:
                clear_execution_context()
            # Clear write buffer
            if WRITE_BUFFER_AVAILABLE and clear_write_buffer:
                clear_write_buffer()
    except TypeError as e:
        # Check if this is the "got multiple values" error caused by missing context parameter
        if "got multiple values for argument" in str(e):
            # This likely means the workflow is missing the context parameter
            # The engine passed context as first positional arg, and it got bound to the first param,
            # then the same param name was passed as a keyword arg
            workflow_logger = logging.getLogger(func.__module__)
            workflow_logger.error(
                f"Workflow function '{func_name}' is missing the 'context' parameter. "
                f"All @workflow decorated functions should have 'context: ExecutionContext' "
                f"as the first parameter (or omit it entirely if only using SDK functions)."
            )
            # Wrap and re-raise with helpful message
            captured_vars = {}
            exception_to_raise = WorkflowExecutionException(e, captured_vars, workflow_logs)
            result = None
        else:
            # Different TypeError - handle normally
            raise
    except Exception as e:
        # On exception, extract variables from the traceback
        # Find the workflow/script function frame in the traceback
        tb_frame = e.__traceback__
        while tb_frame:
            frame_name = tb_frame.tb_frame.f_code.co_name
            # Look for workflow function or script's main() function
            if frame_name in (func_name, 'main'):
                # Found the workflow/script function frame - capture variables
                capture_variables_from_locals(tb_frame.tb_frame.f_locals)
                break
            tb_frame = tb_frame.tb_next

        # Log the error through the logger so it gets streamed in real-time
        workflow_logger = logging.getLogger(func.__module__)
        if isinstance(e, UserError):
            # UserError: Log just the message (user-facing) as ERROR
            workflow_logger.error(str(e))
        else:
            # Other exceptions: Log user-facing error, then traceback at TRACEBACK level
            # First log a generic user-facing error message
            workflow_logger.error("An error occurred during execution")

            # Then log the full traceback with custom TRACEBACK level (only visible to admins)
            import traceback
            # Add custom TRACEBACK level (between ERROR=40 and CRITICAL=50)
            TRACEBACK = 45
            logging.addLevelName(TRACEBACK, "TRACEBACK")

            tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
            for line in ''.join(tb_lines).split('\n'):
                if line.strip():
                    workflow_logger.log(TRACEBACK, line)

        # Wrap exception with captured variables and logs
        exception_to_raise = WorkflowExecutionException(e, captured_vars, workflow_logs)
        result = None
    finally:
        # Note: trace function cleanup is handled in _run_workflow_in_thread
        # Clean up the logging handler
        root_logger.removeHandler(handler)
        # Note: Extra params are now stored in context.parameters instead of being
        # injected into func.__globals__, so no cleanup needed here

    # Re-raise exception if one occurred (after cleanup and variable capture)
    if exception_to_raise:
        raise exception_to_raise

    return result, captured_vars, workflow_logs


def _build_cached_result(
    execution_id: str,
    cached_entry: dict[str, Any],
    start_time: datetime
) -> ExecutionResult:
    """
    Build ExecutionResult from cached data provider result.

    Args:
        execution_id: Execution ID
        cached_entry: Cached entry with 'data' and 'expires_at' (string) keys
        start_time: Execution start time

    Returns:
        ExecutionResult with cached data
    """
    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # expires_at comes as ISO string from Redis cache
    expires_at = cached_entry.get('expires_at', '')
    if not expires_at.endswith('Z') and '+' not in expires_at:
        expires_at = expires_at + 'Z'

    return ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.SUCCESS,
        result=cached_entry['data'],
        duration_ms=duration_ms,
        logs=[],
        variables=None,
        integration_calls=[],
        cached=True,
        cache_expires_at=expires_at
    )
