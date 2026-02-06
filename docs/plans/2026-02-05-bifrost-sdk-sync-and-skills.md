# Bifrost SDK Sync Command & Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `bifrost sync` CLI command that triggers the platform's existing GitHub sync via API polling, then update the Claude Code skills to support both SDK-first (local dev + git + sync) and MCP-only development modes.

**Architecture:** The CLI adds a `sync` command to `api/bifrost/cli.py` (the SDK CLI that users install via `pip install {url}/api/cli/download`). It reuses the existing `BifrostClient` from `api/bifrost/client.py` (which already has `get_sync()`/`post_sync()` methods and handles credential loading + token refresh). The sync command calls the existing sync preview/execute API endpoints, polls `GET /api/jobs/{job_id}` for results, and displays conflicts/orphans for resolution via `--resolve` flags. The jobs endpoint gets a small enhancement to return preview data. Skills are updated to ask the user which development mode they prefer and orchestrate accordingly.

**Tech Stack:** Python 3.11 (CLI), FastAPI (API enhancement), Bash (hook), Markdown (skills)

> **Review note (2026-02-06):** Task 2 (separate CLI HTTP client) was removed — the existing `BifrostClient` already handles auth, token refresh, and sync HTTP methods. Task 3 updated to target `api/bifrost/cli.py` (the distributed SDK CLI) instead of `api/bifrost_cli/main.py` (the Docker-internal CLI). Task 3 also adds `--confirm-unresolved-refs` flag to match the full `SyncExecuteRequest` model.

---

## Task 1: Enhance Jobs Endpoint to Return Preview Data

The existing `GET /api/jobs/{job_id}` returns basic status but not the full preview (conflicts, orphans, files to pull/push). The preview data is already stored in Redis by `publish_git_sync_preview_completed` - we just need the endpoint to return it.

**Files:**
- Modify: `api/src/routers/jobs.py`
- Test: `api/tests/unit/routers/test_jobs.py`

**Step 1: Write the failing test**

Create `api/tests/unit/routers/test_jobs.py`:

```python
"""Tests for job status endpoint with preview data."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.routers.jobs import JobStatusResponse


class TestJobStatusResponse:
    """Test that JobStatusResponse includes preview data."""

    def test_response_includes_preview_field(self):
        """JobStatusResponse should accept a preview dict."""
        response = JobStatusResponse(
            status="success",
            preview={
                "to_pull": [{"path": "workflows/billing.py", "action": "add"}],
                "to_push": [],
                "conflicts": [{
                    "path": "workflows/shared.py",
                    "display_name": "shared",
                    "entity_type": "workflow",
                }],
                "will_orphan": [],
                "is_empty": False,
            },
        )
        assert response.status == "success"
        assert response.preview is not None
        assert len(response.preview["to_pull"]) == 1
        assert len(response.preview["conflicts"]) == 1

    def test_response_preview_defaults_to_none(self):
        """Preview should default to None for non-preview jobs."""
        response = JobStatusResponse(status="pending")
        assert response.preview is None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/routers/test_jobs.py -v`
Expected: FAIL - `preview` field not recognized by `JobStatusResponse`

**Step 3: Update JobStatusResponse and endpoint**

Modify `api/src/routers/jobs.py`:

Add `preview` field to `JobStatusResponse`:

```python
class JobStatusResponse(BaseModel):
    """Response for job status query."""

    status: str = Field(
        description="Job status: 'pending', 'running', 'completed', 'failed', etc."
    )
    message: str | None = Field(default=None, description="Status message")
    # Additional fields from completion (when available)
    pulled: int = Field(default=0, description="Number of files pulled (git sync)")
    pushed: int = Field(default=0, description="Number of files pushed (git sync)")
    commit_sha: str | None = Field(default=None, description="Commit SHA if created")
    error: str | None = Field(default=None, description="Error message if failed")
    # Preview data (for sync preview jobs)
    preview: dict | None = Field(default=None, description="Sync preview data (conflicts, files to pull/push)")
```

In the `get_job_status` function, add `preview` to the response:

```python
return JobStatusResponse(
    status=result.get("status", "unknown"),
    message=result.get("message"),
    pulled=result.get("pulled", 0),
    pushed=result.get("pushed", 0),
    commit_sha=result.get("commit_sha"),
    error=result.get("error"),
    preview=result.get("preview"),
)
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/routers/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/routers/jobs.py api/tests/unit/routers/test_jobs.py
git commit -m "feat: add preview data to job status endpoint for CLI sync"
```

---

## Task 2: ~~Add Authenticated HTTP Client to CLI~~ (REMOVED)

> **Removed:** The existing `BifrostClient` at `api/bifrost/client.py` already provides authenticated HTTP methods (`get_sync()`, `post_sync()`), credential loading, and automatic token refresh. The sync command will use it directly via `BifrostClient.get_instance()`.

---

## Task 3: Add `bifrost sync` Command

Implement the sync command in `api/bifrost/cli.py` (the SDK CLI that gets distributed to users). Uses the existing `BifrostClient` for authenticated API calls.

**Files:**
- Create: `api/bifrost/sync.py` (sync logic)
- Modify: `api/bifrost/cli.py` (register command)
- Test: `api/tests/unit/cli/test_sync.py`

**Step 1: Write the failing test**

Create `api/tests/unit/cli/test_sync.py`:

```python
"""Tests for bifrost sync command."""
from unittest.mock import patch, MagicMock

import pytest

from bifrost.sync import format_preview_summary, EXIT_CLEAN, EXIT_CONFLICTS, EXIT_ERROR


class TestFormatPreviewSummary:
    """Test preview output formatting."""

    def test_empty_sync(self):
        """Should report no changes when preview is empty."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [],
            "will_orphan": [],
            "is_empty": True,
        }
        lines = format_preview_summary(preview)
        assert any("no changes" in line.lower() for line in lines)

    def test_clean_sync(self):
        """Should summarize pull/push counts without conflicts."""
        preview = {
            "to_pull": [
                {"path": "workflows/a.py", "action": "add", "display_name": "a"},
                {"path": "workflows/b.py", "action": "modify", "display_name": "b"},
            ],
            "to_push": [
                {"path": "workflows/c.py", "action": "add", "display_name": "c"},
            ],
            "conflicts": [],
            "will_orphan": [],
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "2" in text  # 2 to pull
        assert "1" in text  # 1 to push

    def test_conflicts_shown(self):
        """Should list each conflict with path and resolve command."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [
                {
                    "path": "workflows/billing.py",
                    "display_name": "billing",
                    "entity_type": "workflow",
                },
            ],
            "will_orphan": [],
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "workflows/billing.py" in text
        assert "--resolve" in text

    def test_orphans_shown(self):
        """Should warn about orphaned workflows."""
        preview = {
            "to_pull": [],
            "to_push": [],
            "conflicts": [],
            "will_orphan": [
                {
                    "workflow_id": "abc",
                    "workflow_name": "Process Ticket",
                    "function_name": "process_ticket",
                    "last_path": "workflows/tickets.py",
                    "used_by": [
                        {"type": "form", "id": "def", "name": "Ticket Form"},
                    ],
                },
            ],
            "is_empty": False,
        }
        lines = format_preview_summary(preview)
        text = "\n".join(lines)
        assert "Process Ticket" in text
        assert "Ticket Form" in text
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/cli/test_sync.py -v`
Expected: FAIL - `bifrost.sync` not found

**Step 3: Write the sync module**

Create `api/bifrost/sync.py`:

```python
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
            lines.append(f"    Modified in both platform and GitHub")
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
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/cli/test_sync.py -v`
Expected: PASS

**Step 5: Register sync command in cli.py**

Modify `api/bifrost/cli.py`:

In the `main()` function, add after the `run` handler:

```python
    if command == "sync":
        return handle_sync(args[1:])
```

Add the handler function:

```python
def handle_sync(args: list[str]) -> int:
    """
    Handle 'bifrost sync' command.

    Args:
        args: Additional arguments

    Returns:
        Exit code
    """
    from .sync import run_sync
    return run_sync(args)
```

Update `print_help()` to include the sync command:

```python
def print_help() -> None:
    """Print CLI help message."""
    print("""
Bifrost CLI - Command-line interface for Bifrost SDK

Usage:
  bifrost <command> [options]

Commands:
  run         Run a workflow file with web-based parameter input
  sync        Sync with Bifrost platform via GitHub
  login       Authenticate with device authorization flow
  logout      Clear stored credentials and sign out
  help        Show this help message

Examples:
  bifrost run my_workflow.py
  bifrost run my_workflow.py --workflow greet --params '{"name": "World"}'
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost logout
  bifrost sync
  bifrost sync --preview
  bifrost sync --resolve workflows/billing.py=keep_remote

For more information, visit: https://docs.gobifrost.com
""".strip())
```

**Step 6: Run all CLI tests**

Run: `./test.sh tests/unit/cli/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add api/bifrost/sync.py api/bifrost/cli.py api/tests/unit/cli/test_sync.py
git commit -m "feat: add bifrost sync command for GitHub sync via API"
```

---

## Task 4: Create Project-Level Hook and Skills

All files live in the project's `.claude/` directory so the entire setup is portable - copy the `.claude/` folder to any Bifrost workspace repo and it works.

**Target structure:**
```
.claude/
├── settings.json              # Hook registration (committed to git)
├── hooks/
│   └── bifrost-detect.sh      # Environment detection
└── skills/
    └── bifrost/
        ├── setup.md           # SDK installation skill
        └── build.md           # Building + mode selection skill
```

**Files:**
- Create: `.claude/hooks/bifrost-detect.sh`
- Create: `.claude/settings.json`
- Keep: `.claude/skills/bifrost_vibecode_debugger/SKILL.md` (removed in Task 7)

**Step 1: Create the hook script**

Create `.claude/hooks/bifrost-detect.sh` - use the existing plugin version as the base since it already has Python/pip/OS detection:

```bash
#!/bin/bash

# Bifrost environment detection hook for Claude Code
# Runs on SessionStart to detect SDK, auth, MCP, and source access

# Only run if CLAUDE_ENV_FILE is available (SessionStart only)
if [ -z "$CLAUDE_ENV_FILE" ]; then
  exit 0
fi

# Initialize all variables
BIFROST_HAS_SOURCE=false
BIFROST_SDK_INSTALLED=false
BIFROST_LOGGED_IN=false
BIFROST_MCP_CONFIGURED=false
BIFROST_DEV_URL=""
BIFROST_SOURCE_PATH=""
BIFROST_PYTHON_CMD=""
BIFROST_PIP_CMD=""
BIFROST_PYTHON_VERSION=""

# 1. Detect Bifrost source code via file markers
check_bifrost_source() {
  local dir="$1"
  local markers=0

  [ -f "$dir/api/shared/models.py" ] && markers=$((markers + 1))
  [ -f "$dir/docker-compose.dev.yml" ] && markers=$((markers + 1))
  [ -f "$dir/api/src/main.py" ] && markers=$((markers + 1))

  if [ $markers -ge 2 ]; then
    echo "$dir"
    return 0
  fi
  return 1
}

search_dir="$(pwd)"
for i in 1 2 3 4 5; do
  if result=$(check_bifrost_source "$search_dir"); then
    BIFROST_HAS_SOURCE=true
    BIFROST_SOURCE_PATH="$result"
    break
  fi
  parent="$(dirname "$search_dir")"
  [ "$parent" = "$search_dir" ] && break
  search_dir="$parent"
done

# 2. Check if bifrost CLI is installed
if command -v bifrost >/dev/null 2>&1; then
  BIFROST_SDK_INSTALLED=true
fi

# 3. Check for credentials file and extract URL
CREDS_FILE=""
if [ -f "$HOME/.bifrost/credentials.json" ]; then
  CREDS_FILE="$HOME/.bifrost/credentials.json"
elif [ -n "$APPDATA" ] && [ -f "$APPDATA/Bifrost/credentials.json" ]; then
  CREDS_FILE="$APPDATA/Bifrost/credentials.json"
fi

if [ -n "$CREDS_FILE" ]; then
  BIFROST_LOGGED_IN=true
  if command -v jq >/dev/null 2>&1; then
    BIFROST_DEV_URL=$(jq -r '.api_url // empty' "$CREDS_FILE" 2>/dev/null)
  fi
fi

# 4. Check if bifrost MCP server is configured
if command -v claude >/dev/null 2>&1; then
  if claude mcp list 2>/dev/null | grep -q "bifrost"; then
    BIFROST_MCP_CONFIGURED=true
  fi
fi

# 5. Detect Python environment (for SDK installation)
for cmd in python3.12 python3.11 python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      BIFROST_PYTHON_CMD="$cmd"
      BIFROST_PYTHON_VERSION="$version"
      break
    fi
  fi
done

if command -v pipx >/dev/null 2>&1; then
  BIFROST_PIP_CMD="pipx install --force"
elif command -v pip3 >/dev/null 2>&1; then
  BIFROST_PIP_CMD="pip3 install --force-reinstall"
elif command -v pip >/dev/null 2>&1; then
  BIFROST_PIP_CMD="pip install --force-reinstall"
elif [ -n "$BIFROST_PYTHON_CMD" ]; then
  if "$BIFROST_PYTHON_CMD" -m pip --version >/dev/null 2>&1; then
    BIFROST_PIP_CMD="$BIFROST_PYTHON_CMD -m pip install --force-reinstall"
  fi
fi

# Detect OS
BIFROST_OS=""
if [ -f /etc/os-release ]; then
  . /etc/os-release
  BIFROST_OS="$ID"
elif [ "$(uname)" = "Darwin" ]; then
  BIFROST_OS="macos"
elif [ -n "$WINDIR" ]; then
  BIFROST_OS="windows"
fi

# Write all variables to CLAUDE_ENV_FILE
{
  echo "export BIFROST_HAS_SOURCE=$BIFROST_HAS_SOURCE"
  echo "export BIFROST_SDK_INSTALLED=$BIFROST_SDK_INSTALLED"
  echo "export BIFROST_LOGGED_IN=$BIFROST_LOGGED_IN"
  echo "export BIFROST_MCP_CONFIGURED=$BIFROST_MCP_CONFIGURED"
  [ -n "$BIFROST_DEV_URL" ] && echo "export BIFROST_DEV_URL=\"$BIFROST_DEV_URL\""
  [ -n "$BIFROST_SOURCE_PATH" ] && echo "export BIFROST_SOURCE_PATH=\"$BIFROST_SOURCE_PATH\""
  [ -n "$BIFROST_PYTHON_CMD" ] && echo "export BIFROST_PYTHON_CMD=\"$BIFROST_PYTHON_CMD\""
  [ -n "$BIFROST_PYTHON_VERSION" ] && echo "export BIFROST_PYTHON_VERSION=\"$BIFROST_PYTHON_VERSION\""
  [ -n "$BIFROST_PIP_CMD" ] && echo "export BIFROST_PIP_CMD=\"$BIFROST_PIP_CMD\""
  [ -n "$BIFROST_OS" ] && echo "export BIFROST_OS=\"$BIFROST_OS\""
} >> "$CLAUDE_ENV_FILE"

exit 0
```

