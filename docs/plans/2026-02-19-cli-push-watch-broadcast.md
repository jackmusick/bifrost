# CLI Push/Watch Rework + Activity Broadcast

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the CLI development workflow so `bifrost push` checks for uncommitted platform changes before pushing, add `--watch` for continuous file syncing, add `bifrost api` as a generic escape hatch, and broadcast file activity to admins in the Header and Editor StatusBar.

**Architecture:** CLI push gates on a fast "repo dirty" check (Redis flag set by platform writes, cleared by git sync). Watch mode uses watchdog for filesystem events with debounced pushes. All file activity broadcasts over WebSocket channel `file-activity` (admin-only), displayed in two persistent UI locations: Header indicator and Editor StatusBar.

**Tech Stack:** Python (watchdog, httpx), Redis (dirty flag + watch session tracking), WebSocket (existing pubsub infrastructure), React (Zustand store, shadcn components)

---

## Task 1: Repo Dirty Flag (Backend)

Track when the platform has uncommitted changes so CLI push pre-check is instant (~0ms) instead of running full git status (~10s).

**Files:**
- Create: `api/src/core/repo_dirty.py`
- Modify: `api/src/services/file_storage/file_ops.py` (hook into `write_file`)
- Modify: `api/src/routers/files.py` (skip dirty flag for CLI push)
- Modify: `api/src/services/github_sync.py` (clear flag on sync)
- Modify: `api/src/routers/github.py` (new `/api/github/repo-status` endpoint)
- Modify: `api/shared/models.py` (add `RepoStatusResponse`)
- Test: `tests/unit/test_repo_dirty.py`
- Test: `tests/e2e/platform/test_repo_dirty.py`

**Step 1: Write unit test for dirty flag helpers**

```python
# tests/unit/test_repo_dirty.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_mark_repo_dirty_sets_redis_key():
    mock_redis = AsyncMock()
    with patch("src.core.repo_dirty.get_redis", return_value=mock_redis):
        from src.core.repo_dirty import mark_repo_dirty
        await mark_repo_dirty()
        mock_redis.set.assert_called_once()
        key = mock_redis.set.call_args[0][0]
        assert key == "bifrost:repo_dirty"

@pytest.mark.asyncio
async def test_clear_repo_dirty_deletes_redis_key():
    mock_redis = AsyncMock()
    with patch("src.core.repo_dirty.get_redis", return_value=mock_redis):
        from src.core.repo_dirty import clear_repo_dirty
        await clear_repo_dirty()
        mock_redis.delete.assert_called_once_with("bifrost:repo_dirty")

@pytest.mark.asyncio
async def test_is_repo_dirty_returns_timestamp_when_set():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"2026-02-19T12:00:00+00:00"
    with patch("src.core.repo_dirty.get_redis", return_value=mock_redis):
        from src.core.repo_dirty import get_repo_dirty_since
        result = await get_repo_dirty_since()
        assert result == "2026-02-19T12:00:00+00:00"

@pytest.mark.asyncio
async def test_is_repo_dirty_returns_none_when_clean():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch("src.core.repo_dirty.get_redis", return_value=mock_redis):
        from src.core.repo_dirty import get_repo_dirty_since
        result = await get_repo_dirty_since()
        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_repo_dirty.py -v`
Expected: FAIL — module `src.core.repo_dirty` does not exist

**Step 3: Implement dirty flag module**

```python
# api/src/core/repo_dirty.py
"""
Repo dirty flag — tracks when platform-side writes have occurred
since the last git sync. Used by CLI push to fast-check staleness.

Set by: FileStorageService.write_file() (when NOT from CLI push)
Cleared by: GitHubSyncService on successful sync
Checked by: GET /api/github/repo-status
"""
from datetime import datetime, timezone

from src.core.cache.redis_client import get_redis

DIRTY_KEY = "bifrost:repo_dirty"


async def mark_repo_dirty() -> None:
    """Mark repo as having uncommitted platform changes."""
    async with get_redis() as r:
        await r.set(DIRTY_KEY, datetime.now(timezone.utc).isoformat())


async def clear_repo_dirty() -> None:
    """Clear dirty flag after successful git sync."""
    async with get_redis() as r:
        await r.delete(DIRTY_KEY)


async def get_repo_dirty_since() -> str | None:
    """Return ISO timestamp if dirty, None if clean."""
    async with get_redis() as r:
        val = await r.get(DIRTY_KEY)
        return val.decode() if val else None
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_repo_dirty.py -v`
Expected: PASS

