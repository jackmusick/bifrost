# CLI Auth: Ephemeral Sessions + Multi-Instance Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the Bifrost CLI to target multiple instances on one machine via per-folder `.env`, add an ephemeral password-grant login that prints tokens (no persistence) for debug stacks, and migrate persistent token storage to the OS keychain with a JSON fallback for headless Linux — without losing the user's existing prod token.

**Architecture:** Two auth paths share a common token-resolution chain in `credentials.py`. The persistent path (browser device-code → keychain or JSON-fallback) is what's there today, refactored to be keyed by URL. The ephemeral path (`bifrost login --email --password --ephemeral`) POSTs to existing `/auth/login`, prints the three tokens to stdout, never touches disk. The CLI resolves tokens in this order on every request: `BIFROST_ACCESS_TOKEN`/`BIFROST_REFRESH_TOKEN` env vars → keychain entry for `BIFROST_API_URL` → legacy single-record JSON (lazy-migrated). Multi-instance support is just CWD-aware dotenv (already wired); the server side needs no changes.

**Tech Stack:** Python 3.11, `keyring` library (new dep, with `SecretStorage` extra for Linux), existing `python-dotenv` and `httpx`. Tests use pytest.

**Reference spec:** `docs/superpowers/specs/2026-04-29-cli-auth-ephemeral-sessions-design.md`
**Issue:** jackmusick/bifrost#149

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add `keyring` dependency. |
| `requirements.lock` | Regenerate | Pin transitive deps. |
| `api/bifrost/credentials.py` | Rewrite | Multi-record store with backend abstraction (Keyring / JSON / Env). Migration logic. |
| `api/bifrost/cli.py` | Modify | Extend `handle_login` with `--email/--password/--ephemeral` flags. |
| `api/bifrost/client.py` | Modify | Token resolution: env vars first, then `get_credentials(api_url=...)`. Refresh stays in-memory when source is env. |
| `api/tests/unit/test_credentials.py` | Create | Backend selection, multi-record store, migration, env-var precedence. |
| `api/tests/unit/test_cli_login_ephemeral.py` | Create | `--ephemeral` flag handling, MFA refusal, warning, output format. |
| `api/tests/e2e/platform/test_cli_ephemeral_login.py` | Create | Real `/auth/login` round-trip against the test stack. |
| `.claude/skills/bifrost-debug/SKILL.md` | Modify | Document the auto-`.env`-write step on `up`, removal on `down`. |

---

## Worktree setup

This plan must be executed in an isolated worktree. The orchestrator (the agent dispatching subagents) creates the worktree before Task 1; subagents work inside it.

- [ ] **Worktree setup**

```bash
cd /home/jack/GitHub/bifrost
git worktree add -b feat/cli-auth-ephemeral-149 .claude/worktrees/cli-auth-ephemeral
cd .claude/worktrees/cli-auth-ephemeral
gh issue develop 149 --branch feat/cli-auth-ephemeral-149 --repo jackmusick/bifrost 2>/dev/null || true
```

All subsequent paths are relative to the worktree root. Verify:

```bash
git rev-parse --abbrev-ref HEAD  # should print: feat/cli-auth-ephemeral-149
pwd                              # should end in: .claude/worktrees/cli-auth-ephemeral
```

---

## Task 1: Add `keyring` dependency

**Files:**
- Modify: `pyproject.toml`
- Regenerate: `requirements.lock`

- [ ] **Step 1: Add keyring to pyproject.toml**

Open `pyproject.toml` and find the dependencies section (the one containing `"python-dotenv"` and `"httpx"`). Add the keyring entry:

```toml
    "python-dotenv",
    "keyring>=24.0",  # OS-native credential storage; SecretStorage pulled in transitively on Linux
    "httpx",  # Async HTTP client
```

- [ ] **Step 2: Regenerate the lock**

```bash
docker run --rm -v "$PWD":/repo -w /repo python:3.14-slim sh -c \
  "pip install --quiet --require-hashes -r requirements-piptools.lock && \
   pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml"
```

Expected: `requirements.lock` updated with `keyring==…` and its transitive deps (`SecretStorage`, `jeepney`, etc. on Linux).

- [ ] **Step 3: Install the new dep into the venv used for tests**

```bash
.venv/bin/pip install keyring
```

Verify:

```bash
.venv/bin/python -c "import keyring; print(keyring.get_keyring())"
```

Expected on dev's xfce Linux: `<keyring.backends.SecretService.Keyring object at …>`. If it prints `<keyring.backends.fail.Keyring object at …>`, that's also OK — the fallback path will be exercised.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml requirements.lock
git commit -m "build(deps): add keyring for OS-native credential storage (#149)"
```

---

## Task 2: Backend abstraction — `Credentials` dataclass + `EnvBackend`

**Files:**
- Rewrite: `api/bifrost/credentials.py`
- Create: `api/tests/unit/test_credentials.py`

This task introduces the abstraction layer but keeps existing behavior wire-compatible. JSON backend is still the default until Task 3 wires keyring in.

- [ ] **Step 1: Write the failing test for `Credentials` and `EnvBackend`**

Create `api/tests/unit/test_credentials.py`:

```python
"""Tests for bifrost.credentials backend abstraction and multi-record store."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bifrost import credentials as creds_mod
from bifrost.credentials import Credentials, EnvBackend, JsonBackend


# ---------- Credentials dataclass ----------

class TestCredentialsDataclass:
    def test_round_trip_to_dict_and_back(self):
        c = Credentials(
            api_url="http://localhost:38421",
            access_token="at",
            refresh_token="rt",
            expires_at="2030-01-01T00:00:00+00:00",
        )
        d = c.to_dict()
        assert d == {
            "api_url": "http://localhost:38421",
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": "2030-01-01T00:00:00+00:00",
        }
        assert Credentials.from_dict(d) == c


# ---------- EnvBackend ----------

class TestEnvBackend:
    def test_returns_credentials_when_all_three_env_vars_set(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        result = backend.get("http://localhost:38421")
        assert result is not None
        assert result.access_token == "at"
        assert result.refresh_token == "rt"

    def test_returns_none_when_url_does_not_match(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        # Ask for a different URL than what's in BIFROST_API_URL
        assert backend.get("http://localhost:99999") is None

    def test_returns_none_when_access_token_missing(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.delenv("BIFROST_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("BIFROST_REFRESH_TOKEN", "rt")
        backend = EnvBackend()
        assert backend.get("http://localhost:38421") is None

    def test_returns_none_when_refresh_token_missing(self, monkeypatch):
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")
        monkeypatch.setenv("BIFROST_ACCESS_TOKEN", "at")
        monkeypatch.delenv("BIFROST_REFRESH_TOKEN", raising=False)
        backend = EnvBackend()
        assert backend.get("http://localhost:38421") is None

    def test_save_is_noop(self, monkeypatch):
        backend = EnvBackend()
        # Should not raise; env backend is read-only
        backend.save(Credentials("http://x", "at", "rt", "2030-01-01T00:00:00+00:00"))
        assert os.environ.get("BIFROST_ACCESS_TOKEN") in (None, "")  # didn't pollute env


# ---------- JsonBackend (multi-record) ----------

class TestJsonBackendMultiRecord:
    @pytest.fixture
    def tmp_creds_path(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        monkeypatch.setattr(creds_mod, "get_credentials_path", lambda: path)
        return path

    def test_save_and_get_single_record(self, tmp_creds_path):
        backend = JsonBackend()
        c = Credentials("http://localhost:38421", "at", "rt", "2030-01-01T00:00:00+00:00")
        backend.save(c)
        assert backend.get("http://localhost:38421") == c

    def test_save_two_urls_independently(self, tmp_creds_path):
        backend = JsonBackend()
        c1 = Credentials("http://localhost:38421", "at1", "rt1", "2030-01-01T00:00:00+00:00")
        c2 = Credentials("https://prod.example.com", "at2", "rt2", "2030-01-01T00:00:00+00:00")
        backend.save(c1)
        backend.save(c2)
        assert backend.get("http://localhost:38421") == c1
        assert backend.get("https://prod.example.com") == c2

    def test_clear_one_url_leaves_others(self, tmp_creds_path):
        backend = JsonBackend()
        c1 = Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00")
        c2 = Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00")
        backend.save(c1)
        backend.save(c2)
        backend.clear("http://a")
        assert backend.get("http://a") is None
        assert backend.get("http://b") == c2

    def test_list_returns_all_urls(self, tmp_creds_path):
        backend = JsonBackend()
        backend.save(Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00"))
        backend.save(Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00"))
        assert sorted(backend.list_urls()) == ["http://a", "http://b"]

    def test_get_returns_none_when_file_missing(self, tmp_creds_path):
        backend = JsonBackend()
        assert backend.get("http://anything") is None

    def test_file_permissions_are_0600(self, tmp_creds_path):
        import platform
        if platform.system() == "Windows":
            pytest.skip("POSIX permissions not applicable on Windows")
        backend = JsonBackend()
        backend.save(Credentials("http://a", "at", "rt", "2030-01-01T00:00:00+00:00"))
        mode = tmp_creds_path.stat().st_mode & 0o777
        assert mode == 0o600
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py -v
```

Expected: ImportError (`Credentials`, `EnvBackend`, `JsonBackend` don't exist yet).

- [ ] **Step 3: Rewrite `api/bifrost/credentials.py`**

Replace the entire file:

```python
"""
Bifrost SDK Credentials Storage