**Step 2: Make the script executable**

```bash
chmod +x .claude/hooks/bifrost-detect.sh
```

**Step 3: Create project-level settings.json with hook registration**

Create `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/bifrost-detect.sh"
          }
        ]
      }
    ]
  }
}
```

**Step 4: Test the hook script manually**

```bash
cd /home/jack/GitHub/bifrost
CLAUDE_ENV_FILE=/tmp/test-env .claude/hooks/bifrost-detect.sh
cat /tmp/test-env
rm /tmp/test-env
```

Expected: `BIFROST_HAS_SOURCE=true` and `BIFROST_SOURCE_PATH=/home/jack/GitHub/bifrost`

**Step 5: Commit**

```bash
git add .claude/hooks/bifrost-detect.sh .claude/settings.json
git commit -m "feat: add project-level SessionStart hook for environment detection"
```

---

## Task 5: Create Setup Skill

**Files:**
- Create: `.claude/skills/bifrost/setup.md`

**Step 1: Write the setup skill**

Create `.claude/skills/bifrost/setup.md` - adapted from the existing plugin version:

```markdown
---
name: setup
description: Set up Bifrost SDK - install CLI, authenticate, configure MCP server. Use when user needs to get started with Bifrost or has incomplete setup.
---

# Bifrost Setup

## Introduction

Before running any commands, introduce the setup process to the user:

> **Bifrost SDK Setup**
>
> I'll help you set up the Bifrost SDK. This involves three steps:
> 1. **Install the CLI** - A command-line tool for developing and testing workflows
> 2. **Authenticate** - Log in to your Bifrost instance
> 3. **Configure MCP** - Connect Claude Code to Bifrost's tools
>
> Let me check your current setup status...

## Check Current State

Run this command to check environment (set by SessionStart hook):

```bash
echo "SDK: $BIFROST_SDK_INSTALLED | Login: $BIFROST_LOGGED_IN | MCP: $BIFROST_MCP_CONFIGURED"
echo "Python: $BIFROST_PYTHON_CMD ($BIFROST_PYTHON_VERSION) | Pip: $BIFROST_PIP_CMD | OS: $BIFROST_OS"
```

## Resume Logic

Based on the environment state:

1. **All true** → Setup complete! Inform user they're ready to use `/bifrost:build`
2. **SDK not installed** → Go to SDK Installation
3. **SDK installed but not logged in** → Go to Login
4. **Logged in but MCP not configured** → Go to MCP Configuration

## SDK Installation

### Prerequisites Check

**If BIFROST_PYTHON_CMD is empty:**
Python 3.11+ is required. Install based on OS:
- **ubuntu/debian**: `sudo apt install python3.11`
- **macos**: `brew install python@3.11`
- **windows**: `winget install Python.Python.3.11`

**If BIFROST_PIP_CMD is empty:**
Need pipx (recommended for CLI tools on modern systems):
- **ubuntu/debian**: `sudo apt install pipx && pipx ensurepath`
- **macos**: `brew install pipx && pipx ensurepath`
- **windows**: `pip install pipx`

### Get Bifrost URL

**If `$BIFROST_DEV_URL` is set:** Use that URL (already detected from credentials).

**Otherwise:** Ask the user: "What is your Bifrost instance URL? (e.g., https://yourcompany.gobifrost.com)"

Do NOT suggest placeholder URLs - every Bifrost instance has a unique URL provided by the user's organization.

### Install SDK

**Use the detected pip command** (from `$BIFROST_PIP_CMD`):

```bash
$BIFROST_PIP_CMD {url}/api/cli/download
```

Verify with:
```bash
bifrost help
```

## Login

```bash
bifrost login --url {url}
```

This opens a browser for authentication and saves credentials to `~/.bifrost/credentials.json`.

## MCP Configuration

Check existing configuration:
```bash
claude mcp list
```

**If `bifrost` exists with wrong URL:** Ask user if they want to update it.

**Add/update MCP server:**
```bash
claude mcp remove bifrost 2>/dev/null; claude mcp add --transport http bifrost {url}/mcp
```

## Restart Required

Tell the user:

> Setup complete! Please restart Claude Code for the MCP server to take effect.
>
> After restarting, you can use `/bifrost:build` to create workflows, forms, and apps.

## Troubleshooting

### pipx install fails with network error
- Verify URL is accessible: `curl {url}/api/cli/download -o /dev/null -w "%{http_code}"`

### bifrost login hangs
- Check if URL is accessible in browser
- Try with `--no-browser` flag and copy the URL manually

### MCP not working after restart
- Verify with `claude mcp list`
- Check Claude Code logs for MCP connection errors
```