**Step 5: Hook into FileStorageService.write_file**

In `api/src/services/file_storage/file_ops.py`, at the end of `write_file()` after the S3 write succeeds, add:

```python
from src.core.repo_dirty import mark_repo_dirty
# ... at end of write_file, after successful write:
await mark_repo_dirty()
```

**Important:** The `push_files` endpoint in `api/src/routers/files.py` calls `FileStorageService.write_file()` directly. To avoid CLI pushes marking the repo dirty, add a `skip_dirty_flag: bool = False` parameter to `write_file()` and pass `True` from the push endpoint. Alternatively, add a request header `X-Bifrost-CLI-Push: true` and check it in `file_ops.py` — but the parameter approach is cleaner.

**Step 6: Clear flag on sync**

In `api/src/services/github_sync.py`, in the method that runs after successful sync execute (look for where `last_synced_at` is updated), add:

```python
from src.core.repo_dirty import clear_repo_dirty
await clear_repo_dirty()
```

**Step 7: Add `/api/github/repo-status` endpoint**

In `api/src/routers/github.py`:

```python
class RepoStatusResponse(BaseModel):
    git_configured: bool
    dirty: bool
    dirty_since: str | None = None

@router.get("/repo-status", response_model=RepoStatusResponse)
async def get_repo_status(user: CurrentSuperuser, db: DbSession):
    config = await get_github_config(db)
    dirty_since = await get_repo_dirty_since()
    return RepoStatusResponse(
        git_configured=config is not None and bool(config.repo_url),
        dirty=dirty_since is not None,
        dirty_since=dirty_since,
    )
```

**Step 8: Write E2E test for repo-status endpoint**

```python
# tests/e2e/platform/test_repo_dirty.py
async def test_repo_status_clean_by_default(auth_client):
    resp = await auth_client.get("/api/github/repo-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dirty"] is False
    assert data["dirty_since"] is None

async def test_repo_status_dirty_after_file_write(auth_client):
    # Write a file through the editor endpoint (platform write)
    await auth_client.put("/api/files/editor/content", json={
        "path": "test-dirty.py",
        "content": "# test",
    })
    resp = await auth_client.get("/api/github/repo-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dirty"] is True
    assert data["dirty_since"] is not None

async def test_repo_status_clean_after_push(auth_client):
    # Push via CLI endpoint should NOT mark dirty
    await auth_client.post("/api/files/push", json={
        "files": {"test-push.py": "# test"},
    })
    resp = await auth_client.get("/api/github/repo-status")
    data = resp.json()
    # Should still be clean (or whatever it was before)
```

**Step 9: Run E2E tests**

Run: `./test.sh tests/e2e/platform/test_repo_dirty.py -v`
Expected: PASS

**Step 10: Commit**

```bash
git add api/src/core/repo_dirty.py api/src/services/file_storage/file_ops.py \
  api/src/routers/github.py api/src/services/github_sync.py \
  api/shared/models.py tests/
git commit -m "feat: add repo dirty flag for fast CLI push pre-check"
```

---

## Task 2: Activity Broadcast (Backend)

Broadcast file push events and watch session state over WebSocket to admins.

**Files:**
- Modify: `api/src/core/pubsub.py` (add `publish_file_activity`)
- Modify: `api/src/routers/websocket.py` (authorize `file-activity` channel for superusers)
- Modify: `api/src/routers/files.py` (broadcast after push, add watch session endpoints)
- Modify: `api/shared/models.py` (add request/response models)
- Test: `tests/unit/test_file_activity_broadcast.py`

**Step 1: Write unit test for publish_file_activity**

```python
# tests/unit/test_file_activity_broadcast.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_publish_file_activity_broadcasts_to_channel():
    with patch("src.core.pubsub.manager") as mock_manager:
        mock_manager.broadcast = AsyncMock()
        from src.core.pubsub import publish_file_activity
        await publish_file_activity(
            user_id="user-1",
            user_name="Jack",
            activity_type="file_push",
            prefix="apps/portal",
            file_count=4,
            is_watch=False,
        )
        mock_manager.broadcast.assert_called_once()
        channel, message = mock_manager.broadcast.call_args[0]
        assert channel == "file-activity"
        assert message["type"] == "file_push"
        assert message["user_name"] == "Jack"
        assert message["prefix"] == "apps/portal"
        assert message["file_count"] == 4
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_file_activity_broadcast.py -v`
Expected: FAIL — `publish_file_activity` does not exist

