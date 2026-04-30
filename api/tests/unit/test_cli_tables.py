"""Smoke tests for ``bifrost tables create/update --access``.

Verifies that:
- ``--access '<json>'`` parses inline JSON and posts it to /api/tables.
- ``--access @path/to/file.json`` reads from disk and posts it.
- ``--access`` on ``update`` patches to /api/tables/{id}.

The tests mock ``BifrostClient.get_instance`` and ``RefResolver`` so no
network or credentials are required.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest.mock as mock

import httpx
import pytest
from click.testing import CliRunner

# Ensure the standalone bifrost package is importable.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from bifrost.commands.tables import tables_group  # noqa: E402


_ACCESS_DICT = {
    "everyone": {"read": True, "create": False, "update": False, "delete": False},
    "role": {"roles": [], "read": False, "create": False, "update": False, "delete": False},
    "creator": {"read": False, "create": False, "update": False, "delete": False},
}
_ACCESS_JSON = json.dumps(_ACCESS_DICT)


import asyncio  # noqa: E402

_DUMMY_REQUEST = httpx.Request("GET", "https://bifrost.test/api/tables")


def _fake_response(body: dict, *, status: int = 200) -> httpx.Response:
    """Build an httpx.Response with a request set (required for raise_for_status)."""
    resp = httpx.Response(status, json=body, request=_DUMMY_REQUEST)
    return resp


def _async_identity(value: str):  # type: ignore[no-untyped-def]
    """Return a coroutine that resolves to ``value``."""

    async def _inner():  # type: ignore[no-untyped-def]
        return value

    return _inner()


def _make_mock_client(captured: dict) -> mock.AsyncMock:
    """Return a mock BifrostClient whose async post/patch record calls."""

    async def capturing_post(path, json=None):  # type: ignore[no-untyped-def]
        captured["post_path"] = path
        captured["post_body"] = json
        return _fake_response({"id": "t1", **(json or {})})

    async def capturing_patch(path, json=None):  # type: ignore[no-untyped-def]
        captured["patch_path"] = path
        captured["patch_body"] = json
        return _fake_response({"id": "t1", **(json or {})})

    async def capturing_get(path):  # type: ignore[no-untyped-def]
        return _fake_response({"id": "t1", "name": "t1", "access": None})

    client = mock.AsyncMock()
    client.post = capturing_post
    client.patch = capturing_patch
    client.get = capturing_get
    return client


def _invoke_create(args: list[str], captured: dict) -> "CliRunner._Result":  # type: ignore[name-defined]
    client = _make_mock_client(captured)

    with (
        mock.patch("bifrost.client.BifrostClient.get_instance", return_value=client),
        mock.patch(
            "bifrost.refs.RefResolver.resolve",
            new_callable=lambda: lambda self, kind, ref: _async_identity(ref),
        ),
    ):
        runner = CliRunner()
        return runner.invoke(tables_group, ["create", "--name", "mytable", *args])


def _invoke_update(args: list[str], captured: dict) -> "CliRunner._Result":  # type: ignore[name-defined]
    client = _make_mock_client(captured)

    with (
        mock.patch("bifrost.client.BifrostClient.get_instance", return_value=client),
        mock.patch(
            "bifrost.refs.RefResolver.resolve",
            new_callable=lambda: lambda self, kind, ref: _async_identity(ref),
        ),
    ):
        runner = CliRunner()
        return runner.invoke(tables_group, ["update", "t1", *args])


class TestCreateWithAccess:
    def test_inline_json_is_posted(self) -> None:
        captured: dict = {}
        result = _invoke_create(["--access", _ACCESS_JSON], captured)
        assert result.exit_code == 0, result.output
        assert captured["post_path"] == "/api/tables"
        assert captured["post_body"]["access"] == _ACCESS_DICT
        assert captured["post_body"]["access"]["everyone"]["read"] is True

    def test_file_reference_is_posted(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "access.json"
        f.write_text(_ACCESS_JSON)
        captured: dict = {}
        result = _invoke_create(["--access", f"@{f}"], captured)
        assert result.exit_code == 0, result.output
        assert captured["post_body"]["access"]["everyone"]["read"] is True

    def test_invalid_json_exits_nonzero(self) -> None:
        captured: dict = {}
        result = _invoke_create(["--access", "not-json"], captured)
        assert result.exit_code != 0

    def test_no_access_flag_omits_field(self) -> None:
        """Omitting --access means ``access`` is not sent in the body."""
        captured: dict = {}
        result = _invoke_create([], captured)
        assert result.exit_code == 0, result.output
        assert "access" not in captured.get("post_body", {})


class TestUpdateWithAccess:
    def test_inline_json_is_patched(self) -> None:
        captured: dict = {}
        result = _invoke_update(["--access", _ACCESS_JSON], captured)
        assert result.exit_code == 0, result.output
        assert captured["patch_path"] == "/api/tables/t1"
        assert captured["patch_body"]["access"] == _ACCESS_DICT
