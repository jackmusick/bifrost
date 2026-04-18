"""E2E tests for ``bifrost forms`` CLI commands.

Covers the CRUD surface from Task 5d of the CLI mutation surface plan:

* ``bifrost forms create --workflow path::func --schema @schema.yaml --name foo``
  resolves the workflow ref, loads the schema YAML from disk, and POSTs the
  form body to ``/api/forms``.
* ``bifrost forms update <ref> --name bar`` PATCHes by name or UUID.
* ``bifrost forms delete <ref>`` soft-deletes the form.

The tests run a real workflow + schema fixture so the ref resolver and
``@file`` loader are exercised end-to-end against the API stack.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from bifrost.commands.forms import forms_group
from tests.e2e.conftest import write_and_register


@pytest.fixture
def _invoke(invoke_cli):
    """Per-file binding: ``_invoke(args)`` → ``invoke_cli(forms_group, args)``."""
    return lambda args: invoke_cli(forms_group, args)


@pytest.fixture
def registered_workflow(e2e_client, platform_admin):
    """Register a minimal workflow so ``--workflow path::func`` can resolve it."""
    suffix = uuid4().hex[:8]
    function_name = f"cli_forms_wf_{suffix}"
    path = f"workflows/cli_forms_{suffix}.py"
    content = (
        "from bifrost import workflow\n\n"
        f"@workflow\ndef {function_name}():\n"
        "    return {'ok': True}\n"
    )
    wf = write_and_register(
        e2e_client,
        platform_admin.headers,
        path=path,
        content=content,
        function_name=function_name,
    )
    return {
        "id": wf["id"],
        "path": path,
        "function_name": function_name,
        "ref": f"{path}::{function_name}",
    }


@pytest.fixture
def schema_yaml_path(tmp_path):
    """Write a form schema YAML file and return its path."""
    schema_file = tmp_path / "schema.yaml"
    schema_file.write_text(
        "fields:\n"
        "  - name: email\n"
        "    type: text\n"
        "    label: Email\n"
        "    required: true\n"
        "  - name: count\n"
        "    type: number\n"
        "    label: Count\n"
        "    required: false\n"
    )
    return schema_file


@pytest.mark.e2e
class TestCliForms:
    """End-to-end coverage for ``bifrost forms`` commands."""

    def test_create_with_workflow_ref_and_schema_file(
        self,
        cli_client,
        _invoke,
        e2e_client,
        platform_admin,
        registered_workflow,
        schema_yaml_path,
    ):
        """``forms create --workflow path::func --schema @file`` builds the body end-to-end."""
        name = f"cli-form-{uuid4().hex[:8]}"
        result = _invoke([
            "--json",
            "create",
            "--name", name,
            "--workflow", registered_workflow["ref"],
            "--form-schema", f"@{schema_yaml_path}",
            "--access-level", "authenticated",
        ])
        assert result.exit_code == 0, result.output
        created = json.loads(result.output)
        created_id = str(created["id"])
        assert created["name"] == name
        assert str(created["workflow_id"]) == str(registered_workflow["id"])

        # Schema fields round-tripped into FormField records.
        get_resp = e2e_client.get(
            f"/api/forms/{created_id}", headers=platform_admin.headers
        )
        assert get_resp.status_code == 200, get_resp.text
        fetched = get_resp.json()
        schema = fetched.get("form_schema") or {}
        field_names = {f["name"] for f in schema.get("fields", [])}
        assert field_names == {"email", "count"}

        # Cleanup.
        _invoke(["--json", "delete", created_id])

    def test_update_by_name_ref(
        self,
        cli_client,
        _invoke,
        e2e_client,
        platform_admin,
        registered_workflow,
        schema_yaml_path,
    ):
        """``forms update <name>`` PATCHes and only supplied fields change."""
        name = f"cli-form-upd-{uuid4().hex[:8]}"
        renamed = f"cli-form-upd-new-{uuid4().hex[:8]}"

        create_result = _invoke([
            "--json",
            "create",
            "--name", name,
            "--workflow", registered_workflow["ref"],
            "--form-schema", f"@{schema_yaml_path}",
            "--access-level", "authenticated",
        ])
        assert create_result.exit_code == 0, create_result.output
        created_id = str(json.loads(create_result.output)["id"])

        update_result = _invoke([
            "--json",
            "update", name,
            "--name", renamed,
            "--description", "updated via cli",
        ])
        assert update_result.exit_code == 0, update_result.output
        updated = json.loads(update_result.output)
        assert str(updated["id"]) == created_id
        assert updated["name"] == renamed
        assert updated["description"] == "updated via cli"
        # Workflow untouched since the flag wasn't supplied.
        assert str(updated["workflow_id"]) == str(registered_workflow["id"])

        # Cleanup.
        _invoke(["--json", "delete", created_id])

    def test_delete_soft_deletes_form(
        self,
        cli_client,
        _invoke,
        e2e_client,
        platform_admin,
        registered_workflow,
        schema_yaml_path,
    ):
        """``forms delete <ref>`` soft-deletes (is_active=False)."""
        name = f"cli-form-del-{uuid4().hex[:8]}"
        create_result = _invoke([
            "--json",
            "create",
            "--name", name,
            "--workflow", registered_workflow["ref"],
            "--form-schema", f"@{schema_yaml_path}",
            "--access-level", "authenticated",
        ])
        assert create_result.exit_code == 0, create_result.output
        created_id = str(json.loads(create_result.output)["id"])

        delete_result = _invoke(["--json", "delete", created_id])
        assert delete_result.exit_code == 0, delete_result.output
        payload = json.loads(delete_result.output)
        assert payload["deleted"] == created_id

        # Superuser GET still returns the soft-deleted record with is_active=False.
        get_resp = e2e_client.get(
            f"/api/forms/{created_id}", headers=platform_admin.headers
        )
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["is_active"] is False
