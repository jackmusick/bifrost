"""E2E tests for ``bifrost roles`` CLI commands.

Covers the CRUD surface from Task 5b of the CLI mutation surface plan:

* ``bifrost roles list`` — returns the seeded / created role set.
* ``bifrost roles create --name foo [--permissions <json>]`` — POSTs a new
  role and returns the created entity.
* ``bifrost roles update <ref> --name bar`` — PATCHes by UUID or name ref.
* ``bifrost roles delete <ref>`` — deletes the role; CASCADE removes all
  assignments.

``permissions`` is carried in the DTO contract as a ``dict`` (a flat
``{"key": true|false, ...}`` permission map), so the CLI generates
``--permissions`` accepting a JSON literal or ``@path`` to a YAML/JSON file.
This test exercises the JSON literal form end-to-end so we cover the wire
contract described in the plan (permissions round-trip from CLI → API →
DB).

The commands are invoked via :class:`click.testing.CliRunner` against the
real API stack. ``BifrostClient.get_instance`` is patched to return a client
bound to the E2E API URL with ``platform_admin``'s JWT so the CLI code path
exercised here is identical to what a real user hits.
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
from bifrost.commands.roles import roles_group  # noqa: E402


@pytest.fixture
def cli_client(e2e_api_url, platform_admin):
    """Construct a ``BifrostClient`` bound to the E2E API + admin JWT.

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


def _invoke(args: list[str]) -> "object":
    """Invoke ``roles_group`` with the given CLI args via CliRunner."""
    runner = CliRunner()
    # ``--json`` goes at the group level; callers append it when needed.
    return runner.invoke(roles_group, args, standalone_mode=False, catch_exceptions=False)


@pytest.mark.e2e
class TestCliRoles:
    """End-to-end coverage for ``bifrost roles`` commands."""

    def test_list_returns_payload(self, cli_client) -> None:
        """``roles list --json`` returns the (possibly empty) role set as JSON."""
        result = _invoke(["--json", "list"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        # Every item has an id and a name; permissions is a dict.
        for item in payload:
            assert "id" in item
            assert "name" in item
            assert "permissions" in item
            assert isinstance(item["permissions"], dict)

    def test_create_update_delete_roundtrip(
        self, cli_client, e2e_client, platform_admin
    ) -> None:
        """Full CRUD cycle: create → update → delete by name ref.

        Also verifies the ``--permissions`` JSON flag round-trips through the
        generated DTO flag: passing ``'{"workflows.read": true}'`` on create
        persists those permissions and returns them on the response.
        """
        original_name = f"cli-role-{uuid4().hex[:8]}"
        renamed = f"cli-role-renamed-{uuid4().hex[:8]}"

        perms = {"workflows.read": True, "workflows.write": False}

        # --- create ---
        create_result = _invoke(
            [
                "--json",
                "create",
                "--name",
                original_name,
                "--description",
                "created by test_cli_roles",
                "--permissions",
                json.dumps(perms),
            ]
        )
        assert create_result.exit_code == 0, create_result.output
        created = json.loads(create_result.output)
        created_id = str(created["id"])
        assert created["name"] == original_name
        assert created["description"] == "created by test_cli_roles"
        assert created["permissions"] == perms

        # Sanity-check via the REST API that the role is reachable by UUID.
        get_resp = e2e_client.get(
            f"/api/roles/{created_id}",
            headers=platform_admin.headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["name"] == original_name

        # --- update (by name ref) ---
        new_perms = {"workflows.read": True, "workflows.write": True}
        update_result = _invoke(
            [
                "--json",
                "update",
                original_name,
                "--name",
                renamed,
                "--permissions",
                json.dumps(new_perms),
            ]
        )
        assert update_result.exit_code == 0, update_result.output
        updated = json.loads(update_result.output)
        assert str(updated["id"]) == created_id
        assert updated["name"] == renamed
        assert updated["permissions"] == new_perms

        # --- delete (by renamed ref) ---
        delete_result = _invoke(["--json", "delete", renamed])
        assert delete_result.exit_code == 0, delete_result.output
        deleted_payload = json.loads(delete_result.output)
        assert deleted_payload["deleted"] == created_id

        # Confirm the delete cascaded through to the API.
        get_after = e2e_client.get(
            f"/api/roles/{created_id}", headers=platform_admin.headers
        )
        assert get_after.status_code == 404, get_after.text

    def test_permissions_flag_is_single_json_value(self, cli_client) -> None:
        """Document the generated flag shape for ``permissions``.

        The DTO declares ``permissions: dict | None``, so
        :func:`build_cli_flags` emits a single ``--permissions`` flag that
        accepts a JSON literal (or ``@path`` to YAML/JSON). This test asserts
        that contract: passing two ``--permissions`` flags uses the *last*
        value (Click's non-multiple default), not concatenation into a list.
        Pair this with the round-trip test above for end-to-end coverage.
        """
        name = f"cli-role-perms-{uuid4().hex[:8]}"
        first = {"a.read": True}
        second = {"b.write": True}

        # When permissions is a plain (non-multiple) flag, Click keeps only
        # the last value — that's the generator's contract.
        result = _invoke(
            [
                "--json",
                "create",
                "--name",
                name,
                "--permissions",
                json.dumps(first),
                "--permissions",
                json.dumps(second),
            ]
        )
        try:
            assert result.exit_code == 0, result.output
            created = json.loads(result.output)
            assert created["permissions"] == second
        finally:
            # Cleanup: best-effort delete.
            _invoke(["--json", "delete", name])

    def test_update_by_uuid(self, cli_client, e2e_client, platform_admin) -> None:
        """Update accepts a UUID ref directly (ref resolver pass-through)."""
        name = f"cli-role-uuid-{uuid4().hex[:8]}"
        renamed = f"cli-role-uuid-new-{uuid4().hex[:8]}"

        create_resp = e2e_client.post(
            "/api/roles",
            headers=platform_admin.headers,
            json={"name": name},
        )
        assert create_resp.status_code == 201, create_resp.text
        role_id = create_resp.json()["id"]

        update_result = _invoke(
            ["--json", "update", str(role_id), "--name", renamed]
        )
        assert update_result.exit_code == 0, update_result.output
        payload = json.loads(update_result.output)
        assert payload["name"] == renamed

        # Cleanup to keep fixtures clean across the session.
        _invoke(["--json", "delete", str(role_id)])
