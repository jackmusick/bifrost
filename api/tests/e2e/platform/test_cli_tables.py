"""E2E tests for ``bifrost tables`` CLI commands.

Covers the CRUD surface from Task 5i of the CLI mutation surface plan:

* ``bifrost tables list`` — returns the wrapped ``{tables, total}`` payload.
* ``bifrost tables create --name foo --schema @file.yaml`` — POSTs a new
  table with a loaded schema dict.
* ``bifrost tables update <ref> --name bar`` — PATCHes and emits a stderr
  rename warning when the name actually changes.
* ``bifrost tables update <ref> --application <slug-or-uuid>`` — reassigns
  the owning application via the ``app`` ref resolver.
* ``bifrost tables delete <ref>`` — hard-deletes the table (cascade).

Stderr separation: Click 8.3's :class:`CliRunner` exposes ``result.stderr``
distinct from ``result.output``; we assert the rename warning appears in
``result.stderr`` specifically (not just mixed output).
"""

from __future__ import annotations

import json
import pathlib
import sys
from uuid import uuid4

import pytest
from click.testing import CliRunner

# Standalone bifrost package import (mirrors test_cli_orgs.py).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from bifrost import client as bifrost_client_module  # noqa: E402
from bifrost.client import BifrostClient  # noqa: E402
from bifrost.commands.tables import tables_group  # noqa: E402


@pytest.fixture
def cli_client(e2e_api_url, platform_admin):
    """Bind a ``BifrostClient`` to the E2E API + admin JWT for the CLI run.

    Replaces the thread-local singleton for the duration of the test so the
    command's ``pass_resolver`` plumbing hands our client to the command body.
    """
    client = BifrostClient(e2e_api_url, platform_admin.access_token)
    previous = getattr(bifrost_client_module._thread_local, "bifrost_client", None)
    bifrost_client_module._thread_local.bifrost_client = client
    try:
        yield client
    finally:
        if previous is None:
            if hasattr(bifrost_client_module._thread_local, "bifrost_client"):
                del bifrost_client_module._thread_local.bifrost_client
        else:
            bifrost_client_module._thread_local.bifrost_client = previous


@pytest.fixture
def schema_yaml_path(tmp_path):
    """Write a table schema YAML file and return its path."""
    schema_file = tmp_path / "table_schema.yaml"
    schema_file.write_text(
        "fields:\n"
        "  - name: email\n"
        "    type: string\n"
        "  - name: count\n"
        "    type: integer\n"
    )
    return schema_file


def _invoke(args: list[str]) -> "object":
    """Invoke ``tables_group`` with the given CLI args via CliRunner."""
    runner = CliRunner()
    return runner.invoke(
        tables_group, args, standalone_mode=False, catch_exceptions=False
    )


def _create_table_via_api(e2e_client, headers, name: str) -> str:
    resp = e2e_client.post(
        "/api/tables",
        headers=headers,
        json={"name": name, "description": "fixture"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_app_via_api(e2e_client, headers, slug: str) -> str:
    resp = e2e_client.post(
        "/api/applications",
        headers=headers,
        json={"name": slug, "slug": slug},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.e2e
class TestCliTables:
    """End-to-end coverage for ``bifrost tables`` commands."""

    def test_create_with_schema_file_then_rename_warning(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        schema_yaml_path,
    ):
        """``tables create --schema @file`` loads YAML; rename warns on stderr."""
        original = f"cli_tbl_{uuid4().hex[:8]}"
        renamed = f"cli_tbl_new_{uuid4().hex[:8]}"

        # --- create ---
        create_result = _invoke([
            "--json",
            "create",
            "--name", original,
            "--schema", f"@{schema_yaml_path}",
        ])
        assert create_result.exit_code == 0, create_result.output
        # ``result.output`` mixes stderr+stdout in Click 8.3; parse ``stdout``.
        created = json.loads(create_result.stdout)
        created_id = str(created["id"])
        assert created["name"] == original
        assert created["schema"] == {
            "fields": [
                {"name": "email", "type": "string"},
                {"name": "count", "type": "integer"},
            ]
        }

        # --- update with rename: warning must appear on stderr ---
        update_result = _invoke([
            "--json",
            "update", original,
            "--name", renamed,
        ])
        assert update_result.exit_code == 0, update_result.output
        updated = json.loads(update_result.stdout)
        assert str(updated["id"]) == created_id
        assert updated["name"] == renamed

        # Rename warning is emitted to stderr (not just stdout).
        assert "Renaming this table will break" in update_result.stderr
        assert original in update_result.stderr
        assert "rg -n" in update_result.stderr

        # Same-name update must NOT emit the warning.
        noop_result = _invoke([
            "--json",
            "update", renamed,
            "--description", "touched without rename",
        ])
        assert noop_result.exit_code == 0, noop_result.output
        assert "Renaming this table will break" not in noop_result.stderr

        # --- cleanup ---
        delete_result = _invoke(["--json", "delete", renamed])
        assert delete_result.exit_code == 0, delete_result.output
        assert json.loads(delete_result.stdout)["deleted"] == created_id

    def test_update_reassigns_application_via_app_ref(
        self,
        cli_client,
        e2e_client,
        platform_admin,
    ):
        """``--application <slug>`` resolves via the app ref resolver."""
        table_name = f"cli_tbl_asg_{uuid4().hex[:8]}"
        app_slug = f"cli-tbl-app-{uuid4().hex[:8]}"

        table_id = _create_table_via_api(
            e2e_client, platform_admin.headers, table_name
        )
        app_id = _create_app_via_api(
            e2e_client, platform_admin.headers, app_slug
        )

        update_result = _invoke([
            "--json",
            "update", table_name,
            "--application", app_slug,
        ])
        assert update_result.exit_code == 0, update_result.output
        updated = json.loads(update_result.stdout)
        assert str(updated["id"]) == table_id
        assert str(updated["application_id"]) == app_id

        # Reassign by UUID ref too — both forms must work.
        app2_slug = f"cli-tbl-app2-{uuid4().hex[:8]}"
        app2_id = _create_app_via_api(
            e2e_client, platform_admin.headers, app2_slug
        )
        update2 = _invoke([
            "--json",
            "update", str(table_id),
            "--application", str(app2_id),
        ])
        assert update2.exit_code == 0, update2.output
        assert str(json.loads(update2.stdout)["application_id"]) == app2_id

        # Cleanup.
        _invoke(["--json", "delete", str(table_id)])

    def test_list_returns_wrapped_payload(
        self,
        cli_client,
        e2e_client,
        platform_admin,
    ):
        """``tables list --json`` returns the ``{tables, total}`` envelope."""
        name = f"cli_tbl_list_{uuid4().hex[:8]}"
        table_id = _create_table_via_api(
            e2e_client, platform_admin.headers, name
        )
        try:
            result = _invoke(["--json", "list"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.stdout)
            assert isinstance(payload, dict)
            assert "tables" in payload and "total" in payload
            names = {t["name"] for t in payload["tables"]}
            assert name in names
        finally:
            _invoke(["--json", "delete", str(table_id)])
