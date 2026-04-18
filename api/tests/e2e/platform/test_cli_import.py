"""E2E tests for ``bifrost import`` CLI command.

The round-trip shape is intentional:

1. Seed a workflow into the live API so the regenerated manifest has real
   content to bundle.
2. Run ``bifrost export --portable`` against a tmp directory to produce a
   scrubbed bundle (matches the Task-14 artefact shape).
3. Run ``bifrost import`` back into the SAME environment with
   ``--role-mode name`` and ``--org <org1-uuid>``. Because the UUIDs on
   the entities themselves are preserved by the scrub, the import is an
   idempotent no-op update on the server side — the test asserts the
   response shape rather than a specific change count.
4. Assert the ``--dry-run`` flag surfaces the server's dry-run response
   without applying writes.
5. Error path: a bundle directory missing ``.bifrost/`` exits 1.

The command is driven through ``_import_impl`` directly rather than
``CliRunner`` so the test can supply an explicit :class:`BifrostClient`
and skip the credentials-file singleton plumbing (same pattern as
``test_cli_export.py``).
"""

from __future__ import annotations

import asyncio
import pathlib
from uuid import UUID, uuid4

import click
import pytest

from bifrost.commands.export import _export_impl
from bifrost.commands.import_cmd import (
    _import_impl,
    _validate_bundle_dir,
    handle_import,
)


def _seed_workflow(e2e_client, headers, slug: str) -> None:
    """Register a simple workflow so the manifest has real content."""
    path = f"workflows/{slug}.py"
    content = (
        "from bifrost import workflow\n\n"
        f"@workflow\n"
        f"def {slug}():\n"
        "    return 'ok'\n"
    )
    resp = e2e_client.post(
        "/api/files/write",
        headers=headers,
        json={
            "path": path,
            "content": content,
            "mode": "cloud",
            "location": "workspace",
            "binary": False,
        },
    )
    assert resp.status_code == 204, f"seed write failed: {resp.status_code} {resp.text}"
    resp = e2e_client.post(
        "/api/workflows/register",
        headers=headers,
        json={"path": path, "function_name": slug},
    )
    assert resp.status_code in (200, 201), (
        f"seed register failed: {resp.status_code} {resp.text}"
    )


def _export_bundle(cli_client, tmp_path: pathlib.Path, slug: str) -> pathlib.Path:
    """Export a portable bundle and return the bundle dir."""
    bundle_dir = tmp_path / "bundle"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workflows").mkdir()
    (workspace / "workflows" / f"{slug}.py").write_text(
        f"def {slug}():\n    return 'ok'\n"
    )

    asyncio.run(
        _export_impl(
            client=cli_client,
            out_dir=bundle_dir,
            portable=True,
            workspace_root=workspace,
        )
    )
    assert (bundle_dir / ".bifrost").is_dir()
    return bundle_dir


@pytest.mark.e2e
class TestCliImport:
    """End-to-end coverage for ``bifrost import``."""

    def test_round_trip_same_env_is_noop_update(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        org1,
        tmp_path,
    ) -> None:
        """Exporting and re-importing into the same env is idempotent.

        Portable-scrubbed bundles preserve entity UUIDs, so upserting back
        into the same DB touches existing rows. The server may report
        ``update`` actions (fields like timestamps can round-trip to "no
        effective change" but the diff detector flags them) — the test
        asserts only that the response is structurally valid and no
        warnings fire about missing names.
        """
        slug = f"import_wf_{uuid4().hex[:8]}"
        _seed_workflow(e2e_client, platform_admin.headers, slug)

        bundle_dir = _export_bundle(cli_client, tmp_path, slug)

        result = asyncio.run(
            _import_impl(
                client=cli_client,
                bundle_dir=bundle_dir,
                target_org=UUID(org1["id"]),
                role_mode="name",
                dry_run=False,
                delete_removed=False,
            )
        )

        assert isinstance(result, dict)
        # Server contract: applied OR no-changes path both produce a valid shape.
        assert "entity_changes" in result
        assert "warnings" in result
        # No "unknown role name" style failures from role_resolution='name'.
        role_warnings = [w for w in result["warnings"] if "role" in w.lower()]
        assert not role_warnings, f"unexpected role warnings: {role_warnings}"

    def test_dry_run_reports_without_writing(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        org1,
        tmp_path,
    ) -> None:
        """``--dry-run`` sets ``dry_run=True`` on the response and skips commit."""
        slug = f"import_dry_{uuid4().hex[:8]}"
        _seed_workflow(e2e_client, platform_admin.headers, slug)

        bundle_dir = _export_bundle(cli_client, tmp_path, slug)

        result = asyncio.run(
            _import_impl(
                client=cli_client,
                bundle_dir=bundle_dir,
                target_org=UUID(org1["id"]),
                role_mode="name",
                dry_run=True,
                delete_removed=False,
            )
        )

        assert result.get("dry_run") is True
        # A dry-run import never reports ``applied=True``.
        assert result.get("applied") is not True

    def test_invalid_bundle_dir_exits_nonzero(self, cli_client, tmp_path) -> None:
        """Missing ``.bifrost/`` directory fails fast with a ClickException.

        Driven via :func:`handle_import` so we exercise the same exit-code
        pipeline the ``bifrost`` binary uses; a non-zero exit means
        ``cli.main`` returns the code to the user. The ``cli_client``
        fixture pre-populates thread-local creds so the ``pass_resolver``
        layer doesn't short-circuit on "not logged in" before validation.
        """
        del cli_client  # fixture side-effects only
        # Empty directory — no .bifrost/ subdir.
        empty = tmp_path / "not-a-bundle"
        empty.mkdir()

        rc = handle_import([str(empty)])
        assert rc != 0, "expected non-zero exit for invalid bundle"

    def test_validate_bundle_dir_missing_manifest_yaml(self, tmp_path) -> None:
        """``.bifrost/`` present but empty also fails validation."""
        bundle = tmp_path / "bundle"
        (bundle / ".bifrost").mkdir(parents=True)

        with pytest.raises(click.ClickException):
            _validate_bundle_dir(bundle)
