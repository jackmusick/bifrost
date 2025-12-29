"""
Bifrost CLI

Command-line interface for the Bifrost SDK.

Commands:
  bifrost login   - Authenticate with device authorization flow
  bifrost logout  - Clear stored credentials

Note: This module is standalone and doesn't import the main bifrost package
to avoid dependencies on src.* modules that only exist in the Docker environment.
"""

import asyncio
import inspect
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

# Import credentials module directly (it's standalone)
import bifrost.credentials as credentials
from bifrost.client import BifrostClient


async def refresh_tokens() -> bool:
    """
    Refresh access token using refresh token.

    Uses credentials from credentials file.
    Updates credentials file with new tokens.

    Returns:
        True if refresh successful, False otherwise
    """
    creds = credentials.get_credentials()
    if not creds:
        return False

    api_url = creds["api_url"]
    refresh_token = creds["refresh_token"]

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            response = await client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token}
            )

            if response.status_code != 200:
                return False

            data = response.json()

            # Calculate expiry time (30 minutes from now)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 1800))

            # Save new credentials
            credentials.save_credentials(
                api_url=api_url,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=expires_at.isoformat(),
            )

            return True
    except Exception:
        return False


async def login_flow(api_url: str | None = None, auto_open: bool = True) -> bool:
    """
    Interactive device authorization flow.

    1. Request device code from API
    2. Display user code and verification URL
    3. Open browser automatically (if auto_open=True)
    4. Poll for authorization
    5. Save credentials when authorized

    Args:
        api_url: Bifrost API URL (uses BIFROST_DEV_URL env var if not provided)
        auto_open: Whether to automatically open browser (default: True)

    Returns:
        True if login successful, False otherwise
    """
    # Get API URL
    if not api_url:
        api_url = os.getenv("BIFROST_DEV_URL", "http://localhost:8000")

    api_url = api_url.rstrip("/")

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            # Step 1: Request device code
            response = await client.post("/auth/device/code")
            if response.status_code != 200:
                print(f"Error requesting device code: {response.status_code}", file=sys.stderr)
                return False

            data = response.json()
            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_url = data["verification_url"]
            interval = data.get("interval", 5)

            # Step 2: Display instructions
            full_url = f"{api_url}{verification_url}"
            print(f"\nOpening browser to {full_url}")
            print(f"Enter this code: {user_code}\n")

            # Step 3: Open browser
            if auto_open:
                try:
                    webbrowser.open(full_url)
                except Exception:
                    pass  # Ignore browser open failures

            # Step 4: Poll for authorization
            print("Waiting for authorization", end="", flush=True)
            max_attempts = 60  # 5 minutes max (60 * 5 seconds)
            attempts = 0

            while attempts < max_attempts:
                await asyncio.sleep(interval)
                print(".", end="", flush=True)
                attempts += 1

                poll_response = await client.post(
                    "/auth/device/token",
                    json={"device_code": device_code}
                )

                if poll_response.status_code != 200:
                    print(f"\nError polling for token: {poll_response.status_code}", file=sys.stderr)
                    return False

                poll_data = poll_response.json()

                # Check for error
                if "error" in poll_data:
                    error = poll_data["error"]
                    if error == "authorization_pending":
                        continue  # Keep polling
                    elif error == "expired_token":
                        print("\nDevice code expired. Please try again.", file=sys.stderr)
                        return False
                    elif error == "access_denied":
                        print("\nAuthorization denied.", file=sys.stderr)
                        return False
                    else:
                        print(f"\nUnknown error: {error}", file=sys.stderr)
                        return False

                # Success - we have tokens
                if "access_token" in poll_data:
                    print(" ✓")

                    # Calculate expiry time
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=poll_data.get("expires_in", 1800))

                    # Step 5: Save credentials
                    credentials.save_credentials(
                        api_url=api_url,
                        access_token=poll_data["access_token"],
                        refresh_token=poll_data["refresh_token"],
                        expires_at=expires_at.isoformat(),
                    )

                    # Get user info
                    try:
                        user_response = await client.get(
                            "/auth/me",
                            headers={"Authorization": f"Bearer {poll_data['access_token']}"}
                        )
                        if user_response.status_code == 200:
                            user_data = user_response.json()
                            print(f"Logged in as {user_data.get('email', 'unknown')}\n")
                    except Exception:
                        print("Logged in successfully\n")

                    return True

            print("\nTimeout waiting for authorization.", file=sys.stderr)
            return False

    except Exception as e:
        print(f"\nLogin failed: {e}", file=sys.stderr)
        return False


