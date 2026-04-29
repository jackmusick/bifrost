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
        # top-level shape (any credential field at the top level), the
        # migration path will rewrite it; treat as empty for now.
        if not isinstance(data, dict):
            return {}
        legacy_keys = {"api_url", "access_token", "refresh_token", "expires_at"}
        if legacy_keys & set(data.keys()):
            return {}  # legacy single-record or malformed; migration handles it
        # Defensive: drop any entries whose value isn't a dict (corrupted file).
        return {k: v for k, v in data.items() if isinstance(v, dict)}

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
