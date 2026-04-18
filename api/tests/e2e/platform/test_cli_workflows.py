"""E2E tests for ``bifrost workflows`` CLI commands.

Covers the lifecycle + role-assignment surface from Task 5c of the CLI
mutation surface plan:

* ``bifrost workflows list`` — returns registered workflows.
* ``bifrost workflows update <ref>`` — PATCHes a workflow by UUID, name, or
  ``path::func`` ref; asserts DTO-driven flags round-trip through
  :class:`WorkflowUpdateRequest`.
* ``bifrost workflows delete <ref>`` — deletes a workflow; ``--force``
  bypasses the deactivation protection check.
* ``bifrost workflows grant-role <ref> <role-ref>`` — POSTs a single-role
  assignment; success is observable via ``GET /api/workflows/{id}/roles``.
* ``bifrost workflows revoke-role <ref> <role-ref>`` — DELETEs the role
  assignment; the role disappears from the roles endpoint.

``register`` is NOT exercised E2E here — it takes a workspace-relative path
plus decorated function name and is tightly coupled to the file-storage
service. The unit-level argparse / flag contract is sanity-checked instead
via a ``--help`` invocation (see :class:`TestCliWorkflowsRegisterHelp`).

The commands are invoked via :class:`click.testing.CliRunner` against the
real API stack. ``BifrostClient.get_instance`` is replaced with a client
bound to the E2E API URL and the platform admin's JWT so the CLI code path
exercised here is identical to what a real user hits.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from click.testing import CliRunner

from bifrost.commands.workflows import workflows_group


_WORKFLOW_SOURCE = '''"""Test workflow used by bifrost workflows CLI E2E."""

from src.sdk import workflow


@workflow
def {function_name}(name: str = "world") -> str:
    """Simple greeter used by CLI E2E tests."""
    return f"hello {{name}}"
'''


@pytest.fixture
def _invoke(invoke_cli):
    """Per-file binding: ``_invoke(args)`` → ``invoke_cli(workflows_group, args)``."""
    return lambda args: invoke_cli(workflows_group, args)


def _register_workflow(
    e2e_client, platform_admin, *, function_name: str
) -> dict:
    """Write a workflow source file and register it via the API.

    Returns the register response payload (contains ``id``, ``name``, ``path``,
    etc.) — the DB row the CLI commands will manipulate.
    """
    path = f"workflows/cli_wf_{function_name}.py"
    content = _WORKFLOW_SOURCE.format(function_name=function_name)

    write_resp = e2e_client.put(
        "/api/files/editor/content",
        headers=platform_admin.headers,
        json={"path": path, "content": content, "encoding": "utf-8"},
    )
    assert write_resp.status_code in (200, 201), (
        f"File write failed: {write_resp.status_code} {write_resp.text}"
    )

    register_resp = e2e_client.post(
        "/api/workflows/register",
        headers=platform_admin.headers,
        json={"path": path, "function_name": function_name},
    )
    # If a prior test run left this registered, look it up.
    if register_resp.status_code == 409:
        list_resp = e2e_client.get(
            "/api/workflows", headers=platform_admin.headers
        )
        assert list_resp.status_code == 200, list_resp.text
        for wf in list_resp.json():
            if (
                wf.get("function_name") == function_name
                and wf.get("source_file_path") == path
            ):
                return {
                    "id": wf["id"],
                    "name": wf["name"],
                    "function_name": wf["function_name"],
                    "path": path,
                }
        raise AssertionError(
            f"409 on register but could not find existing {function_name}"
        )
    assert register_resp.status_code in (200, 201), (
        f"Register failed: {register_resp.status_code} {register_resp.text}"
    )
    return register_resp.json()


def _create_role(e2e_client, platform_admin, *, name: str) -> str:
    """Create a platform role via the REST API; returns the role UUID."""
    resp = e2e_client.post(
        "/api/roles",
        headers=platform_admin.headers,
        json={"name": name},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


@pytest.mark.e2e
class TestCliWorkflows:
    """End-to-end coverage for ``bifrost workflows`` commands."""

    def test_list_returns_payload(self, cli_client, _invoke) -> None:
        """``workflows list --json`` returns a JSON array of workflow metadata."""
        result = _invoke(["--json", "list"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        # Every item has an id and a name; workflows visible to a platform
        # admin include at least the function_name field for CodeLens.
        for item in payload:
            assert "id" in item
            assert "name" in item

    def test_update_by_name_roundtrip(
        self, cli_client, _invoke, e2e_client, platform_admin
    ) -> None:
        """``workflows update <name> --description ...`` patches via name ref."""
        fn = f"cli_wf_update_{uuid4().hex[:8]}"
        wf = _register_workflow(e2e_client, platform_admin, function_name=fn)
        wf_id = wf["id"]

        # Description is a tri-state; pass a value to exercise the PATCH path.
        new_description = f"updated by CLI test {uuid4().hex[:6]}"
        new_timeout = 120

        try:
            result = _invoke(
                [
                    "--json",
                    "update",
                    wf["name"],
                    "--description",
                    new_description,
                    "--timeout-seconds",
                    str(new_timeout),
                ]
            )
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert str(payload["id"]) == wf_id
            assert payload["description"] == new_description
            assert payload["timeout_seconds"] == new_timeout
        finally:
            _invoke(["--json", "delete", wf_id, "--force"])

    def test_update_by_path_func_ref(
        self, cli_client, _invoke, e2e_client, platform_admin
    ) -> None:
        """Ref resolver accepts ``path::func`` for workflows."""
        fn = f"cli_wf_pathfunc_{uuid4().hex[:8]}"
        wf = _register_workflow(e2e_client, platform_admin, function_name=fn)
        wf_id = wf["id"]
        path_ref = f"{wf['path']}::{fn}"

        try:
            result = _invoke(
                [
                    "--json",
                    "update",
                    path_ref,
                    "--category",
                    "CLI-Test",
                ]
            )
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert str(payload["id"]) == wf_id
            assert payload["category"] == "CLI-Test"
        finally:
            _invoke(["--json", "delete", wf_id, "--force"])

    def test_delete_force_bypasses_deactivation_check(
        self, cli_client, _invoke, e2e_client, platform_admin
    ) -> None:
        """``workflows delete --force`` removes the workflow unconditionally."""
        fn = f"cli_wf_delete_{uuid4().hex[:8]}"
        wf = _register_workflow(e2e_client, platform_admin, function_name=fn)
        wf_id = wf["id"]

        result = _invoke(["--json", "delete", wf_id, "--force"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload.get("status") == "deleted"

        # Deleted workflows disappear from the active list.
        list_resp = e2e_client.get(
            "/api/workflows", headers=platform_admin.headers
        )
        assert list_resp.status_code == 200
        ids = {str(w["id"]) for w in list_resp.json()}
        assert wf_id not in ids

    def test_grant_and_revoke_role(
        self, cli_client, _invoke, e2e_client, platform_admin
    ) -> None:
        """``grant-role`` and ``revoke-role`` update the roles endpoint."""
        fn = f"cli_wf_role_{uuid4().hex[:8]}"
        wf = _register_workflow(e2e_client, platform_admin, function_name=fn)
        wf_id = wf["id"]

        role_name = f"cli-wf-role-{uuid4().hex[:8]}"
        role_id = _create_role(e2e_client, platform_admin, name=role_name)

        try:
            # Grant by workflow name + role name (both name-based refs).
            grant_result = _invoke(
                ["--json", "grant-role", wf["name"], role_name]
            )
            assert grant_result.exit_code == 0, grant_result.output
            grant_payload = json.loads(grant_result.output)
            assert grant_payload["granted"] is True
            assert grant_payload["role_id"] == role_id
            assert grant_payload["workflow_id"] == wf_id

            # Confirm via the server-side roles endpoint.
            roles_resp = e2e_client.get(
                f"/api/workflows/{wf_id}/roles",
                headers=platform_admin.headers,
            )
            assert roles_resp.status_code == 200, roles_resp.text
            assert role_id in roles_resp.json()["role_ids"]

            # Revoke by UUID refs (exercises the ref pass-through path).
            revoke_result = _invoke(
                ["--json", "revoke-role", wf_id, role_id]
            )
            assert revoke_result.exit_code == 0, revoke_result.output
            revoke_payload = json.loads(revoke_result.output)
            assert revoke_payload["revoked"] is True

            roles_after = e2e_client.get(
                f"/api/workflows/{wf_id}/roles",
                headers=platform_admin.headers,
            )
            assert roles_after.status_code == 200
            assert role_id not in roles_after.json()["role_ids"]
        finally:
            _invoke(["--json", "delete", wf_id, "--force"])
            e2e_client.delete(
                f"/api/roles/{role_id}", headers=platform_admin.headers
            )

    def test_revoke_role_missing_returns_exit_1(
        self, cli_client, _invoke, e2e_client, platform_admin
    ) -> None:
        """Revoking a role that isn't granted surfaces the server 404 as exit 1.

        This documents the accept-partial-failure decision from the plan's
        open question #3: each grant/revoke is a single server round-trip;
        failures surface via the standard HTTP error path (exit 1, body in
        stderr). A future ``--roles foo,bar,baz`` diff-and-apply command can
        reuse this contract by collecting per-role outcomes and exiting 1
        when any leg fails.
        """
        fn = f"cli_wf_missing_{uuid4().hex[:8]}"
        wf = _register_workflow(e2e_client, platform_admin, function_name=fn)
        wf_id = wf["id"]

        role_name = f"cli-wf-missing-{uuid4().hex[:8]}"
        role_id = _create_role(e2e_client, platform_admin, name=role_name)

        try:
            result = _invoke(["--json", "revoke-role", wf_id, role_id])
            # Server returns 404 for a non-existent assignment; CLI surfaces
            # as exit 1 with the HTTP body on stderr (see base._print_http_error).
            assert result.exit_code == 1, result.output
        finally:
            _invoke(["--json", "delete", wf_id, "--force"])
            e2e_client.delete(
                f"/api/roles/{role_id}", headers=platform_admin.headers
            )


@pytest.mark.e2e
class TestCliWorkflowsRegisterHelp:
    """Argparse-level smoke test for ``workflows register``.

    Full E2E of ``register`` is intentionally skipped: the command takes a
    workspace-relative path and a decorated function name, which are tightly
    coupled to the file-storage write path (writing through ``/api/files``,
    then calling ``/api/workflows/register``). The higher-level lifecycle
    commands above exercise the same DB state by registering through the
    REST helper; that covers the downstream CLI contract. Keep this help
    check so a missing ``--path`` / ``--function-name`` argument fails loudly.
    """

    def test_register_help_lists_required_flags(self, _invoke) -> None:
        result = _invoke(["register", "--help"])
        assert result.exit_code == 0, result.output
        assert "--path" in result.output
        assert "--function-name" in result.output
        # ``--org`` flag is present for optional scope.
        assert "--org" in result.output

    def test_register_missing_path_fails(self) -> None:
        runner = CliRunner()
        # ``standalone_mode=True`` so Click's missing-option error exits cleanly.
        result = runner.invoke(workflows_group, ["register"])
        assert result.exit_code != 0