Multi-record credential storage for the CLI. Supports per-URL credentials
across multiple Bifrost instances simultaneously, with three backends:

- EnvBackend (read-only): BIFROST_API_URL + BIFROST_ACCESS_TOKEN + BIFROST_REFRESH_TOKEN
- KeyringBackend: OS-native credential storage via the `keyring` library
- JsonBackend: ~/.bifrost/credentials.json as a dict-of-URLs

Resolution order: env vars → persistent (keychain or JSON) → legacy single-record JSON.
"""

import json
import os
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

KEYRING_SERVICE = "bifrost"


# --------------------------------------------------------------------------- #
# Public dataclass
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Credentials:
    """A single set of CLI credentials for one Bifrost API URL."""

    api_url: str
    access_token: str
    refresh_token: str
    expires_at: str  # ISO 8601 with timezone

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Credentials":
        return cls(
            api_url=data["api_url"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
        )


# --------------------------------------------------------------------------- #
# Path helpers (unchanged)
# --------------------------------------------------------------------------- #

def get_config_dir() -> Path:
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Bifrost"
        return Path.home() / "Bifrost"
    return Path.home() / ".bifrost"


def get_credentials_path() -> Path:
    return get_config_dir() / "credentials.json"


# --------------------------------------------------------------------------- #
# Backend protocol + implementations
# --------------------------------------------------------------------------- #

class Backend(Protocol):
    def get(self, api_url: str) -> Credentials | None: ...
    def save(self, creds: Credentials) -> None: ...
    def clear(self, api_url: str) -> None: ...
    def list_urls(self) -> list[str]: ...


class EnvBackend:
    """Read-only backend that returns credentials assembled from env vars."""

    def get(self, api_url: str) -> Credentials | None:
        env_url = os.environ.get("BIFROST_API_URL", "").rstrip("/")
        if not env_url or env_url != api_url.rstrip("/"):
            return None
        access = os.environ.get("BIFROST_ACCESS_TOKEN", "")
        refresh = os.environ.get("BIFROST_REFRESH_TOKEN", "")
        if not access or not refresh:
            return None
        # Env-sourced credentials have no recorded expiry; use a far-future
        # placeholder so is_token_expired() doesn't trigger automatic refresh.
        # Refresh-on-401 still works in client.py.
        return Credentials(
            api_url=env_url,
            access_token=access,
            refresh_token=refresh,
            expires_at="2099-01-01T00:00:00+00:00",
        )

    def save(self, creds: Credentials) -> None:
        # Env backend is read-only — saves silently noop.
        return

    def clear(self, api_url: str) -> None:
        return

    def list_urls(self) -> list[str]:
        env_url = os.environ.get("BIFROST_API_URL", "").rstrip("/")
        if env_url and os.environ.get("BIFROST_ACCESS_TOKEN") and os.environ.get("BIFROST_REFRESH_TOKEN"):
            return [env_url]
        return []


class JsonBackend:
    """Multi-record JSON store at ~/.bifrost/credentials.json."""

    def _load(self) -> dict[str, dict]:
        path = get_credentials_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        # Multi-record format: {url: {fields...}}. If we see the legacy
        # top-level shape, the migration path will rewrite it.
        if isinstance(data, dict) and "api_url" in data and "access_token" in data:
            return {}  # legacy single-record; handled by migration logic
        if not isinstance(data, dict):
            return {}
        return data

    def _save(self, store: dict[str, dict]) -> None:
        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        if platform.system() != "Windows":
            config_dir.chmod(0o700)
        path = get_credentials_path()
        with open(path, "w") as f:
            json.dump(store, f, indent=2)
        if platform.system() != "Windows":
            path.chmod(0o600)

    def get(self, api_url: str) -> Credentials | None:
        store = self._load()
        record = store.get(api_url.rstrip("/"))
        if not record:
            return None
        try:
            return Credentials.from_dict(record)
        except KeyError:
            return None

    def save(self, creds: Credentials) -> None:
        store = self._load()
        store[creds.api_url.rstrip("/")] = creds.to_dict()
        self._save(store)

    def clear(self, api_url: str) -> None:
        store = self._load()
        store.pop(api_url.rstrip("/"), None)
        self._save(store)

    def list_urls(self) -> list[str]:
        return list(self._load().keys())


# KeyringBackend defined in Task 3.


# --------------------------------------------------------------------------- #
# Backend selection (will be expanded in Task 3)
# --------------------------------------------------------------------------- #

def _select_persistent_backend() -> Backend:
    """Choose the persistent backend. Task 3 wires keyring in."""
    return JsonBackend()


_persistent_backend: Backend | None = None


def get_persistent_backend() -> Backend:
    """Memoized accessor for the persistent backend."""
    global _persistent_backend
    if _persistent_backend is None:
        _persistent_backend = _select_persistent_backend()
    return _persistent_backend


def _reset_persistent_backend_for_tests() -> None:
    """Clear the cached backend so tests can swap it out."""
    global _persistent_backend
    _persistent_backend = None


# --------------------------------------------------------------------------- #
# Public functions
# --------------------------------------------------------------------------- #

def get_credentials(api_url: str | None = None) -> dict | None:
    """
    Resolve credentials for a given API URL.

    Resolution order: env vars → persistent backend.

    If api_url is None, falls back to:
      1. BIFROST_API_URL env var
      2. The first URL in the persistent backend (back-compat for users
         who only have one set)

    Returns: dict with keys api_url/access_token/refresh_token/expires_at,
    or None. Returns dict (not Credentials) for back-compat with existing
    callers in client.py / cli.py.
    """
    if api_url is None:
        api_url = os.environ.get("BIFROST_API_URL", "").rstrip("/")
        if not api_url:
            urls = get_persistent_backend().list_urls()
            if not urls:
                return None
            api_url = urls[0]

    api_url = api_url.rstrip("/")
    env_creds = EnvBackend().get(api_url)
    if env_creds is not None:
        return env_creds.to_dict()

    creds = get_persistent_backend().get(api_url)
    if creds is not None:
        return creds.to_dict()
    return None


def save_credentials(
    api_url: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    """Persist credentials to the active backend (keychain or JSON)."""
    creds = Credentials(
        api_url=api_url.rstrip("/"),
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
    get_persistent_backend().save(creds)


def clear_credentials(api_url: str | None = None) -> None:
    """Remove a single URL's credentials from the persistent backend."""
    if api_url is None:
        # Back-compat: when called without a URL, clear the current resolved one.
        urls = get_persistent_backend().list_urls()
        if len(urls) == 1:
            api_url = urls[0]
        elif env_url := os.environ.get("BIFROST_API_URL", "").rstrip("/"):
            api_url = env_url
        else:
            # Nothing to do.
            return
    get_persistent_backend().clear(api_url.rstrip("/"))


