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
import hashlib
import inspect
import json
import os
import pathlib
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

# Import credentials module directly (it's standalone)
import bifrost.credentials as credentials
from bifrost.client import BifrostClient

# Shared constants for file operations
BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2",
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
})

KNOWN_ROOTS = frozenset({"apps", "workflows", "modules", "agents", "forms", ".bifrost"})

# Watch session heartbeat must be < Redis TTL (WATCH_SESSION_TTL_SECONDS in files.py)
WATCH_HEARTBEAT_SECONDS = 60


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
                    print(" OK")

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

    if command == "git":
        return handle_git(args[1:])

    if command == "push":
        return handle_push(args[1:])

    if command == "watch":
        return handle_watch(args[1:])

    if command == "api":
        return handle_api(args[1:])

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
  run         Run a workflow directly (silent JSON output) or interactively via browser
  git         Git source control operations (fetch, status, commit, push, resolve, diff, discard)
  push        Push local files to Bifrost platform
  watch       Watch for file changes and auto-push (requires .bifrost/ workspace)
  api         Generic authenticated API request
  login       Authenticate with device authorization flow
  logout      Clear stored credentials and sign out
  help        Show this help message

Examples:
  bifrost run workflow.py -w greet
  bifrost run workflow.py -w greet -p '{"name": "World"}'
  bifrost run workflow.py -w greet | jq .
  bifrost run workflow.py --interactive
  bifrost git fetch
  bifrost git status
  bifrost git commit -m "sync clients"
  bifrost git push
  bifrost git resolve workflows/billing.py=keep_remote
  bifrost push apps/my-app
  bifrost push apps/my-app --clean
  bifrost watch
  bifrost watch apps/my-app
  bifrost api GET /api/workflows
  bifrost api POST /api/applications/my-app/validate
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


def _run_direct(
    selected_workflow: str,
    workflows: dict[str, Any],
    params: dict[str, Any],
    verbose: bool = False,
) -> int:
    """
    Run a workflow directly in standalone mode.

    Args:
        selected_workflow: Name of the workflow to run
        workflows: Dict of discovered workflow functions
        params: Parameters to pass to the workflow
        verbose: Whether to print status messages

    Returns:
        Exit code (0 for success, 1 for error)
    """
    import uuid

    # Try to authenticate for SDK features (knowledge, ai, etc.)
    # but don't require it — standalone mode can run without API access
    try:
        client = BifrostClient.get_instance(require_auth=True)

        # Set up execution context so context.org_id, context.user_id, etc. work
        try:
            from bifrost._context import set_execution_context

            user_info = client.user
            org_info = client.organization

            class _Org:
                def __init__(self, id, name):
                    self.id = id
                    self.name = name

            class _StandaloneContext:
                def __init__(self, user_id, email, name, scope, organization, execution_id, workflow_name):
                    self.user_id = user_id
                    self.email = email
                    self.name = name
                    self.scope = scope
                    self.organization = organization
                    self.execution_id = execution_id
                    self.workflow_name = workflow_name
                    self.is_platform_admin = False
                    self.is_function_key = False
                    self.parameters = {}
                    self.startup = None
                    self._dynamic_secrets = set()

                @property
                def org_id(self):
                    return self.organization.id if self.organization else None

                @property
                def org_name(self):
                    return self.organization.name if self.organization else None

                def _register_dynamic_secret(self, value):
                    """Register a secret for redaction (standalone mode)."""
                    if value and len(value) >= 4:
                        self._dynamic_secrets.add(value)

                def _collect_secret_values(self):
                    """Return registered secrets (standalone mode)."""
                    return self._dynamic_secrets

            org = _Org(org_info["id"], org_info.get("name", "")) if org_info else None
            scope = org_info["id"] if org_info else "GLOBAL"

            ctx = _StandaloneContext(
                user_id=user_info.get("id", "cli-user"),
                email=user_info.get("email", ""),
                name=user_info.get("name", "CLI User"),
                scope=scope,
                organization=org,
                execution_id=f"standalone-{uuid.uuid4()}",
                workflow_name=selected_workflow,
            )
            set_execution_context(ctx)
        except Exception:
            pass  # Context setup is best-effort

    except (RuntimeError, Exception):
        pass  # Standalone mode works without auth

    if verbose:
        print(f"Running in standalone mode: {selected_workflow}")

    workflow_fn = workflows[selected_workflow]

    try:
        result = asyncio.run(workflow_fn(**params))
        if verbose:
            print(f"Result: {json.dumps(result, indent=2, default=str)}")
        else:
            print(json.dumps(result, default=str))
        return 0
    except Exception as e:
        print(f"Error executing workflow: {e}", file=sys.stderr)
        return 1