**Step 3: Implement publish_file_activity in pubsub.py**

Add to `api/src/core/pubsub.py`:

```python
async def publish_file_activity(
    user_id: str,
    user_name: str,
    activity_type: str,  # "file_push" | "watch_start" | "watch_stop"
    prefix: str,
    file_count: int = 0,
    is_watch: bool = False,
) -> None:
    """Broadcast file activity to admin-only file-activity channel."""
    await manager.broadcast("file-activity", {
        "type": activity_type,
        "user_id": user_id,
        "user_name": user_name,
        "prefix": prefix,
        "file_count": file_count,
        "is_watch": is_watch,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_file_activity_broadcast.py -v`
Expected: PASS

**Step 5: Authorize file-activity channel in WebSocket router**

In `api/src/routers/websocket.py`, in the channel authorization section (around line 213), add a case:

```python
elif channel == "file-activity":
    if user.is_superuser:
        allowed_channels.append(channel)
```

**Step 6: Add watch session endpoints to files router**

In `api/src/routers/files.py`, add:

```python
from src.core.pubsub import publish_file_activity

class WatchSessionRequest(BaseModel):
    action: Literal["start", "stop", "heartbeat"]
    prefix: str

@router.post("/watch")
async def manage_watch_session(
    request: WatchSessionRequest,
    user: CurrentSuperuser,
):
    """Register, heartbeat, or deregister a CLI watch session."""
    key = f"bifrost:watch:{user.id}:{request.prefix}"

    if request.action in ("start", "heartbeat"):
        async with get_redis() as r:
            await r.setex(key, 120, json.dumps({
                "user_id": str(user.id),
                "user_name": user.name or user.email,
                "prefix": request.prefix,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }))
        if request.action == "start":
            await publish_file_activity(
                user_id=str(user.id),
                user_name=user.name or user.email or "CLI",
                activity_type="watch_start",
                prefix=request.prefix,
            )
    elif request.action == "stop":
        async with get_redis() as r:
            await r.delete(key)
        await publish_file_activity(
            user_id=str(user.id),
            user_name=user.name or user.email or "CLI",
            activity_type="watch_stop",
            prefix=request.prefix,
        )
    return {"ok": True}

@router.get("/watchers")
async def list_active_watchers(user: CurrentSuperuser):
    """List active CLI watch sessions."""
    async with get_redis() as r:
        keys = [k async for k in r.scan_iter("bifrost:watch:*")]
        watchers = []
        for key in keys:
            data = await r.get(key)
            if data:
                watchers.append(json.loads(data))
    return {"watchers": watchers}
```

**Step 7: Broadcast from push_files endpoint**

In `api/src/routers/files.py`, in the `push_files()` function, after `db.commit()`:

```python
total_changed = result.created + result.updated + result.deleted
if total_changed > 0:
    is_watch = request_obj.headers.get("X-Bifrost-Watch") == "true"
    prefix = request.delete_missing_prefix or next(iter(request.files.keys()), "").rsplit("/", 1)[0]
    await publish_file_activity(
        user_id=str(user.id),
        user_name=user.name or user.email or "CLI",
        activity_type="file_push",
        prefix=prefix,
        file_count=total_changed,
        is_watch=is_watch,
    )
```

Note: Need access to the raw `Request` object to read headers. Add `request_obj: Request` parameter to the endpoint.

**Step 8: Run tests**

Run: `./test.sh tests/unit/test_file_activity_broadcast.py -v`
Expected: PASS

**Step 9: Commit**

```bash
git add api/src/core/pubsub.py api/src/routers/websocket.py \
  api/src/routers/files.py api/shared/models.py tests/
git commit -m "feat: add file activity broadcast and watch session tracking"
```

---

## Task 3: Rework CLI `bifrost push` with Pre-Check

Gate push on repo-status check. Require git configured. Add `--watch` flag parsing.

**Files:**
- Modify: `api/bifrost/cli.py` (rewrite `handle_push`, add `_check_repo_status`)

**Step 1: Add `_check_repo_status` function**

```python
async def _check_repo_status(client: "BifrostClient") -> bool:
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
            print(f"Error: Platform has uncommitted changes (since {since}).", file=sys.stderr)
            print("  Run 'bifrost sync' to commit and reconcile before pushing.", file=sys.stderr)
            return False

        return True
    except Exception as e:
        print(f"Warning: could not check repo status: {e}. Proceeding anyway.", file=sys.stderr)
        return True
```