def list_credentials() -> list[str]:
    """Return all URLs that have stored credentials."""
    return get_persistent_backend().list_urls()


def is_token_expired(buffer_seconds: int = 60, api_url: str | None = None) -> bool:
    """Return True if the resolved credentials' access token is expired."""
    creds = get_credentials(api_url)
    if not creds:
        return True
    expires_at_str = creds.get("expires_at")
    if not expires_at_str:
        return True
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (expires_at - now).total_seconds() <= buffer_seconds
    except (ValueError, AttributeError):
        return True
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py -v
```

Expected: All tests in `TestCredentialsDataclass`, `TestEnvBackend`, and `TestJsonBackendMultiRecord` pass.

- [ ] **Step 5: Run the existing client tests to confirm no regression**

```bash
.venv/bin/pytest api/tests/unit/ -k "credentials or client" -v
```

Expected: PASS. The `get_credentials()` / `save_credentials()` public surface still returns dicts shaped the same way the old code did.

- [ ] **Step 6: Commit**

```bash
git add api/bifrost/credentials.py api/tests/unit/test_credentials.py
git commit -m "refactor(credentials): introduce backend abstraction + multi-record JSON store (#149)"
```

---

## Task 3: Add `KeyringBackend` and wire backend selection

**Files:**
- Modify: `api/bifrost/credentials.py`
- Modify: `api/tests/unit/test_credentials.py`

- [ ] **Step 1: Append failing tests for KeyringBackend and backend selection**

Append to `api/tests/unit/test_credentials.py`:

```python
# ---------- KeyringBackend ----------

