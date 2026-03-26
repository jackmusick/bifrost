"""
Bifrost SDK credentials storage.

CLI authentication credentials are stored in one of two backends:
- `pass` password store on Unix-like systems when available
- legacy JSON file storage as a fallback
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

AUTO_BACKEND = "auto"
FILE_BACKEND = "file"
PASS_BACKEND = "pass"
DEFAULT_PASS_ENTRY = "bifrost/credentials"
REQUIRED_KEYS = ("api_url", "access_token", "refresh_token", "expires_at")


def get_config_dir() -> Path:
    """
    Get platform-specific config directory.

    Returns:
        Path to config directory:
        - Windows: %APPDATA%/Bifrost
        - macOS/Linux: ~/.bifrost
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Bifrost"
        return Path.home() / "Bifrost"
    return Path.home() / ".bifrost"


def get_credentials_path() -> Path:
    """Get the legacy credentials file path."""
    return get_config_dir() / "credentials.json"


def get_pass_entry() -> str:
    """Get the pass entry used for CLI credentials."""
    return os.environ.get("BIFROST_PASS_ENTRY", DEFAULT_PASS_ENTRY)


def get_credentials_backend() -> str:
    """Resolve credential storage backend."""
    backend = os.environ.get("BIFROST_CREDENTIALS_BACKEND", AUTO_BACKEND).strip().lower()
    if backend in {AUTO_BACKEND, FILE_BACKEND, PASS_BACKEND}:
        return backend
    return AUTO_BACKEND


def _validate_credentials(data: dict | None) -> dict | None:
    """Validate raw credential payload shape."""
    if not isinstance(data, dict):
        return None
    if not all(key in data for key in REQUIRED_KEYS):
        return None
    return data


def _pass_supported() -> bool:
    """Return True when pass-backed storage is available."""
    if platform.system() == "Windows":
        return False
    return shutil.which("pass") is not None


def _should_use_pass() -> bool:
    """Return True when pass should be used for active operations."""
    backend = get_credentials_backend()
    if backend == PASS_BACKEND:
        return True
    return backend == AUTO_BACKEND and _pass_supported()


def _run_pass(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a pass command."""
    return subprocess.run(
        ["pass", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def _load_pass_credentials() -> dict | None:
    """Load credentials from pass."""
    try:
        result = _run_pass("show", get_pass_entry())
    except (OSError, subprocess.CalledProcessError):
        return None

    try:
        return _validate_credentials(json.loads(result.stdout))
    except json.JSONDecodeError:
        return None


def _save_pass_credentials(data: dict) -> None:
    """Persist credentials in pass."""
    if not _pass_supported():
        raise RuntimeError("pass backend requested but 'pass' is not available")

    _run_pass(
        "insert",
        "-m",
        "-f",
        get_pass_entry(),
        input_text=json.dumps(data, indent=2) + "\n",
    )


def _clear_pass_credentials() -> None:
    """Remove credentials from pass if present."""
    if not _pass_supported():
        return
    try:
        _run_pass("rm", "-f", get_pass_entry())
    except (OSError, subprocess.CalledProcessError):
        pass


def _load_file_credentials() -> dict | None:
    """Load credentials from the legacy JSON file."""
    creds_path = get_credentials_path()
    if not creds_path.exists():
        return None

    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            return _validate_credentials(json.load(f))
    except (json.JSONDecodeError, OSError):
        return None


def _save_file_credentials(data: dict) -> None:
    """Persist credentials to the legacy JSON file."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    if platform.system() != "Windows":
        config_dir.chmod(0o700)

    creds_path = get_credentials_path()
    with open(creds_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if platform.system() != "Windows":
        creds_path.chmod(0o600)


def _clear_file_credentials() -> None:
    """Delete the legacy credentials file if present."""
    creds_path = get_credentials_path()
    if creds_path.exists():
        creds_path.unlink()


def _migrate_file_credentials_to_pass(file_creds: dict) -> dict:
    """Best-effort migration from legacy file storage into pass."""
    try:
        _save_pass_credentials(file_creds)
        _clear_file_credentials()
    except Exception:
        return file_creds
    return file_creds


def get_credentials() -> dict | None:
    """
    Load CLI credentials.

    Returns:
        Dict with keys: api_url, access_token, refresh_token, expires_at
        None if credentials don't exist or are invalid
    """
    if _should_use_pass():
        pass_creds = _load_pass_credentials()
        if pass_creds is not None:
            return pass_creds

    file_creds = _load_file_credentials()
    if file_creds is None:
        return None

    if _should_use_pass():
        return _migrate_file_credentials_to_pass(file_creds)

    return file_creds


def save_credentials(
    api_url: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    """
    Save CLI credentials.

    Prefers pass-backed storage when available; otherwise falls back to the
    legacy JSON file.
    """
    data = {
        "api_url": api_url,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }

    if _should_use_pass():
        _save_pass_credentials(data)
        _clear_file_credentials()
        return

    _save_file_credentials(data)


def clear_credentials() -> None:
    """Delete stored credentials from all supported backends."""
    _clear_pass_credentials()
    _clear_file_credentials()


def is_token_expired(buffer_seconds: int = 60) -> bool:
    """
    Check if access token is expired.

    Args:
        buffer_seconds: Refresh token this many seconds before actual expiry

    Returns:
        True if token is expired or will expire within buffer_seconds
        False if token is still valid
        True if credentials don't exist
    """
    creds = get_credentials()
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
