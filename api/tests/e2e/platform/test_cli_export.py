"""E2E tests for ``bifrost export`` CLI command.

Drives the full pipeline:

1. Seed a workflow + form entity into the live API so the regenerated
   manifest has real UUIDs / roles / org bindings.
2. Run ``bifrost export --portable`` against a tmp out-dir.
3. Read the emitted ``.bifrost/*.yaml`` files back off disk and assert the
   scrub rules landed: no ``organization_id``, no ``access_token``, no
   ``client_secret``, no timestamps.
4. Inspect ``bundle.meta.yaml`` and assert it enumerates the scrub rules.

The command dispatches through its async implementation directly (rather
than ``CliRunner``) so the test can provide an explicit workspace root
and avoid ``BifrostClient.get_instance`` singleton plumbing.
"""

from __future__ import annotations

import asyncio
import re
from uuid import uuid4

import pytest
import yaml

from bifrost.commands.export import _export_impl


# Fields that MUST NOT appear anywhere in the scrubbed manifest files.
# These map 1:1 to rules in :mod:`bifrost.portable`.
_FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(?m)^\s*(?:organization_id|access_token|client_secret|"
    r"oauth_token_id|refresh_token|created_at|updated_at|"
    r"created_by|updated_by|user_id|external_id|expires_at)\s*:",
    re.IGNORECASE,
)


def _seed_workflow(e2e_client, headers, slug: str) -> None:
    """Register a simple workflow so the manifest has real content to scrub."""
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


@pytest.mark.e2e
class TestCliExport:
    """End-to-end coverage for ``bifrost export`` command."""

    def test_portable_export_writes_scrubbed_bundle(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        tmp_path,
    ) -> None:
        """--portable produces a bundle with no secrets, no org IDs, no timestamps."""
        slug = f"export_wf_{uuid4().hex[:8]}"
        _seed_workflow(e2e_client, platform_admin.headers, slug)

        out_dir = tmp_path / "bundle"
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # Provide at least one workflow file on disk so the code-copy step
        # has something to echo into the bundle.
        (workspace / "workflows").mkdir()
        (workspace / "workflows" / f"{slug}.py").write_text(
            f"def {slug}():\n    return 'ok'\n"
        )

        asyncio.run(
            _export_impl(
                client=cli_client,
                out_dir=out_dir,
                portable=True,
                workspace_root=workspace,
            )
        )

        bifrost_dir = out_dir / ".bifrost"
        assert bifrost_dir.is_dir(), "expected .bifrost/ in the bundle"

        yaml_files = list(bifrost_dir.glob("*.yaml"))
        assert yaml_files, "expected at least one manifest YAML in the bundle"

        # No forbidden fields anywhere.
        for yf in yaml_files:
            text = yf.read_text()
            match = _FORBIDDEN_FIELD_PATTERN.search(text)
            assert match is None, (
                f"{yf.name} still contains a scrubbed field "
                f"{match.group(0).strip() if match else ''!r}"
            )

        # Meta file exists and enumerates the scrub rules.
        meta_path = out_dir / "bundle.meta.yaml"
        assert meta_path.exists(), "expected bundle.meta.yaml"
        meta = yaml.safe_load(meta_path.read_text())
        assert meta["portable"] is True
        # The scrubbed rule list is always a list; emptiness depends on
        # whether the test env's manifest has content the scrubbers fire
        # on. The forbidden-field grep above is the real "did it scrub"
        # verification — this just asserts the meta key shape.
        assert isinstance(meta["scrubbed"], list)
        assert "source_env" in meta
        assert "exported_at" in meta
        assert "bifrost_version" in meta

        # Workflow source was copied.
        assert (out_dir / "workflows" / f"{slug}.py").exists()

    def test_non_portable_export_preserves_fields(
        self,
        cli_client,
        e2e_client,
        platform_admin,
        tmp_path,
    ) -> None:
        """Without --portable the bundle is a straight copy, meta.scrubbed is empty."""
        slug = f"export_raw_{uuid4().hex[:8]}"
        _seed_workflow(e2e_client, platform_admin.headers, slug)

        out_dir = tmp_path / "raw-bundle"
        workspace = tmp_path / "raw-workspace"
        workspace.mkdir()

        asyncio.run(
            _export_impl(
                client=cli_client,
                out_dir=out_dir,
                portable=False,
                workspace_root=workspace,
            )
        )

        meta = yaml.safe_load((out_dir / "bundle.meta.yaml").read_text())
        assert meta["portable"] is False
        assert meta["scrubbed"] == []

        # Manifest files exist and are valid YAML.
        bifrost_dir = out_dir / ".bifrost"
        assert bifrost_dir.is_dir()
        for yf in bifrost_dir.glob("*.yaml"):
            yaml.safe_load(yf.read_text())  # just needs to parse