def logout_flow() -> bool:
    """
    Logout by clearing stored credentials.

    Returns:
        True if credentials were cleared, False if no credentials existed
    """
    creds = credentials.get_credentials()
    if creds:
        credentials.clear_credentials()
        print("Logged out successfully.")
        return True
    else:
        print("No active session found.")
        return False


def main(args: list[str] | None = None) -> int:
    """
    Main CLI entry point.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if args is None:
        args = sys.argv[1:]

    # No args - show help
    if not args:
        print_help()
        return 0

    command = args[0].lower()

    if command in ("help", "-h", "--help"):
        print_help()
        return 0

    if command == "login":
        return handle_login(args[1:])

    if command == "logout":
        return handle_logout(args[1:])

    if command == "run":
        return handle_run(args[1:])

    # Unknown command
    print(f"Unknown command: {command}", file=sys.stderr)
    print_help()
    return 1


def print_help() -> None:
    """Print CLI help message."""
    print("""
Bifrost CLI - Command-line interface for Bifrost SDK

Usage:
  bifrost <command> [options]

Commands:
  run         Run a workflow file with web-based parameter input
  login       Authenticate with device authorization flow
  logout      Clear stored credentials and sign out
  help        Show this help message

Examples:
  bifrost run my_workflow.py
  bifrost run my_workflow.py --workflow greet
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost logout

For more information, visit: https://docs.gobifrost.com
""".strip())


def handle_login(args: list[str]) -> int:
    """
    Handle 'bifrost login' command.

    Args:
        args: Additional arguments (e.g., --url, --no-browser)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    api_url = None
    auto_open = True

    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]

        if arg in ("--url", "-u"):
            if i + 1 >= len(args):
                print("Error: --url requires a value", file=sys.stderr)
                return 1
            api_url = args[i + 1]
            i += 2
        elif arg in ("--no-browser", "-n"):
            auto_open = False
            i += 1
        elif arg in ("--help", "-h"):
            print("""
Usage: bifrost login [options]

Authenticate with Bifrost using device authorization flow.
Opens a browser window where you can enter the displayed code to authorize.

Options:
  --url, -u URL         API URL (default: BIFROST_DEV_URL or http://localhost:8000)
  --no-browser, -n      Don't automatically open browser
  --help, -h            Show this help message

Examples:
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost login --no-browser
""".strip())
            return 0
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 1

    # Run login flow
    success = asyncio.run(login_flow(api_url=api_url, auto_open=auto_open))
    return 0 if success else 1


def handle_logout(args: list[str]) -> int:
    """
    Handle 'bifrost logout' command.

    Args:
        args: Additional arguments (e.g., --help)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost logout

Clear stored credentials and sign out.
This removes the credentials file from your system.

Examples:
  bifrost logout
""".strip())
        return 0

    # Run logout
    logout_flow()
    return 0


def _extract_workflow_parameters(func: Any) -> list[dict[str, Any]]:
    """Extract parameter info from a workflow function signature."""
    params = []
    sig = inspect.signature(func)

    for name, param in sig.parameters.items():
        # Skip *args and **kwargs
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        param_info: dict[str, Any] = {
            "name": name,
            "type": "string",  # default
            "required": param.default is inspect.Parameter.empty,
            "label": name.replace("_", " ").title(),
            "default_value": None if param.default is inspect.Parameter.empty else param.default,
        }

        # Try to determine type from annotation
        if param.annotation is not inspect.Parameter.empty:
            annotation = param.annotation
            type_name = getattr(annotation, "__name__", str(annotation))
            if type_name in ("int", "float", "bool", "str"):
                param_info["type"] = type_name
            elif "list" in type_name.lower():
                param_info["type"] = "list"
            elif "dict" in type_name.lower():
                param_info["type"] = "dict"

        params.append(param_info)

    return params