**Step 2: Rewrite `handle_push` to add pre-check and --watch**

Update `handle_push` to:
1. Parse `--watch` flag alongside existing `--clean` and `--validate`.
2. Default `local_path` to `"."` if not provided.
3. Authenticate via `BifrostClient.get_instance(require_auth=True)`.
4. Call `_check_repo_status(client)` — return 1 if fails.
5. If `--watch`: call `_watch_and_push(...)`.
6. Else: call existing `_push_files(...)`.

**Step 3: Update help text**

Update `print_help()` and push-specific help to document:
- Git must be configured
- Pre-check for uncommitted platform changes
- `--watch` flag
- Project root = `_repo/` root

**Step 4: Manual test**

Run (with dev stack up):
```bash
cd /path/to/project && bifrost push .
# Should check repo-status first, then push
```

**Step 5: Commit**

```bash
git add api/bifrost/cli.py
git commit -m "feat: gate CLI push on repo dirty check, add --watch flag"
```

---

## Task 4: CLI `bifrost push --watch` (File Watcher)

Continuous file watching with debounced auto-push.

**Files:**
- Modify: `api/bifrost/cli.py` (add `_watch_and_push`, `_push_changed_files`)
- Modify: `api/bifrost/pyproject.toml` (add watchdog dependency)

**Step 1: Add watchdog dependency**

In `api/bifrost/pyproject.toml`, add to dependencies:
```toml
dependencies = [
    "httpx>=0.24.0",
    "pydantic>=2.0.0",
    "watchdog>=4.0.0",
]
```

**Step 2: Implement `_watch_and_push`**

```python
async def _watch_and_push(
    local_path: str,
    clean: bool,
    validate: bool,
    client: "BifrostClient",
) -> int:
    """Watch directory for changes and auto-push."""
    import pathlib
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    import threading

    path = pathlib.Path(local_path).resolve()
    if not path.exists() or not path.is_dir():
        print(f"Error: {local_path} is not a valid directory", file=sys.stderr)
        return 1

    # Determine repo_prefix (same logic as _push_files)
    parts = path.parts
    repo_prefix = None
    known_roots = {"apps", "workflows", "modules", "agents", "forms"}
    for i, part in enumerate(parts):
        if part in known_roots:
            repo_prefix = "/".join(parts[i:])
            break
    if repo_prefix is None:
        repo_prefix = path.name

    # Notify server: watch started
    try:
        await client.post("/api/files/watch", json={
            "action": "start", "prefix": repo_prefix,
        })
    except Exception:
        pass  # Non-fatal

    # Initial full push
    print(f"Initial push of {path}...")
    await _push_files(local_path, clean=clean, validate=validate)

    # File change tracking
    pending_changes: set[str] = set()
    lock = threading.Lock()

    binary_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".woff", ".woff2", ".ttf", ".eot",
        ".zip", ".tar", ".gz", ".bz2",
        ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    }

    class ChangeHandler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            src = event.src_path
            rel_parts = pathlib.Path(src).relative_to(path).parts
            # Skip hidden, __pycache__, node_modules, binary
            if any(p.startswith(".") for p in rel_parts):
                return
            if any(p in ("__pycache__", "node_modules") for p in rel_parts):
                return
            if pathlib.Path(src).suffix.lower() in binary_extensions:
                return
            with lock:
                pending_changes.add(src)

    observer = Observer()
    observer.schedule(ChangeHandler(), str(path), recursive=True)
    observer.start()

    print(f"Watching {path} for changes... (Ctrl+C to stop)")

    heartbeat_interval = 60  # seconds
    last_heartbeat = asyncio.get_event_loop().time()

    try:
        while True:
            await asyncio.sleep(0.5)

            # Debounce: collect changes
            with lock:
                if pending_changes:
                    changes = pending_changes.copy()
                    pending_changes.clear()
                else:
                    changes = set()

            if changes:
                await _push_changed_files(changes, path, repo_prefix, client)

            # Heartbeat
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > heartbeat_interval:
                try:
                    await client.post("/api/files/watch", json={
                        "action": "heartbeat", "prefix": repo_prefix,
                    })
                except Exception:
                    pass
                last_heartbeat = now

    except KeyboardInterrupt:
        print("\nStopping watch...")
    finally:
        observer.stop()
        observer.join()
        try:
            await client.post("/api/files/watch", json={
                "action": "stop", "prefix": repo_prefix,
            })
        except Exception:
            pass

    return 0
```

