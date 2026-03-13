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
import base64
import hashlib
import inspect
import json
import os
import pathlib
import shutil
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pathspec
from uuid import uuid4

import httpx

# Import credentials module directly (it's standalone)
import bifrost.credentials as credentials
from bifrost.client import BifrostClient

# Default ignore patterns applied even without a .gitignore file.
# .bifrost/ is always force-included via negation.
_DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    "__pycache__/",
    ".ruff_cache/",
    "node_modules/",
    ".venv/",
    "venv/",
    ".DS_Store",
    "*.pyc",
]

_FORCE_INCLUDE_PATTERNS = [
    "!.bifrost/",
]


# ---------------------------------------------------------------------------
# Shared CLI utilities
# ---------------------------------------------------------------------------


@dataclass
class _CliColors:
    """ANSI color codes, empty strings when not a TTY."""
    green: str
    yellow: str
    red: str
    dim: str
    reset: str


def _get_colors() -> _CliColors:
    """Return ANSI color codes based on whether stdout is a TTY."""
    use_color = sys.stdout.isatty()
    return _CliColors(
        green="\033[32m" if use_color else "",
        yellow="\033[33m" if use_color else "",
        red="\033[31m" if use_color else "",
        dim="\033[2m" if use_color else "",
        reset="\033[0m" if use_color else "",
    )


def _is_bifrost_path(path: str) -> bool:
    """Check if a path refers to a .bifrost/ manifest directory."""
    return ".bifrost" in path.replace("\\", "/").split("/")


