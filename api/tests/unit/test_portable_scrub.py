"""Unit tests for :mod:`bifrost.portable`.

Each test pins one rule from Task 14 of the CLI mutation surface plan:

* ``organization_id`` is stripped from every entity.
* ``user_id`` / ``created_by`` / ``updated_by`` are stripped everywhere.
* Timestamp fields (``created_at``, ``updated_at``, ``deleted_at``,
  ``last_*``) are stripped everywhere.
* OAuth secrets (``client_secret``, ``oauth_token_id``, ``access_token``,
  ``refresh_token``) are stripped anywhere in the tree.
* ``value`` on ``config_type == "secret"`` configs is nulled; other
  configs are untouched and ``description`` is preserved.
* Event-source adapter runtime state (``external_id``, ``expires_at``,
  ``state``) is stripped.
* ``roles`` lists on forms / agents / apps are rewritten to ``role_names``
  via the supplied ``role_names_by_id`` map.
* Workflow ``path::func`` refs are kept.
* Entity ``id`` UUIDs are preserved on every entity.
* The scrubbed manifest can be round-tripped through a stub
  ``import_manifest_from_repo`` without surfacing any stripped field.
"""

from __future__ import annotations

import pathlib
import sys
from copy import deepcopy
from typing import Any

# Standalone bifrost package import — mirrors test_dto_flags.py.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from bifrost.portable import scrub  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_manifest() -> dict[str, Any]:
    """Return a full-fidelity manifest that exercises every scrub rule."""
    return {
        "organizations": [
            {
                "id": "org-aaaa",
                "name": "Acme",
                "created_at": "2026-01-01T00:00:00Z",
                "created_by": "alice",
            }
        ],
        "roles": [
            {"id": "role-admin", "name": "admin"},
            {"id": "role-viewer", "name": "viewer"},
        ],
        "workflows": {
            "wf-1": {
                "id": "wf-1",
                "name": "Onboard",
                "path": "workflows/onboard.py",
                "function_name": "run_onboard",
                "type": "workflow",
                "organization_id": "org-aaaa",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "last_run_at": "2026-01-03T00:00:00Z",
                "created_by": "alice",
            }
        },
        "forms": {
            "form-1": {
                "id": "form-1",
                "name": "Intake",
                "path": "forms/intake.form.yaml",
                "organization_id": "org-aaaa",
                "roles": ["role-admin", "role-viewer"],
                "updated_by": "bob",
            }
        },
        "agents": {
            "agent-1": {
                "id": "agent-1",
                "name": "Support",
                "path": "agents/support.agent.yaml",
                "organization_id": "org-aaaa",
                "roles": ["role-admin"],
            }
        },
        "apps": {
            "app-1": {
                "id": "app-1",
                "name": "Dashboard",
                "path": "apps/dashboard",
                "organization_id": "org-aaaa",
                "roles": ["role-viewer"],
            }
        },
        "integrations": {
            "int-1": {
                "id": "int-1",
                "name": "HaloPSA",
                "organization_id": "org-aaaa",
                "oauth_provider": {
                    "provider_name": "halopsa",
                    "client_id": "halopsa-client",
                    "client_secret": "ssshh",
                    "access_token": "token-abc",
                    "refresh_token": "refresh-xyz",
                },
                "mappings": [
                    {
                        "organization_id": "org-aaaa",
                        "entity_id": "tenant-1",
                        "oauth_token_id": "oauth-123",
                    }
                ],
            }
        },
        "configs": {
            "cfg-1": {
                "id": "cfg-1",
                "key": "api_key",
                "config_type": "secret",
                "organization_id": "org-aaaa",
                "value": "super-secret",
                "description": "Third-party API key",
            },
            "cfg-2": {
                "id": "cfg-2",
                "key": "base_url",
                "config_type": "string",
                "organization_id": "org-aaaa",
                "value": "https://api.example.com",
                "description": "Base URL",
            },
        },
        "events": {
            "ev-1": {
                "id": "ev-1",
                "name": "ticket-webhook",
                "source_type": "webhook",
                "organization_id": "org-aaaa",
                "external_id": "adapter-ext-42",
                "expires_at": "2026-06-01T00:00:00Z",
                "state": "subscribed",
                "subscriptions": [
                    {
                        "id": "sub-1",
                        "workflow_id": "wf-1",
                        "event_type": "ticket.created",
                    }
                ],
            }
        },
        "tables": {
            "tbl-1": {
                "id": "tbl-1",
                "name": "incidents",
                "organization_id": "org-aaaa",
            }
        },
    }


