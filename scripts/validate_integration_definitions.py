#!/usr/bin/env python3
"""
Validate source-backed integration definition files.

Usage:
    python scripts/validate_integration_definitions.py
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from bifrost.integration_definition import discover_integration_definitions  # noqa: E402


def main() -> int:
    definitions = discover_integration_definitions(REPO_ROOT)
    if not definitions:
        print("No source-backed integration definitions found.")
        return 0

    print(f"Validated {len(definitions)} source-backed integration definition(s):")
    for slug, definition in definitions.items():
        print(f"  - {slug}: {definition.name} ({definition.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