def _separate_manifest_files(files: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Split a files dict into (bifrost_manifest_files, regular_files)."""
    bifrost: dict[str, str] = {}
    regular: dict[str, str] = {}
    for repo_path, content in files.items():
        if _is_bifrost_path(repo_path):
            bifrost[repo_path] = content
        else:
            regular[repo_path] = content
    return bifrost, regular


def _format_count_summary(
    counts: dict[str, int],
    labels: dict[str, tuple[str, str]],
    cc: _CliColors,
    separator: str = ", ",
) -> str:
    """Format a colored count summary string.

    Args:
        counts: Dict of count_key -> count_value
        labels: Dict of count_key -> (color_attr, label_template) where
                label_template may use {n} for count and {s} for plural suffix
        cc: CLI colors instance
        separator: String to join parts with

    Returns:
        Formatted summary string, or empty string if no counts > 0.
    """
    parts: list[str] = []
    for key, (color_attr, label_tpl) in labels.items():
        n = counts.get(key, 0)
        if n:
            color = getattr(cc, color_attr, "")
            s = "s" if n != 1 else ""
            parts.append(f"{color}{label_tpl.format(n=n, s=s)}{cc.reset}")
    return separator.join(parts)


def _build_file_filter(local_root: pathlib.Path) -> "pathspec.PathSpec":
    """Build a gitignore-style file filter for the given directory.

    Loads .gitignore if present, otherwise uses sensible defaults.
    Always force-includes .bifrost/ regardless of ignore rules.
    """
    import pathspec

    # Always start with defaults (.git/, __pycache__, etc.) — .gitignore
    # never lists .git/ because git handles it implicitly, but we need it.
    lines = list(_DEFAULT_IGNORE_PATTERNS)

    gitignore_path = local_root / ".gitignore"
    if gitignore_path.is_file():
        lines.extend(gitignore_path.read_text(encoding="utf-8").splitlines())

    # Always force-include .bifrost/
    lines.extend(_FORCE_INCLUDE_PATTERNS)

    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


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

    if command == "pull":
        return handle_pull(args[1:])

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
  pull        Pull files from Bifrost platform to local directory
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
  bifrost push apps/my-app --mirror
  bifrost pull
  bifrost pull apps/my-app
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
            warn = "\033[33m⚠ Warning: Git is enabled in the platform.\033[0m" if sys.stderr.isatty() else "Warning: Git is enabled in the platform."
            print(warn, file=sys.stderr)
            return


@dataclass
class _PushWatchArgs:
    """Parsed arguments for push/watch commands."""
    local_path: str = "."
    mirror: bool = False
    validate: bool = False
    force: bool = False


def _parse_push_watch_args(args: list[str]) -> _PushWatchArgs | None:
    """Parse shared arguments for push/watch commands. Returns None on error."""
    result = _PushWatchArgs()
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--mirror":
            result.mirror = True
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

    Pushes local files to Bifrost _repo/ via per-file writes and manifest import.

    Usage:
      bifrost push <path> [--mirror] [--validate]

    Args:
      path: Local directory to push (defaults to ".")
      --mirror: Make target match source exactly (delete files not present locally)
      --validate: Validate after push (for apps)
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost push [path] [options]

Push local files to Bifrost platform.

Arguments:
  path                  Local directory to push (default: current directory)

Options:
  --mirror              Make target match source exactly (delete files not present locally)
  --validate            Validate after push (for apps)
  --force               Skip confirmation prompts
  --help, -h            Show this help message

Use 'bifrost watch' for continuous file watching.

Examples:
  bifrost push apps/my-app
  bifrost push apps/my-app --mirror
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
            parsed.local_path, mirror=parsed.mirror, validate=parsed.validate, watch=False, force=parsed.force,
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
      bifrost watch [path] [--mirror] [--validate] [--force]
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost watch [path] [options]

Watch for file changes and auto-push to Bifrost platform.
Must be run from a Bifrost workspace (directory containing .bifrost/).

Arguments:
  path                  Local directory to watch (default: current directory)

Options:
  --mirror              Make target match source exactly (delete files not present locally)
  --validate            Validate after push (for apps)
  --force               Skip repo dirty check
  --help, -h            Show this help message

Examples:
  bifrost watch
  bifrost watch apps/my-app
  bifrost watch --mirror
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
            parsed.local_path, mirror=parsed.mirror, validate=parsed.validate, watch=True, force=parsed.force,
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


def handle_pull(args: list[str]) -> int:
    """
    Handle 'bifrost pull' command.

    Pulls files from Bifrost platform to local directory. Downloads code files
    from S3 and regenerated manifests from DB. Only transfers changed files
    by comparing local MD5 hashes against S3 ETags.

    Usage:
      bifrost pull [path] [--mirror] [--force]

    Args:
      path: Local directory to pull into (defaults to ".")
      --mirror: Make local match platform exactly (delete local files not on platform)
      --force: Skip overwrite confirmation prompts
    """
    if args and args[0] in ("--help", "-h"):
        print("""
Usage: bifrost pull [path] [options]

Pull files from Bifrost platform to local directory.

Downloads changed code files and updated manifests. Uses MD5/ETag
comparison to only transfer files that differ from local state.

Arguments:
  path                  Local directory to pull into (default: current directory)

Options:
  --mirror              Make local match platform exactly (delete local files not on platform)
  --force               Skip overwrite confirmation prompts
  --help, -h            Show this help message

Overwrite safety:
  - Files with uncommitted git changes trigger a warning
  - Git-tracked files can be recovered from history
  - Non-git files warn about irreversible loss
  - Use --force to skip all prompts

Examples:
  bifrost pull
  bifrost pull apps/my-app
  bifrost pull --force
""".strip())
        return 0

    # Parse args
    local_path = "."
    force = False
    mirror = False
    for arg in args:
        if arg == "--force":
            force = True
        elif arg == "--mirror":
            mirror = True
        elif arg.startswith("--"):
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 1
        elif local_path == ".":
            local_path = arg
        else:
            print(f"Unexpected argument: {arg}", file=sys.stderr)
            return 1

    # Authenticate
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    resolved = pathlib.Path(local_path).resolve()
    if not resolved.exists() or not resolved.is_dir():
        print(f"Error: {local_path} is not a valid directory", file=sys.stderr)
        return 1

    repo_prefix = _detect_repo_prefix(resolved)

    print(f"Pulling from platform{f' (prefix: {repo_prefix})' if repo_prefix else ''}...")

    try:
        success = asyncio.run(_pull_from_server(
            client, resolved, repo_prefix,
            include_code_files=True, force=force, mirror=mirror,
        ))
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nPull cancelled.")
        return 130



def _detect_repo_prefix(path: pathlib.Path) -> str:
    """Detect the repo prefix from a local path by finding the .bifrost/ directory.

    Anchors on the .bifrost/ directory — its parent is the workspace root.
    Everything relative to that root is the repo prefix.

    Examples:
        /home/user/workspace/apps/my-app -> "apps/my-app"
        /home/user/workspace/.bifrost     -> ".bifrost"
        /home/user/workspace/             -> "" (workspace root, no prefix needed)
    """
    # Find .bifrost/ directory — its parent is the workspace root
    bifrost_dir = _find_bifrost_dir(path)
    if bifrost_dir.exists():
        workspace_root = bifrost_dir.parent
        try:
            relative = path.relative_to(workspace_root)
            prefix = str(relative)
            return "" if prefix == "." else prefix
        except ValueError:
            pass

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
    mirror: bool = False,
    validate: bool = False,
    watch: bool = False,
    force: bool = False,
    client: "BifrostClient | None" = None,
) -> int:
    """Push files with repo status pre-check."""
    if client is None:
        try:
            client = BifrostClient.get_instance(require_auth=True)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Detect repo prefix for watch mode
    path = pathlib.Path(local_path).resolve()
    repo_prefix = ""
    if path.exists() and path.is_dir():
        repo_prefix = _detect_repo_prefix(path)

    if watch:
        return await _watch_and_push(local_path, repo_prefix=repo_prefix, mirror=mirror, validate=validate, client=client)
    else:
        return await _push_files(local_path, repo_prefix=repo_prefix, mirror=mirror, validate=validate, force=force, client=client)


class _WatchState:
    """Mutable shared state between the watcher thread and the async main loop."""

    def __init__(self, base_path: pathlib.Path):
        import threading
        self.base_path = base_path
        self.pending_changes: set[str] = set()
        self.pending_deletes: set[str] = set()
        self.lock = threading.Lock()
        self.writeback_paused = False
        # Unique session ID for filtering own changes from WebSocket events
        self.session_id: str = str(uuid4())
        # Incoming changes from other sessions (populated by WebSocket listener)
        self.incoming_files: list[tuple[list[str], str]] = []      # (paths, user_name)
        self.incoming_deletes: list[tuple[list[str], str]] = []     # (paths, user_name)
        self.incoming_entities: list[dict[str, Any]] = []           # entity_change events

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

    def queue_incoming_files(self, paths: list[str], user_name: str) -> None:
        """Queue incoming file changes from another session."""
        with self.lock:
            self.incoming_files.append((paths, user_name))

    def queue_incoming_deletes(self, paths: list[str], user_name: str) -> None:
        """Queue incoming file deletes from another session."""
        with self.lock:
            self.incoming_deletes.append((paths, user_name))

    def queue_entity_change(self, event: dict[str, Any]) -> None:
        """Queue incoming entity change from another session."""
        with self.lock:
            self.incoming_entities.append(event)

    def drain_incoming(self) -> tuple[
        list[tuple[list[str], str]],
        list[tuple[list[str], str]],
        list[dict[str, Any]],
    ]:
        """Atomically drain all incoming queues."""
        with self.lock:
            files = self.incoming_files.copy()
            deletes = self.incoming_deletes.copy()
            entities = self.incoming_entities.copy()
            self.incoming_files.clear()
            self.incoming_deletes.clear()
            self.incoming_entities.clear()
        return files, deletes, entities


class _WatchChangeHandler:
    """Watchdog event handler that tracks file changes for push."""

    def __init__(self, state: _WatchState):
        self.state = state
        self._spec = _build_file_filter(state.base_path)

    def _should_skip(self, file_path: str) -> bool:
        p = pathlib.Path(file_path)
        rel = str(p.relative_to(self.state.base_path))
        return _should_skip_path(rel, self._spec)

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
    session_id: str | None = None,
) -> tuple[int, list[str]]:
    """Process pending file deletions. Returns (count, relative_paths)."""
    deleted_count = 0
    deleted_rels: list[str] = []
    extra_headers: dict[str, str] = {}
    if session_id:
        extra_headers["X-Bifrost-Watch-Session"] = session_id

    for abs_path_str in deletes:
        abs_p = pathlib.Path(abs_path_str)
        if not abs_p.exists():
            rel = abs_p.relative_to(base_path)
            if _is_bifrost_path(str(rel)):
                continue
            repo_path = f"{repo_prefix}/{rel}" if repo_prefix else str(rel)
            try:
                resp = await client.post("/api/files/delete", json={
                    "path": repo_path, "location": "workspace", "mode": "cloud",
                }, headers=extra_headers)
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
        client, deletes, base_path, repo_prefix, session_id=state.session_id,
    )

    # Build files dict from changed paths
    push_files: dict[str, str] = {}
    for abs_path_str in changes:
        abs_p = pathlib.Path(abs_path_str)
        if abs_p.exists():
            try:
                raw = abs_p.read_bytes()
                content = base64.b64encode(raw).decode("ascii")
                rel = abs_p.relative_to(base_path)
                repo_path = f"{repo_prefix}/{rel}" if repo_prefix else str(rel)
                push_files[repo_path] = content
            except OSError:
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

        # Separate .bifrost/ manifest files from regular files
        bifrost_watch_files, regular_watch_files = _separate_manifest_files(push_files)

        # Upload regular files via per-file writes
        watch_created = 0
        watch_errors: list[str] = []
        for rp, c in regular_watch_files.items():
            try:
                resp = await client.post("/api/files/write", json={
                    "path": rp,
                    "content": c,
                    "mode": "cloud",
                    "location": "workspace",
                    "binary": True,
                }, headers={
                    "X-Bifrost-Watch": "true",
                    "X-Bifrost-Watch-Session": state.session_id,
                })
                if resp.status_code == 204:
                    watch_created += 1
                else:
                    watch_errors.append(f"{rp}: HTTP {resp.status_code}")
            except Exception as e:
                watch_errors.append(f"{rp}: {e}")

        # Import manifest if .bifrost/ files changed
        watch_warnings: list[str] = []
        manifest_result: dict[str, Any] = {}
        if bifrost_watch_files:
            try:
                import_payload: dict[str, Any] = {
                    "files": bifrost_watch_files,
                    "delete_removed_entities": True,
                }
                resp = await client.post("/api/files/manifest/import", json=import_payload, headers={
                    "X-Bifrost-Watch-Session": state.session_id,
                })
                if resp.status_code == 200:
                    manifest_result = resp.json()
                    watch_warnings = manifest_result.get("warnings", [])
                else:
                    watch_warnings.append(f"Manifest import failed: HTTP {resp.status_code}")
            except Exception as e:
                watch_warnings.append(f"Manifest import failed: {e}")

        ts = datetime.now().strftime('%H:%M:%S')
        parts = []
        total_written = watch_created
        if total_written:
            parts.append(f"{total_written} written")
        if deleted_count:
            parts.append(f"{deleted_count} deleted")
        if bifrost_watch_files:
            parts.append("manifest imported")
        print(f"  [{ts}] Pushed \u2192 {', '.join(parts) if parts else 'no changes'}", flush=True)

        if watch_errors:
            for error in watch_errors:
                print(f"    Error: {error}", flush=True)
        if watch_warnings:
            for warning in watch_warnings:
                print(f"    Warning: {warning}", flush=True)
        deleted_entities = manifest_result.get("deleted_entities", [])
        if deleted_entities:
            print(f"  [{ts}] Removed {len(deleted_entities)} entity(ies):", flush=True)
            for de in deleted_entities:
                print(f"    - {de}", flush=True)

        # Write back server files (pause watcher to avoid re-trigger)
        result = manifest_result
        if result.get("manifest_files") or result.get("modified_files"):
            state.writeback_paused = True
            writeback_paths: set[str] = set()
            try:
                writeback_paths = _write_back_server_files(base_path, repo_prefix, result)
            finally:
                await asyncio.sleep(0.2)
                state.discard_writeback_paths(writeback_paths)
                state.writeback_paused = False


async def _ws_listener(state: _WatchState, api_url: str, token: str) -> None:
    """Listen for file-activity WebSocket events from other sessions."""
    try:
        import websockets
    except ImportError:
        print("  ⚠ 'websockets' not installed — bidirectional sync disabled", flush=True)
        print("  Reinstall CLI: pipx install --force <url>", flush=True)
        return

    ws_url = api_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url += "/ws/connect?channels=file-activity"
    backoff = 1.0
    connected_once = False

    while True:
        try:
            async with websockets.connect(
                ws_url,
                additional_headers={"Authorization": f"Bearer {token}"},
            ) as ws:
                backoff = 1.0  # Reset on successful connect
                if not connected_once:
                    print("  WebSocket connected — listening for remote changes", flush=True)
                    connected_once = True
                async for msg in ws:
                    try:
                        event = json.loads(msg)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # Ignore events from our own session
                    if event.get("session_id") == state.session_id:
                        continue

                    evt_type = event.get("type", "")
                    if evt_type == "file_push":
                        paths = event.get("paths", [])
                        user_name = event.get("user_name", "unknown")
                        if paths:
                            state.queue_incoming_files(paths, user_name)
                    elif evt_type == "file_delete":
                        paths = event.get("paths", [])
                        user_name = event.get("user_name", "unknown")
                        if paths:
                            state.queue_incoming_deletes(paths, user_name)
                    elif evt_type == "entity_change":
                        state.queue_entity_change(event)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"  WebSocket error: {e} — reconnecting in {backoff:.0f}s", flush=True)
            await asyncio.sleep(min(backoff, 30))
            backoff *= 2


async def _process_incoming(
    client: "BifrostClient",
    files: list[tuple[list[str], str]],
    deletes: list[tuple[list[str], str]],
    entities: list[dict[str, Any]],
    base_path: pathlib.Path,
    repo_prefix: str,
) -> set[str]:
    """Process incoming changes from other sessions. Returns set of written absolute paths."""
    written_paths: set[str] = set()
    ts = datetime.now().strftime('%H:%M:%S')

    # Process incoming file changes
    for paths, user_name in files:
        for repo_path in paths:
            try:
                resp = await client.post("/api/files/read", json={
                    "path": repo_path,
                    "mode": "cloud",
                    "location": "workspace",
                    "binary": True,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    content = base64.b64decode(data["content"])
                    # Convert repo_path to local path
                    if repo_prefix and repo_path.startswith(repo_prefix + "/"):
                        rel = repo_path[len(repo_prefix) + 1:]
                    elif repo_prefix and repo_path.startswith(repo_prefix):
                        rel = repo_path[len(repo_prefix):]
                    else:
                        rel = repo_path
                    local_file = base_path / rel
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    # Skip if content is identical
                    if local_file.exists():
                        try:
                            if local_file.read_bytes() == content:
                                continue
                        except OSError:
                            pass
                    local_file.write_bytes(content)
                    written_paths.add(str(local_file))
                    print(f"  [{ts}] \u2190 {user_name}: {rel}", flush=True)
            except Exception as e:
                print(f"  [{ts}] \u2190 Error pulling {repo_path}: {e}", flush=True)

    # Process incoming deletes
    for paths, user_name in deletes:
        for repo_path in paths:
            if repo_prefix and repo_path.startswith(repo_prefix + "/"):
                rel = repo_path[len(repo_prefix) + 1:]
            elif repo_prefix and repo_path.startswith(repo_prefix):
                rel = repo_path[len(repo_prefix):]
            else:
                rel = repo_path
            local_file = base_path / rel
            if local_file.exists():
                try:
                    local_file.unlink()
                    written_paths.add(str(local_file))
                    print(f"  [{ts}] \u2190 {user_name} deleted: {rel}", flush=True)
                except OSError as e:
                    print(f"  [{ts}] \u2190 Error deleting {rel}: {e}", flush=True)

    # Process incoming entity changes — update local .bifrost/*.yaml
    if entities:
        from bifrost.manifest import MANIFEST_FILES
        import yaml

        # Map entity_type → manifest yaml filename
        entity_to_file = MANIFEST_FILES

        bifrost_dir = _find_bifrost_dir(base_path)
        for event in entities:
            entity_type = event.get("entity_type", "")
            entity_id = event.get("entity_id", "")
            action = event.get("action", "")
            user_name = event.get("user_name", "unknown")
            filename = entity_to_file.get(entity_type)
            if not filename or not entity_id:
                continue

            yaml_path = bifrost_dir / filename
            try:
                # Read existing yaml
                existing_data: dict[str, Any] = {}
                if yaml_path.exists():
                    raw = yaml_path.read_text(encoding="utf-8")
                    existing_data = yaml.safe_load(raw) or {}

                section = existing_data.get(entity_type, {})
                data = event.get("data")

                # For list-type sections (organizations, roles)
                if entity_type in ("organizations", "roles"):
                    if not isinstance(section, list):
                        section = []
                    if action == "delete":
                        section = [e for e in section if e.get("id") != entity_id]
                        existing_data[entity_type] = section
                        yaml_path.parent.mkdir(parents=True, exist_ok=True)
                        yaml_path.write_text(
                            yaml.dump(existing_data, default_flow_style=False, sort_keys=False, allow_unicode=True),
                            encoding="utf-8",
                        )
                        written_paths.add(str(yaml_path))
                        print(f"  [{ts}] \u2190 {user_name} deleted {entity_type[:-1]} {entity_id}", flush=True)
                    elif data:
                        replaced = False
                        for i, entry in enumerate(section):
                            if entry.get("id") == entity_id:
                                section[i] = data
                                replaced = True
                                break
                        if not replaced:
                            section.append(data)
                        existing_data[entity_type] = section
                        yaml_path.parent.mkdir(parents=True, exist_ok=True)
                        yaml_path.write_text(
                            yaml.dump(existing_data, default_flow_style=False, sort_keys=False, allow_unicode=True),
                            encoding="utf-8",
                        )
                        written_paths.add(str(yaml_path))
                        print(f"  [{ts}] \u2190 {user_name} {action}d {entity_type[:-1]} {entity_id}", flush=True)
                    else:
                        print(f"  [{ts}] \u2190 {user_name} {action}d {entity_type[:-1]} {entity_id} (no data)", flush=True)
                    continue

                if isinstance(section, dict):
                    if action == "delete":
                        if entity_id in section:
                            del section[entity_id]
                            existing_data[entity_type] = section
                            yaml_path.parent.mkdir(parents=True, exist_ok=True)
                            yaml_path.write_text(
                                yaml.dump(existing_data, default_flow_style=False, sort_keys=False, allow_unicode=True),
                                encoding="utf-8",
                            )
                            written_paths.add(str(yaml_path))
                            print(f"  [{ts}] \u2190 {user_name} deleted {entity_type[:-1]} {entity_id}", flush=True)
                    elif data:
                        section[entity_id] = data
                        existing_data[entity_type] = section
                        yaml_path.parent.mkdir(parents=True, exist_ok=True)
                        yaml_path.write_text(
                            yaml.dump(existing_data, default_flow_style=False, sort_keys=False, allow_unicode=True),
                            encoding="utf-8",
                        )
                        written_paths.add(str(yaml_path))
                        print(f"  [{ts}] \u2190 {user_name} {action}d {entity_type[:-1]} {entity_id}", flush=True)
                    else:
                        print(f"  [{ts}] \u2190 {user_name} {action}d {entity_type[:-1]} {entity_id} (no data)", flush=True)

            except Exception as e:
                print(f"  [{ts}] \u2190 Error updating {filename}: {e}", flush=True)

    return written_paths


async def _watch_and_push(
    local_path: str,
    repo_prefix: str,
    mirror: bool,
    validate: bool,
    client: "BifrostClient",
) -> int:
    """Watch directory for changes and auto-push."""
    from watchdog.observers import Observer

    path = pathlib.Path(local_path).resolve()
    if not path.exists() or not path.is_dir():
        print(f"Error: {local_path} is not a valid directory", file=sys.stderr)
        return 1

    # Set up file watcher state (generates session_id)
    state = _WatchState(path)

    # Notify server with session_id
    try:
        await client.post("/api/files/watch", json={
            "action": "start", "prefix": repo_prefix, "session_id": state.session_id,
        })
    except Exception:
        pass

    # Initial full push
    print(f"Initial push of {path}...", flush=True)
    await _push_files(str(path), repo_prefix=repo_prefix, mirror=mirror, validate=validate, client=client)

    # Set up file watcher
    handler = _WatchChangeHandler(state)
    observer = Observer()
    observer.schedule(handler, str(path), recursive=True)
    observer.start()

    # Start WebSocket listener for incoming changes from other sessions
    ws_task: asyncio.Task | None = None
    try:
        ws_task = asyncio.create_task(
            _ws_listener(state, client.api_url, client._access_token)
        )
    except Exception:
        pass  # WebSocket listener is best-effort

    print(f"Watching {path} for changes... (Ctrl+C to stop)", flush=True)
    print(f"  Bidirectional sync enabled (session {state.session_id[:8]})", flush=True)

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

            # Process incoming changes from other sessions
            inc_files, inc_deletes, inc_entities = state.drain_incoming()
            if inc_files or inc_deletes or inc_entities:
                state.writeback_paused = True
                wb_paths: set[str] = set()
                try:
                    wb_paths = await _process_incoming(
                        client, inc_files, inc_deletes, inc_entities, path, repo_prefix,
                    )
                finally:
                    await asyncio.sleep(0.2)
                    state.discard_writeback_paths(wb_paths)
                    state.writeback_paused = False

            # Heartbeat
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > heartbeat_interval:
                try:
                    await client.post("/api/files/watch", json={
                        "action": "heartbeat", "prefix": repo_prefix, "session_id": state.session_id,
                    })
                except Exception:
                    pass
                last_heartbeat = now

    except KeyboardInterrupt:
        pass
    finally:
        if ws_task and not ws_task.done():
            ws_task.cancel()
            try:
                await ws_task
            except (asyncio.CancelledError, Exception):
                pass
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


def _compute_local_md5s(
    local_root: pathlib.Path,
    repo_prefix: str,
) -> dict[str, str]:
    """Walk local directory and compute MD5 of all files.

    Returns {repo_path: md5_hex} matching the format the server expects.
    """
    import hashlib as _hashlib

    hashes: dict[str, str] = {}
    spec = _build_file_filter(local_root)

    for file_path in sorted(local_root.rglob("*")):
        if file_path.is_dir():
            continue
        rel = file_path.relative_to(local_root)
        rel_str = str(rel)
        if spec.match_file(rel_str):
            continue
        try:
            content = file_path.read_bytes()
            md5 = _hashlib.md5(content).hexdigest()
            repo_path = f"{repo_prefix}/{rel_str}" if repo_prefix else rel_str
            hashes[repo_path] = md5
        except OSError:
            continue

    return hashes


def _check_git_status(local_root: pathlib.Path, files_to_check: list[str]) -> tuple[bool, set[str]]:
    """Check git status for overwrite safety.

    Returns (is_git_repo, uncommitted_files).
    """
    import subprocess

    # Check if inside a git repo
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, cwd=str(local_root),
        )
        is_git = result.returncode == 0 and result.stdout.strip() == "true"
    except FileNotFoundError:
        return False, set()

    if not is_git or not files_to_check:
        return is_git, set()

    # Check which of the specified files have uncommitted changes
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--"] + files_to_check,
            capture_output=True, text=True, cwd=str(local_root),
        )
        uncommitted = set()
        for line in result.stdout.strip().splitlines():
            if line:
                # porcelain format: XY filename
                path = line[3:].strip()
                uncommitted.add(path)
        return True, uncommitted
    except Exception:
        return True, set()


def _format_file_time(file_path: pathlib.Path) -> str:
    """Format a file's modification time for display (short format)."""
    try:
        mtime = file_path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.strftime("%b %d %H:%M")
    except OSError:
        return "unknown"


def _print_progress(current: int, total: int, label: str) -> None:
    """Print a single-line progress counter that overwrites itself."""
    cols = shutil.get_terminal_size().columns
    text = f"  [{current}/{total}] {label}"
    # Truncate to terminal width and pad to clear previous line
    sys.stdout.write(f"\r{text[:cols]:<{cols}}")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")


def _get_file_mtime(file_path: pathlib.Path) -> datetime | None:
    """Get a file's modification time as a timezone-aware datetime."""
    try:
        return datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _format_server_time(iso_str: str) -> str:
    """Format an ISO 8601 timestamp for display (short format)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d %H:%M")
    except (ValueError, TypeError):
        return "unknown"


def _parse_server_time(iso_str: str) -> datetime | None:
    """Parse an ISO 8601 timestamp into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _strip_repo_prefix(repo_path: str, repo_prefix: str) -> str:
    """Strip the repo prefix from a repo path to get the local relative path."""
    if repo_prefix and repo_path.startswith(repo_prefix + "/"):
        return repo_path[len(repo_prefix) + 1:]
    if repo_prefix and repo_path.startswith(repo_prefix):
        return repo_path[len(repo_prefix):]
    return repo_path


def _render_overwrite_table(
    files_to_write: list[str],
    local_root: pathlib.Path,
    server_files: dict[str, Any],
    repo_prefix: str,
    uncommitted: set[str],
    direction: str = "pull",
    files_to_delete: list[str] | None = None,
    print_summary: bool = True,
) -> dict[str, int]:
    """Render a color-coded table of ALL files involved in the operation.

    Colors indicate what happens to each file:
      - Green: the winning file (will exist after the operation)
      - Orange: the file being overwritten (existed on target, getting replaced)
      - Red: file being deleted with --mirror (no replacement)
      - No color: new file being created (nothing existed on target side)

    Args:
        files_to_write: ALL files being written (overwrites + new)
        direction: "pull" (server overwrites local) or "push" (local overwrites server)
        files_to_delete: files that will be deleted (--mirror only)
    """
    c = _get_colors()
    GREEN, ORANGE, RED, RESET = c.green, c.yellow, c.red, c.reset

    all_files = sorted(set(files_to_write) | set(files_to_delete or []))
    if not all_files:
        return {"new": 0, "changed": 0, "deleted": 0}

    # Compute column widths
    max_name = max(len(f) for f in all_files)
    max_name = max(max_name, 4)  # minimum "File" header width
    ts_width = 24  # "Mar 10 14:23 (newer)" max width

    header_file = "File".ljust(max_name)
    header_local = "Local".ljust(ts_width)
    header_platform = "Platform".ljust(ts_width)

    if direction == "pull":
        print()
        print("  Files to pull from platform:")
        print()
    else:
        print()
        print("  Files to push to platform:")
        print()
    print(f"  {header_file}  {header_local}  {header_platform}")
    print(f"  {'─' * max_name}  {'─' * ts_width}  {'─' * ts_width}")

    uncommitted_files: list[str] = []
    delete_set = set(files_to_delete or [])
    count_new = 0
    count_changed = 0
    count_deleted = 0

    for rel in all_files:
        local_path = local_root / rel
        local_ts = _format_file_time(local_path) if local_path.exists() else ""
        local_dt = _get_file_mtime(local_path) if local_path.exists() else None

        # Get server timestamp — server_files values may be dicts or strings
        repo_path = f"{repo_prefix}/{rel}" if repo_prefix else rel
        server_info = server_files.get(repo_path)
        if isinstance(server_info, dict):
            server_ts = _format_server_time(server_info.get("last_modified", ""))
            server_dt = _parse_server_time(server_info.get("last_modified", ""))
        else:
            server_ts = ""
            server_dt = None

        # Determine which side is newer (only meaningful when both exist)
        # Skip for .bifrost/ manifest files (always regenerated, timestamps meaningless)
        # and when display timestamps are identical (sub-second diff not visible to user)
        is_manifest = rel.startswith(".bifrost/")
        timestamps_differ = local_ts != server_ts and local_ts and server_ts
        local_newer = (not is_manifest and timestamps_differ
                       and local_dt is not None and server_dt is not None and local_dt > server_dt)
        server_newer = (not is_manifest and timestamps_differ
                        and local_dt is not None and server_dt is not None and server_dt > local_dt)

        name_display = rel.ljust(max_name)

        if rel in delete_set:
            # File being deleted (red) — --mirror mode
            count_deleted += 1
            if direction == "pull":
                # Pull --mirror: local file being deleted
                local_display = f"{RED}{local_ts} (delete){RESET}".ljust(ts_width + len(RED) + len(RESET))
                server_display = "".ljust(ts_width)
            else:
                # Push --mirror: server file being deleted
                server_display = f"{RED}{server_ts} (delete){RESET}".ljust(ts_width + len(RED) + len(RESET))
                local_display = "".ljust(ts_width)
            print(f"  {name_display}  {local_display}  {server_display}")
        elif direction == "pull":
            # Pull: server wins (green), local loses (orange)
            has_target = bool(local_ts)
            if has_target:
                count_changed += 1
            else:
                count_new += 1
            newer_tag = " (newer)" if server_newer else ""
            overwritten_tag = " (newer)" if local_newer else ""
            winner_display = f"{GREEN}{server_ts}{newer_tag}{RESET}".ljust(ts_width + len(GREEN) + len(RESET)) if server_ts else "".ljust(ts_width)
            loser_display = f"{ORANGE}{local_ts}{overwritten_tag}{RESET}".ljust(ts_width + len(ORANGE) + len(RESET)) if local_ts else "".ljust(ts_width)
            print(f"  {name_display}  {loser_display}  {winner_display}")
        else:
            # Push: local wins (green), server loses (orange)
            has_target = bool(server_ts)
            if has_target:
                count_changed += 1
            else:
                count_new += 1
            newer_tag = " (newer)" if local_newer else ""
            overwritten_tag = " (newer)" if server_newer else ""
            winner_display = f"{GREEN}{local_ts}{newer_tag}{RESET}".ljust(ts_width + len(GREEN) + len(RESET)) if local_ts else "".ljust(ts_width)
            loser_display = f"{ORANGE}{server_ts}{overwritten_tag}{RESET}".ljust(ts_width + len(ORANGE) + len(RESET)) if server_ts else "".ljust(ts_width)
            print(f"  {name_display}  {winner_display}  {loser_display}")

        if rel in uncommitted:
            uncommitted_files.append(rel)

    # Summary line
    file_summary = _format_count_summary(
        {"new": count_new, "changed": count_changed, "deleted": count_deleted},
        {"new": ("green", "{n} new"), "changed": ("yellow", "{n} changed"), "deleted": ("red", "{n} deleted")},
        c, separator="  ",
    )
    if file_summary and print_summary:
        print(f"\n  {file_summary}")

    if uncommitted_files:
        print(f"\n  {RED}⚠ {len(uncommitted_files)} file(s) have uncommitted git changes (overwrite = lost work):{RESET}")
        for f in uncommitted_files:
            print(f"  {RED}  {f}{RESET}")

    return {"new": count_new, "changed": count_changed, "deleted": count_deleted}


async def _pull_from_server(
    client: BifrostClient,
    local_root: pathlib.Path,
    repo_prefix: str,
    include_code_files: bool = False,
    force: bool = False,
    mirror: bool = False,
) -> bool:
    """Pull files from server using per-file operations. Returns True on success."""
    # 1. Get server file listing with metadata
    server_metadata: dict[str, dict[str, str]] = {}
    try:
        resp = await client.post("/api/files/list", json={
            "include_metadata": True,
            "mode": "cloud",
            "location": "workspace",
        })
        if resp.status_code != 200:
            print(f"Warning: file listing failed ({resp.status_code})", file=sys.stderr)
            return True
        data = resp.json()
        for item in data.get("files_metadata", []):
            server_metadata[item["path"]] = {"etag": item["etag"], "last_modified": item["last_modified"]}
    except Exception as e:
        print(f"Warning: file listing failed: {e}", file=sys.stderr)
        return True

    # Filter out .git/ objects
    server_metadata = {
        path: meta for path, meta in server_metadata.items()
        if not path.startswith(".git/")
    }

    # 2. Get manifest files from DB
    manifest_files: dict[str, str] = {}
    try:
        resp = await client.get("/api/files/manifest")
        if resp.status_code == 200:
            manifest_files = resp.json()
    except Exception:
        pass

    if include_code_files:
        # Compute MD5 for all local files (matches S3 ETags)
        local_hashes = _compute_local_md5s(local_root, repo_prefix)
    else:
        # Legacy behavior: only hash manifest files
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

    # 3. Compute diff: find files to download
    # Filter out paths the CLI would skip during push (respects .gitignore)
    pull_spec = _build_file_filter(local_root)

    files_to_download: list[str] = []  # repo paths
    for path_str, meta in server_metadata.items():
        # Skip .bifrost/ files — manifests come from DB
        if _is_bifrost_path(path_str):
            continue
        if _should_skip_path(path_str, pull_spec):
            continue
        local_hash = local_hashes.get(path_str)
        if local_hash != meta["etag"]:
            files_to_download.append(path_str)

    # Filter manifest files to only include changed ones
    filtered_manifest_files: dict[str, str] = {}
    for filename, content in manifest_files.items():
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        local_hash = None
        for key_candidate in [
            f".bifrost/{filename}",
            f"{repo_prefix}/.bifrost/{filename}" if repo_prefix else None,
            f"{repo_prefix.rstrip('/')}/.bifrost/{filename}" if repo_prefix else None,
        ]:
            if key_candidate and key_candidate in local_hashes:
                local_hash = local_hashes[key_candidate]
                break
        if local_hash != content_hash:
            filtered_manifest_files[filename] = content

    # Find local-only files (deleted from platform)
    server_paths = set(server_metadata.keys())
    deleted = [
        p for p in local_hashes
        if p not in server_paths
        and not _is_bifrost_path(p)
    ]

    # Files to delete when --mirror is used
    files_to_delete: list[str] = []
    if mirror:
        for local_path_str in local_hashes:
            if local_path_str not in server_metadata and not _is_bifrost_path(local_path_str):
                rel = _strip_repo_prefix(local_path_str, repo_prefix)
                if _should_skip_path(rel, pull_spec):
                    continue
                files_to_delete.append(rel)

    if not files_to_download and not filtered_manifest_files and not files_to_delete:
        if include_code_files:
            print("Already up to date.")
        return True

    # Build list of files that will be written (changed/new from server)
    files_to_write: list[str] = [_strip_repo_prefix(p, repo_prefix) for p in files_to_download]

    # Confirmation (unless --force or not user-facing pull)
    if (files_to_write or files_to_delete) and include_code_files and not force:
        is_git, uncommitted = _check_git_status(local_root, [
            rel for rel in files_to_write if (local_root / rel).exists()
        ])

        _render_overwrite_table(files_to_write, local_root, server_metadata, repo_prefix, uncommitted, direction="pull", files_to_delete=files_to_delete)

        if uncommitted:
            pass  # Warning already shown in table
        elif is_git:
            print("\n  Git is enabled, so overwritten versions can be recovered from git history.")
        else:
            print("\n  Git is not detected — overwritten changes will be irreversibly lost.")

        try:
            answer = input("\nAre you sure you want to continue? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nPull cancelled.")
            return True
        if answer not in ("y", "yes"):
            print("Pull cancelled.")
            return True

    # 5. Download files one at a time with progress
    code_written = 0
    total = len(files_to_download)
    for idx, repo_path in enumerate(files_to_download, 1):
        rel = _strip_repo_prefix(repo_path, repo_prefix)
        _print_progress(idx, total, f"Pulling {rel}")
        try:
            resp = await client.post("/api/files/read", json={
                "path": repo_path,
                "mode": "cloud",
                "location": "workspace",
                "binary": True,
            })
            if resp.status_code == 200:
                file_data = resp.json()
                content_bytes = base64.b64decode(file_data["content"])
                local_path = local_root / rel
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content_bytes)
                code_written += 1
            else:
                print(f"  Warning: failed to read {repo_path}: HTTP {resp.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: failed to read {repo_path}: {e}", file=sys.stderr)

    # Delete local-only files when --mirror
    mirror_deleted = 0
    if mirror and files_to_delete:
        for del_idx, rel in enumerate(files_to_delete, 1):
            target = local_root / rel
            if target.exists():
                target.unlink()
                mirror_deleted += 1
                if include_code_files:
                    _print_progress(del_idx, len(files_to_delete), f"Deleting {rel}")

    # 6. Write manifest files
    bifrost_dir = _find_bifrost_dir(local_root)
    manifest_dir = bifrost_dir if bifrost_dir.exists() else local_root / ".bifrost"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_written = 0
    for filename, content in filtered_manifest_files.items():
        local_path = manifest_dir / filename
        local_path.write_text(content, encoding="utf-8")
        manifest_written += 1

    # Print summary
    if include_code_files:
        if code_written:
            print(f"  \u2713 Downloaded {code_written} file(s)")
        if manifest_written:
            print(f"  Wrote {manifest_written} manifest file(s)")
        if mirror_deleted:
            print(f"  Deleted {mirror_deleted} local file(s)")

        # Informational: local files not on platform (skip if --mirror already deleted them)
        local_only = [
            p for p in local_hashes
            if p not in server_metadata
            and not _is_bifrost_path(p)
        ] if not mirror else []
        if local_only:
            print(f"\n  {len(local_only)} local file(s) not on platform (push to deploy):")
            for p in sorted(local_only)[:10]:
                print(f"    {p}")
            if len(local_only) > 10:
                print(f"    ... and {len(local_only) - 10} more")

        # Informational: platform files not local
        if deleted:
            print(f"\n  {len(deleted)} local file(s) not found on platform:")
            for p in sorted(deleted)[:10]:
                print(f"    {p}")
            if len(deleted) > 10:
                print(f"    ... and {len(deleted) - 10} more")
    else:
        if manifest_written:
            print(f"  Updated {manifest_written} manifest file(s) from server.")

    return True