def handle_run(args: list[str]) -> int:
    """
    Handle 'bifrost run <file>' command.

    Default behavior: direct execution (silent, pipeable output).
    Use --interactive for browser-based session.

    Args:
        args: Command arguments [file, --workflow, etc.]

    Returns:
        Exit code (0 for success, 1 for error)
    """
    import importlib.util
    import logging

    if not args or args[0] in ("--help", "-h"):
        print_run_help()
        return 0

    workflow_file = args[0]
    selected_workflow: str | None = None
    no_browser = False
    interactive = False
    verbose = False
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
        elif args[i] in ("--interactive", "-i"):
            interactive = True
            i += 1
        elif args[i] in ("--verbose", "-v"):
            verbose = True
            i += 1
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

    # Add current working directory to sys.path for workspace imports
    # This allows workflows to import from their workspace (e.g., `from features.x import y`)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # In non-verbose direct mode, suppress decorator warnings before loading the module
    if not interactive and not verbose:
        logging.getLogger("bifrost.decorators").setLevel(logging.ERROR)

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
        if callable(obj) and hasattr(obj, "_executable_metadata"):
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

    # Direct execution mode (default) — requires --workflow
    if not interactive:
        if not selected_workflow:
            print(
                f"Error: --workflow is required. Available workflows: {list(workflows.keys())}. "
                "Use --interactive for browser UI.",
                file=sys.stderr,
            )
            return 1

        params = inline_params if inline_params is not None else {}
        return _run_direct(selected_workflow, workflows, params, verbose=verbose)

    # Interactive mode (--interactive) — browser-based session
    # Ensure user is authenticated (only needed for API-based flow)
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Authentication required: {e}", file=sys.stderr)
        return 1

    # Build workflow info for session registration
    workflow_infos = []
    for name, func in workflows.items():
        metadata = getattr(func, "_executable_metadata", None)
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
                print(f" OK\n\nExecuting workflow: {workflow_name}")
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


def handle_git(args: list[str]) -> int:
    """
    Handle 'bifrost git <subcommand>' command.

    Dispatches to git subcommands: fetch, status, commit, push, resolve, diff, discard.

    Args:
        args: Subcommand and its arguments

    Returns:
        Exit code
    """
    from .git_commands import (
        EXIT_CLEAN,
        EXIT_ERROR,
        RESOLUTION_MAP,
        run_git_commit,
        run_git_diff,
        run_git_discard,
        run_git_fetch,
        run_git_push,
        run_git_resolve,
        run_git_status,
    )

    if not args or args[0] in ("--help", "-h"):
        _print_git_help()
        return EXIT_CLEAN

    subcmd = args[0].lower()
    sub_args = args[1:]

    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    if subcmd == "fetch":
        return run_git_fetch(client)

    if subcmd == "status":
        return run_git_status(client)

    if subcmd == "commit":
        # Parse -m "message"
        message = None
        i = 0
        while i < len(sub_args):
            if sub_args[i] in ("-m", "--message"):
                if i + 1 >= len(sub_args):
                    print("Error: -m requires a commit message", file=sys.stderr)
                    return EXIT_ERROR
                message = sub_args[i + 1]
                i += 2
            else:
                print(f"Unknown option: {sub_args[i]}", file=sys.stderr)
                return EXIT_ERROR
        if not message:
            print("Error: commit requires -m <message>", file=sys.stderr)
            return EXIT_ERROR
        return run_git_commit(client, message)

    if subcmd == "push":
        return run_git_push(client)

    if subcmd == "resolve":
        # Parse path=strategy pairs
        resolutions: dict[str, str] = {}
        for arg in sub_args:
            parts = arg.split("=", 1)
            if len(parts) != 2 or parts[1] not in RESOLUTION_MAP:
                print(
                    f"Error: invalid resolution '{arg}'. "
                    "Use path=keep_local or path=keep_remote",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            resolutions[parts[0]] = parts[1]
        if not resolutions:
            print("Error: resolve requires at least one path=strategy argument", file=sys.stderr)
            return EXIT_ERROR
        return run_git_resolve(client, resolutions)

    if subcmd == "diff":
        if not sub_args:
            print("Error: diff requires a file path", file=sys.stderr)
            return EXIT_ERROR
        return run_git_diff(client, sub_args[0])

    if subcmd == "discard":
        if not sub_args:
            print("Error: discard requires at least one file path", file=sys.stderr)
            return EXIT_ERROR
        return run_git_discard(client, sub_args)

    print(f"Unknown git subcommand: {subcmd}", file=sys.stderr)
    _print_git_help()
    return EXIT_ERROR


def _print_git_help() -> None:
    """Print git subcommand help."""
    print("""
Usage: bifrost git <subcommand> [options]

Git source control operations for Bifrost platform.

Subcommands:
  fetch                          Regenerate manifest from DB, fetch remote, show status
  status                         Show changed files and commits ahead/behind
  commit -m "message"            Regenerate manifest, stage, preflight, commit
  push                           Pull remote + push local + import entities (deploy)
  resolve path=strategy [...]    Resolve merge conflicts (keep_local or keep_remote)
  diff <path>                    Show file diff
  discard <path> [...]           Discard working tree changes

Typical workflow:
  bifrost git fetch                     # regenerate manifest, see what's changed
  bifrost git commit -m "sync clients"  # commit DB changes to manifest
  bifrost git push                      # pull + push + import to deploy

Examples:
  bifrost git fetch
  bifrost git status
  bifrost git commit -m "add onboarding workflow"
  bifrost git push
  bifrost git resolve workflows/billing.py=keep_remote
  bifrost git diff .bifrost/workflows.yaml
  bifrost git discard workflows/old.py
""".strip())


def _warn_if_git_workspace(target_path: str) -> None:
    """Print a warning if the target path is inside a git repository."""
    p = pathlib.Path(target_path).resolve()
    # Walk up to find .git/
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            print(
                "Warning: This workspace is git-enabled (.git/ detected).\n"
                "  Direct push/watch bypasses git history — platform and local git may diverge.\n"
                "  When done, discard local changes and run:\n"
                "    bifrost git fetch → bifrost git commit -m \"msg\" → bifrost git push → git pull\n",
                file=sys.stderr,
            )
            return


@dataclass
class _PushWatchArgs:
    """Parsed arguments for push/watch commands."""
    local_path: str = "."
    clean: bool = False
    validate: bool = False
    force: bool = False


def _parse_push_watch_args(args: list[str]) -> _PushWatchArgs | None:
    """Parse shared arguments for push/watch commands. Returns None on error."""
    result = _PushWatchArgs()
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--clean":
            result.clean = True
        elif arg == "--validate":
            result.validate = True
        elif arg == "--force":
            result.force = True
        elif arg.startswith("--"):
            print(f"Unknown option: {arg}", file=sys.stderr)
            return None
        elif result.local_path == ".":
            result.local_path = arg
        else:
            print(f"Unexpected argument: {arg}", file=sys.stderr)
            return None
        i += 1
    return result


def handle_push(args: list[str]) -> int:
    """
    Handle 'bifrost push' command.

    Pushes local files to Bifrost _repo/ via the /api/files/push endpoint.
    Gates on repo-status check (git must be configured, no uncommitted platform changes).

    Usage:
      bifrost push <path> [--clean] [--validate]

    Args:
      path: Local directory to push (defaults to ".")
      --clean: Delete remote files not present locally
      --validate: Validate after push (for apps)
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost push [path] [options]

Push local files to Bifrost platform.

Before pushing, checks that:
  1. Git integration is configured
  2. No uncommitted platform changes exist (run 'bifrost git commit' and 'bifrost git push' first)

Arguments:
  path                  Local directory to push (default: current directory)

Options:
  --clean               Delete remote files not present locally
  --validate            Validate after push (for apps)
  --force               Skip repo dirty check
  --help, -h            Show this help message

Use 'bifrost watch' for continuous file watching.

Examples:
  bifrost push apps/my-app
  bifrost push apps/my-app --clean
  bifrost push .
""".strip())
        return 0

    # --watch migration guard before shared parsing
    if args and args[0] == "--watch":
        print("--watch has moved to its own command: bifrost watch", file=sys.stderr)
        return 1

    parsed = _parse_push_watch_args(args)
    if parsed is None:
        return 1

    # Authenticate BEFORE entering asyncio.run() so token refresh works
    # (refresh_tokens() uses asyncio.run() internally, which fails inside a running loop)
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    _warn_if_git_workspace(parsed.local_path)

    try:
        return asyncio.run(_push_with_precheck(
            parsed.local_path, clean=parsed.clean, validate=parsed.validate, watch=False, force=parsed.force,
            client=client,
        ))
    except KeyboardInterrupt:
        return 130


