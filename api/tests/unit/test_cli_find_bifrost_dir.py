"""Tests for workspace detection in the Bifrost CLI.

Regression: an earlier walk-up implementation accepted *any* ``.bifrost/``
ancestor as the workspace root. On a machine with
``~/.bifrost/credentials.json`` (the CLI auth config dir) and a workspace
under ``~/some-project/`` that did NOT yet have its own ``.bifrost/``, the
walk-up reached ``~/.bifrost/`` and returned it, collapsing the workspace
root to ``$HOME`` and pushing files to the wrong key prefix.

The new design drops walk-up entirely. The launch directory IS the
workspace root. If ``.bifrost/`` is absent, the CLI prompts the user
(``_ensure_workspace_marker``) to drop a ``.bifrost/.workspace`` sentinel
so subsequent commands recognise the dir.
"""
from __future__ import annotations

import pathlib
from unittest import mock

from bifrost.cli import (
    _ensure_workspace_marker,
    _find_bifrost_dir,
    _is_workspace_bifrost_dir,
)


# ─── _find_bifrost_dir ─────────────────────────────────────────────────


def test_local_root_with_workspace_bifrost_returns_it(tmp_path: pathlib.Path) -> None:
    """A workspace .bifrost/ in the launch dir is returned directly."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bifrost = workspace / ".bifrost"
    bifrost.mkdir()
    (bifrost / "tables.yaml").write_text("tables: {}\n")

    assert _find_bifrost_dir(workspace) == bifrost


def test_local_root_is_the_workspace_bifrost(tmp_path: pathlib.Path) -> None:
    """If ``local_root`` IS the ``.bifrost/`` itself, return it as-is."""
    bifrost = tmp_path / ".bifrost"
    bifrost.mkdir()
    (bifrost / "tables.yaml").write_text("tables: {}\n")

    assert _find_bifrost_dir(bifrost) == bifrost


def test_credentials_only_dir_is_not_a_workspace(tmp_path: pathlib.Path) -> None:
    """A ``.bifrost/`` containing only ``credentials.json`` (CLI config dir)
    must NOT be treated as a workspace. This is the regression case."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    config = fake_home / ".bifrost"
    config.mkdir()
    (config / "credentials.json").write_text('{"access_token":"x"}')

    workspace = fake_home / "GitHub" / "my-project"
    workspace.mkdir(parents=True)

    found = _find_bifrost_dir(workspace)

    # Must NOT be the CLI config dir
    assert found != config
    # Falls back to the workspace's own (non-existent) .bifrost/
    assert found == workspace / ".bifrost"


def test_no_walk_up(tmp_path: pathlib.Path) -> None:
    """The new design has no walk-up: a child directory of a workspace
    does NOT inherit its parent's ``.bifrost/``. The launch directory is
    expected to be the workspace root."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    parent_bifrost = workspace / ".bifrost"
    parent_bifrost.mkdir()
    (parent_bifrost / "tables.yaml").write_text("tables: {}\n")
    sub = workspace / "apps" / "my-app"
    sub.mkdir(parents=True)

    # Walk-up is gone — we get sub/.bifrost, not the parent's .bifrost.
    assert _find_bifrost_dir(sub) == sub / ".bifrost"


def test_no_bifrost_anywhere_returns_fallback(tmp_path: pathlib.Path) -> None:
    """No ``.bifrost/`` anywhere → fallback to ``local_root/.bifrost``."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    found = _find_bifrost_dir(workspace)
    assert found == workspace / ".bifrost"
    assert not found.exists()


# ─── _is_workspace_bifrost_dir ─────────────────────────────────────────


def test_is_workspace_bifrost_dir_with_yaml(tmp_path: pathlib.Path) -> None:
    d = tmp_path / ".bifrost"
    d.mkdir()
    (d / "agents.yaml").write_text("agents: {}\n")
    assert _is_workspace_bifrost_dir(d) is True