def _should_skip_path(rel_path: str, spec: "pathspec.PathSpec") -> bool:
    """Check if a relative path should be skipped during push/watch."""
    return spec.match_file(rel_path)


def _collect_push_files(
    path: pathlib.Path,
    repo_prefix: str,
) -> tuple[dict[str, str], int]:
    """Walk a directory and collect text files for push.

    Returns (files_dict, skipped_count).
    """
    files: dict[str, str] = {}
    skipped = 0
    spec = _build_file_filter(path)

    for file_path in sorted(path.rglob("*")):
        if file_path.is_dir():
            continue
        rel = file_path.relative_to(path)
        rel_str = str(rel)
        if spec.match_file(rel_str):
            continue
        try:
            raw = file_path.read_bytes()
            content = base64.b64encode(raw).decode("ascii")
            repo_path = f"{repo_prefix}/{rel_str}" if repo_prefix else rel_str
            files[repo_path] = content
        except OSError:
            skipped += 1
            continue

    return files, skipped



def _render_entity_changes_table(changes: list[dict[str, str]], print_summary: bool = True) -> dict[str, int]:
    """Render a color-coded entity changes table from server dry-run data."""
    if not changes:
        return {"adds": 0, "updates": 0, "deletes": 0, "keeps": 0}

    cc = _get_colors()
    GREEN, YELLOW, RED, DIM, RESET = cc.green, cc.yellow, cc.red, cc.dim, cc.reset

    max_type = max((len(c.get("entity_type", "")) for c in changes), default=4)
    max_type = max(max_type, 4)
    max_name = max((len(c.get("name", "")) for c in changes), default=4)
    max_name = max(max_name, 4)
    max_org = max((len(c.get("organization", "")) for c in changes), default=6)
    max_org = max(max_org, 12)  # "Organization" header
    max_action = max((len(c.get("action", "")) for c in changes), default=6)
    max_action = max(max_action, 6)

    print()
    print("  Entity changes:")
    print()
    print(
        f"  {'Type'.ljust(max_type)}  {'Name'.ljust(max_name)}  {'Organization'.ljust(max_org)}  {'Action'.ljust(max_action)}"
    )
    print(f"  {'─' * max_type}  {'─' * max_name}  {'─' * max_org}  {'─' * max_action}")

    for c in changes:
        action = c.get("action", "")
        entity_type = c.get("entity_type", "")
        name = c.get("name", "")
        org = c.get("organization", "Global")

        if action == "add":
            color = GREEN
        elif action == "update":
            color = YELLOW
        elif action == "delete":
            color = RED
        elif action == "keep":
            color = DIM
        else:
            color = ""

        action_padded = action.ljust(max_action)
        action_display = f"{color}{action_padded}{RESET}" if color else action_padded

        print(f"  {entity_type.ljust(max_type)}  {name.ljust(max_name)}  {org.ljust(max_org)}  {action_display}")

    # Summary
    adds = sum(1 for c in changes if c.get("action") == "add")
    updates = sum(1 for c in changes if c.get("action") == "update")
    deletes = sum(1 for c in changes if c.get("action") == "delete")
    keeps = sum(1 for c in changes if c.get("action") == "keep")
    entity_summary = _format_count_summary(
        {"adds": adds, "updates": updates, "deletes": deletes, "keeps": keeps},
        {
            "adds": ("green", "{n} add{s}"),
            "updates": ("yellow", "{n} update{s}"),
            "deletes": ("red", "{n} delete{s}"),
            "keeps": ("dim", "{n} kept (data preserved)"),
        },
        cc,
    )
    if entity_summary and print_summary:
        print()
        print(f"  {entity_summary}")

    return {"adds": adds, "updates": updates, "deletes": deletes, "keeps": keeps}


