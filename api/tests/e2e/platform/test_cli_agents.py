"""E2E tests for ``bifrost agents`` CLI commands.

Covers the CRUD surface from Task 5e of the CLI mutation surface plan:

* ``bifrost agents create --name foo --system-prompt @prompt.md`` — POSTs a
  new agent with the prompt loaded from disk.
* ``bifrost agents update <ref> --llm-model ...`` — PUTs (the audit
  correction — **not** PATCH) by UUID or name ref.
* ``bifrost agents delete <ref>`` — soft-deletes the agent; subsequent
  fetches via the admin API return 404 / mark the record inactive.

The commands are invoked via :class:`click.testing.CliRunner` against the
real API stack. ``BifrostClient.get_instance`` is patched via the thread-
local to return a client bound to the E2E API URL with ``platform_admin``'s
JWT so the CLI code path exercised here is identical to what a real user
hits.
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
from bifrost.commands.agents import agents_group  # noqa: E402


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
    """Invoke ``agents_group`` with the given CLI args via CliRunner."""
    runner = CliRunner()
    return runner.invoke(agents_group, args, standalone_mode=False, catch_exceptions=False)


@pytest.mark.e2e
class TestCliAgents:
    """End-to-end coverage for ``bifrost agents`` commands."""

    def test_create_update_delete_roundtrip(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        tmp_path,
    ) -> None:
        """Create via @file prompt → update llm-model → delete."""
        name = f"cli-agent-{uuid4().hex[:8]}"

        # --- prompt file (multi-line to exercise the loader) ---
        prompt_path = tmp_path / "prompt.md"
        prompt_text = (
            "# System Prompt\n"
            "\n"
            "You are a test agent used by the CLI agents command suite.\n"
            "Stay terse.\n"
        )
        prompt_path.write_text(prompt_text, encoding="utf-8")

        # --- create ---
        create_result = _invoke(
            [
                "--json",
                "create",
                "--name",
                name,
                "--system-prompt",
                f"@{prompt_path}",
                "--access-level",
                "authenticated",
            ]
        )
        assert create_result.exit_code == 0, create_result.output
        created = json.loads(create_result.output)
        created_id = str(created["id"])
        assert created["name"] == name
        assert created["system_prompt"] == prompt_text
        assert created["access_level"] == "authenticated"

        # Sanity-check via REST that the agent is reachable by UUID.
        get_resp = e2e_client.get(
            f"/api/agents/{created_id}",
            headers=platform_admin.headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["system_prompt"] == prompt_text

        # --- update (by name ref) — changes the llm-model ---
        new_model = "claude-3-5-sonnet-20241022"
        update_result = _invoke(
            ["--json", "update", name, "--llm-model", new_model]
        )
        assert update_result.exit_code == 0, update_result.output
        updated = json.loads(update_result.output)
        assert str(updated["id"]) == created_id
        assert updated["llm_model"] == new_model
        # The unrelated prompt should be left untouched (default-omit for unset flags).
        assert updated["system_prompt"] == prompt_text

        # --- delete (by UUID — exercise the pass-through path) ---
        delete_result = _invoke(["--json", "delete", created_id])
        assert delete_result.exit_code == 0, delete_result.output
        deleted_payload = json.loads(delete_result.output)
        assert deleted_payload["deleted"] == created_id

        # Confirm the soft-delete: admin list filters inactive agents by default.
        list_resp = e2e_client.get(
            "/api/agents", headers=platform_admin.headers
        )
        assert list_resp.status_code == 200
        active_ids = {str(a["id"]) for a in list_resp.json()}
        assert created_id not in active_ids, (
            f"Agent {created_id} should be absent from active list after delete"
        )