**Step 3: Implement `_push_changed_files`**

```python
async def _push_changed_files(
    changed_paths: set[str],
    root: "pathlib.Path",
    repo_prefix: str,
    client: "BifrostClient",
) -> None:
    """Push only the changed files."""
    import pathlib

    files: dict[str, str] = {}
    deleted: list[str] = []

    for abs_path_str in changed_paths:
        abs_path = pathlib.Path(abs_path_str)
        rel = abs_path.relative_to(root)
        repo_path = f"{repo_prefix}/{rel}"

        if abs_path.exists():
            try:
                content = abs_path.read_text(encoding="utf-8")
                files[repo_path] = content
            except (UnicodeDecodeError, OSError):
                continue
        else:
            # File was deleted
            deleted.append(repo_path)

    if not files and not deleted:
        return

    # Push changed files
    if files:
        try:
            response = await client.post(
                "/api/files/push",
                json={"files": files},
                headers={"X-Bifrost-Watch": "true"},
            )
            if response.status_code == 200:
                result = response.json()
                parts = []
                if result.get("created"): parts.append(f"{result['created']} created")
                if result.get("updated"): parts.append(f"{result['updated']} updated")
                if parts:
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {', '.join(parts)}")
        except Exception as e:
            print(f"  Push error: {e}", file=sys.stderr)

    # TODO: Handle deletes (would need a delete endpoint or push with delete_missing_prefix)
```

**Step 4: Manual test**

```bash
# Terminal 1: Start watch
cd /path/to/project/apps/my-app && bifrost push --watch .

# Terminal 2: Make a change
echo "// test" >> /path/to/project/apps/my-app/page.tsx

# Terminal 1 should show: [14:23:05] 1 updated
```

**Step 5: Commit**

```bash
git add api/bifrost/cli.py api/bifrost/pyproject.toml
git commit -m "feat: add bifrost push --watch with watchdog file monitoring"
```

---

## Task 5: CLI `bifrost api` Command

Generic authenticated pass-through to any API endpoint.

**Files:**
- Modify: `api/bifrost/cli.py` (add `handle_api`, wire into dispatch)

**Step 1: Implement handle_api**

```python
def handle_api(args: list[str]) -> int:
    """bifrost api <METHOD> <endpoint> [json-body]"""
    if len(args) < 2:
        print("Usage: bifrost api <METHOD> <endpoint> [json-body]", file=sys.stderr)
        print("  Example: bifrost api GET /api/workflows", file=sys.stderr)
        print("  Example: bifrost api POST /api/applications/my-app/validate", file=sys.stderr)
        return 1

    method = args[0].upper()
    endpoint = args[1]
    body = None

    if len(args) > 2:
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

    return asyncio.run(_api_request(method, endpoint, body))


async def _api_request(method: str, endpoint: str, body: Any | None) -> int:
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
```

**Step 2: Wire into main() dispatch**

```python
if command == "api":
    return handle_api(args[1:])
```

**Step 3: Update help text**

Add to `print_help()`:
```
  bifrost api <METHOD> <endpoint> [body]   Generic API request
```

**Step 4: Manual test**

```bash
bifrost api GET /api/workflows
bifrost api GET /api/github/repo-status
bifrost api POST /api/applications/my-app/validate
```

**Step 5: Commit**

```bash
git add api/bifrost/cli.py
git commit -m "feat: add bifrost api command for generic authenticated requests"
```

---

## Task 6: Frontend - File Activity Store and Hook

Zustand store and WebSocket hook for file activity events.

**Files:**
- Create: `client/src/stores/fileActivityStore.ts`
- Create: `client/src/hooks/useFileActivity.ts`

**Step 1: Create Zustand store**