def test_is_workspace_bifrost_dir_with_sentinel(tmp_path: pathlib.Path) -> None:
    """The empty ``.workspace`` sentinel alone marks a workspace dir."""
    d = tmp_path / ".bifrost"
    d.mkdir()
    (d / ".workspace").touch()
    assert _is_workspace_bifrost_dir(d) is True


def test_is_workspace_bifrost_dir_credentials_only(tmp_path: pathlib.Path) -> None:
    d = tmp_path / ".bifrost"
    d.mkdir()
    (d / "credentials.json").write_text("{}")
    assert _is_workspace_bifrost_dir(d) is False


def test_is_workspace_bifrost_dir_missing(tmp_path: pathlib.Path) -> None:
    assert _is_workspace_bifrost_dir(tmp_path / "nope") is False


def test_is_workspace_bifrost_dir_not_a_dir(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "thing"
    f.write_text("not a dir")
    assert _is_workspace_bifrost_dir(f) is False


# ─── _ensure_workspace_marker ──────────────────────────────────────────


def test_ensure_workspace_marker_existing_yaml_workspace(tmp_path: pathlib.Path) -> None:
    """An existing workspace with manifest YAMLs is recognised without prompting."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bifrost = workspace / ".bifrost"
    bifrost.mkdir()
    (bifrost / "tables.yaml").write_text("tables: {}\n")

    with mock.patch("bifrost.cli.input", side_effect=AssertionError("should not prompt")):
        assert _ensure_workspace_marker(workspace) is True


def test_ensure_workspace_marker_existing_sentinel(tmp_path: pathlib.Path) -> None:
    """A sentinel-only .bifrost/ is also recognised without prompting."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bifrost = workspace / ".bifrost"
    bifrost.mkdir()
    (bifrost / ".workspace").touch()

    with mock.patch("bifrost.cli.input", side_effect=AssertionError("should not prompt")):
        assert _ensure_workspace_marker(workspace) is True


def test_ensure_workspace_marker_creates_sentinel_on_yes(tmp_path: pathlib.Path) -> None:
    """When the user confirms, ``.bifrost/.workspace`` is created."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with mock.patch("bifrost.cli.sys.stdin.isatty", return_value=True), mock.patch(
        "bifrost.cli.input", return_value="y",
    ):
        assert _ensure_workspace_marker(workspace) is True

    sentinel = workspace / ".bifrost" / ".workspace"
    assert sentinel.exists()
    # The marker alone is enough for subsequent calls.
    assert _is_workspace_bifrost_dir(workspace / ".bifrost") is True


def test_ensure_workspace_marker_returns_false_on_no(tmp_path: pathlib.Path) -> None:
    """Declining the prompt returns False and creates no files."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with mock.patch("bifrost.cli.sys.stdin.isatty", return_value=True), mock.patch(
        "bifrost.cli.input", return_value="n",
    ):
        assert _ensure_workspace_marker(workspace) is False

    assert not (workspace / ".bifrost").exists()


def test_ensure_workspace_marker_returns_false_on_non_tty(tmp_path: pathlib.Path) -> None:
    """Non-interactive shells must not block on input(); they just fail."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with mock.patch("bifrost.cli.sys.stdin.isatty", return_value=False), mock.patch(
        "bifrost.cli.input", side_effect=AssertionError("must not prompt on non-tty"),
    ):
        assert _ensure_workspace_marker(workspace) is False

    assert not (workspace / ".bifrost").exists()


def test_ensure_workspace_marker_no_prompt_kwarg(tmp_path: pathlib.Path) -> None:
    """``prompt=False`` is a programmatic guard for non-interactive callers."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with mock.patch(
        "bifrost.cli.input", side_effect=AssertionError("prompt=False must skip input()"),
    ):
        assert _ensure_workspace_marker(workspace, prompt=False) is False
    assert not (workspace / ".bifrost").exists()
