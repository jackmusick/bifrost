"""Unit: upgrade-preview diff (Task 22) — pure function, no DB/S3.

``compute_upgrade_diff`` compares a parsed zip (:class:`PreviewResult`) against
an existing install's solution-owned rows using the SAME per-install uuid5
remapping the deployer applies (``solution_entity_id``), so the diff mirrors
exactly what a deploy of the zip would do:

* manifest entry whose remapped id exists on the install → kept (not listed)
* manifest entry whose remapped id is absent → added
* install row whose id matches no remapped manifest id → removed
* config declarations compared by key: added / removed / changed (type, required)
"""
from __future__ import annotations

import uuid

import pytest

from src.services.solutions.deploy import solution_entity_id
from src.services.solutions.zip_install import PreviewResult, compute_upgrade_diff

pytestmark = pytest.mark.unit

INSTALL_ID = uuid.uuid4()

# Stable manifest ids (what a workspace's .bifrost/*.yaml would carry).
WF_KEPT = uuid.uuid4()
WF_NEW = uuid.uuid4()
TBL_KEPT = uuid.uuid4()


def _remapped(manifest_id: uuid.UUID) -> uuid.UUID:
    return solution_entity_id(INSTALL_ID, manifest_id)


def _empty_installed() -> dict[str, list[tuple[uuid.UUID, str]]]:
    return {"workflows": [], "tables": [], "apps": [], "forms": [], "agents": []}


def test_added_removed_kept_entities_use_uuid5_identity():
    """Identity is uuid5(install, manifest_id) — NOT raw manifest id equality."""
    removed_row_id = uuid.uuid4()  # an install row no manifest entry maps to
    preview = PreviewResult(
        slug="s",
        workflows=[
            {"id": str(WF_KEPT), "name": "kept-wf"},
            {"id": str(WF_NEW), "name": "new-wf"},
        ],
        tables=[{"id": str(TBL_KEPT), "name": "kept-tbl"}],
    )
    installed = _empty_installed()
    installed["workflows"] = [
        (_remapped(WF_KEPT), "kept-wf"),
        (removed_row_id, "old-wf"),
    ]
    installed["tables"] = [(_remapped(TBL_KEPT), "kept-tbl")]

    diff = compute_upgrade_diff(
        preview,
        install_id=INSTALL_ID,
        installed=installed,
        installed_config_schemas=[],
    )

    assert diff.workflows.added == ["new-wf"]
    assert diff.workflows.removed == ["old-wf"]
    # kept entities appear in NEITHER list
    assert "kept-wf" not in diff.workflows.added + diff.workflows.removed
    assert diff.tables.added == [] and diff.tables.removed == []
    # untouched entity types are empty, not omitted
    assert diff.apps.added == [] and diff.apps.removed == []
    assert diff.forms.added == [] and diff.forms.removed == []
    assert diff.agents.added == [] and diff.agents.removed == []


def test_display_name_falls_back_to_id():
    nameless_manifest_id = uuid.uuid4()
    nameless_row_id = uuid.uuid4()
    preview = PreviewResult(
        slug="s", agents=[{"id": str(nameless_manifest_id)}]
    )
    installed = _empty_installed()
    installed["agents"] = [(nameless_row_id, "")]

    diff = compute_upgrade_diff(
        preview,
        install_id=INSTALL_ID,
        installed=installed,
        installed_config_schemas=[],
    )

    assert diff.agents.added == [str(nameless_manifest_id)]
    assert diff.agents.removed == [str(nameless_row_id)]


def test_config_schema_added_removed_changed():
    preview = PreviewResult(
        slug="s",
        config_schemas=[
            {"key": "NEW_KEY", "type": "string", "required": False},
            {"key": "TYPE_CHANGED", "type": "string", "required": True},
            {"key": "REQ_CHANGED", "type": "secret", "required": True},
            {"key": "SAME", "type": "secret", "required": True},
        ],
    )
    installed_schemas = [
        ("GONE_KEY", "string", False),
        ("TYPE_CHANGED", "secret", True),
        ("REQ_CHANGED", "secret", False),
        ("SAME", "secret", True),
    ]

    diff = compute_upgrade_diff(
        preview,
        install_id=INSTALL_ID,
        installed=_empty_installed(),
        installed_config_schemas=installed_schemas,
    )

    assert diff.config_schemas.added == ["NEW_KEY"]
    assert diff.config_schemas.removed == ["GONE_KEY"]
    changed = {c.key: c for c in diff.config_schemas.changed}
    assert set(changed) == {"TYPE_CHANGED", "REQ_CHANGED"}
    assert changed["TYPE_CHANGED"].from_.type == "secret"
    assert changed["TYPE_CHANGED"].to.type == "string"
    assert changed["REQ_CHANGED"].from_.required is False
    assert changed["REQ_CHANGED"].to.required is True


def test_changed_entry_serializes_from_alias():
    """The wire shape uses ``from`` (the natural API name), not ``from_``."""
    preview = PreviewResult(
        slug="s", config_schemas=[{"key": "K", "type": "string", "required": False}]
    )
    diff = compute_upgrade_diff(
        preview,
        install_id=INSTALL_ID,
        installed=_empty_installed(),
        installed_config_schemas=[("K", "secret", False)],
    )
    payload = diff.model_dump(by_alias=True)
    assert payload["config_schemas"]["changed"][0]["from"] == {
        "type": "secret",
        "required": False,
    }


def test_empty_diff_when_identical():
    preview = PreviewResult(
        slug="s",
        workflows=[{"id": str(WF_KEPT), "name": "wf"}],
        config_schemas=[{"key": "K", "type": "secret", "required": True}],
    )
    installed = _empty_installed()
    installed["workflows"] = [(_remapped(WF_KEPT), "wf")]

    diff = compute_upgrade_diff(
        preview,
        install_id=INSTALL_ID,
        installed=installed,
        installed_config_schemas=[("K", "secret", True)],
    )

    for etype in ("workflows", "tables", "apps", "forms", "agents"):
        section = getattr(diff, etype)
        assert section.added == [] and section.removed == []
    assert diff.config_schemas.added == []
    assert diff.config_schemas.removed == []
    assert diff.config_schemas.changed == []