def handle_watch(args: list[str]) -> int:
    """
    Handle 'bifrost watch' command.

    Watches a Bifrost workspace for file changes and auto-pushes.
    Requires the directory to contain a .bifrost/ directory (workspace root).

    Usage:
      bifrost watch [path] [--clean] [--validate] [--force]
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost watch [path] [options]

Watch for file changes and auto-push to Bifrost platform.
Must be run from a Bifrost workspace (directory containing .bifrost/).

Arguments:
  path                  Local directory to watch (default: current directory)

Options:
  --clean               Delete remote files not present locally
  --validate            Validate after push (for apps)
  --force               Skip repo dirty check
  --help, -h            Show this help message

Examples:
  bifrost watch
  bifrost watch apps/my-app
  bifrost watch --clean
""".strip())
        return 0

    parsed = _parse_push_watch_args(args)
    if parsed is None:
        return 1

    # Resolve path and verify .bifrost/ exists
    resolved = pathlib.Path(parsed.local_path).resolve()
    if not resolved.exists() or not resolved.is_dir():
        print(f"Error: {parsed.local_path} is not a valid directory", file=sys.stderr)
        return 1

    bifrost_dir = _find_bifrost_dir(resolved)
    if not bifrost_dir.exists() or not bifrost_dir.is_dir():
        print("Error: not a Bifrost workspace (no .bifrost/ directory found)", file=sys.stderr)
        print("  Run 'bifrost watch' from a directory that contains .bifrost/,", file=sys.stderr)
        print("  or run 'bifrost git commit' and 'bifrost git push' to initialize your workspace first.", file=sys.stderr)
        return 1

    # Authenticate
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    _warn_if_git_workspace(parsed.local_path)

    repo_prefix = _detect_repo_prefix(resolved)
    try:
        return asyncio.run(_push_with_precheck(
            parsed.local_path, clean=parsed.clean, validate=parsed.validate, watch=True, force=parsed.force,
            client=client,
        ))
    except KeyboardInterrupt:
        print("\nStopping watch...", flush=True)
        try:
            client.post_sync("/api/files/watch", json={
                "action": "stop", "prefix": repo_prefix,
            })
        except Exception:
            pass
        return 130


