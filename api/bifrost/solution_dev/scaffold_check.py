"""Detect an app whose main.tsx predates the VITE_BIFROST_APP_ID dev fallback."""
from __future__ import annotations

from pathlib import Path

PATCH_HINT = (
    "Your app's src/main.tsx predates `bifrost solution start`. Update two lines so\n"
    "local dev can scope to this install (deployed behavior is unchanged):\n\n"
    "  const appId    = boot?.appId    ?? import.meta.env.VITE_BIFROST_APP_ID  ?? null;\n"
    "  const orgScope = boot?.orgScope ?? import.meta.env.VITE_BIFROST_ORG_ID  ?? null;\n"
)


def main_tsx_needs_dev_fallback(main_tsx: Path) -> bool:
    """True if the file exists but lacks the VITE_BIFROST_APP_ID local fallback."""
    if not main_tsx.is_file():
        return False
    text = main_tsx.read_text(encoding="utf-8")
    return "VITE_BIFROST_APP_ID" not in text
