"""End-to-end style test for watch echo suppression using two real
watchdog observers against a shared fake server.

The unit tests in `test_watch_echo_suppression.py` prove the gating logic
by simulating observer events. This test goes further: it wires up two
real `watchdog.Observer` instances against two temp directories, with a
shared in-memory "server" that fans pushes from one session out as
incoming events on the other. The full path exercised is:

    A edits file
      -> A's real observer fires
      -> A's batch pushes to server
      -> server stores + notifies B
      -> B's _process_incoming writes file to disk
      -> B's real observer fires on that write        [ECHO RISK]
      -> B's batch MUST NOT re-push
      -> user edits on B
      -> B's real observer fires
      -> B's batch pushes to server
      -> server notifies A
      -> A's _process_incoming writes to disk
      -> A's real observer fires                      [REVERSE ECHO RISK]
      -> A's batch MUST NOT re-push

This is the closest a unit test can get to the reported two-user bug
without actually spinning up two `bifrost watch` processes.
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
from typing import Any

import pytest

from bifrost.cli import (
    _process_incoming,
    _process_watch_batch,
    _WatchChangeHandler,
    _WatchState,
)


# Observer events are delivered on a background thread. Give the thread
# a moment to drain after each filesystem mutation. 150ms is generous;
# inotify is usually sub-millisecond.
_OBSERVER_SETTLE_SECONDS = 0.15


class _MockResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


class _FakeServer:
    """In-memory stand-in for the Bifrost API.

    Stores files keyed by repo path. When one session writes, the server
    notifies every other registered session by appending a tuple to that
    session's `incoming_files` queue (mirroring what the real WebSocket
    broadcast would do).
    """

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        # session_id -> (_WatchState, user_name)
        self.sessions: dict[str, tuple[_WatchState, str]] = {}

    def register(self, state: _WatchState, user_name: str) -> None:
        self.sessions[state.session_id] = (state, user_name)

    def write(self, path: str, raw: bytes, origin_session_id: str, origin_user: str) -> None:
        self.files[path] = raw
        for sid, (state, _) in self.sessions.items():
            if sid == origin_session_id:
                continue
            state.queue_incoming_files([path], origin_user)

    def read(self, path: str) -> bytes | None:
        return self.files.get(path)


class _SessionClient:
    """Per-session client. Routes writes through `_FakeServer` so the
    other session sees an incoming file notification."""

    def __init__(self, server: _FakeServer, state: _WatchState, user_name: str) -> None:
        self.server = server
        self.state = state
        self.user_name = user_name
        self.push_count = 0

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _MockResponse:
        _ = headers
        payload = json or {}

        if url == "/api/files/read":
            path = payload["path"]
            raw = self.server.read(path)
            if raw is None:
                return _MockResponse(404)
            return _MockResponse(
                200,
                {"content": base64.b64encode(raw).decode("ascii")},
            )

        if url == "/api/files/write":
            path = payload["path"]
            raw = base64.b64decode(payload["content"])
            self.push_count += 1
            self.server.write(path, raw, self.state.session_id, self.user_name)
            return _MockResponse(204)

        if url == "/api/files/delete":
            self.server.files.pop(payload["path"], None)
            return _MockResponse(204)

        # _auto_validate_app and any other unhandled endpoint: 404 noop.
        return _MockResponse(404)

    async def get(self, url: str) -> _MockResponse:
        _ = url
        return _MockResponse(404)


class _Session:
    """Bundle of state + real observer + client for one "user"."""

    def __init__(
        self,
        name: str,
        root: pathlib.Path,
        server: _FakeServer,
    ) -> None:
        from watchdog.observers import Observer

        self.name = name
        self.root = root
        self.state = _WatchState(root)
        self.client = _SessionClient(server, self.state, user_name=name)
        self.handler = _WatchChangeHandler(self.state)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(root), recursive=True)  # type: ignore[arg-type]
        self.observer.start()
        server.register(self.state, name)

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=2.0)

    async def run_one_cycle(self) -> None:
        """Do what `_watch_loop` does in one tick: drain incoming, then
        drain observer events and push.

        Each drain is followed by a short sleep so the next observer
        event from a disk write has time to enqueue before the cycle
        completes.
        """
        # 1. Drain + process any incoming (pull from server).
        inc_files, inc_deletes = self.state.drain_incoming()
        if inc_files or inc_deletes:
            await _process_incoming(
                self.client,  # type: ignore[arg-type]
                inc_files,
                inc_deletes,
                self.root,
                repo_prefix="",
                state=self.state,
            )
        # Let the observer catch the events our pull writes just caused.
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)

        # 2. Drain + process observer events (push to server).
        changes, deletes = self.state.drain()
        if changes or deletes:
            await _process_watch_batch(
                self.client,  # type: ignore[arg-type]
                changes,
                deletes,
                self.root,
                repo_prefix="",
                state=self.state,
            )


@pytest.mark.asyncio
async def test_two_observers_no_pingpong(tmp_path: pathlib.Path) -> None:
    """Full two-user simulation with real watchdog observers.

    User A edits a file → B pulls it → B does not re-push → user edits
    on B → A pulls it → A does not re-push. At the end each user has
    pushed exactly once (their own genuine edit) — no echoes.
    """
    server = _FakeServer()
    a_root = tmp_path / "userA"
    b_root = tmp_path / "userB"
    a_root.mkdir()
    b_root.mkdir()

    sess_a = _Session("userA", a_root, server)
    sess_b = _Session("userB", b_root, server)

    try:
        # ── Round 1: A edits, B must not echo ──────────────────────────
        target = "apps/demo/index.tsx"
        (a_root / "apps" / "demo").mkdir(parents=True)
        (a_root / target).write_bytes(b"export default () => <div>v1</div>\n")
        # Let A's observer see the write.
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)

        # A's cycle: push v1 to server. B receives incoming notification.
        await sess_a.run_one_cycle()
        assert sess_a.client.push_count == 1, (
            f"A should have pushed v1 once, got {sess_a.client.push_count}"
        )

        # B's cycle: pull v1, write to disk, observer fires, batch runs.
        # The cache must drop the echo push.
        await sess_b.run_one_cycle()
        assert (b_root / target).read_bytes() == b"export default () => <div>v1</div>\n"
        assert sess_b.client.push_count == 0, (
            f"B must not echo A's push; got {sess_b.client.push_count} spurious push(es)"
        )

        # A's next cycle shouldn't spontaneously re-push either.
        await sess_a.run_one_cycle()
        assert sess_a.client.push_count == 1

        # ── Round 2: user edits on B, A must not echo ──────────────────
        (b_root / target).write_bytes(b"export default () => <div>v2</div>\n")
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)

        await sess_b.run_one_cycle()
        assert sess_b.client.push_count == 1, (
            f"B's real edit should push exactly once, got {sess_b.client.push_count}"
        )
        assert server.files[target] == b"export default () => <div>v2</div>\n"

        # A pulls v2. Its observer fires. Its batch must not re-push.
        await sess_a.run_one_cycle()
        assert (a_root / target).read_bytes() == b"export default () => <div>v2</div>\n"
        assert sess_a.client.push_count == 1, (
            f"A must not echo B's push; got {sess_a.client.push_count - 1} spurious push(es)"
        )

        # One more idle cycle each to catch any late straggler events.
        await sess_b.run_one_cycle()
        await sess_a.run_one_cycle()
        assert sess_a.client.push_count == 1
        assert sess_b.client.push_count == 1

    finally:
        sess_a.stop()
        sess_b.stop()


@pytest.mark.asyncio
async def test_two_observers_rapid_alternating_edits(tmp_path: pathlib.Path) -> None:
    """Stress the back-and-forth: A and B alternate edits on the same
    file several times. Each user's total push count must equal the
    number of edits they made — never more."""
    server = _FakeServer()
    a_root = tmp_path / "userA"
    b_root = tmp_path / "userB"
    a_root.mkdir()
    b_root.mkdir()

    sess_a = _Session("userA", a_root, server)
    sess_b = _Session("userB", b_root, server)

    target = "notes.txt"

    try:
        (a_root / target).write_bytes(b"a1\n")
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)
        await sess_a.run_one_cycle()
        await sess_b.run_one_cycle()

        (b_root / target).write_bytes(b"b1\n")
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)
        await sess_b.run_one_cycle()
        await sess_a.run_one_cycle()

        (a_root / target).write_bytes(b"a2\n")
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)
        await sess_a.run_one_cycle()
        await sess_b.run_one_cycle()

        (b_root / target).write_bytes(b"b2\n")
        await asyncio.sleep(_OBSERVER_SETTLE_SECONDS)
        await sess_b.run_one_cycle()
        await sess_a.run_one_cycle()

        # Let any late events drain.
        await sess_a.run_one_cycle()
        await sess_b.run_one_cycle()

        assert sess_a.client.push_count == 2, (
            f"A made 2 edits, expected 2 pushes, got {sess_a.client.push_count}"
        )
        assert sess_b.client.push_count == 2, (
            f"B made 2 edits, expected 2 pushes, got {sess_b.client.push_count}"
        )
        assert server.files[target] == b"b2\n"
        assert (a_root / target).read_bytes() == b"b2\n"
        assert (b_root / target).read_bytes() == b"b2\n"

    finally:
        sess_a.stop()
        sess_b.stop()