async def _check_repo_status(client: BifrostClient) -> bool:
    """Check if repo is clean enough to push. Returns True if OK to proceed."""
    try:
        response = await client.get("/api/github/repo-status")
        if response.status_code != 200:
            print("Warning: could not check repo status. Proceeding anyway.", file=sys.stderr)
            return True

        data = response.json()

        if not data.get("git_configured"):
            print("Error: Git is not configured. Set up GitHub integration first.", file=sys.stderr)
            print("  Configure at: Settings > GitHub", file=sys.stderr)
            return False

        if data.get("dirty"):
            since = data.get("dirty_since", "unknown")
            print(f"Platform has uncommitted changes (since {since}).", file=sys.stderr)
            print("  Run 'bifrost git commit' to commit platform changes first,", file=sys.stderr)
            print("  then 'git pull' locally to get them.", file=sys.stderr)
            print("  Or use --force to push anyway (platform changes will be overwritten).", file=sys.stderr)
            return False

        return True
    except Exception as e:
        print(f"Warning: could not check repo status: {e}. Proceeding anyway.", file=sys.stderr)
        return True


def _detect_repo_prefix(path: pathlib.Path) -> str:
    """Detect the repo prefix from a local path by finding the first known root directory.

    Examples:
        /home/user/workspace/apps/my-app -> "apps/my-app"
        /home/user/workspace/.bifrost     -> ".bifrost"
        /home/user/workspace/             -> "" (workspace root, no prefix needed)
    """
    for i, part in enumerate(path.parts):
        if part in KNOWN_ROOTS:
            return "/".join(path.parts[i:])

    # Workspace root — files already have correct relative paths
    return ""


def _find_bifrost_dir(local_root: pathlib.Path) -> pathlib.Path:
    """Find the .bifrost/ manifest directory relative to a push root.

    Resolution order:
    1. If local_root IS the .bifrost/ directory, return it
    2. Check local_root/.bifrost/
    3. Walk up parent directories (max 10 levels) looking for .bifrost/
    4. Fallback: return local_root/.bifrost/ (may not exist)
    """
    if local_root.name == ".bifrost":
        return local_root

    candidate = local_root / ".bifrost"
    if candidate.exists() and candidate.is_dir():
        return candidate

    search = local_root.parent
    for _ in range(10):
        candidate = search / ".bifrost"
        if candidate.exists() and candidate.is_dir():
            return candidate
        if search.parent == search:
            break  # Hit filesystem root
        search = search.parent

    return local_root / ".bifrost"  # Fallback (may not exist)


async def _push_with_precheck(
    local_path: str,
    clean: bool = False,
    validate: bool = False,
    watch: bool = False,
    force: bool = False,
    client: "BifrostClient | None" = None,
) -> int:
    """Push files with repo status pre-check and initial pull."""
    if client is None:
        try:
            client = BifrostClient.get_instance(require_auth=True)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Check repo status (unless --force)
    if not force:
        if not await _check_repo_status(client):
            return 1

    # Pull at session start: sync server state to local before pushing
    path = pathlib.Path(local_path).resolve()
    if path.exists() and path.is_dir():
        repo_prefix = _detect_repo_prefix(path)

        if not await _pull_from_server(client, path, repo_prefix):
            return 1

    if watch:
        return await _watch_and_push(local_path, repo_prefix=repo_prefix, clean=clean, validate=validate, client=client)
    else:
        return await _push_files(local_path, repo_prefix=repo_prefix, clean=clean, validate=validate, client=client)


