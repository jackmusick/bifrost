"""Unit tests for watch known-server-hash cache primitives.

The cache gates `bifrost watch` pushes so that a file's observer event
triggered by our own pull-side `write_bytes` does not round-trip the
content back to the server. Covered here:

- `_hash_for_cache` collapses CRLF/LF so a hash of pre-push normalized
  bytes matches the server's md5 ETag (S3 stores what we sent).
- `_WatchState` get/set/forget/seed helpers round-trip correctly and are
  safe against concurrent mutation from the watchdog thread.
"""
from __future__ import annotations

import hashlib
import pathlib
import threading

from bifrost.cli import _hash_for_cache, _WatchState


# ---------------------------------------------------------------------------
# _hash_for_cache
# ---------------------------------------------------------------------------


def test_hash_for_cache_matches_server_etag_for_lf_bytes():
    raw = b"hello\nworld\n"
    assert _hash_for_cache(raw) == hashlib.md5(raw).hexdigest()


def test_hash_for_cache_normalizes_crlf_to_lf():
    crlf = b"hello\r\nworld\r\n"
    lf = b"hello\nworld\n"
    assert _hash_for_cache(crlf) == _hash_for_cache(lf)


def test_hash_for_cache_passes_binary_through_unchanged():
    binary = b"\x00\x01\x02\r\n\x03"
    assert _hash_for_cache(binary) == hashlib.md5(binary).hexdigest()


# ---------------------------------------------------------------------------
# _WatchState cache helpers
# ---------------------------------------------------------------------------


def _make_state() -> _WatchState:
    return _WatchState(pathlib.Path("/tmp/unused"))


def test_set_and_get_known_hash_round_trip():
    state = _make_state()
    state.set_known_hash("apps/x/page.tsx", "deadbeef")
    assert state.get_known_hash("apps/x/page.tsx") == "deadbeef"


def test_get_known_hash_missing_returns_none():
    state = _make_state()
    assert state.get_known_hash("does/not/exist") is None


def test_forget_known_hash_removes_entry_and_is_idempotent():
    state = _make_state()
    state.set_known_hash("p", "h")
    state.forget_known_hash("p")
    assert state.get_known_hash("p") is None
    state.forget_known_hash("p")  # does not raise


def test_seed_known_hashes_populates_and_overwrites():
    state = _make_state()
    state.set_known_hash("a", "old")
    state.seed_known_hashes({"a": "new", "b": "bh"})
    assert state.get_known_hash("a") == "new"
    assert state.get_known_hash("b") == "bh"


def test_concurrent_writes_are_safe():
    """The watchdog thread mutates the cache concurrently with the asyncio
    loop. Hammer both sides and confirm no lost updates or exceptions."""
    state = _make_state()
    iterations = 500

    def writer(key: str, value: str) -> None:
        for _ in range(iterations):
            state.set_known_hash(key, value)

    def reader() -> None:
        for _ in range(iterations):
            # Reads must not throw under concurrent mutation.
            state.get_known_hash("shared")

    threads = [
        threading.Thread(target=writer, args=("shared", "A")),
        threading.Thread(target=writer, args=("shared", "B")),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Final value is one of A or B — no partial writes, no crashes.
    assert state.get_known_hash("shared") in {"A", "B"}