ROLE_NAMES = {"role-admin": "admin", "role-viewer": "viewer"}


# ---------------------------------------------------------------------------
# Per-rule assertions
# ---------------------------------------------------------------------------


def test_strips_organization_id_from_every_entity() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)

    # No ``organization_id`` anywhere in the tree.
    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            assert "organization_id" not in value
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(scrubbed)
    assert any("organization_id" in rule for rule in rules)


def test_strips_attribution_fields() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    wf = scrubbed["workflows"]["wf-1"]
    assert "created_by" not in wf
    assert "updated_by" not in wf
    assert "user_id" not in wf
    form = scrubbed["forms"]["form-1"]
    assert "updated_by" not in form
    assert any("attribution" in rule for rule in rules)


def test_strips_timestamps_including_last_prefix() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    wf = scrubbed["workflows"]["wf-1"]
    assert "created_at" not in wf
    assert "updated_at" not in wf
    assert "last_run_at" not in wf
    # Organizations (list shape) also get timestamps stripped.
    assert "created_at" not in scrubbed["organizations"][0]
    assert any("timestamp" in rule for rule in rules)


def test_strips_oauth_secrets_anywhere_in_tree() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    oauth = scrubbed["integrations"]["int-1"]["oauth_provider"]
    assert "client_secret" not in oauth
    assert "access_token" not in oauth
    assert "refresh_token" not in oauth
    # client_id is NOT a secret and must remain.
    assert oauth["client_id"] == "halopsa-client"
    mapping = scrubbed["integrations"]["int-1"]["mappings"][0]
    assert "oauth_token_id" not in mapping
    assert any("OAuth" in rule for rule in rules)


def test_strips_service_oauth_token_id_anywhere_in_tree() -> None:
    """MCP connections carry service_oauth_token_id — a live service-token FK.
    It must be scrubbed from portable exports just like oauth_token_id
    (prereq for Export Solution; success-criteria §5)."""
    manifest = {
        "mcp_connections": {
            "conn-1": {
                "id": "conn-1",
                "name": "halo-mcp",
                "organization_id": "org-aaaa",
                "service_oauth_token_id": "svc-token-999",
            }
        }
    }
    scrubbed, _rules = scrub(manifest, role_names_by_id=ROLE_NAMES)
    conn = scrubbed["mcp_connections"]["conn-1"]
    assert "service_oauth_token_id" not in conn
    # Non-secret identity fields remain.
    assert conn["name"] == "halo-mcp"


def test_nulls_secret_config_values_preserving_description() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    secret_cfg = scrubbed["configs"]["cfg-1"]
    assert secret_cfg["value"] is None
    # Description preserved.
    assert secret_cfg["description"] == "Third-party API key"
    # Non-secret config value is left intact.
    plain_cfg = scrubbed["configs"]["cfg-2"]
    assert plain_cfg["value"] == "https://api.example.com"
    assert any("secret-type config" in rule for rule in rules)


def test_strips_event_source_runtime_state() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    event = scrubbed["events"]["ev-1"]
    assert "external_id" not in event
    assert "expires_at" not in event
    assert "state" not in event
    # Subscriptions retained verbatim.
    assert event["subscriptions"][0]["workflow_id"] == "wf-1"
    assert any("event-source" in rule for rule in rules)


def test_rewrites_role_ids_to_role_names() -> None:
    scrubbed, rules = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    form = scrubbed["forms"]["form-1"]
    assert form["role_names"] == ["admin", "viewer"]
    assert "roles" not in form
    agent = scrubbed["agents"]["agent-1"]
    assert agent["role_names"] == ["admin"]
    app = scrubbed["apps"]["app-1"]
    assert app["role_names"] == ["viewer"]
    assert any("role_ids -> role_names" in rule for rule in rules)


def test_unresolved_role_ids_are_surfaced() -> None:
    manifest = _fresh_manifest()
    manifest["forms"]["form-1"]["roles"] = ["role-admin", "role-missing"]
    scrubbed, _ = scrub(manifest, role_names_by_id=ROLE_NAMES)
    form = scrubbed["forms"]["form-1"]
    assert form["role_names"] == ["admin"]
    assert form["unresolved_role_ids"] == ["role-missing"]