async def _do_push(
    files: dict[str, str],
    delete_missing_prefix: str | None = None,
    extra_headers: dict[str, str] | None = None,
    client: "BifrostClient | None" = None,
) -> dict[str, Any] | None:
    """Push a files dict to the API. Returns the response JSON or None on error."""
    if client is None:
        client = BifrostClient.get_instance(require_auth=True)
    payload: dict[str, Any] = {"files": files}
    if delete_missing_prefix:
        payload["delete_missing_prefix"] = delete_missing_prefix

    try:
        response = await client.post(
            "/api/files/push",
            json=payload,
            headers=extra_headers or {},
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Push failed: {response.status_code}", file=sys.stderr)
            if response.text:
                print(response.text, file=sys.stderr)
            return None
    except Exception as e:
        print(f"Push error: {e}", file=sys.stderr)
        return None


class _WatchState:
    """Mutable shared state between the watcher thread and the async main loop."""

    def __init__(self, base_path: pathlib.Path):
        import threading
        self.base_path = base_path
        self.pending_changes: set[str] = set()
        self.pending_deletes: set[str] = set()
        self.lock = threading.Lock()
        self.writeback_paused = False

    def drain(self) -> tuple[set[str], set[str]]:
        """Atomically drain pending changes and deletes."""
        with self.lock:
            changes = self.pending_changes.copy()
            deletes = self.pending_deletes.copy()
            self.pending_changes.clear()
            self.pending_deletes.clear()
        return changes, deletes

    def requeue(self, changes: set[str], deletes: set[str]) -> None:
        """Put changes back for retry."""
        with self.lock:
            self.pending_changes.update(changes)
            self.pending_deletes.update(deletes)

    def discard_writeback_paths(self, paths: set[str]) -> None:
        """Remove paths generated by server writeback from pending sets."""
        with self.lock:
            self.pending_changes -= paths
            self.pending_deletes -= paths


class _WatchChangeHandler:
    """Watchdog event handler that tracks file changes for push."""

    def __init__(self, state: _WatchState):
        self.state = state

    def _should_skip(self, file_path: str) -> bool:
        p = pathlib.Path(file_path)
        rel_parts = p.relative_to(self.state.base_path).parts
        return _should_skip_path(rel_parts, p.suffix)

    def dispatch(self, event: Any) -> None:
        """Called by watchdog for all events."""
        if self.state.writeback_paused or event.is_directory:
            return

        # For moved/renamed events, track the destination as a change.
        # Don't auto-delete the source — it may be a temp file that was
        # never on the server (editors often write to .tmp then rename).
        if event.event_type == "moved":
            dest = str(getattr(event, "dest_path", ""))
            if not dest or self._should_skip(dest):
                return
            with self.state.lock:
                self.state.pending_changes.add(dest)
                self.state.pending_deletes.discard(dest)
            return

        src = str(event.src_path)
        if self._should_skip(src):
            return
        with self.state.lock:
            if event.event_type == "deleted":
                self.state.pending_deletes.add(src)
                self.state.pending_changes.discard(src)
            elif event.event_type in ("created", "modified", "closed"):
                self.state.pending_changes.add(src)
                self.state.pending_deletes.discard(src)


async def _process_watch_deletes(
    client: "BifrostClient",
    deletes: set[str],
    base_path: pathlib.Path,
    repo_prefix: str,
) -> tuple[int, list[str]]:
    """Process pending file deletions. Returns (count, relative_paths)."""
    deleted_count = 0
    deleted_rels: list[str] = []

    for abs_path_str in deletes:
        abs_p = pathlib.Path(abs_path_str)
        if not abs_p.exists():
            rel = abs_p.relative_to(base_path)
            if str(rel).startswith(".bifrost/") or str(rel).startswith(".bifrost\\"):
                continue
            repo_path = f"{repo_prefix}/{rel}" if repo_prefix else str(rel)
            try:
                resp = await client.post("/api/files/delete", json={
                    "path": repo_path, "location": "workspace", "mode": "cloud",
                })
                if resp.status_code == 204:
                    deleted_count += 1
                    deleted_rels.append(str(rel))
            except Exception as del_err:
                status_code = getattr(getattr(del_err, "response", None), "status_code", None)
                if status_code == 404:
                    deleted_count += 1
                    deleted_rels.append(str(rel))
                else:
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"  [{ts}] Delete error for {rel}: {del_err}", flush=True)

    return deleted_count, deleted_rels


async def _process_watch_batch(
    client: "BifrostClient",
    changes: set[str],
    deletes: set[str],
    base_path: pathlib.Path,
    repo_prefix: str,
    state: _WatchState,
) -> None:
    """Process a batch of file changes and deletions."""
    deleted_count, deleted_rels = await _process_watch_deletes(
        client, deletes, base_path, repo_prefix,
    )

    # Build files dict from changed paths
    push_files: dict[str, str] = {}
    for abs_path_str in changes:
        abs_p = pathlib.Path(abs_path_str)
        if abs_p.exists():
            try:
                content = abs_p.read_text(encoding="utf-8")
                rel = abs_p.relative_to(base_path)
                repo_path = f"{repo_prefix}/{rel}" if repo_prefix else str(rel)
                push_files[repo_path] = content
            except (UnicodeDecodeError, OSError):
                continue

    ts = datetime.now().strftime('%H:%M:%S')
    for repo_path in sorted(push_files):
        print(f"  [{ts}] File changed: {repo_path}", flush=True)
    for rel_path in sorted(deleted_rels):
        print(f"  [{ts}] File deleted: {rel_path}", flush=True)

    if push_files:
        # Local manifest validation
        has_manifest = any(".bifrost/" in k for k in push_files)
        if has_manifest:
            val_errors = _validate_manifest_locally(base_path)
            if val_errors:
                print(f"  [{ts}] Manifest invalid, push skipped:", flush=True)
                for err in val_errors:
                    print(f"    - {err}", flush=True)
                state.requeue(changes, deletes)
                return

        result = await _do_push(
            push_files, extra_headers={"X-Bifrost-Watch": "true"}, client=client,
        )
        if result:
            ts = datetime.now().strftime('%H:%M:%S')
            parts = []
            if result.get("created"):
                parts.append(f"{result['created']} created")
            if result.get("updated"):
                parts.append(f"{result['updated']} updated")
            if deleted_count:
                parts.append(f"{deleted_count} deleted")
            if result.get("unchanged"):
                parts.append(f"{result['unchanged']} unchanged")
            print(f"  [{ts}] Pushed \u2192 {', '.join(parts) if parts else 'no changes'}", flush=True)

            if result.get("errors"):
                for error in result["errors"]:
                    print(f"    Error: {error}", flush=True)
            if result.get("warnings"):
                for warning in result["warnings"]:
                    print(f"    Warning: {warning}", flush=True)

            # Write back server files (pause watcher to avoid re-trigger)
            if result.get("manifest_files") or result.get("modified_files"):
                state.writeback_paused = True
                writeback_paths: set[str] = set()
                try:
                    writeback_paths = _write_back_server_files(base_path, repo_prefix, result)
                finally:
                    await asyncio.sleep(0.2)
                    state.discard_writeback_paths(writeback_paths)
                    state.writeback_paused = False


