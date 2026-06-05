"""Regression guard: the deploy CLI's vendoring must be importable from the
``bifrost`` package, NOT ``src.*``.

`bifrost deploy` runs in the INSTALLED CLI, which packages only the ``bifrost``
top-level package — it has no ``src`` on its path. A previous version imported
``from src.services.solutions.vendoring import vendor_shared_deps`` inside the
deploy command, which raised ModuleNotFoundError in the real CLI (the unit tests
missed it because they run in-repo where ``src`` resolves). This test fails if
that regression returns.
"""
from __future__ import annotations

import ast
from pathlib import Path


def test_vendoring_importable_from_bifrost_package() -> None:
    from bifrost.solution_vendoring import vendor_shared_deps  # noqa: F401

    assert callable(vendor_shared_deps)


def test_cli_commands_do_not_import_src() -> None:
    """No module under ``bifrost/commands/`` may import ``src.*``.

    These modules are CLI-only — they run exclusively in the installed CLI,
    which packages only the ``bifrost`` top-level package and has no ``src`` on
    its path. (Dual-purpose ``bifrost`` modules like ``_logging`` legitimately
    use lazy, function-scoped ``src.*`` imports that only fire server-side; the
    command modules have no such excuse and must stay CLI-pure.)"""
    pkg = Path(__file__).resolve().parents[2] / "bifrost" / "commands"
    bad: list[str] = []
    for py in pkg.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        rel = py.relative_to(pkg)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "src" or mod.startswith("src."):
                    bad.append(f"{rel}:{node.lineno}: from {mod} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "src" or alias.name.startswith("src."):
                        bad.append(f"{rel}:{node.lineno}: import {alias.name}")
    assert not bad, "CLI modules must not import src.* (absent in packaged CLI):\n" + "\n".join(bad)