def test_workflow_path_and_function_preserved() -> None:
    scrubbed, _ = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    wf = scrubbed["workflows"]["wf-1"]
    # path::func equivalents are preserved.
    assert wf["path"] == "workflows/onboard.py"
    assert wf["function_name"] == "run_onboard"


def test_entity_ids_are_preserved() -> None:
    scrubbed, _ = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    assert scrubbed["workflows"]["wf-1"]["id"] == "wf-1"
    assert scrubbed["forms"]["form-1"]["id"] == "form-1"
    assert scrubbed["agents"]["agent-1"]["id"] == "agent-1"
    assert scrubbed["apps"]["app-1"]["id"] == "app-1"
    assert scrubbed["integrations"]["int-1"]["id"] == "int-1"
    assert scrubbed["configs"]["cfg-1"]["id"] == "cfg-1"
    assert scrubbed["configs"]["cfg-2"]["id"] == "cfg-2"
    assert scrubbed["events"]["ev-1"]["id"] == "ev-1"
    assert scrubbed["tables"]["tbl-1"]["id"] == "tbl-1"
    assert scrubbed["organizations"][0]["id"] == "org-aaaa"
    assert {r["id"] for r in scrubbed["roles"]} == {"role-admin", "role-viewer"}


def test_input_manifest_is_not_mutated() -> None:
    manifest = _fresh_manifest()
    snapshot = deepcopy(manifest)
    scrub(manifest, role_names_by_id=ROLE_NAMES)
    assert manifest == snapshot, "scrub must not mutate the caller's manifest"


def test_empty_manifest_produces_no_rules() -> None:
    scrubbed, rules = scrub({}, role_names_by_id={})
    assert scrubbed == {}
    assert rules == []


def test_deterministic_output_same_input_same_rules_list() -> None:
    scrubbed_a, rules_a = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    scrubbed_b, rules_b = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    assert scrubbed_a == scrubbed_b
    assert rules_a == rules_b


# ---------------------------------------------------------------------------
# Round-trip through a stubbed importer
# ---------------------------------------------------------------------------


_STRIPPED_FIELD_NAMES = {
    "organization_id",
    "user_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "deleted_at",
    "client_secret",
    "oauth_token_id",
    "service_oauth_token_id",
    "access_token",
    "refresh_token",
    "external_id",
    "expires_at",
    "state",
}


def _stub_import_manifest_from_repo(manifest: dict[str, Any]) -> list[str]:
    """Surface every stripped field that still appears anywhere in the tree.

    Stand-in for ``src.services.manifest_import.import_manifest_from_repo``
    that the portable-bundle importer (Task 13) will call. The real function
    doesn't accept a dict today; we stub it so the scrub is self-contained
    and fails loudly if a new stripped field regresses.

    Returns the list of ``(path, field_name)`` descriptors that should have
    been scrubbed. An empty list means the scrub left nothing behind.
    """
    leaks: list[str] = []

    def _walk(value: Any, trail: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                # ``state`` is a reserved field only on event sources; skip
                # other sections where "state" has a legitimate meaning.
                if key == "state" and "events/" not in trail:
                    _walk(child, f"{trail}/{key}")
                    continue
                if key.startswith("last_") or key in _STRIPPED_FIELD_NAMES:
                    leaks.append(f"{trail}/{key}")
                _walk(child, f"{trail}/{key}")
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _walk(item, f"{trail}[{idx}]")

    # Secret configs: ``value`` must be None, not missing.
    for cfg_id, cfg in (manifest.get("configs") or {}).items():
        if isinstance(cfg, dict) and cfg.get("config_type") == "secret":
            if cfg.get("value") not in (None,):
                leaks.append(f"configs/{cfg_id}/value (secret must be null)")

    for section_name, section_value in manifest.items():
        _walk(section_value, section_name)
    return leaks


def test_round_trip_through_stub_importer_has_no_leaks() -> None:
    scrubbed, _ = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    leaks = _stub_import_manifest_from_repo(scrubbed)
    assert leaks == [], f"scrub left fields behind: {leaks}"


def test_stub_importer_detects_field_that_slips_through() -> None:
    """Self-check: the stub must catch fields we forget to scrub."""
    scrubbed, _ = scrub(_fresh_manifest(), role_names_by_id=ROLE_NAMES)
    # Simulate a regression: something re-introduces organization_id.
    scrubbed["workflows"]["wf-1"]["organization_id"] = "org-aaaa"
    leaks = _stub_import_manifest_from_repo(scrubbed)
    assert any("organization_id" in leak for leak in leaks)