async def _watch_and_push(
    local_path: str,
    repo_prefix: str,
    clean: bool,
    validate: bool,
    client: "BifrostClient",
) -> int:
    """Watch directory for changes and auto-push."""
    from watchdog.observers import Observer

    path = pathlib.Path(local_path).resolve()
    if not path.exists() or not path.is_dir():
        print(f"Error: {local_path} is not a valid directory", file=sys.stderr)
        return 1

    # Notify server
    try:
        await client.post("/api/files/watch", json={"action": "start", "prefix": repo_prefix})
    except Exception:
        pass

    # Initial full push
    print(f"Initial push of {path}...", flush=True)
    await _push_files(str(path), repo_prefix=repo_prefix, clean=clean, validate=validate, client=client)

    # Set up file watcher
    state = _WatchState(path)
    handler = _WatchChangeHandler(state)
    observer = Observer()
    observer.schedule(handler, str(path), recursive=True)
    observer.start()

    print(f"Watching {path} for changes... (Ctrl+C to stop)", flush=True)

    heartbeat_interval = WATCH_HEARTBEAT_SECONDS
    last_heartbeat = asyncio.get_event_loop().time()
    consecutive_errors = 0

    try:
        while True:
            await asyncio.sleep(0.5)

            # Restart observer if thread died
            if not observer.is_alive():
                print("  \u26a0 File watcher died, attempting restart...", flush=True)
                try:
                    observer = Observer()
                    observer.schedule(handler, str(path), recursive=True)
                    observer.start()
                    print("  \u2713 File watcher restarted", flush=True)
                except Exception as e:
                    print(f"  \u2717 Could not restart file watcher: {e}", file=sys.stderr, flush=True)
                    break

            changes, deletes = state.drain()
            if changes or deletes:
                try:
                    await _process_watch_batch(client, changes, deletes, path, repo_prefix, state)
                    consecutive_errors = 0
                except KeyboardInterrupt:
                    raise
                except Exception as batch_err:
                    consecutive_errors += 1
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"  [{ts}] Push error: {batch_err}", flush=True)
                    state.requeue(changes, deletes)
                    if consecutive_errors >= 10:
                        print(f"  [{ts}] \u26a0 {consecutive_errors} consecutive errors, backing off to 5s", flush=True)
                        await asyncio.sleep(5)

            # Heartbeat
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > heartbeat_interval:
                try:
                    await client.post("/api/files/watch", json={"action": "heartbeat", "prefix": repo_prefix})
                except Exception:
                    pass
                last_heartbeat = now

    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()

    return 0


def _validate_manifest_locally(workspace_dir: "pathlib.Path") -> list[str]:
    """Validate .bifrost/ manifest files locally before pushing.

    Reads ALL manifest files from disk so cross-file references (e.g.
    workflow → organization) are validated against the complete manifest,
    not just the files that changed in this push batch.
    """
    from bifrost.manifest import parse_manifest_dir, validate_manifest, MANIFEST_FILES

    bifrost_dir = workspace_dir / ".bifrost"
    if not bifrost_dir.is_dir():
        return []

    yaml_files: dict[str, str] = {}
    for filename in MANIFEST_FILES.values():
        filepath = bifrost_dir / filename
        if filepath.exists():
            try:
                yaml_files[filename] = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

    if not yaml_files:
        return []

    try:
        manifest = parse_manifest_dir(yaml_files)
    except Exception as e:
        return [f"Failed to parse manifest: {e}"]

    return validate_manifest(manifest)


def _write_back_server_files(
    local_root: pathlib.Path,
    repo_prefix: str,
    result: dict[str, Any],
) -> set[str]:
    """Write manifest_files and modified_files from server response back to local disk.

    Only writes files that actually differ from local content.
    Returns set of absolute paths that were actually written (for watch mode event filtering).
    """
    written_paths: set[str] = set()

    manifest_dir = _find_bifrost_dir(local_root)

    # Write back regenerated .bifrost/ manifest files (only if changed)
    for filename, content in result.get("manifest_files", {}).items():
        local_path = manifest_dir / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        # Skip if local file already has identical content
        if local_path.exists():
            try:
                if local_path.read_text(encoding="utf-8") == content:
                    continue
            except OSError:
                pass
        local_path.write_text(content, encoding="utf-8")
        written_paths.add(str(local_path))

    # Write back modified source files (e.g. forms/agents with resolved refs)
    for repo_path, content in result.get("modified_files", {}).items():
        if repo_prefix and repo_path.startswith(repo_prefix + "/"):
            rel = repo_path[len(repo_prefix) + 1:]
        elif repo_prefix and repo_path.startswith(repo_prefix):
            rel = repo_path[len(repo_prefix):]
        else:
            rel = repo_path
        local_path = local_root / rel
        # Skip if local file already has identical content
        if local_path.exists():
            try:
                if local_path.read_text(encoding="utf-8") == content:
                    continue
            except OSError:
                pass
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        written_paths.add(str(local_path))

    if written_paths:
        print(f"  Wrote back {len(written_paths)} file(s) from server.")

    return written_paths