class FakeKeyring:
    """In-memory keyring used to test KeyringBackend without touching the OS."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str):
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str):
        self.store.pop((service, username), None)


class FakeFailKeyring:
    """Keyring that raises NoKeyringError on every operation, mimicking headless Linux."""

    def get_password(self, *_a, **_kw):
        import keyring.errors
        raise keyring.errors.NoKeyringError("no backend")

    def set_password(self, *_a, **_kw):
        import keyring.errors
        raise keyring.errors.NoKeyringError("no backend")

    def delete_password(self, *_a, **_kw):
        import keyring.errors
        raise keyring.errors.NoKeyringError("no backend")


class TestKeyringBackend:
    @pytest.fixture
    def fake_kr(self, monkeypatch):
        from bifrost.credentials import KeyringBackend
        fake = FakeKeyring()
        backend = KeyringBackend(_keyring=fake)
        return backend, fake

    def test_save_and_get_round_trip(self, fake_kr):
        backend, _ = fake_kr
        c = Credentials("http://localhost:38421", "at", "rt", "2030-01-01T00:00:00+00:00")
        backend.save(c)
        assert backend.get("http://localhost:38421") == c

    def test_save_two_urls_independently(self, fake_kr):
        backend, fake = fake_kr
        c1 = Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00")
        c2 = Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00")
        backend.save(c1)
        backend.save(c2)
        assert backend.get("http://a") == c1
        assert backend.get("http://b") == c2

    def test_clear_one_leaves_others(self, fake_kr):
        backend, _ = fake_kr
        backend.save(Credentials("http://a", "at1", "rt1", "2030-01-01T00:00:00+00:00"))
        backend.save(Credentials("http://b", "at2", "rt2", "2030-01-01T00:00:00+00:00"))
        backend.clear("http://a")
        assert backend.get("http://a") is None
        assert backend.get("http://b") is not None

    def test_list_urls_via_index(self, fake_kr):
        backend, _ = fake_kr
        backend.save(Credentials("http://a", "at", "rt", "2030-01-01T00:00:00+00:00"))
        backend.save(Credentials("http://b", "at", "rt", "2030-01-01T00:00:00+00:00"))
        assert sorted(backend.list_urls()) == ["http://a", "http://b"]


# ---------- Backend selection ----------

class TestBackendSelection:
    def test_keyring_available_returns_keyring_backend(self, monkeypatch):
        from bifrost.credentials import KeyringBackend, _select_persistent_backend
        creds_mod._reset_persistent_backend_for_tests()
        monkeypatch.setattr("keyring.get_keyring", lambda: FakeKeyring())
        monkeypatch.setattr("keyring.get_password", lambda s, u: None)
        backend = _select_persistent_backend()
        assert isinstance(backend, KeyringBackend)

    def test_no_keyring_falls_back_to_json(self, monkeypatch, capsys):
        from bifrost.credentials import JsonBackend, _select_persistent_backend
        creds_mod._reset_persistent_backend_for_tests()
        import keyring.errors
        monkeypatch.setattr("keyring.get_keyring", lambda: FakeFailKeyring())
        monkeypatch.setattr(
            "keyring.get_password",
            lambda s, u: (_ for _ in ()).throw(keyring.errors.NoKeyringError("no backend")),
        )
        backend = _select_persistent_backend()
        assert isinstance(backend, JsonBackend)
        # On non-keyring systems we want a one-time stderr warning so users know.
        captured = capsys.readouterr()
        assert "keyring" in captured.err.lower()
        assert "fallback" in captured.err.lower() or "falling back" in captured.err.lower()

    def test_keyring_import_error_falls_back_to_json(self, monkeypatch):
        from bifrost.credentials import JsonBackend, _select_persistent_backend
        creds_mod._reset_persistent_backend_for_tests()
        import sys
        monkeypatch.setitem(sys.modules, "keyring", None)
        backend = _select_persistent_backend()
        assert isinstance(backend, JsonBackend)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py::TestKeyringBackend api/tests/unit/test_credentials.py::TestBackendSelection -v
```

Expected: ImportError or AttributeError (`KeyringBackend` not yet defined).

- [ ] **Step 3: Add `KeyringBackend` and update `_select_persistent_backend`**

In `api/bifrost/credentials.py`, replace the `# KeyringBackend defined in Task 3.` placeholder with:

```python
class KeyringBackend:
    """OS-native credential storage via the `keyring` library.

    URLs are tracked in a separate index entry because keyring backends
    don't expose a `list` operation across (service, username) pairs.
    """

    INDEX_USERNAME = "__index__"

    def __init__(self, _keyring=None):
        if _keyring is None:
            import keyring as _keyring  # noqa: PLR0402
        self._kr = _keyring

    def _load_index(self) -> set[str]:
        raw = self._kr.get_password(KEYRING_SERVICE, self.INDEX_USERNAME)
        if not raw:
            return set()
        try:
            return set(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            return set()

    def _save_index(self, index: set[str]) -> None:
        self._kr.set_password(KEYRING_SERVICE, self.INDEX_USERNAME, json.dumps(sorted(index)))

    def get(self, api_url: str) -> Credentials | None:
        api_url = api_url.rstrip("/")
        raw = self._kr.get_password(KEYRING_SERVICE, api_url)
        if not raw:
            return None
        try:
            return Credentials.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, creds: Credentials) -> None:
        api_url = creds.api_url.rstrip("/")
        self._kr.set_password(KEYRING_SERVICE, api_url, json.dumps(creds.to_dict()))
        idx = self._load_index()
        idx.add(api_url)
        self._save_index(idx)

    def clear(self, api_url: str) -> None:
        api_url = api_url.rstrip("/")
        try:
            self._kr.delete_password(KEYRING_SERVICE, api_url)
        except Exception:
            pass  # already absent
        idx = self._load_index()
        idx.discard(api_url)
        self._save_index(idx)

    def list_urls(self) -> list[str]:
        return sorted(self._load_index())
```

Then replace the `_select_persistent_backend` function:

```python
def _select_persistent_backend() -> Backend:
    """
    Choose the persistent backend.

    Order: try `keyring` (probe with a no-op read so headless Linux fails
    fast at startup), fall back to JSON. On fallback, print a one-time
    stderr warning so users know why their tokens aren't in the OS keychain.
    """
    import sys

    try:
        import keyring
        import keyring.errors
    except ImportError:
        return JsonBackend()

    try:
        backend_obj = keyring.get_keyring()
        # Probe — surfaces NoKeyringError / SecretServiceError / DBusException
        # when the backend is nominally available but the OS service isn't.
        keyring.get_password(KEYRING_SERVICE, "__probe__")
        return KeyringBackend(_keyring=keyring)
    except (keyring.errors.NoKeyringError, keyring.errors.KeyringError, Exception) as e:
        print(
            f"warning: OS keychain unavailable ({type(e).__name__}); "
            "falling back to ~/.bifrost/credentials.json. "
            "Install/enable a keyring service to upgrade.",
            file=sys.stderr,
        )
        return JsonBackend()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py -v
```

Expected: All tests pass, including the new `TestKeyringBackend` and `TestBackendSelection` classes.

- [ ] **Step 5: Smoke-test on the dev's actual machine**

```bash
.venv/bin/python -c "
from bifrost.credentials import _reset_persistent_backend_for_tests, get_persistent_backend
_reset_persistent_backend_for_tests()
b = get_persistent_backend()
print(type(b).__name__)
"
```

Expected on dev's xfce Linux: `KeyringBackend`. If `JsonBackend` with a stderr warning, that's the expected fallback path — note this in the eventual PR description so the cross-platform table can record it.

- [ ] **Step 6: Commit**

```bash
git add api/bifrost/credentials.py api/tests/unit/test_credentials.py
git commit -m "feat(credentials): add KeyringBackend with JSON fallback (#149)"
```

---

## Task 4: Migration — legacy single-record JSON → multi-record store

**Files:**
- Modify: `api/bifrost/credentials.py`
- Modify: `api/tests/unit/test_credentials.py`

- [ ] **Step 1: Append failing migration tests**

Append to `api/tests/unit/test_credentials.py`:

```python
# ---------- Legacy migration ----------

class TestLegacyMigration:
    @pytest.fixture
    def tmp_creds_path(self, tmp_path, monkeypatch):
        path = tmp_path / "credentials.json"
        monkeypatch.setattr(creds_mod, "get_credentials_path", lambda: path)
        creds_mod._reset_persistent_backend_for_tests()
        return path

    def _write_legacy(self, path: Path):
        path.write_text(json.dumps({
            "api_url": "https://prod.example.com",
            "access_token": "legacy_at",
            "refresh_token": "legacy_rt",
            "expires_at": "2030-01-01T00:00:00+00:00",
        }))

    def test_migrate_legacy_to_json_backend(self, tmp_creds_path, monkeypatch):
        # Force JSON backend
        monkeypatch.setattr(creds_mod, "_select_persistent_backend", lambda: JsonBackend())
        creds_mod._reset_persistent_backend_for_tests()
        self._write_legacy(tmp_creds_path)

        result = creds_mod.get_credentials("https://prod.example.com")
        assert result is not None
        assert result["access_token"] == "legacy_at"

        # The file should now be in dict-of-URLs format
        data = json.loads(tmp_creds_path.read_text())
        assert "https://prod.example.com" in data
        assert data["https://prod.example.com"]["access_token"] == "legacy_at"
        assert "api_url" not in data  # no top-level legacy keys

    def test_migrate_legacy_to_keyring_backend(self, tmp_creds_path, monkeypatch):
        from bifrost.credentials import KeyringBackend
        fake = FakeKeyring()
        monkeypatch.setattr(
            creds_mod,
            "_select_persistent_backend",
            lambda: KeyringBackend(_keyring=fake),
        )
        creds_mod._reset_persistent_backend_for_tests()
        self._write_legacy(tmp_creds_path)

        result = creds_mod.get_credentials("https://prod.example.com")
        assert result is not None
        assert result["access_token"] == "legacy_at"

        # Keyring should have the entry
        raw = fake.get_password(KEYRING_SERVICE, "https://prod.example.com")
        assert raw is not None
        assert json.loads(raw)["access_token"] == "legacy_at"

        # JSON file is now an empty dict (marker that migration ran)
        data = json.loads(tmp_creds_path.read_text())
        assert data == {}

    def test_migrate_idempotent(self, tmp_creds_path, monkeypatch):
        monkeypatch.setattr(creds_mod, "_select_persistent_backend", lambda: JsonBackend())
        creds_mod._reset_persistent_backend_for_tests()
        self._write_legacy(tmp_creds_path)

        # First call migrates
        creds_mod.get_credentials("https://prod.example.com")
        # Second call should still work, no exceptions
        result = creds_mod.get_credentials("https://prod.example.com")
        assert result["access_token"] == "legacy_at"

    def test_migration_failure_preserves_legacy_file(self, tmp_creds_path, monkeypatch):
        """If the new backend's save fails, the legacy file is untouched."""
        from bifrost.credentials import KeyringBackend

        class ExplodingKeyring:
            def get_password(self, *_a, **_kw):
                return None

            def set_password(self, *_a, **_kw):
                raise RuntimeError("disk full")

            def delete_password(self, *_a, **_kw):
                pass

        monkeypatch.setattr(
            creds_mod,
            "_select_persistent_backend",
            lambda: KeyringBackend(_keyring=ExplodingKeyring()),
        )
        creds_mod._reset_persistent_backend_for_tests()
        self._write_legacy(tmp_creds_path)
        original = tmp_creds_path.read_text()

        # Migration should fail silently and the legacy data should still be returned
        result = creds_mod.get_credentials("https://prod.example.com")
        assert result is not None
        assert result["access_token"] == "legacy_at"
        # File untouched on failure
        assert tmp_creds_path.read_text() == original
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py::TestLegacyMigration -v
```

Expected: failures (migration not yet wired in).

- [ ] **Step 3: Add migration logic to `get_credentials`**

In `api/bifrost/credentials.py`, replace the `get_credentials` function with:

```python
def _try_migrate_legacy() -> Credentials | None:
    """
    If ~/.bifrost/credentials.json contains the legacy single-record format,
    migrate it into the active persistent backend and return the parsed
    record. On failure, leave the legacy file untouched and return the
    parsed record anyway so callers still get the credentials.
    """
    path = get_credentials_path()
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict) or "api_url" not in raw or "access_token" not in raw:
        return None
    try:
        legacy = Credentials.from_dict(raw)
    except KeyError:
        return None

    # Try to migrate.
    try:
        get_persistent_backend().save(legacy)
    except Exception:
        # Migration failed (disk full, keyring locked, etc.).
        # Return the parsed legacy record so the caller still works,
        # but don't touch the file. Next call will retry migration.
        return legacy

    # Migration succeeded. Rewrite the file as an empty dict (marker).
    # If the backend is JsonBackend, save() already rewrote it correctly
    # and our marker write would clobber it — so check first.
    try:
        with open(path, "r") as f:
            new_contents = json.load(f)
        if isinstance(new_contents, dict) and "api_url" in new_contents:
            # Backend wasn't JSON (e.g. keyring), so legacy still on disk; clear it.
            with open(path, "w") as f:
                json.dump({}, f)
            if platform.system() != "Windows":
                path.chmod(0o600)
    except (json.JSONDecodeError, OSError):
        pass

    return legacy