```typescript
// client/src/stores/fileActivityStore.ts
import { create } from "zustand";

export interface FileActivityEvent {
  type: "file_push" | "watch_start" | "watch_stop";
  user_id: string;
  user_name: string;
  prefix: string;
  file_count: number;
  is_watch: boolean;
  timestamp: string;
}

interface FileActivityState {
  recentPushes: FileActivityEvent[];
  activeWatchers: FileActivityEvent[];  // watch_start events (deduplicated by user_id+prefix)
  addEvent: (event: FileActivityEvent) => void;
}

const MAX_RECENT = 20;
const MAX_AGE_MS = 5 * 60 * 1000; // 5 minutes

export const useFileActivityStore = create<FileActivityState>((set) => ({
  recentPushes: [],
  activeWatchers: [],
  addEvent: (event) =>
    set((state) => {
      const now = Date.now();

      if (event.type === "file_push") {
        const pruned = state.recentPushes
          .filter((e) => now - new Date(e.timestamp).getTime() < MAX_AGE_MS)
          .slice(-(MAX_RECENT - 1));
        return { recentPushes: [...pruned, event] };
      }

      if (event.type === "watch_start") {
        const key = `${event.user_id}:${event.prefix}`;
        const filtered = state.activeWatchers.filter(
          (w) => `${w.user_id}:${w.prefix}` !== key
        );
        return { activeWatchers: [...filtered, event] };
      }

      if (event.type === "watch_stop") {
        const key = `${event.user_id}:${event.prefix}`;
        return {
          activeWatchers: state.activeWatchers.filter(
            (w) => `${w.user_id}:${w.prefix}` !== key
          ),
        };
      }

      return state;
    }),
}));
```

**Step 2: Create WebSocket hook**

```typescript
// client/src/hooks/useFileActivity.ts
import { useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { webSocketService } from "@/services/websocket";
import { useFileActivityStore, type FileActivityEvent } from "@/stores/fileActivityStore";

export function useFileActivity() {
  const { isPlatformAdmin } = useAuth();
  const addEvent = useFileActivityStore((s) => s.addEvent);

  useEffect(() => {
    if (!isPlatformAdmin) return;

    const channel = "file-activity";
    webSocketService.subscribe(channel);

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (
          data.type === "file_push" ||
          data.type === "watch_start" ||
          data.type === "watch_stop"
        ) {
          addEvent(data as FileActivityEvent);
        }
      } catch {
        // ignore
      }
    };

    // Access the underlying WebSocket (following pattern from Header.tsx)
    const ws = (webSocketService as unknown as { ws: WebSocket | null }).ws;
    ws?.addEventListener("message", handleMessage);

    return () => {
      ws?.removeEventListener("message", handleMessage);
      webSocketService.unsubscribe(channel);
    };
  }, [isPlatformAdmin, addEvent]);
}
```

**Step 3: Commit**

```bash
git add client/src/stores/fileActivityStore.ts client/src/hooks/useFileActivity.ts
git commit -m "feat: add file activity Zustand store and WebSocket hook"
```

---

## Task 7: Frontend - Header Activity Indicator

Show other admins' file activity in the Header bar.

**Files:**
- Create: `client/src/components/layout/FileActivityIndicator.tsx`
- Modify: `client/src/components/layout/Header.tsx` (add indicator)
- Modify: `client/src/components/layout/Layout.tsx` (add `useFileActivity` hook)

**Step 1: Create FileActivityIndicator component**

```tsx
// client/src/components/layout/FileActivityIndicator.tsx
import { Radio } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useFileActivityStore } from "@/stores/fileActivityStore";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function FileActivityIndicator() {
  const { user } = useAuth();
  const activeWatchers = useFileActivityStore((s) => s.activeWatchers);
  const recentPushes = useFileActivityStore((s) => s.recentPushes);

  // Filter out own activity
  const otherWatchers = activeWatchers.filter((w) => w.user_id !== user?.id);
  const otherPushes = recentPushes.filter(
    (p) =>
      p.user_id !== user?.id &&
      Date.now() - new Date(p.timestamp).getTime() < 60_000 // last 60s
  );

  if (otherWatchers.length === 0 && otherPushes.length === 0) return null;

  const label =
    otherWatchers.length > 1
      ? `${otherWatchers.length} developers active`
      : otherWatchers.length === 1
        ? `${otherWatchers[0].user_name} editing ${otherWatchers[0].prefix}`
        : otherPushes.length > 0
          ? `${otherPushes[otherPushes.length - 1].user_name} pushed files`
          : "";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-center gap-1.5 mr-2 text-xs text-muted-foreground">
          <Radio
            className={cn(
              "h-3.5 w-3.5",
              otherWatchers.length > 0
                ? "text-green-500 animate-pulse"
                : "text-blue-500"
            )}
          />
          <span className="hidden lg:inline max-w-48 truncate">{label}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-64">
        {otherWatchers.length > 0 && (
          <div className="space-y-1">
            <p className="font-medium">Active watchers:</p>
            {otherWatchers.map((w) => (
              <p key={`${w.user_id}:${w.prefix}`}>
                {w.user_name} — {w.prefix}
              </p>
            ))}
          </div>
        )}
        {otherPushes.length > 0 && (
          <div className="space-y-1 mt-1">
            <p className="font-medium">Recent pushes:</p>
            {otherPushes.slice(-3).map((p, i) => (
              <p key={i}>
                {p.user_name} — {p.file_count} files to {p.prefix}
              </p>
            ))}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
```

