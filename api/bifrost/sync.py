"""
Bifrost CLI Sync Command

Triggers GitHub sync via the platform API.
Polls for results and displays summary.
Uses BifrostClient from bifrost.client for authenticated requests.
"""

import sys
import time

from .client import BifrostClient

# Exit codes
EXIT_CLEAN = 0      # Sync completed or no changes
EXIT_CONFLICTS = 1  # Conflicts need resolution
EXIT_ERROR = 2      # Error occurred

# Map CLI-friendly names to API resolution strategies
RESOLUTION_MAP = {
    "keep_local": "ours",
    "keep_remote": "theirs",
}


def format_sync_result(result: dict) -> list[str]:
    """
    Format sync result data into human-readable lines.

    Args:
        result: Job result dict with status, pulled, pushed, commit_sha, conflicts, error

    Returns:
        List of output lines
    """
    lines: list[str] = []
    status = result.get("status", "unknown")

    if status in ("success", "completed"):
        pulled = result.get("pulled", 0)
        pushed = result.get("pushed", 0)
        commit_sha = result.get("commit_sha")
        parts = []
        if pulled:
            parts.append(f"pulled {pulled} change{'s' if pulled != 1 else ''}")
        if pushed:
            parts.append(f"pushed {pushed} commit{'s' if pushed != 1 else ''}")
        summary = ", ".join(parts) if parts else "no changes"
        sha_info = f" (commit {commit_sha[:7]})" if commit_sha else ""
        lines.append(f"Sync complete: {summary}{sha_info}")
        return lines

    if status == "conflict":
        conflicts = result.get("conflicts", [])
        lines.append(f"{len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''} detected:")
        lines.append("")
        for conflict in conflicts:
            name = conflict.get("display_name") or conflict.get("path", "unknown")
            entity_type = conflict.get("entity_type", "file")
            path = conflict.get("path", "unknown")
            lines.append(f"  {path} ({entity_type}: {name})")
        lines.append("")
        lines.append("To resolve conflicts, run:")
        for conflict in conflicts:
            path = conflict.get("path", "unknown")
            lines.append(f"  bifrost sync --resolve {path}=keep_remote")
            lines.append(f"  bifrost sync --resolve {path}=keep_local")
        lines.append("")
        lines.append(
            "Or manage this in the Code Editor's Source Control at your Bifrost instance."
        )
        return lines

    # Failed or unknown
    error = result.get("error") or result.get("message") or "Unknown error"
    lines.append(f"Sync failed: {error}")
    return lines


def poll_job(client: BifrostClient, job_id: str, timeout: int = 120) -> dict:
    """
    Poll job status endpoint until completion or timeout.

    Args:
        client: BifrostClient instance (uses sync HTTP methods)
        job_id: Job ID to poll
        timeout: Max seconds to wait

    Returns:
        Job result dict

    Raises:
        TimeoutError: If job doesn't complete within timeout
    """
    start = time.time()
    print("Syncing", end="", flush=True)

    while time.time() - start < timeout:
        response = client.get_sync(f"/api/jobs/{job_id}")

        if response.status_code != 200:
            raise RuntimeError(f"Failed to check job status: {response.status_code}")

        result = response.json()

        if result["status"] == "pending":
            print(".", end="", flush=True)
            time.sleep(2)
            continue

        print()  # Newline after dots
        return result

    print()
    raise TimeoutError("Sync timed out. Check the platform UI for status.")


def run_sync(args: list[str]) -> int:
    """
    Main sync command handler.

    Usage:
        bifrost sync              Sync changes (pull + push)
        bifrost sync --resolve path=keep_remote [--resolve path2=keep_local]

    Args:
        args: Command arguments

    Returns:
        Exit code: 0=success, 1=conflicts, 2=error
    """
    resolutions: dict[str, str] = {}

    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--resolve":
            if i + 1 >= len(args):
                print("Error: --resolve requires path=resolution", file=sys.stderr)
                return EXIT_ERROR
            parts = args[i + 1].split("=", 1)
            if len(parts) != 2 or parts[1] not in ("keep_local", "keep_remote"):
                print(
                    f"Error: invalid resolution '{args[i + 1]}'. "
                    "Use path=keep_local or path=keep_remote",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            resolutions[parts[0]] = parts[1]
            i += 2
        elif arg in ("--help", "-h"):
            print_sync_help()
            return EXIT_CLEAN
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return EXIT_ERROR

    # Authenticate
    try:
        client = BifrostClient.get_instance(require_auth=True)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Resolve conflicts or run sync
    if resolutions:
        return _resolve_conflicts(client, resolutions)
    return _run_sync(client)


def _run_sync(client: BifrostClient) -> int:
    """Queue sync and poll for result."""
    response = client.post_sync("/api/github/sync", json={})
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
        return EXIT_ERROR

    job_id = response.json()["job_id"]

    try:
        result = poll_job(client, job_id)
    except (TimeoutError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    lines = format_sync_result(result)
    for line in lines:
        print(line)

    status = result.get("status", "unknown")
    if status in ("success", "completed"):
        return EXIT_CLEAN
    elif status == "conflict":
        return EXIT_CONFLICTS
    else:
        return EXIT_ERROR


def _resolve_conflicts(client: BifrostClient, resolutions: dict[str, str]) -> int:
    """Post conflict resolutions and poll for result."""
    # Map CLI names to API names
    api_resolutions = {
        path: RESOLUTION_MAP[resolution]
        for path, resolution in resolutions.items()
    }

    response = client.post_sync(
        "/api/github/resolve",
        json={"resolutions": api_resolutions},
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
        return EXIT_ERROR

    job_id = response.json()["job_id"]

    try:
        result = poll_job(client, job_id)
    except (TimeoutError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    lines = format_sync_result(result)
    for line in lines:
        print(line)

    status = result.get("status", "unknown")
    if status in ("success", "completed"):
        return EXIT_CLEAN
    elif status == "conflict":
        return EXIT_CONFLICTS
    else:
        return EXIT_ERROR


def print_sync_help() -> None:
    """Print sync command help."""
    print("""
Usage: bifrost sync [options]

Sync local changes with the Bifrost platform via GitHub.

Pulls remote changes and pushes local commits. If conflicts are
detected, shows them and exits with code 1 so you can resolve them.

Options:
  --resolve PATH=RESOLUTION   Resolve a conflict (keep_local, keep_remote)
  --help, -h                  Show this help message

Examples:
  bifrost sync                              # Pull + push sync
  bifrost sync --resolve workflows/billing.py=keep_remote
  bifrost sync --resolve a.py=keep_local --resolve b.py=keep_remote

Exit codes:
  0  Sync completed successfully (or no changes)
  1  Conflicts detected - resolve with --resolve
  2  Error occurred
""".strip())