**Step 2: Commit**

```bash
git add .claude/skills/bifrost/setup.md
git commit -m "feat: add bifrost:setup skill for SDK installation"
```

---

## Task 6: Create Build Skill with Mode Selection

**Files:**
- Create: `.claude/skills/bifrost/build.md`

**Step 1: Write the build skill**

Create `.claude/skills/bifrost/build.md`. This skill is intentionally thin on reference docs - it relies on MCP schema tools (`get_workflow_schema`, `get_sdk_schema`, `get_app_schema`) for current documentation rather than hardcoding content that drifts.

```markdown
---
name: build
description: Build Bifrost workflows, forms, and apps. Use when user wants to create, debug, or modify Bifrost artifacts. Supports SDK-first (local dev + git) and MCP-only modes.
---

# Bifrost Build

Create and debug Bifrost artifacts.

## First: Check Prerequisites

```bash
echo "SDK: $BIFROST_SDK_INSTALLED | Login: $BIFROST_LOGGED_IN | MCP: $BIFROST_MCP_CONFIGURED"
echo "Source: $BIFROST_HAS_SOURCE | Path: $BIFROST_SOURCE_PATH | URL: $BIFROST_DEV_URL"
```

**If SDK or Login is false/empty:** Direct user to run `/bifrost:setup` first.

## Development Mode

Ask the user which development mode they prefer:

### Option 1: SDK-First (Local Development)

Best for: developers who want git history, local testing, code review before deploying.

**Requirements:** Git repository, Bifrost SDK installed, GitHub sync configured in platform.

**Flow:**
1. Write workflow code locally in the git repo
2. Test locally with `bifrost run <file> <function> --params '{...}'`
3. Iterate until happy with the result
4. `git add && git commit && git push` to push to GitHub
5. `bifrost sync` to tell the platform to pull from GitHub
6. If conflicts: show them, help user resolve with `bifrost sync --resolve`
7. Verify deployment with MCP tools (`list_workflows`, `execute_workflow`)
8. For forms/apps: switch to MCP tools (these are platform-only artifacts)

**Limitations:** Forms and apps cannot be developed locally. After syncing workflows, use MCP tools to create forms and apps that reference them.

### Option 2: MCP-Only (Remote Development)

Best for: quick iterations, non-developers, working without a local git repo.

**Flow:**
1. Understand the goal
2. Read SDK docs via `get_workflow_schema`, `get_sdk_schema`
3. Create artifact via MCP (`create_workflow`, `create_form`, `create_app`)
4. Test via `execute_workflow` or access preview URL
5. Check logs via `get_execution` if issues
6. Iterate with `patch_content` or `replace_content`

### Per-Artifact Switching

Even in SDK-first mode, some artifacts require MCP:

| Artifact | SDK-First | MCP-Only |
|----------|-----------|----------|
| Workflow | Local dev + sync | `create_workflow` |
| Data Provider | Local dev + sync | `create_workflow` |
| Tool | Local dev + sync | `create_workflow` |
| Form | MCP only | `create_form` |
| App | MCP only | `create_app` |

When the user needs a form or app in SDK-first mode: "Forms and apps are platform artifacts - I'll create these using the MCP tools against your synced workflows."

## Before Building

Clarify with the user:
1. **Which organization?** Use `list_organizations` to show options, or "global" for platform-wide
2. **What triggers this?** (webhook, form, schedule, manual)
3. **If webhook:** Get sample payload
4. **What integrations?** Use `list_integrations` to verify availability
5. **Error handling requirements?**

## MCP Tools Reference

### Discovery
- `list_workflows` - List workflows (filter by query, category, type)
- `get_workflow` - Get workflow metadata by ID or name
- `get_workflow_schema` - Workflow decorator documentation
- `get_sdk_schema` - Full SDK documentation
- `list_integrations` - Available integrations and auth status
- `list_forms` - List forms with URLs
- `get_form_schema` - Form structure documentation
- `list_apps` - List App Builder applications
- `get_app_schema` - App structure documentation
- `get_data_provider_schema` - Data provider patterns
- `get_agent_schema` - Agent structure and channels

### Creation (Auto-Validating)
- `create_workflow` - Create workflow, tool, or data provider
- `create_form` - Create a form linked to a workflow
- `create_app` - Create an App Builder application

### Editing
- `list_content` - List files by entity type
- `search_content` - Search code patterns
- `read_content_lines` - Read specific lines
- `patch_content` - Surgical string replacement
- `replace_content` - Replace entire file

### Execution
- `execute_workflow` - Execute by workflow ID
- `list_executions` - List recent executions
- `get_execution` - Get execution details and logs

### Organization
- `list_organizations` - List all organizations
- `get_organization` - Get org details
- `list_tables` - List data tables

## Development Process

1. **Read the schema** - Use appropriate schema tool to understand structure
2. **Check dependencies** - Use `list_integrations` to verify integrations exist
3. **Create the artifact** - Use creation tools (auto-validates)
4. **Test** - Use `execute_workflow` for workflows, preview URL for apps
5. **Iterate** - Use editing tools to refine

**Creation tools auto-validate. Always test execution before declaring something ready.**

## Debugging

### MCP-First Debugging
1. Check execution logs via `get_execution`
2. Verify integrations with `list_integrations`
3. Test workflows with `execute_workflow`
4. Inspect workflow metadata with `get_workflow`

### When Errors Suggest System Bugs

If an error appears to be a backend bug (not user error or doc issue):

**If BIFROST_HAS_SOURCE is true:**
> "This appears to be a backend bug ({error description}). I have access to the Bifrost source code at $BIFROST_SOURCE_PATH. Would you like me to debug and fix this on the backend?"

**If BIFROST_HAS_SOURCE is false:**
> "This appears to be a backend bug ({error description}). Please report this to the platform team with these details: {error details}"

### Issue Categories
- **Documentation/Schema issue** → Note for recommendation, work around, continue
- **System bug** → Detect source access, offer to fix or escalate

## App URLs

- **Preview:** `$BIFROST_DEV_URL/apps/{slug}/preview`
- **Live (after `publish_app`):** `$BIFROST_DEV_URL/apps/{slug}`

## Session Summary

At end of session, provide:

```markdown
## Session Summary

