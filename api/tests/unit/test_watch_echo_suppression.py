"""Integration-flavored tests for the watch echo-suppression path.

The reported bug: User B's `bifrost watch` receives a file via the
pull side (`_process_incoming`), writes it to disk, which fires the
watchdog observer, which queues the path for push, which round-trips
the same content back to the server. The fix is a path→hash cache on
`_WatchState`; these tests drive the pull and push functions together
against a mock client to confirm the echo is dropped and that a genuine
local edit still pushes.
"""
from __future__ import annotations

import base64
import json
import pathlib
from typing import Any

import pytest

from bifrost.cli import (
    _hash_for_cache,
    _process_incoming,
    _process_watch_batch,
    _WatchState,
)


# ---------------------------------------------------------------------------
# Mock client
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


class _RecordingClient:
    """Mock BifrostClient that records every POST and returns programmable
    responses based on URL.

    `server_files` is the canonical state the mock represents; reads pull
    from it, writes update it, deletes remove entries.
    """

    def __init__(self, server_files: dict[str, bytes]) -> None:
        self.server_files = dict(server_files)
        self.posted: list[tuple[str, dict[str, Any]]] = []

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _MockResponse:
        _ = headers
        payload = json or {}
        self.posted.append((url, payload))

        if url == "/api/files/read":
            path = payload["path"]
            if path in self.server_files:
                return _MockResponse(
                    200,
                    {"content": base64.b64encode(self.server_files[path]).decode("ascii")},
                )
            return _MockResponse(404)

        if url == "/api/files/write":
            path = payload["path"]
            raw = base64.b64decode(payload["content"])
            self.server_files[path] = raw
            return _MockResponse(204)

        if url == "/api/files/delete":
            self.server_files.pop(payload["path"], None)
            return _MockResponse(204)

        # _auto_validate_app makes GET-like probes via client.get; any other
        # unhandled endpoint returns 404 (harmless for the batch code path).
        return _MockResponse(404)

    async def get(self, url: str) -> _MockResponse:
        # _auto_validate_app queries /api/applications/{slug}; always 404 so
        # it short-circuits without doing validation work.
        _ = url
        return _MockResponse(404)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _push_count(client: Any) -> int:
    return sum(1 for url, _ in client.posted if url == "/api/files/write")


def _writes(client: Any) -> list[dict[str, Any]]:
    return [payload for url, payload in client.posted if url == "/api/files/write"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_populates_cache_and_suppresses_echo(tmp_path: pathlib.Path) -> None:
    """After a pull writes a file to disk, a watchdog-simulated observer
    event for that same file must NOT produce a push — the cache already
    knows the server has this content."""
    repo_path = "apps/demo/index.tsx"
    content = b"export default () => <div>hello</div>\n"

    state = _WatchState(tmp_path)
    client: Any = _RecordingClient(server_files={repo_path: content})

    # Simulate a WS event from another user pushing the file.
    await _process_incoming(
        client,
        files=[([repo_path], "user_a")],
        deletes=[],
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )

    # Pull side wrote the file to disk and recorded the hash.
    abs_path = tmp_path / repo_path
    assert abs_path.read_bytes() == content
    assert state.get_known_hash(repo_path) == _hash_for_cache(content)

    # Now simulate what the observer would do after that disk write: put
    # the file's absolute path into `changes` and run a push batch. The
    # cache lookup must drop it.
    posted_before = len(client.posted)
    await _process_watch_batch(
        client,
        changes={str(abs_path)},
        deletes=set(),
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )
    posted_after = len(client.posted)

    assert _push_count(client) == 0, (
        "Pull-then-observer-fire must not round-trip the pulled content "
        f"back to the server. Posts recorded: {client.posted[posted_before:posted_after]}"
    )


@pytest.mark.asyncio
async def test_real_local_edit_after_pull_still_pushes(tmp_path: pathlib.Path) -> None:
    """A genuine local edit after a pull must push — hash differs from cache."""
    repo_path = "apps/demo/index.tsx"
    initial = b"export default () => <div>v1</div>\n"
    edited = b"export default () => <div>v2</div>\n"

    state = _WatchState(tmp_path)
    client: Any = _RecordingClient(server_files={repo_path: initial})

    # Pull v1.
    await _process_incoming(
        client,
        files=[([repo_path], "user_a")],
        deletes=[],
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )
    abs_path = tmp_path / repo_path
    assert abs_path.read_bytes() == initial

    # User B edits locally to v2.
    abs_path.write_bytes(edited)

    # Observer fires, batch runs.
    await _process_watch_batch(
        client,
        changes={str(abs_path)},
        deletes=set(),
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )

    writes = _writes(client)
    assert len(writes) == 1, f"Expected exactly one push, got {len(writes)}"
    pushed_raw = base64.b64decode(writes[0]["content"])
    assert pushed_raw == edited
    # Cache now tracks the server's new content.
    assert state.get_known_hash(repo_path) == _hash_for_cache(edited)


@pytest.mark.asyncio
async def test_new_local_file_without_cache_entry_pushes(tmp_path: pathlib.Path) -> None:
    """Cold-start case: no cache entry means the file is new-to-this-session
    and must push."""
    repo_path = "apps/demo/brand-new.tsx"
    content = b"export const x = 1;\n"

    state = _WatchState(tmp_path)
    client: Any = _RecordingClient(server_files={})

    abs_path = tmp_path / repo_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)

    await _process_watch_batch(
        client,
        changes={str(abs_path)},
        deletes=set(),
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )

    writes = _writes(client)
    assert len(writes) == 1
    assert base64.b64decode(writes[0]["content"]) == content
    assert state.get_known_hash(repo_path) == _hash_for_cache(content)


@pytest.mark.asyncio
async def test_seeded_cache_drops_identical_local_file_push(tmp_path: pathlib.Path) -> None:
    """If /api/files/list seeded the cache with a hash that already matches
    the local file, the first observer event (e.g. editor touch on open)
    does not round-trip."""
    repo_path = "apps/demo/index.tsx"
    content = b"already synced\n"

    state = _WatchState(tmp_path)
    client: Any = _RecordingClient(server_files={repo_path: content})

    abs_path = tmp_path / repo_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)

    # Simulate the startup seed.
    state.seed_known_hashes({repo_path: _hash_for_cache(content)})

    await _process_watch_batch(
        client,
        changes={str(abs_path)},
        deletes=set(),
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )

    assert _push_count(client) == 0


@pytest.mark.asyncio
async def test_incoming_delete_evicts_cache(tmp_path: pathlib.Path) -> None:
    """A delete event from another user must remove the cache entry so a
    later recreation of the file with the same bytes still pushes."""
    repo_path = "apps/demo/gone.tsx"
    content = b"temporary\n"

    state = _WatchState(tmp_path)
    client: Any = _RecordingClient(server_files={repo_path: content})

    # Populate the cache via a pull.
    await _process_incoming(
        client,
        files=[([repo_path], "user_a")],
        deletes=[],
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )
    assert state.get_known_hash(repo_path) == _hash_for_cache(content)

    # User A deletes the file.
    await _process_incoming(
        client,
        files=[],
        deletes=[([repo_path], "user_a")],
        base_path=tmp_path,
        repo_prefix="",
        state=state,
    )
    assert state.get_known_hash(repo_path) is None