async def _pull_from_server(
    client: BifrostClient,
    local_root: pathlib.Path,
    repo_prefix: str,
) -> bool:
    """Pull manifest files from server at session start. Returns True if successful."""

    # Compute local manifest hashes
    local_hashes: dict[str, str] = {}
    bifrost_dir = _find_bifrost_dir(local_root)

    if bifrost_dir.exists() and bifrost_dir.is_dir():
        for bf in sorted(bifrost_dir.iterdir()):
            if bf.is_file() and bf.suffix in (".yaml", ".yml"):
                try:
                    content = bf.read_bytes()
                    local_hashes[f".bifrost/{bf.name}"] = hashlib.sha256(content).hexdigest()
                except (OSError, UnicodeDecodeError):
                    continue

    # Call pull endpoint
    try:
        response = await client.post("/api/files/pull", json={
            "prefix": repo_prefix,
            "local_hashes": local_hashes,
        })
        if response.status_code != 200:
            print(f"Warning: pull failed ({response.status_code})", file=sys.stderr)
            return True

        data = response.json()
    except Exception as e:
        print(f"Warning: pull failed: {e}", file=sys.stderr)
        return True

    manifest_files = data.get("manifest_files", {})

    if not manifest_files:
        return True

    # Write manifest files — always authoritative from server
    manifest_dir = bifrost_dir if bifrost_dir.exists() else local_root / ".bifrost"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for filename, content in manifest_files.items():
        local_path = manifest_dir / filename
        local_path.write_text(content, encoding="utf-8")
        written += 1

    print(f"  Updated {written} manifest file(s) from server.")
    return True


def _should_skip_path(rel_parts: tuple[str, ...], suffix: str) -> bool:
    """Check if a relative path should be skipped during push/watch."""
    if any(p.startswith(".") and p != ".bifrost" for p in rel_parts):
        return True
    if any(p in ("__pycache__", "node_modules") for p in rel_parts):
        return True
    if suffix.lower() in BINARY_EXTENSIONS:
        return True
    return False


def _collect_push_files(
    path: pathlib.Path,
    repo_prefix: str,
) -> tuple[dict[str, str], int]:
    """Walk a directory and collect text files for push.

    Returns (files_dict, skipped_count).
    """
    files: dict[str, str] = {}
    skipped = 0

    for file_path in sorted(path.rglob("*")):
        if file_path.is_dir():
            continue
        rel_parts = file_path.relative_to(path).parts
        if any(part.startswith(".") and part != ".bifrost" for part in rel_parts):
            continue
        if file_path.name in ("__pycache__", ".DS_Store", "node_modules"):
            continue
        if any(part == "__pycache__" or part == "node_modules" for part in rel_parts):
            continue
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            skipped += 1
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            rel = file_path.relative_to(path)
            repo_path = f"{repo_prefix}/{rel}" if repo_prefix else str(rel)
            files[repo_path] = content
        except UnicodeDecodeError:
            skipped += 1
            continue

    return files, skipped


def _print_push_summary(result: dict[str, Any]) -> None:
    """Print push result summary."""
    summary_parts = []
    if result.get("created"):
        summary_parts.append(f"{result['created']} created")
    if result.get("updated"):
        summary_parts.append(f"{result['updated']} updated")
    if result.get("deleted"):
        summary_parts.append(f"{result['deleted']} deleted")
    if result.get("unchanged"):
        summary_parts.append(f"{result['unchanged']} unchanged")
    print(f"  {', '.join(summary_parts) if summary_parts else 'No changes'}")

    if result.get("errors"):
        print(f"\n  Errors ({len(result['errors'])}):")
        for error in result["errors"]:
            print(f"    - {error}")

    if result.get("warnings"):
        print(f"\n  Warnings ({len(result['warnings'])}):")
        for warning in result["warnings"]:
            print(f"    - {warning}")