**Step 2: Add to Header**

In `client/src/components/layout/Header.tsx`, after the CLI Sessions button and before NotificationCenter:

```tsx
import { FileActivityIndicator } from "@/components/layout/FileActivityIndicator";

// In the JSX, after the CLI Sessions button block:
{isPlatformAdmin && <FileActivityIndicator />}
```

**Step 3: Initialize the hook**

In `client/src/components/layout/Layout.tsx` (or `ContentLayout.tsx`), add:

```tsx
import { useFileActivity } from "@/hooks/useFileActivity";

// Inside the component:
useFileActivity();
```

This ensures the WebSocket subscription is active whenever an admin is using the app.

**Step 4: Commit**

```bash
git add client/src/components/layout/FileActivityIndicator.tsx \
  client/src/components/layout/Header.tsx \
  client/src/components/layout/Layout.tsx
git commit -m "feat: add file activity indicator to Header for admin awareness"
```

---

## Task 8: Frontend - Editor StatusBar Activity

Show file activity in the Editor's bottom status bar, regardless of tab.

**Files:**
- Modify: `client/src/components/editor/StatusBar.tsx`

**Step 1: Add activity section to StatusBar**

In the right-side `<div>` of StatusBar, before the language/cursor items, add a file activity section:

```tsx
import { useFileActivityStore } from "@/stores/fileActivityStore";
import { Radio } from "lucide-react";

// Inside StatusBar component:
const activeWatchers = useFileActivityStore((s) => s.activeWatchers);
const recentPushes = useFileActivityStore((s) => s.recentPushes);

// Most recent push in last 2 minutes
const latestPush = recentPushes
  .filter((p) => Date.now() - new Date(p.timestamp).getTime() < 120_000)
  .at(-1);

// In the right-side div, before language/cursor:
{activeWatchers.length > 0 && (
  <span className="flex items-center gap-1 text-green-600">
    <Radio className="h-3 w-3 animate-pulse" />
    {activeWatchers.length === 1
      ? `CLI watch (${activeWatchers[0].user_name})`
      : `${activeWatchers.length} CLI watchers`}
  </span>
)}
{!activeWatchers.length && latestPush && (
  <span className="flex items-center gap-1 text-muted-foreground">
    {latestPush.user_name} pushed {latestPush.file_count} files to{" "}
    {latestPush.prefix}
  </span>
)}
```

**Step 2: Verify styling**

The StatusBar is `h-6 text-xs`. The new elements should fit within this constraint. Use the same `text-xs text-muted-foreground` pattern as existing elements.

**Step 3: Commit**

```bash
git add client/src/components/editor/StatusBar.tsx
git commit -m "feat: show file activity in Editor status bar"
```

---

## Verification

After all tasks are complete:

1. **Backend checks:**
   ```bash
   cd api && pyright && ruff check .
   ```

2. **Frontend checks:**
   ```bash
   cd client && npm run tsc && npm run lint
   ```

3. **Regenerate types** (if models changed):
   ```bash
   cd client && npm run generate:types
   ```

4. **Run tests:**
   ```bash
   ./test.sh
   ```

5. **Manual E2E flow:**
   - Start dev stack: `./debug.sh`
   - In terminal: `bifrost push --watch apps/my-app`
   - Verify initial push succeeds
   - Edit a file in `apps/my-app/` — verify auto-push in terminal
   - Open app in browser as admin — verify Header shows activity indicator
   - Open Shell/Editor — verify StatusBar shows "CLI watch (YourName)"
   - Stop watch (Ctrl+C) — verify indicator disappears
   - Make a platform edit (via MCP or UI editor)
   - Try `bifrost push .` — should fail with "Platform has uncommitted changes"
   - Run `bifrost sync` — should succeed
   - Try `bifrost push .` again — should succeed
   - Test `bifrost api GET /api/workflows` — should return JSON