def handle_run(args: list[str]) -> int:
    """
    Handle 'bifrost run <file>' command.

    Starts a dev session:
    1. Discovers workflows in the file
    2. Registers session with API
    3. Opens browser to DevRun page
    4. Polls for pending execution
    5. Executes workflow locally
    6. Posts results back to API

    Args:
        args: Command arguments [file, --workflow, etc.]

    Returns:
        Exit code (0 for success, 1 for error)
    """
    import importlib.util

    if not args:
        print("Error: No workflow file specified", file=sys.stderr)
        print("Usage: bifrost run <file> [--workflow NAME]", file=sys.stderr)
        return 1

    workflow_file = args[0]
    selected_workflow: str | None = None
    no_browser = False
    inline_params: dict[str, Any] | None = None

    # Parse arguments
    i = 1
    while i < len(args):
        if args[i] in ("--workflow", "-w"):
            if i + 1 >= len(args):
                print("Error: --workflow requires a value", file=sys.stderr)
                return 1
            selected_workflow = args[i + 1]
            i += 2
        elif args[i] in ("--params", "-p"):
            if i + 1 >= len(args):
                print("Error: --params requires a JSON value", file=sys.stderr)
                return 1
            try:
                inline_params = json.loads(args[i + 1])
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON for --params: {e}", file=sys.stderr)
                return 1
            i += 2
        elif args[i] in ("--no-browser", "-n"):
            no_browser = True
            i += 1
        elif args[i] in ("--help", "-h"):
            print_run_help()
            return 0
        else:
            print(f"Unknown option: {args[i]}", file=sys.stderr)
            return 1

    # Check file exists
    if not os.path.isfile(workflow_file):
        print(f"Error: File not found: {workflow_file}", file=sys.stderr)
        return 1

    # Get absolute path
    abs_file_path = os.path.abspath(workflow_file)

    # Load the workflow file
    try:
        spec = importlib.util.spec_from_file_location("workflow_module", abs_file_path)
        if spec is None or spec.loader is None:
            print(f"Error: Cannot load {workflow_file}", file=sys.stderr)
            return 1
        module = importlib.util.module_from_spec(spec)
        sys.modules["workflow_module"] = module
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Error loading workflow file: {e}", file=sys.stderr)
        return 1

    # Find @workflow decorated functions
    workflows: dict[str, Any] = {}
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and hasattr(obj, "_workflow_metadata"):
            workflows[name] = obj

    if not workflows:
        print("Error: No @workflow decorated functions found", file=sys.stderr)
        return 1

    # Validate selected workflow if specified
    if selected_workflow and selected_workflow not in workflows:
        print(
            f"Error: Workflow '{selected_workflow}' not found. Available: {list(workflows.keys())}",
            file=sys.stderr,
        )
        return 1

    # If --params is provided with --workflow, run in standalone mode (no API required)
    if inline_params is not None:
        if not selected_workflow:
            # If only one workflow, use it; otherwise require --workflow
            if len(workflows) == 1:
                selected_workflow = list(workflows.keys())[0]
            else:
                print("Error: --params requires --workflow when multiple workflows exist", file=sys.stderr)
                return 1

        print(f"Running in standalone mode: {selected_workflow}")
        workflow_fn = workflows[selected_workflow]

        try:
            result = asyncio.run(workflow_fn(**inline_params))
            print(f"Result: {json.dumps(result, indent=2, default=str)}")
            return 0
        except Exception as e:
            print(f"Error executing workflow: {e}", file=sys.stderr)
            return 1

    # Ensure user is authenticated (only needed for API-based flow)
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Authentication required: {e}", file=sys.stderr)
        return 1

    # Build workflow info for session registration
    workflow_infos = []
    for name, func in workflows.items():
        metadata = getattr(func, "_workflow_metadata", None)
        description = ""
        if metadata is not None:
            # WorkflowMetadata is a dataclass, access attributes directly
            description = getattr(metadata, "description", "") or ""
        workflow_infos.append({
            "name": name,
            "description": description,
            "parameters": _extract_workflow_parameters(func),
        })

    # Generate session ID
    session_id = str(uuid4())

    # Run the session flow
    return asyncio.run(_run_session_flow(
        client=client,
        session_id=session_id,
        file_path=abs_file_path,
        workflow_infos=workflow_infos,
        workflows=workflows,
        selected_workflow=selected_workflow,
        no_browser=no_browser,
    ))