async def _push_files(local_path: str, repo_prefix: str = "", clean: bool = False, validate: bool = False, client: "BifrostClient | None" = None) -> int:
    """Push local directory to Bifrost _repo/."""
    path = pathlib.Path(local_path).resolve()

    if not path.exists():
        print(f"Error: path does not exist: {local_path}", file=sys.stderr)
        return 1

    if not path.is_dir():
        print(f"Error: path is not a directory: {local_path}", file=sys.stderr)
        return 1

    # Walk the directory and collect files
    files, skipped = _collect_push_files(path, repo_prefix)

    if not files:
        print("No files found to push.", file=sys.stderr)
        return 1

    # Local manifest validation before push
    has_manifest = any(".bifrost/" in k or ".bifrost\\" in k for k in files)
    if has_manifest:
        validation_errors = _validate_manifest_locally(path)
        if validation_errors:
            print("Manifest validation errors (push skipped):", file=sys.stderr)
            for err in validation_errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    if repo_prefix:
        print(f"Scanning {len(files)} file(s) in {repo_prefix}/...")
    else:
        print(f"Scanning {len(files)} file(s)...")
    if skipped:
        print(f"  (skipped {skipped} binary file(s))")

    # Push files via _do_push helper
    delete_prefix = repo_prefix if clean else None
    result = await _do_push(files, delete_missing_prefix=delete_prefix, client=client)

    if result is None:
        return 1

    # Print summary
    _print_push_summary(result)

    # Write back manifest files and modified files from server response
    if result.get("manifest_files") or result.get("modified_files"):
        _write_back_server_files(path, repo_prefix, result)

    if result.get("manifest_applied"):
        print("  Manifest applied to platform.")

    # Validate if requested
    if validate and repo_prefix:
        # Extract slug (last path component) — server 404s gracefully if not an app
        slug = repo_prefix.rstrip("/").rsplit("/", 1)[-1]
        print(f"\nValidating app '{slug}'...")

        try:
            if client is None:
                client = BifrostClient.get_instance(require_auth=True)
            # Look up app by slug
            val_response = await client.get(f"/api/applications/{slug}")
            if val_response.status_code == 200:
                app_data = val_response.json()
                app_id = app_data.get("id")
                if app_id:
                    val_result = await client.post(f"/api/applications/{app_id}/validate")
                    if val_result.status_code == 200:
                        val_data = val_result.json()
                        if val_data.get("errors"):
                            print(f"  Errors ({len(val_data['errors'])}):")
                            for err in val_data["errors"]:
                                print(f"    - [{err.get('severity', 'error')}] {err.get('message', err)}")
                        elif val_data.get("warnings"):
                            print(f"  Warnings ({len(val_data['warnings'])}):")
                            for warn in val_data["warnings"]:
                                print(f"    - {warn.get('message', warn)}")
                        else:
                            print("  No issues found.")
                    else:
                        print(f"  Validation failed: {val_result.status_code}", file=sys.stderr)
            else:
                print(f"  Could not find app '{slug}' for validation", file=sys.stderr)
        except Exception as e:
            print(f"  Validation error: {e}", file=sys.stderr)

    return 0 if not result.get("errors") else 1


def handle_api(args: list[str]) -> int:
    """bifrost api <METHOD> <endpoint> [json-body]"""
    if not args or args[0] in ("--help", "-h"):
        print("""
Usage: bifrost api <METHOD> <endpoint> [json-body]

Make an authenticated API request to Bifrost.

Arguments:
  METHOD                HTTP method (GET, POST, PUT, PATCH, DELETE)
  endpoint              API endpoint path (e.g., /api/workflows)
  json-body             Optional JSON body (inline or @filename)

Examples:
  bifrost api GET /api/workflows
  bifrost api GET /api/github/repo-status
  bifrost api POST /api/applications/my-app/validate
  bifrost api POST /api/files/push @payload.json
""".strip())
        return 0 if args and args[0] in ("--help", "-h") else 1

    if len(args) < 2:
        print("Usage: bifrost api <METHOD> <endpoint> [json-body]", file=sys.stderr)
        return 1

    method = args[0].upper()
    endpoint = args[1]
    body = None

    if len(args) > 2:
        import pathlib
        raw = args[2]
        # Support @filename for reading body from file
        if raw.startswith("@"):
            try:
                body = json.loads(pathlib.Path(raw[1:]).read_text())
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                return 1
        else:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e}", file=sys.stderr)
                return 1

    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        print(f"Unsupported method: {method}", file=sys.stderr)
        return 1

    # Authenticate BEFORE entering asyncio.run() so token refresh works
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return asyncio.run(_api_request(method, endpoint, body, client=client))


async def _api_request(method: str, endpoint: str, body: Any | None, client: "BifrostClient | None" = None) -> int:
    if client is None:
        try:
            client = BifrostClient.get_instance(require_auth=True)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    http_fn = getattr(client, method.lower())
    kwargs: dict[str, Any] = {}
    if body is not None:
        kwargs["json"] = body

    try:
        response = await http_fn(endpoint, **kwargs)
        # Pretty-print response
        try:
            data = response.json()
            print(json.dumps(data, indent=2, default=str))
        except Exception:
            print(response.text)
        return 0 if response.status_code < 400 else 1
    except httpx.ConnectError:
        print("Error: could not connect to Bifrost API.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def print_run_help() -> None:
    """Print run command help."""
    print("""
Usage: bifrost run <file> -w <workflow> [options]

Run a workflow directly. Output is raw JSON (pipeable). Use --interactive for browser UI.

Arguments:
  file                  Python file containing @workflow decorated functions

Options:
  --workflow, -w NAME   Workflow to run (required in direct mode)
  --params, -p JSON     JSON parameters to pass to the workflow (default: {})
  --verbose, -v         Show status messages (e.g., "Running...", "Result:")
  --interactive, -i     Open browser-based session instead of direct execution
  --no-browser, -n      Don't auto-open browser (only with --interactive)
  --help, -h            Show this help message

Examples:
  bifrost run workflow.py -w greet                                         # Direct execution, raw JSON output
  bifrost run workflow.py -w greet -p '{"name": "World"}'                  # With parameters
  bifrost run workflow.py -w greet -v                                      # Verbose output
  bifrost run workflow.py -w greet | jq .                                  # Pipe to jq
  bifrost run workflow.py --interactive                                    # Browser-based session
""".strip())


if __name__ == "__main__":
    sys.exit(main())
