"""Per-workspace exclusion lock for `bifrost watch` / `bifrost sync`.

Two `bifrost watch` instances pointed at the same workspace, or a `bifrost
sync` running concurrently with a `bifrost watch`, both produce broken
behavior — distinct session_ids that the server can't dedupe, so they ping-
pong each other's writes back as "incoming" events. This module enforces
single-session-per-workspace using an OS-level file lock.

Why an OS lock and not a PID file:

A PID file requires us to detect stale entries (process died without
cleaning up) by checking whether the PID is still alive — racy and gets
fooled by PID reuse. `fcntl.flock` (POSIX) and `msvcrt.locking` (Windows)
are kernel-tracked: when the file descriptor is released — *whatever* the
reason: clean exit, Ctrl-C, SIGKILL, OOM, panic, reboot — the kernel
releases the lock automatically. There is no reaper, no TTL, no stale
state to clean up.

The lock file *also* records PID + command + start time, but as
informational metadata only — the lock itself is the FD, not the file.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import threading
from datetime import datetime, timezone
from typing import IO, Any

logger = logging.getLogger(__name__)


_LOCK_NAME = ".session.lock"

# In-process registry of currently-held workspace locks. POSIX flock is
# advisory and per-open-file-description: multiple FDs in the same process
# can hold an "exclusive" flock at the same time. That breaks the guarantee
# we want (one session per workspace, period), so we add a process-local
# guard that raises before flock is even attempted. Across processes, flock
# still does the work.
_HELD: set[str] = set()
_HELD_LOCK = threading.Lock()


def _lock_path(workspace: pathlib.Path) -> pathlib.Path:
    return workspace / ".bifrost" / _LOCK_NAME


def _platform_lock(fh: IO[Any]) -> None:
    """Acquire an exclusive non-blocking lock on `fh`. Raises BlockingIOError
    if another process holds it."""
    if sys.platform == "win32":
        import msvcrt
        # LK_NBLCK = exclusive non-blocking. The "1 byte at offset 0" idiom
        # is the standard pattern for advisory locking on Windows.
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        except OSError as e:
            # Windows raises OSError(EACCES/EDEADLK) on contention. Translate
            # to BlockingIOError so callers have one exception type.
            raise BlockingIOError(str(e)) from e
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _read_metadata(path: pathlib.Path) -> dict[str, Any]:
    """Read informational metadata from the lock file. Returns {} on any
    error — metadata is for the error message only, never for correctness."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class WorkspaceLockError(RuntimeError):
    """A different bifrost session already holds the workspace lock."""

    def __init__(self, workspace: pathlib.Path, holder: dict[str, Any]) -> None:
        self.workspace = workspace
        self.holder = holder
        super().__init__(self._format())

    def _format(self) -> str:
        pid = self.holder.get("pid", "?")
        command = self.holder.get("command", "?")
        started = self.holder.get("started_at", "")
        when = ""
        if started:
            try:
                # Best-effort: parse the ISO timestamp and emit a friendlier
                # "started 14:32:01" suffix. Fall back to raw string.
                ts = datetime.fromisoformat(started)
                when = f"  (started {ts.astimezone().strftime('%Y-%m-%d %H:%M:%S')})"
            except ValueError:
                when = f"  (started {started})"
        return (
            f"another bifrost session is active in this workspace.\n"
            f"  PID {pid}  bifrost {command}{when}\n"
            f"Stop it first or wait for it to finish."
        )


class WorkspaceLock:
    """Acquire on `__enter__`, release on `__exit__` (or on process exit —
    the kernel cleans up the FD if we crash)."""

    def __init__(self, workspace: pathlib.Path, command: str) -> None:
        self.workspace = workspace.resolve()
        self.command = command
        self.path = _lock_path(self.workspace)
        self._fh: IO[Any] | None = None

    def __enter__(self) -> "WorkspaceLock":
        # In-process check first. POSIX flock is advisory and lets the same
        # process flock one path twice — without this guard, two sessions
        # in the same Python process would both succeed and ping-pong each
        # other.
        key = str(self.path)
        with _HELD_LOCK:
            if key in _HELD:
                raise WorkspaceLockError(self.workspace, _read_metadata(self.path))
            # Reserve before opening the file so two threads racing through
            # __enter__ can't both observe the empty set.
            _HELD.add(key)

        # `fh` is opened inside the try/except so any failure between
        # open() and the successful self._fh assignment closes it. The
        # outer except handles every remaining error path: BlockingIOError
        # from cross-process contention, OSError from open/seek/truncate,
        # KeyboardInterrupt mid-json.dump, anything. If we don't reach the
        # successful return, the FD is closed and the in-process
        # reservation is rolled back.
        fh: IO[Any] | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Open in append mode so we don't truncate before we've
            # acquired the lock — if someone else holds it, we'd otherwise
            # wipe their metadata. We seek+truncate AFTER acquiring.
            fh = open(self.path, "a+", encoding="utf-8")
            try:
                _platform_lock(fh)
            except BlockingIOError:
                holder = _read_metadata(self.path)
                raise WorkspaceLockError(self.workspace, holder)

            # We hold the lock. Now stamp our metadata. Failure here
            # doesn't break correctness — the lock is on the FD, not the
            # metadata. Log and continue.
            try:
                fh.seek(0)
                fh.truncate()
                json.dump({
                    "pid": os.getpid(),
                    "command": self.command,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }, fh)
                fh.flush()
            except OSError as e:
                logger.debug(f"could not write lock metadata: {e}")

            self._fh = fh
            return self
        except BaseException:
            if fh is not None and self._fh is None:
                try:
                    fh.close()
                except OSError as e:
                    logger.debug(f"error closing lock file during rollback: {e}")
            with _HELD_LOCK:
                _HELD.discard(key)
            raise

    def __exit__(self, *exc: Any) -> None:
        # Closing the FD releases the kernel-level lock. We deliberately do
        # NOT delete the file — leaving it lets the next holder write fresh
        # metadata, and a stale file with no FD holder doesn't block anyone
        # (the next acquire just claims it).
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError as e:
                logger.debug(f"error closing lock file: {e}")
            self._fh = None
        with _HELD_LOCK:
            _HELD.discard(str(self.path))




