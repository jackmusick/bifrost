#!/usr/bin/env python3
"""
Audit the tracked .bifrost manifests and summarize how much metadata is still
carried only in the manifest layer.

Usage:
    python scripts/audit_manifest_inventory.py
    python scripts/audit_manifest_inventory.py --markdown
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / ".bifrost"


def load_manifest(name: str, key: str) -> dict[str, dict]:
    path = MANIFEST_DIR / name
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or key not in data or not isinstance(data[key], dict):
        raise ValueError(f"{path} did not contain a top-level '{key}' mapping")
    return data[key]


def existing_paths(entries: dict[str, dict]) -> tuple[int, list[tuple[str, str, str | None]]]:
    missing: list[tuple[str, str, str | None]] = []
    for entry_id, meta in entries.items():
        path = meta.get("path")
        if path and not (REPO_ROOT / path).exists():
            missing.append((entry_id, path, meta.get("name")))
    return len(entries) - len(missing), missing


def workflow_prefix_counts(entries: dict[str, dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for meta in entries.values():
        path = meta.get("path", "")
        if path.startswith("features/"):
            counts["features"] += 1
        elif path.startswith("shared/"):
            counts["shared"] += 1
        elif path.startswith("workflows/"):
            counts["legacy_workflows"] += 1
        else:
            counts["other"] += 1
    return counts


def field_counts(entries: dict[str, dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for meta in entries.values():
        for key in meta:
            counts[key] += 1
    return counts


def format_counter(counter: Counter[str]) -> str:
    return "\n".join(f"  - {key}: {value}" for key, value in counter.most_common())


def render_text() -> str:
    workflows = load_manifest("workflows.yaml", "workflows")
    integrations = load_manifest("integrations.yaml", "integrations")
    agents = load_manifest("agents.yaml", "agents")
    apps = load_manifest("apps.yaml", "apps")

    workflow_present, workflow_missing = existing_paths(workflows)
    agent_present, agent_missing = existing_paths(agents)
    app_present, app_missing = existing_paths(apps)

    lines = [
        ".bifrost manifest inventory",
        "",
        f"repo_root: {REPO_ROOT}",
        "",
        "entity counts:",
        f"  - workflows: {len(workflows)}",
        f"  - integrations: {len(integrations)}",
        f"  - agents: {len(agents)}",
        f"  - apps: {len(apps)}",
        "",
        "path-backed entities:",
        f"  - workflows with existing paths: {workflow_present}/{len(workflows)}",
        f"  - agents with existing paths: {agent_present}/{len(agents)}",
        f"  - apps with existing paths: {app_present}/{len(apps)}",
        "",
        "workflow path prefixes:",
        format_counter(workflow_prefix_counts(workflows)),
        "",
        "workflow field frequency:",
        format_counter(field_counts(workflows)),
        "",
        "integration field frequency:",
        format_counter(field_counts(integrations)),
    ]

    if workflow_missing or agent_missing or app_missing:
        lines.extend(["", "missing paths:"])
        for entry_id, path, name in workflow_missing + agent_missing + app_missing:
            lines.append(f"  - {entry_id}: {path} ({name})")

    return "\n".join(lines)


def render_markdown() -> str:
    workflows = load_manifest("workflows.yaml", "workflows")
    integrations = load_manifest("integrations.yaml", "integrations")
    agents = load_manifest("agents.yaml", "agents")
    apps = load_manifest("apps.yaml", "apps")

    workflow_present, workflow_missing = existing_paths(workflows)
    agent_present, agent_missing = existing_paths(agents)
    app_present, app_missing = existing_paths(apps)

    lines = [
        "# `.bifrost` Inventory",
        "",
        f"- Workflows: `{len(workflows)}`",
        f"- Integrations: `{len(integrations)}`",
        f"- Agents: `{len(agents)}`",
        f"- Apps: `{len(apps)}`",
        "",
        "## Source-backed Paths",
        "",
        f"- Workflows with existing source paths: `{workflow_present}/{len(workflows)}`",
        f"- Agents with existing source paths: `{agent_present}/{len(agents)}`",
        f"- Apps with existing source paths: `{app_present}/{len(apps)}`",
        "",
        "## Workflow Path Prefixes",
        "",
    ]

    for key, value in workflow_prefix_counts(workflows).most_common():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Workflow Field Frequency", ""])
    for key, value in field_counts(workflows).most_common():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Integration Field Frequency", ""])
    for key, value in field_counts(integrations).most_common():
        lines.append(f"- `{key}`: `{value}`")

    missing = workflow_missing + agent_missing + app_missing
    if missing:
        lines.extend(["", "## Missing Paths", ""])
        for entry_id, path, name in missing:
            lines.append(f"- `{entry_id}` -> `{path}` ({name})")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true", help="render markdown instead of plain text")
    args = parser.parse_args()

    output = render_markdown() if args.markdown else render_text()
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