### Completed
- [What was built/accomplished]

### System Bugs Fixed (if source available)
- [Bug] → [Fix] → [File]

### Documentation Recommendations
- [Tool/Schema]: [Issue] → [Recommendation]

### Notes for Future Sessions
- [Relevant context]
```
```

**Step 2: Commit**

```bash
git add .claude/skills/bifrost/build.md
git commit -m "feat: add bifrost:build skill with SDK-first and MCP-only modes"
```

---

## Task 7: Clean Up Old Skill and Plugin

**Files:**
- Delete: `.claude/skills/bifrost_vibecode_debugger/`

**Step 1: Verify new skills work**

Restart Claude Code and confirm:
- Hook fires and sets environment variables
- `/bifrost:setup` is discoverable and detects state
- `/bifrost:build` is discoverable and shows mode selection

**Step 2: Remove the old skill directory**

```bash
rm -rf .claude/skills/bifrost_vibecode_debugger
```

**Step 3: Disable the plugin**

The `bifrost@local-plugins` plugin in `~/.claude/plugins/installed_plugins.json` can be removed or left inactive. It's no longer needed since skills and hooks are now project-level.

**Step 4: Commit**

```bash
git add -A .claude/skills/
git commit -m "chore: remove old bifrost_vibecode_debugger skill

Replaced by project-level skills at .claude/skills/bifrost/
Skills, hooks, and settings are now fully portable - copy .claude/ to any workspace."
```