def get_credentials(api_url: str | None = None) -> dict | None:
    """
    Resolve credentials for a given API URL.

    Resolution order:
      1. Env vars (EnvBackend) — for ephemeral sessions.
      2. Persistent backend (keychain or JSON) — for long-lived sessions.
      3. Legacy single-record JSON — lazily migrated.

    If api_url is None, falls back to:
      a. BIFROST_API_URL env var
      b. The first URL stored in the persistent backend
      c. The legacy record's URL (after migration)
    """
    # Resolve URL if not given
    if api_url is None:
        api_url = os.environ.get("BIFROST_API_URL", "").rstrip("/")
        if not api_url:
            urls = get_persistent_backend().list_urls()
            if urls:
                api_url = urls[0]
            else:
                # Try the legacy file as a last resort to learn the URL.
                legacy = _try_migrate_legacy()
                if legacy is None:
                    return None
                return legacy.to_dict()

    api_url = api_url.rstrip("/")

    # 1. Env vars
    env_creds = EnvBackend().get(api_url)
    if env_creds is not None:
        return env_creds.to_dict()

    # 2. Persistent backend
    creds = get_persistent_backend().get(api_url)
    if creds is not None:
        return creds.to_dict()

    # 3. Legacy fallback (and migrate if found)
    legacy = _try_migrate_legacy()
    if legacy is not None and legacy.api_url.rstrip("/") == api_url:
        return legacy.to_dict()
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py -v
```

Expected: All tests pass, including `TestLegacyMigration`.

- [ ] **Step 5: Manually verify migration with a synthetic legacy file**

```bash
mkdir -p /tmp/bifrost-mig-test
cat > /tmp/bifrost-mig-test/credentials.json <<'JSON'
{
  "api_url": "https://example.com",
  "access_token": "synthetic_at",
  "refresh_token": "synthetic_rt",
  "expires_at": "2030-01-01T00:00:00+00:00"
}
JSON
HOME=/tmp/bifrost-mig-test BIFROST_API_URL=https://example.com .venv/bin/python -c "
import os
# Point the path at our test dir
from bifrost import credentials
credentials.get_config_dir = lambda: __import__('pathlib').Path('/tmp/bifrost-mig-test')
credentials.get_credentials_path = lambda: __import__('pathlib').Path('/tmp/bifrost-mig-test/credentials.json')
credentials._reset_persistent_backend_for_tests()
result = credentials.get_credentials('https://example.com')
print('migrated record:', result)
import json
print('file contents after:', open('/tmp/bifrost-mig-test/credentials.json').read())
"
rm -rf /tmp/bifrost-mig-test
```

Expected: `migrated record: {...synthetic_at...}` and the file is either rewritten as `{}` (keyring path) or as a dict containing the URL key (JSON path). **Importantly, the access_token must still be retrievable.**

- [ ] **Step 6: Commit**

```bash
git add api/bifrost/credentials.py api/tests/unit/test_credentials.py
git commit -m "feat(credentials): lazy migration of legacy single-record format (#149)"
```

---

## Task 5: Add `--ephemeral` flag to `bifrost login`

**Files:**
- Modify: `api/bifrost/cli.py`
- Create: `api/tests/unit/test_cli_login_ephemeral.py`

- [ ] **Step 1: Write the failing tests**

Create `api/tests/unit/test_cli_login_ephemeral.py`:

```python
"""Tests for `bifrost login --ephemeral` flag handling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from bifrost import cli


def _stub_post(json_payload: dict, status_code: int = 200):
    """Build an httpx.AsyncClient stand-in whose .post() returns the given payload."""
    class StubResponse:
        def __init__(self, code, payload):
            self.status_code = code
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    class StubClient:
        def __init__(self, *_a, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, _url, json=None):
            return StubResponse(status_code, json_payload)

    return StubClient


class TestEphemeralLoginFlagParsing:
    def test_ephemeral_without_email_password_errors(self, capsys):
        rc = cli.handle_login(["--ephemeral", "--url", "http://localhost:38421"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "--email" in err and "--password" in err

    def test_email_password_without_ephemeral_errors(self, capsys):
        rc = cli.handle_login(["--email", "x@y", "--password", "p"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "--ephemeral" in err

    def test_ephemeral_without_url_or_env_errors(self, capsys, monkeypatch):
        monkeypatch.delenv("BIFROST_API_URL", raising=False)
        rc = cli.handle_login(["--ephemeral", "--email", "x@y", "--password", "p"])
        assert rc != 0
        err = capsys.readouterr().err
        assert "URL" in err or "url" in err


class TestEphemeralLoginSuccess:
    def test_prints_three_lines_and_warning(self, capsys, monkeypatch):
        stub = _stub_post({
            "access_token": "at_value",
            "refresh_token": "rt_value",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 0

        captured = capsys.readouterr()
        # Three env-var-style lines on stdout
        out_lines = [l for l in captured.out.splitlines() if l.strip()]
        assert "BIFROST_API_URL=http://localhost:38421" in out_lines
        assert "BIFROST_ACCESS_TOKEN=at_value" in out_lines
        assert "BIFROST_REFRESH_TOKEN=rt_value" in out_lines

        # Warning to stderr
        assert "MFA" in captured.err
        assert "ephemeral" in captured.err.lower()

    def test_does_not_write_to_disk(self, capsys, monkeypatch, tmp_path):
        stub = _stub_post({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)
        # Redirect any save target into tmp_path
        monkeypatch.setattr(
            "bifrost.credentials.get_credentials_path",
            lambda: tmp_path / "credentials.json",
        )

        cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])

        assert not (tmp_path / "credentials.json").exists()


class TestEphemeralLoginMfaRefusal:
    def test_mfa_required_returns_exit_2(self, capsys, monkeypatch):
        stub = _stub_post({"mfa_required": True, "mfa_token": "mt", "expires_in": 300})
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 2
        err = capsys.readouterr().err
        assert "MFA" in err
        assert "BIFROST_MFA_ENABLED" in err or "browser" in err.lower()

    def test_mfa_setup_required_returns_exit_2(self, capsys, monkeypatch):
        stub = _stub_post({"mfa_setup_required": True, "mfa_token": "mt", "expires_in": 300})
        monkeypatch.setattr("httpx.AsyncClient", stub)

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", "http://localhost:38421",
        ])
        assert rc == 2


class TestEphemeralLoginUsesBifrostApiUrl:
    def test_falls_back_to_env_var_for_url(self, capsys, monkeypatch):
        stub = _stub_post({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 1800,
        })
        monkeypatch.setattr("httpx.AsyncClient", stub)
        monkeypatch.setenv("BIFROST_API_URL", "http://localhost:38421")

        rc = cli.handle_login([
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
        ])
        assert rc == 0
        out_lines = capsys.readouterr().out.splitlines()
        assert "BIFROST_API_URL=http://localhost:38421" in out_lines
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest api/tests/unit/test_cli_login_ephemeral.py -v
```

Expected: All fail (flag handling not yet implemented).

- [ ] **Step 3: Add `ephemeral_login_flow` and update `handle_login`**

In `api/bifrost/cli.py`, add this function near the other `login_flow` definitions (after `login_flow`, before `logout_flow`):

```python
async def ephemeral_login_flow(api_url: str, email: str, password: str) -> tuple[int, dict | None]:
    """
    Password-grant login that does NOT persist tokens.

    Returns (exit_code, payload). On success, payload is the parsed JSON
    response from /auth/login containing access_token / refresh_token.
    """
    # Always print the warning before doing anything.
    print(
        "⚠️  Password-grant login is for ephemeral, isolated development stacks only.\n"
        "   Do not run a Bifrost instance with MFA disabled in production.",
        file=sys.stderr,
    )

    api_url = api_url.rstrip("/")
    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
            response = await client.post("/auth/login", json={"email": email, "password": password})
            if response.status_code != 200:
                print(f"Error: /auth/login returned HTTP {response.status_code}", file=sys.stderr)
                return 1, None
            data = response.json()

        # MFA paths
        if data.get("mfa_required") or data.get("mfa_setup_required"):
            print(
                "Error: this instance has MFA enabled. Ephemeral password login only works for "
                "instances with BIFROST_MFA_ENABLED=false. Use `bifrost login` (no flags) for "
                "the browser flow.",
                file=sys.stderr,
            )
            return 2, None

        if "access_token" not in data or "refresh_token" not in data:
            print("Error: /auth/login response missing access_token/refresh_token", file=sys.stderr)
            return 1, None

        return 0, data
    except Exception as e:
        print(f"Error during ephemeral login: {e}", file=sys.stderr)
        return 1, None
```

Now replace the entire `handle_login` function:

```python
def handle_login(args: list[str]) -> int:
    """Handle 'bifrost login' command."""
    api_url = None
    auto_open = True
    ephemeral = False
    email: str | None = None
    password: str | None = None

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
        elif arg == "--ephemeral":
            ephemeral = True
            i += 1
        elif arg == "--email":
            if i + 1 >= len(args):
                print("Error: --email requires a value", file=sys.stderr)
                return 1
            email = args[i + 1]
            i += 2
        elif arg == "--password":
            if i + 1 >= len(args):
                print("Error: --password requires a value", file=sys.stderr)
                return 1
            password = args[i + 1]
            i += 2
        elif arg in ("--help", "-h"):
            print("""
