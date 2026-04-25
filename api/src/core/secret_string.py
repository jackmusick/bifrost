"""
SecretString: a str subclass that masks itself in display/logging contexts.

Used for config values of type SECRET. Works transparently as a string
for HTTP headers, f-strings, concatenation, etc. Only masks in:
- repr() / str() / print() — display and logging
- % formatting — logging.info("key=%s", secret)

Note: json.dumps bypasses __str__ for str subclasses (uses C-level buffer).
Secret protection in JSON serialization is handled by:
- redact_secrets() — deep scrub before persistence
- remove_circular_refs() in engine.py — converts SecretString to [REDACTED]
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
_MIN_SECRET_LENGTH = 4


class SecretString(str):
    """A string that masks itself in repr/logging but works normally as a value."""

    def __repr__(self) -> str:
        return f"'{REDACTED}'"

    def __str__(self) -> str:
        return REDACTED

    def __format__(self, format_spec: str) -> str:
        return super().__str__().__format__(format_spec)

    def get_secret_value(self) -> str:
        """Get the actual secret value."""
        return super().__str__()


def redact_secrets(obj: Any, secret_values: set[str]) -> Any:
    """
    Deep-walk a JSON-serializable object, replacing secret substrings with [REDACTED].

    Args:
        obj: Any JSON-serializable object (dict, list, str, int, etc.)
        secret_values: Set of plaintext secret values to redact.
                       Secrets shorter than 4 characters are skipped.

    Returns:
        A new object with all secret substrings replaced. Original is not mutated.
    """
    # Filter out short secrets to avoid false positives
    effective_secrets = {s for s in secret_values if len(s) >= _MIN_SECRET_LENGTH}

    if not effective_secrets:
        return obj

    return _redact_recursive(obj, effective_secrets)


def _redact_recursive(obj: Any, secrets: set[str]) -> Any:
    if isinstance(obj, str):
        result = obj
        for secret in secrets:
            result = result.replace(secret, REDACTED)
        return result
    if isinstance(obj, dict):
        return {k: _redact_recursive(v, secrets) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        redacted = [_redact_recursive(item, secrets) for item in obj]
        return redacted if isinstance(obj, list) else tuple(redacted)
    if isinstance(obj, set):
        return {_redact_recursive(item, secrets) for item in obj}
    # Handle Pydantic models — convert to dict and recurse
    try:
        from pydantic import BaseModel
        if isinstance(obj, BaseModel):
            return _redact_recursive(obj.model_dump(), secrets)
    except ImportError as e:
        # Pydantic is a hard dep but guard for unusual envs (e.g. minimal CLI bundles)
        logger.debug(f"pydantic unavailable for redact recursion: {e}")
    # int, float, bool, None — pass through
    return obj