async def _entity_diff_pre_push(
    client: "BifrostClient",
    bifrost_files: dict[str, str],
) -> dict[str, Any]:
    """Compare local manifest against server via dry-run import.

    Returns:
        dict with keys:
            - has_deletions: bool
            - entity_changes: list of change dicts
    """
    try:
        resp = await client.post("/api/files/manifest/import", json={
            "files": bifrost_files,
            "delete_removed_entities": True,
            "dry_run": True,
        })
        if resp.status_code != 200:
            return {"has_deletions": False, "entity_changes": []}

        entity_changes = resp.json().get("entity_changes", [])
        has_deletions = any(c["action"] == "delete" for c in entity_changes)

        return {
            "has_deletions": has_deletions,
            "entity_changes": entity_changes,
        }

    except Exception:
        return {"has_deletions": False, "entity_changes": []}


async def _push_files(
    local_path: str,
    repo_prefix: str = "",
    mirror: bool = False,
    validate: bool = False,
    force: bool = False,
    client: "BifrostClient | None" = None,
) -> int:
    """Push local directory to Bifrost _repo/ using per-file operations."""
    path = pathlib.Path(local_path).resolve()

    if not path.exists():
        print(f"Error: path does not exist: {local_path}", file=sys.stderr)
        return 1

    if not path.is_dir():
        print(f"Error: path is not a directory: {local_path}", file=sys.stderr)
        return 1

    if client is None:
        client = BifrostClient.get_instance(require_auth=True)

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

    # Separate .bifrost/ manifest files from regular files
    bifrost_files, regular_files = _separate_manifest_files(files)

    # Entity diff: compare local manifest against server manifest
    entity_changes: list[dict[str, Any]] = []
    delete_removed_entities = False
    if has_manifest:
        entity_diff_result = await _entity_diff_pre_push(client, bifrost_files)
        delete_removed_entities = entity_diff_result.get("has_deletions", False)
        entity_changes = entity_diff_result.get("entity_changes", [])

    scan_count = len(regular_files)
    if repo_prefix:
        print(f"Scanning {scan_count} file(s) in {repo_prefix}/...")
    else:
        print(f"Scanning {scan_count} file(s)...")
    if skipped:
        print(f"  (skipped {skipped} unreadable file(s))")

    # Fetch server file metadata for diff
    server_metadata: dict[str, dict[str, str]] = {}
    try:
        resp = await client.post("/api/files/list", json={
            "include_metadata": True,
            "mode": "cloud",
            "location": "workspace",
        })
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("files_metadata", []):
                server_metadata[item["path"]] = {"etag": item["etag"], "last_modified": item["last_modified"]}
    except Exception:
        pass

    # Compute diff: compare local MD5 vs server ETag (regular files only)
    files_to_upload: dict[str, str] = {}  # repo_path -> content
    unchanged = 0
    for repo_path, content in regular_files.items():
        local_md5 = hashlib.md5(base64.b64decode(content)).hexdigest()
        server_info = server_metadata.get(repo_path)
        if server_info and server_info["etag"] == local_md5:
            unchanged += 1
        else:
            files_to_upload[repo_path] = content

    # Determine files to delete (--mirror)
    files_to_delete_paths: list[str] = []
    if mirror:
        spec = _build_file_filter(path)
        local_paths = set(files.keys())
        prefix_filter = repo_prefix + "/" if repo_prefix else ""
        for server_path in server_metadata:
            if prefix_filter and not server_path.startswith(prefix_filter):
                continue
            if server_path not in local_paths:
                rel = _strip_repo_prefix(server_path, repo_prefix)
                if _is_bifrost_path(rel):
                    continue
                if _should_skip_path(rel, spec):
                    continue
                files_to_delete_paths.append(server_path)

    # Check if anything changed at all
    has_file_changes = bool(files_to_upload or files_to_delete_paths)
    has_entity_changes = bool(entity_changes)
    if not has_file_changes and not has_entity_changes:
        print("Already up to date.")
        return 0

    # Render entity table if there are entity changes
    entity_counts: dict[str, int] = {"adds": 0, "updates": 0, "deletes": 0, "keeps": 0}
    if has_entity_changes:
        entity_counts = _render_entity_changes_table(entity_changes, print_summary=False)

    # Render file table if there are file changes
    file_counts: dict[str, int] = {"new": 0, "changed": 0, "deleted": 0}
    files_to_write_display: list[str] = []
    files_to_delete_display: list[str] = []
    if has_file_changes:
        for repo_path in files_to_upload:
            rel = _strip_repo_prefix(repo_path, repo_prefix)
            files_to_write_display.append(rel)
        for server_path in files_to_delete_paths:
            rel = _strip_repo_prefix(server_path, repo_prefix)
            files_to_delete_display.append(rel)
        table_server_files = {p: v for p, v in server_metadata.items()}
        file_counts = _render_overwrite_table(
            files_to_write_display, path, table_server_files, repo_prefix,
            uncommitted=set(), direction="push", files_to_delete=files_to_delete_display,
            print_summary=False,
        )

    # Combined summary
    cc = _get_colors()

    _ENTITY_LABELS: dict[str, tuple[str, str]] = {
        "adds": ("green", "{n} add{s}"),
        "updates": ("yellow", "{n} update{s}"),
        "deletes": ("red", "{n} delete{s}"),
        "keeps": ("dim", "{n} kept"),
    }
    _FILE_LABELS: dict[str, tuple[str, str]] = {
        "new": ("green", "{n} new"),
        "changed": ("yellow", "{n} changed"),
        "deleted": ("red", "{n} deleted"),
    }

    summary_sections: list[str] = []
    if has_entity_changes:
        entity_text = _format_count_summary(entity_counts, _ENTITY_LABELS, cc)
        if entity_text:
            summary_sections.append(f"Entities: {entity_text}")

    if has_file_changes:
        file_text = _format_count_summary(file_counts, _FILE_LABELS, cc)
        if file_text:
            summary_sections.append(f"Files: {file_text}")

    if summary_sections:
        print(f"\n  {' · '.join(summary_sections)}")

    # Single combined prompt
    if not force:
        if delete_removed_entities:
            prompt = "\nEntities marked 'delete' will be removed. Push changes? [y/N] "
        else:
            prompt = "\nPush changes? [y/N] "
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nPush cancelled.")
            return 1
        if answer not in ("y", "yes"):
            print("Push cancelled.")
            return 0

    # Upload regular files one at a time with progress
    created = 0
    updated = 0
    errors: list[str] = []
    total = len(files_to_upload)

    for idx, (repo_path, content) in enumerate(files_to_upload.items(), 1):
        rel = _strip_repo_prefix(repo_path, repo_prefix)
        _print_progress(idx, total, f"Pushing {rel}")
        is_new = repo_path not in server_metadata
        try:
            resp = await client.post("/api/files/write", json={
                "path": repo_path,
                "content": content,
                "mode": "cloud",
                "location": "workspace",
                "binary": True,
            })
            if resp.status_code == 204:
                if is_new:
                    created += 1
                else:
                    updated += 1
            else:
                errors.append(f"{repo_path}: HTTP {resp.status_code}")
        except Exception as e:
            errors.append(f"{repo_path}: {e}")

    # Import manifest via dedicated endpoint (sends .bifrost/ files inline)
    warnings: list[str] = []
    manifest_applied = False
    modified_files_response: dict[str, str] = {}

    if has_manifest:
        try:
            import_payload: dict[str, Any] = {"files": bifrost_files}
            if delete_removed_entities:
                import_payload["delete_removed_entities"] = True
            resp = await client.post("/api/files/manifest/import", json=import_payload)
            if resp.status_code == 200:
                manifest_data = resp.json()
                manifest_applied = manifest_data.get("applied", False)
                warnings = manifest_data.get("warnings", [])
                modified_files_response = manifest_data.get("modified_files", {})
                # Print deleted entities summary
                deleted_entities = manifest_data.get("deleted_entities", [])
                if deleted_entities:
                    print(f"  Removed {len(deleted_entities)} entity(ies):")
                    for de in deleted_entities:
                        print(f"    - {de}")
            else:
                warnings.append(f"Manifest import failed: HTTP {resp.status_code}")
        except Exception as e:
            warnings.append(f"Manifest import failed: {e}")

    # Delete server-only files (--mirror)
    deleted = 0
    if files_to_delete_paths:
        for del_idx, server_path in enumerate(files_to_delete_paths, 1):
            rel = _strip_repo_prefix(server_path, repo_prefix)
            _print_progress(del_idx, len(files_to_delete_paths), f"Deleting {rel}")
            try:
                resp = await client.post("/api/files/delete", json={
                    "path": server_path,
                    "mode": "cloud",
                    "location": "workspace",
                })
                if resp.status_code == 204:
                    deleted += 1
                else:
                    errors.append(f"delete {server_path}: HTTP {resp.status_code}")
            except Exception as e:
                errors.append(f"delete {server_path}: {e}")

    # Print summary
    parts = []
    if created:
        parts.append(f"{created} created")
    if updated:
        parts.append(f"{updated} updated")
    if deleted:
        parts.append(f"{deleted} deleted")
    if unchanged:
        parts.append(f"{unchanged} unchanged")
    if has_manifest and manifest_applied and has_entity_changes:
        parts.append("manifest applied")
    print(f"  \u2713 {', '.join(parts) if parts else 'No changes'}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for error in errors:
            print(f"    - {error}")

    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"    - {warning}")

    # Write back modified files from server response (e.g. forms/agents with resolved refs)
    if modified_files_response:
        _write_back_server_files(path, repo_prefix, {"modified_files": modified_files_response})

    # Validate if requested
    if validate and repo_prefix:
        slug = repo_prefix.rstrip("/").rsplit("/", 1)[-1]
        print(f"\nValidating app '{slug}'...")

        try:
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

    return 0 if not errors else 1


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