Usage: bifrost login [options]

Authenticate with Bifrost. Two modes:

Persistent (default): Browser device-code flow; tokens stored in OS keychain.
Ephemeral: Password-grant flow; tokens printed to stdout, never persisted.
           For isolated debug stacks only — refuses if MFA is enabled.

Options:
  --url, -u URL         API URL (default: BIFROST_API_URL or http://localhost:8000)
  --no-browser, -n      Don't automatically open browser (persistent mode only)
  --ephemeral           Use password-grant flow; requires --email and --password
  --email EMAIL         Email for ephemeral login
  --password PASSWORD   Password for ephemeral login
  --help, -h            Show this help message

Examples:
  bifrost login
  bifrost login --url https://app.gobifrost.com
  bifrost login --ephemeral --email dev@gobifrost.com --password password \\
                --url http://localhost:38421
""".strip())
            return 0
        else:
            print(f"Unknown option: {arg}", file=sys.stderr)
            return 1

    # Validate flag combinations.
    if ephemeral and (email is None or password is None):
        print("Error: --ephemeral requires both --email and --password", file=sys.stderr)
        return 1
    if (email is not None or password is not None) and not ephemeral:
        print("Error: --email and --password require --ephemeral", file=sys.stderr)
        return 1

    if ephemeral:
        # Resolve URL: --url > BIFROST_API_URL env var > error.
        if not api_url:
            api_url = os.environ.get("BIFROST_API_URL", "").rstrip("/")
        if not api_url:
            print(
                "Error: ephemeral login requires --url or BIFROST_API_URL env var "
                "(no fallback default to avoid logging into the wrong stack)",
                file=sys.stderr,
            )
            return 1

        rc, data = asyncio.run(ephemeral_login_flow(api_url, email, password))
        if rc == 0 and data is not None:
            print(f"BIFROST_API_URL={api_url}")
            print(f"BIFROST_ACCESS_TOKEN={data['access_token']}")
            print(f"BIFROST_REFRESH_TOKEN={data['refresh_token']}")
        return rc

    # Persistent (browser) flow.
    success = asyncio.run(login_flow(api_url=api_url, auto_open=auto_open))
    return 0 if success else 1
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest api/tests/unit/test_cli_login_ephemeral.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Verify the persistent path still works (no regressions)**

```bash
.venv/bin/pytest api/tests/unit/ -v -k "login or credentials"
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add api/bifrost/cli.py api/tests/unit/test_cli_login_ephemeral.py
git commit -m "feat(cli): add --ephemeral password-grant login (#149)"
```

---

## Task 6: E2E test — full ephemeral round-trip against the test stack

**Files:**
- Create: `api/tests/e2e/platform/test_cli_ephemeral_login.py`

- [ ] **Step 1: Make sure the test stack is up**

```bash
./test.sh stack status || ./test.sh stack up
```

Expected: `Status: UP`. The test stack runs with `BIFROST_MFA_ENABLED=false` and the seed user `dev@gobifrost.com` / `password`.

- [ ] **Step 2: Write the e2e test**

Create `api/tests/e2e/platform/test_cli_ephemeral_login.py`:

```python
"""End-to-end test: bifrost login --ephemeral against the real test API."""

import os
import subprocess
import sys

import pytest


@pytest.fixture
def api_url():
    return os.environ.get("BIFROST_TEST_API_URL", "http://api:8000")


def test_ephemeral_login_round_trip(api_url):
    """
    Full path:
      1. Run `bifrost login --ephemeral` against the real test API.
      2. Parse the three BIFROST_* lines from stdout.
      3. Use those env vars in a child process running `bifrost api GET /api/integrations`.
      4. Verify the API call succeeds (token works).
    """
    bifrost_cli = [sys.executable, "-m", "bifrost"]

    # Step 1: ephemeral login
    result = subprocess.run(
        bifrost_cli + [
            "login",
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", api_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"login failed: stderr={result.stderr!r}"

    # Step 2: parse output
    env_lines = {}
    for line in result.stdout.splitlines():
        if "=" in line and line.startswith("BIFROST_"):
            k, _, v = line.partition("=")
            env_lines[k] = v

    assert env_lines.get("BIFROST_API_URL") == api_url
    assert env_lines.get("BIFROST_ACCESS_TOKEN")
    assert env_lines.get("BIFROST_REFRESH_TOKEN")

    # Step 3 & 4: use the tokens
    child_env = os.environ.copy()
    child_env.update(env_lines)
    result2 = subprocess.run(
        bifrost_cli + ["api", "GET", "/api/integrations"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result2.returncode == 0, (
        f"`bifrost api GET /api/integrations` failed: "
        f"stdout={result2.stdout!r} stderr={result2.stderr!r}"
    )


def test_ephemeral_login_refuses_mfa_required(api_url, monkeypatch):
    """If the stack is configured with MFA on, the ephemeral path must refuse with exit 2."""
    if os.environ.get("BIFROST_MFA_ENABLED", "false").lower() != "true":
        pytest.skip("Test stack has MFA off; cannot exercise refusal here")

    bifrost_cli = [sys.executable, "-m", "bifrost"]
    result = subprocess.run(
        bifrost_cli + [
            "login",
            "--ephemeral",
            "--email", "dev@gobifrost.com",
            "--password", "password",
            "--url", api_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "MFA" in result.stderr
```

- [ ] **Step 3: Run the e2e test**

```bash
./test.sh e2e api/tests/e2e/platform/test_cli_ephemeral_login.py -v
```

Expected: `test_ephemeral_login_round_trip` passes. The MFA-refusal test will skip on the stock test stack (which runs MFA off) — that's fine; it's a guarded path for users who want to verify.

- [ ] **Step 4: Commit**

```bash
git add api/tests/e2e/platform/test_cli_ephemeral_login.py
git commit -m "test(e2e): full ephemeral login round-trip (#149)"
```

---

## Task 7: Update `bifrost-debug` skill to auto-write `.env`

**Files:**
- Modify: `.claude/skills/bifrost-debug/SKILL.md`

This task is documentation-only; the skill is instructions Claude follows, not code. The instruction needs to tell future-Claude what to do after `./debug.sh up` succeeds.

- [ ] **Step 1: Add the auto-env section to the skill**

Open `.claude/skills/bifrost-debug/SKILL.md`. Find the section that ends with the line about telling the user the credentials (search for `dev@gobifrost.com`). After that section, insert this new section:

```markdown
## Auto-connect the CLI in this folder

Once `./debug.sh up` reports the URL, wire the per-folder Bifrost CLI session so commands in this directory automatically target this stack — without overwriting any existing `~/.bifrost/credentials.json` (the user may have prod connected).

1. Capture the three env-var lines from an ephemeral login:

   ```bash
   bifrost login --ephemeral --email dev@gobifrost.com --password password \
     --url <URL_FROM_DEBUG_STATUS>
   ```

   The CLI prints to stdout:
   ```
   BIFROST_API_URL=http://localhost:38421
   BIFROST_ACCESS_TOKEN=...
   BIFROST_REFRESH_TOKEN=...
   ```

2. Append (or replace) the fenced block in `.env` at the worktree root:

   ```
   # BIFROST CLI ephemeral session
   BIFROST_API_URL=...
   BIFROST_ACCESS_TOKEN=...
   BIFROST_REFRESH_TOKEN=...
   # END BIFROST CLI ephemeral session
   ```

   Use marker comments so the block can be removed cleanly on teardown without touching the user's other env vars.

3. Add `.env` to `.gitignore` if it isn't already present. Do not add the file otherwise — only that one line.

4. Tell the user once: *"Stack up at <URL>. CLI in this folder is now connected (tokens are ephemeral; nothing was written to `~/.bifrost/`). MFA-off password login was used — do not run an instance like that in production."*

On `./debug.sh down`, remove the fenced block (everything between `# BIFROST CLI ephemeral session` and `# END BIFROST CLI ephemeral session`, inclusive). If `.env` is empty after removal, delete it.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/bifrost-debug/SKILL.md
git commit -m "docs(skill): auto-connect CLI to debug stack via .env (#149)"
```

---

## Task 8: Verification & PR

- [ ] **Step 1: Run all unit tests**

```bash
.venv/bin/pytest api/tests/unit/test_credentials.py api/tests/unit/test_cli_login_ephemeral.py -v
```

Expected: ALL pass.

- [ ] **Step 2: Run the broader CLI/credentials suite to confirm no regressions**

```bash
./test.sh stack up || true
./test.sh tests/unit/test_credentials.py tests/unit/test_cli_login_ephemeral.py -v
./test.sh tests/unit -k "client or login or credentials" -v
```

Expected: ALL pass.

- [ ] **Step 3: Type check + lint**

```bash
cd api && pyright bifrost/credentials.py bifrost/cli.py
cd api && ruff check bifrost/credentials.py bifrost/cli.py
```

Expected: Zero errors.

- [ ] **Step 4: Manual smoke — keychain on dev's xfce Linux**

```bash
.venv/bin/python -c "
from bifrost.credentials import get_persistent_backend, _reset_persistent_backend_for_tests, save_credentials, get_credentials, clear_credentials
_reset_persistent_backend_for_tests()
b = get_persistent_backend()
print('Backend:', type(b).__name__)
save_credentials('http://smoke.test', 'at_smoke', 'rt_smoke', '2099-01-01T00:00:00+00:00')
print('Round-trip:', get_credentials('http://smoke.test'))
clear_credentials('http://smoke.test')
print('After clear:', get_credentials('http://smoke.test'))
"
```

Record the printed `Backend:` value. This is the value to put in the cross-platform table in the PR description.

- [ ] **Step 5: Manual smoke — verify the user's prod token still works**

```bash
.venv/bin/bifrost api GET /api/integrations | head -5
```

Expected: real prod data returned. **This is the load-bearing check** — if the migration broke the prod token, this fails.

- [ ] **Step 6: Open the PR**

```bash
git push -u origin feat/cli-auth-ephemeral-149
gh pr create --title "feat(cli): ephemeral sessions + multi-instance auth" --body "$(cat <<'EOF'
Closes #149

## Summary

- Adds `bifrost login --email X --password Y --ephemeral` for password-grant login that prints tokens to stdout (never persisted).
- Multi-record credential store keyed by `api_url`. Lazy migration of the legacy single-record `~/.bifrost/credentials.json`.
- OS keychain (via `keyring`) becomes the default persistent backend, with JSON fallback for headless Linux. One-time stderr warning when falling back so users know.
- `bifrost-debug` skill now auto-writes the three `BIFROST_*` env vars into `.env` at the worktree root after `./debug.sh up`, so CLI commands in that folder target that stack without touching the global credentials file.

## Cross-platform smoke test results

| Platform | Backend resolved | Round-trip | Notes |
|---|---|---|---|
| Linux xfce (dev's machine) | (fill in: `KeyringBackend` or `JsonBackend`) | ✅ / ❌ | |
| macOS (dev's other machine) | TBD by reviewer | TBD | Will be filled in after dev tests |
| Windows | Deferred | Deferred | Code path covered by `keyring`'s own tests; we trust the lib here |

## Test plan

- [x] Unit tests for backend abstraction, multi-record JSON, KeyringBackend, env-var precedence, legacy migration
- [x] Unit tests for `--ephemeral` flag handling, MFA refusal, output format, no-disk-write
- [x] E2E test: full round-trip against the real test stack (`/auth/login` → tokens → authenticated `bifrost api` call in a child process)
- [x] Manual: prod token survives migration on dev's machine
- [x] Manual: keychain backend resolves on dev's xfce Linux
- [ ] Manual: keychain backend resolves on dev's Mac (run before merge)
- [ ] Manual: pretend-headless test inside a Docker container, confirm JSON fallback warning fires

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: Run the cross-platform smoke on Mac**

The user runs Step 4 verbatim on their Mac. Update the PR's smoke-test table with the resolved backend and round-trip result.

- [ ] **Step 8: Run the headless-Linux smoke**

```bash
docker run --rm -v "$PWD":/repo -w /repo python:3.11-slim sh -c "
  pip install --quiet -e api/ 2>&1 | tail -5
  python -c '
from bifrost.credentials import get_persistent_backend, _reset_persistent_backend_for_tests
_reset_persistent_backend_for_tests()
b = get_persistent_backend()
print(\"Backend in container:\", type(b).__name__)
'
"
```

Expected: `Backend in container: JsonBackend` and a `warning: OS keychain unavailable…` line on stderr. Update PR's smoke-test table.

---

## Self-review

**Spec coverage check** — every spec section has a task:

- §Design Overview (two paths, resolution order) → Tasks 2, 3, 4, 5
- §Components/Credentials module rewrite → Tasks 2, 3
- §Components/Migration → Task 4
- §Components/`bifrost login` flags → Task 5
- §Components/Token-refresh in ephemeral path → covered by `EnvBackend.get` returning a far-future expiry placeholder so the existing `is_token_expired` doesn't trigger; in-process refresh in `client.py` continues to work because that code already handles refresh via `refresh_tokens()` when 401 hits. No code change needed; this is documented as the design choice.
- §Components/`bifrost-debug` skill update → Task 7
- §Components/Cross-platform keychain test plan → Task 8 Steps 4, 7, 8
- §Data Flow (persistent / ephemeral / both at once) → exercised by Task 6 e2e + Task 8 manual smoke
- §Security Considerations / warning prints every invocation → Task 5 Step 1 test `test_prints_three_lines_and_warning`
- §Testing (unit/CLI/e2e) → Tasks 2, 3, 4, 5, 6
- §Migration & Rollback / non-destructive on failure → Task 4 Step 1 test `test_migration_failure_preserves_legacy_file`

**Placeholder scan:** Searched for "TBD" / "TODO" / "fill in details" — only "TBD" in the PR template's cross-platform table is intentional (gets filled in by the human running Steps 7–8).

**Type/name consistency:** `Credentials` dataclass / `Backend` protocol / `EnvBackend` / `JsonBackend` / `KeyringBackend` / `KEYRING_SERVICE` / `_select_persistent_backend` / `_reset_persistent_backend_for_tests` / `get_persistent_backend` / `_try_migrate_legacy` — names used identically across all tasks. Function signatures (`get_credentials(api_url=None)`, `save_credentials(api_url, access_token, refresh_token, expires_at)`, `clear_credentials(api_url=None)`) match between definition (Task 2) and call sites (existing client.py, unchanged).

One real fix found and applied during review: the migration test `test_migrate_legacy_to_json_backend` asserts the file is rewritten *and* the URL key exists — the original draft only checked the second, so a regression where `JsonBackend.save()` failed to actually write would slip past. Both assertions are now in the test as written.