async def _run_session_flow(
    client: BifrostClient,
    session_id: str,
    file_path: str,
    workflow_infos: list[dict[str, Any]],
    workflows: dict[str, Any],
    selected_workflow: str | None,
    no_browser: bool,
) -> int:
    """
    Run the session-based workflow execution flow.

    1. Register session with API
    2. Open browser to DevRun page
    3. Poll for pending execution
    4. Execute workflow locally
    5. Post results back to API
    """
    api_url = client.api_url

    # Step 1: Register session
    print(f"Registering session with {len(workflow_infos)} workflow(s)...")
    try:
        response = await client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": file_path,
                "workflows": workflow_infos,
                "selected_workflow": selected_workflow,
            },
        )
        if response.status_code not in (200, 201):
            print(f"Error registering session: {response.status_code} - {response.text}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error registering session: {e}", file=sys.stderr)
        return 1

    # Step 2: Open browser to CLI session page
    session_url = f"{api_url}/cli/{session_id}"
    print(f"\nOpening browser to {session_url}")
    print("Select a workflow and enter parameters in the browser, then click 'Continue'.\n")

    if not no_browser:
        try:
            webbrowser.open(session_url)
        except Exception:
            pass  # Ignore browser open failures

    # Step 3: Poll for pending execution
    print("Waiting for execution", end="", flush=True)
    poll_interval = 2  # seconds
    heartbeat_interval = 5  # seconds
    last_heartbeat = time.time()

    while True:
        await asyncio.sleep(poll_interval)
        print(".", end="", flush=True)

        # Send heartbeat periodically
        if time.time() - last_heartbeat > heartbeat_interval:
            try:
                await client.post(f"/api/cli/sessions/{session_id}/heartbeat")
                last_heartbeat = time.time()
            except Exception:
                pass  # Ignore heartbeat failures

        # Poll for pending execution
        try:
            response = await client.get(f"/api/cli/sessions/{session_id}/pending")

            if response.status_code == 204:
                # No pending execution yet
                continue
            elif response.status_code == 200:
                # Execution is pending!
                pending_data = response.json()
                execution_id = pending_data["execution_id"]
                workflow_name = pending_data["workflow_name"]
                params = pending_data["params"]
                print(f" ✓\n\nExecuting workflow: {workflow_name}")
                break
            elif response.status_code == 404:
                print("\n\nSession expired or deleted.", file=sys.stderr)
                return 1
            else:
                print(f"\n\nError polling: {response.status_code}", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"\n\nError polling: {e}", file=sys.stderr)
            return 1

    # Step 4: Execute workflow locally
    workflow_fn = workflows.get(workflow_name)
    if not workflow_fn:
        error_msg = f"Workflow '{workflow_name}' not found in loaded module"
        print(f"Error: {error_msg}", file=sys.stderr)
        await _post_result(client, session_id, execution_id, "Failed", None, error_msg, 0)
        return 1

    start_time = time.time()
    result = None
    error_message = None
    status = "Success"

    try:
        result = await workflow_fn(**params)
        print(f"\nResult: {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        status = "Failed"
        error_message = str(e)
        print(f"\nError: {error_message}", file=sys.stderr)

    duration_ms = int((time.time() - start_time) * 1000)

    # Step 5: Post results back to API
    await _post_result(client, session_id, execution_id, status, result, error_message, duration_ms)

    return 0 if status == "Success" else 1


async def _post_result(
    client: BifrostClient,
    session_id: str,
    execution_id: str,
    status: str,
    result: Any,
    error_message: str | None,
    duration_ms: int,
) -> None:
    """Post execution result back to API."""
    try:
        await client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/result",
            json={
                "status": status,
                "result": result,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "logs": [],  # Could collect logs during execution
            },
        )
        print(f"\nExecution completed ({status})")
    except Exception as e:
        print(f"\nWarning: Failed to post result: {e}", file=sys.stderr)


def print_run_help() -> None:
    """Print run command help."""
    print("""
Usage: bifrost run <file> [options]

Run a workflow file with web-based parameter input or standalone execution.

This command:
1. Discovers @workflow decorated functions in your file
2. Opens a browser to the DevRun page (or runs standalone with --params)
3. Waits for you to select a workflow and enter parameters
4. Executes the workflow locally and shows results

Arguments:
  file                  Python file containing @workflow decorated functions

Options:
  --workflow, -w NAME   Pre-select a workflow (required with --params if multiple workflows)
  --params, -p JSON     Run in standalone mode with JSON parameters (no API required)
  --no-browser, -n      Don't automatically open browser
  --help, -h            Show this help message

Examples:
  bifrost run workflow.py                                                  # Interactive mode with browser
  bifrost run workflow.py --workflow greet                                 # Pre-select workflow
  bifrost run workflow.py --workflow greet --params '{"name": "World"}'    # Standalone mode
  bifrost run workflow.py --no-browser                                     # No auto-open browser
""".strip())


if __name__ == "__main__":
    sys.exit(main())