---

## Task 8: End-to-End Verification

**Step 1: Restart Claude Code**

Close and reopen Claude Code to trigger the SessionStart hook.

**Step 2: Verify environment variables**

```bash
echo "SOURCE: $BIFROST_HAS_SOURCE"
echo "SDK: $BIFROST_SDK_INSTALLED"
echo "LOGGED_IN: $BIFROST_LOGGED_IN"
echo "MCP: $BIFROST_MCP_CONFIGURED"
echo "URL: $BIFROST_DEV_URL"
echo "PATH: $BIFROST_SOURCE_PATH"
```

**Step 3: Test `/bifrost:setup`**

Invoke the skill and verify it detects current state correctly.

**Step 4: Test `/bifrost:build`**

Invoke the skill and verify:
- Mode selection prompt appears
- MCP tools are accessible
- Environment context is shown

**Step 5: Test `bifrost sync --preview`**

```bash
bifrost sync --preview
```

Verify it authenticates, calls the API, polls for results, and displays the preview.

**Step 6: Test portability**

Copy `.claude/` to another directory and verify skills are discoverable:

```bash
mkdir /tmp/test-workspace
cp -r .claude /tmp/test-workspace/
cd /tmp/test-workspace
# Start Claude Code here - skills and hook should work
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Enhance jobs endpoint for preview data | `api/src/routers/jobs.py` |
| 2 | ~~Add authenticated HTTP client~~ (REMOVED) | Uses existing `api/bifrost/client.py` |
| 3 | Add `bifrost sync` command | `api/bifrost/sync.py`, `api/bifrost/cli.py` |
| 4 | Create project-level hook and settings | `.claude/hooks/bifrost-detect.sh`, `.claude/settings.json` |
| 5 | Create setup skill | `.claude/skills/bifrost/setup.md` |
| 6 | Create build skill with mode selection | `.claude/skills/bifrost/build.md` |
| 7 | Clean up old skill and plugin | `.claude/skills/bifrost_vibecode_debugger/` |
| 8 | End-to-end verification | Manual testing |
