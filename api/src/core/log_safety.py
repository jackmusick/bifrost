"""Log sanitization for user-controlled values.

Strips control chars and ANSI escape sequences from values that flow into
log statements, preventing log forgery (newline injection, terminal escape
injection) when the application's logger uses plain-text formatters.
"""

import re
from typing import Any

_CTRL_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def log_safe(value: Any, max_len: int = 200) -> str:
    """Sanitize a value for safe inclusion in a log message.

    Replaces \\r and \\n with literal escapes, removes other ASCII control
    chars and ANSI escape sequences, and truncates to ``max_len`` characters.
    Use at log callsites whose interpolated value comes from user input
    (HTTP body, URL param, webhook payload, third-party API response).
    """
    s = str(value).replace("\r", "\\r").replace("\n", "\\n")
    s = _CTRL_RE.sub("", s)
    return s if len(s) <= max_len else s[:max_len] + "..."
