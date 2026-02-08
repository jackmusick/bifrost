"""
Bifrost CLI Sync Command

Triggers GitHub sync via the platform API.
Polls for results and displays preview/execution summary.
Uses BifrostClient from bifrost.client for authenticated requests.
"""

import sys
import time

from .client import BifrostClient

# Exit codes
EXIT_CLEAN = 0      # Sync completed or no changes
EXIT_CONFLICTS = 1  # Conflicts need resolution
EXIT_ERROR = 2      # Error occurred


def format_preview_summary(preview: dict) -> list[str]:
    """
    Format sync preview data into human-readable lines.

    Args:
        preview: Preview dict with to_pull, to_push, conflicts, will_orphan, is_empty

    Returns:
        List of output lines
    """
    lines: list[str] = []

    if preview.get("is_empty"):
        lines.append("Already up to date - no changes to sync.")
        return lines

    to_pull = preview.get("to_pull", [])
    to_push = preview.get("to_push", [])
    conflicts = preview.get("conflicts", [])
    will_orphan = preview.get("will_orphan", [])

    # Summary counts
    parts = []
    if to_pull:
        parts.append(f"{len(to_pull)} to pull")
    if to_push:
        parts.append(f"{len(to_push)} to push")
    if conflicts:
        parts.append(f"{len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''}")
    lines.append(", ".join(parts) if parts else "No changes.")

    # Pull details
    if to_pull:
        lines.append("")
        lines.append("Pull from GitHub:")
        for action in to_pull:
            name = action.get("display_name") or action["path"]
            lines.append(f"  {action['action']:8s} {action['path']} ({name})")

    # Push details
    if to_push:
        lines.append("")
        lines.append("Push to GitHub:")
        for action in to_push:
            name = action.get("display_name") or action["path"]
            lines.append(f"  {action['action']:8s} {action['path']} ({name})")

    # Conflicts
    if conflicts:
        lines.append("")
        lines.append("Conflicts:")
        for conflict in conflicts:
            name = conflict.get("display_name") or conflict["path"]
            entity_type = conflict.get("entity_type", "file")
            lines.append(f"  {conflict['path']} ({entity_type}: {name})")
            lines.append("    Modified in both platform and GitHub")
        lines.append("")
        lines.append("To resolve conflicts, run:")
        for conflict in conflicts:
            path = conflict["path"]
            lines.append(f"  bifrost sync --resolve {path}=keep_remote")
            lines.append(f"  bifrost sync --resolve {path}=keep_local")
        lines.append("")
        lines.append(
            "Or manage this in the Code Editor's Source Control at your Bifrost instance."
        )

    # Orphans
    if will_orphan:
        lines.append("")
        lines.append("Warning - these workflows will be orphaned:")
        for orphan in will_orphan:
            lines.append(f"  {orphan['workflow_name']} ({orphan['function_name']})")
            lines.append(f"    Last path: {orphan['last_path']}")
            if orphan.get("used_by"):
                for ref in orphan["used_by"]:
                    lines.append(f"    Used by {ref['type']}: {ref['name']}")

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
        bifrost sync              Preview changes, auto-execute if no conflicts
        bifrost sync --resolve path=keep_remote [--resolve path2=keep_local]
        bifrost sync --preview    Preview only, don't execute

    Args:
        args: Command arguments

    Returns:
        Exit code: 0=success, 1=conflicts, 2=error
    """
    preview_only = False
    resolutions: dict[str, str] = {}
    confirm_orphans = False
    confirm_unresolved_refs = False

    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--preview":
            preview_only = True
            i += 1
        elif arg == "--resolve":
            if i + 1 >= len(args):
                print("Error: --resolve requires path=resolution", file=sys.stderr)
                return EXIT_ERROR
            parts = args[i + 1].split("=", 1)
            if len(parts) != 2 or parts[1] not in ("keep_local", "keep_remote", "skip"):
                print(
                    f"Error: invalid resolution '{args[i + 1]}'. "
                    "Use path=keep_local, path=keep_remote, or path=skip",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            resolutions[parts[0]] = parts[1]
            i += 2
        elif arg == "--confirm-orphans":
            confirm_orphans = True
            i += 1
        elif arg == "--confirm-unresolved-refs":
            confirm_unresolved_refs = True
            i += 1
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

    # If resolutions provided, go straight to execute
    if resolutions:
        return _execute_sync(client, resolutions, confirm_orphans, confirm_unresolved_refs)

    # Otherwise, run preview first
    return _preview_sync(client, preview_only, confirm_orphans, confirm_unresolved_refs)


def _preview_sync(
    client: BifrostClient,
    preview_only: bool,
    confirm_orphans: bool,
    confirm_unresolved_refs: bool,
) -> int:
    """Run sync preview, optionally followed by execution."""
    # Queue preview
    response = client.get_sync("/api/github/sync")
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
        return EXIT_ERROR

    job_id = response.json()["job_id"]

    # Poll for preview result
    try:
        result = poll_job(client, job_id)
    except (TimeoutError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    if result.get("status") == "error":
        print(f"Sync error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return EXIT_ERROR

    preview = result.get("preview", {})
    lines = format_preview_summary(preview)
    for line in lines:
        print(line)

    # Check for conflicts
    conflicts = preview.get("conflicts", [])
    if conflicts:
        return EXIT_CONFLICTS

    # If preview only, stop here
    if preview_only or preview.get("is_empty"):
        return EXIT_CLEAN

    # No conflicts - auto-execute
    return _execute_sync(client, {}, confirm_orphans, confirm_unresolved_refs)


def _execute_sync(
    client: BifrostClient,
    resolutions: dict[str, str],
    confirm_orphans: bool,
    confirm_unresolved_refs: bool,
) -> int:
    """Execute sync with conflict resolutions."""
    response = client.post_sync(
        "/api/github/sync",
        json={
            "conflict_resolutions": resolutions,
            "confirm_orphans": confirm_orphans,
            "confirm_unresolved_refs": confirm_unresolved_refs,
        },
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
        return EXIT_ERROR

    job_id = response.json()["job_id"]

    # Poll for execution result
    try:
        result = poll_job(client, job_id)
    except (TimeoutError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    if result.get("status") in ("success", "completed"):
        pulled = result.get("pulled", 0)
        pushed = result.get("pushed", 0)
        commit_sha = result.get("commit_sha")
        parts = []
        if pulled:
            parts.append(f"pulled {pulled} file{'s' if pulled != 1 else ''}")
        if pushed:
            parts.append(f"pushed {pushed} file{'s' if pushed != 1 else ''}")
        summary = ", ".join(parts) if parts else "no changes"
        sha_info = f" (commit {commit_sha[:7]})" if commit_sha else ""
        print(f"Sync complete: {summary}{sha_info}")
        return EXIT_CLEAN
    else:
        error = result.get("error") or result.get("message") or "Unknown error"
        print(f"Sync failed: {error}", file=sys.stderr)
        return EXIT_ERROR


def print_sync_help() -> None:
    """Print sync command help."""
    print("""
Usage: bifrost sync [options]

Sync local changes with the Bifrost platform via GitHub.

Runs a sync preview first. If there are no conflicts, automatically
executes the sync. If conflicts exist, shows them and exits with
code 1 so you can resolve them.

Options:
  --preview                   Preview only, don't execute
  --resolve PATH=RESOLUTION   Resolve a conflict (keep_local, keep_remote, skip)
  --confirm-orphans           Acknowledge orphaned workflows
  --confirm-unresolved-refs   Acknowledge unresolved workflow references
  --help, -h                  Show this help message

Examples:
  bifrost sync                              # Preview and auto-sync if clean
  bifrost sync --preview                    # Preview only
  bifrost sync --resolve workflows/billing.py=keep_remote
  bifrost sync --resolve a.py=keep_local --resolve b.py=keep_remote
  bifrost sync --confirm-orphans            # Acknowledge orphan warnings
  bifrost sync --confirm-unresolved-refs    # Acknowledge unresolved refs

Exit codes:
  0  Sync completed successfully (or no changes)
  1  Conflicts detected - resolve with --resolve
  2  Error occurred
""".strip())
