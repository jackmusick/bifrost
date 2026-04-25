"""Unit tests for the esbuild-based app bundler (src/services/app_bundler).

These tests cover the two synthesis helpers — `_write_entry` (which writes
`_entry.tsx`) and `_write_bifrost_package` (which writes the synthetic
`node_modules/bifrost/index.js`). Both are driven via string assertions on
generated source; no esbuild subprocess is run.
"""
from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from src.services.app_bundler import (
    _PLATFORM_EXPORT_NAMES,
    SCHEMA_VERSION,
    BundleManifest,
    BundleResult,
    BundlerService,
    build_with_migrate,
)


@pytest.fixture
def bundler() -> BundlerService:
    return BundlerService()


# ---------------------------------------------------------------------------
# _write_entry — regression tests for the 2026-04-16 late-afternoon bugs:
#   - Entry exported a mount() wrapping <BrowserRouter> → "You cannot render
#     a <Router> inside another <Router>". Fix: default-export a React
#     component, no BrowserRouter.
#   - Entry used `createRoot(container).render(...)` → sibling React root
#     that didn't inherit AuthProvider / QueryClientProvider context.
#     Fix: no createRoot; host renders the default export inline.
# ---------------------------------------------------------------------------


def test_write_entry_exports_default_bundled_app(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    sources = ["_layout.tsx", "pages/index.tsx", "pages/clients/index.tsx"]

    bundler._write_entry(src_dir, "_entry.tsx", sources)
    entry = (src_dir / "_entry.tsx").read_text(encoding="utf-8")

    # Must export a React component as the default — the host shell renders
    # it inline so React context (Auth, Query, theme) inherits from the host.
    assert "export default function BundledApp" in entry


def test_write_entry_has_no_browser_router(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    sources = ["_layout.tsx", "pages/index.tsx"]

    bundler._write_entry(src_dir, "_entry.tsx", sources)
    entry = (src_dir / "_entry.tsx").read_text(encoding="utf-8")

    # Host mounts BrowserRouter at the app root. React Router rejects
    # nested routers, so the synthesized entry must NOT include its own.
    assert "BrowserRouter" not in entry


def test_write_entry_has_no_create_root_call(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    sources = ["pages/index.tsx"]

    bundler._write_entry(src_dir, "_entry.tsx", sources)
    entry = (src_dir / "_entry.tsx").read_text(encoding="utf-8")

    # A sibling createRoot() would make the bundled app a detached React
    # tree that doesn't inherit the host's context providers.
    assert "createRoot(" not in entry
    assert "react-dom/client" not in entry


# ---------------------------------------------------------------------------
# _write_bifrost_package — regression test for Phase 3.5 item 5:
#
# The synthesized `node_modules/bifrost/index.js` must only export platform
# proxy entries for names user code actually imports from "bifrost". Today
# it emits the full ~50-name table regardless — post-migration apps import
# a handful of names, so the full table is dead weight.
# ---------------------------------------------------------------------------


def _build_pkg_with_bifrost_imports(
    bundler: BundlerService,
    tmp_path: pathlib.Path,
    imported_names: set[str],
    extra_sources: dict[str, str] | None = None,
) -> str:
    """Materialize a minimal app whose user source imports `imported_names`
    from `"bifrost"`, then run `_write_bifrost_package` and return the
    generated index.js text.
    """
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Seed a single page that pulls the requested names from "bifrost".
    names_list = ", ".join(sorted(imported_names))
    page_body = (
        f'import {{ {names_list} }} from "bifrost";\n'
        'export default function Page() { return null; }\n'
    ) if imported_names else "export default function Page() { return null; }\n"
    (src_dir / "pages").mkdir()
    (src_dir / "pages" / "index.tsx").write_text(page_body, encoding="utf-8")

    sources = ["pages/index.tsx"]

    for rel, body in (extra_sources or {}).items():
        dest = src_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        sources.append(rel)

    bundler._write_bifrost_package(src_dir, sources)
    return (src_dir / "node_modules" / "bifrost" / "index.js").read_text(
        encoding="utf-8"
    )


def test_write_bifrost_package_only_emits_imported_platform_proxies(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    imported = {"Button", "Card"}
    pkg = _build_pkg_with_bifrost_imports(bundler, tmp_path, imported)

    # Exactly the imported platform names get proxy entries. The generator
    # uses repr() for the key literal, which in CPython emits single quotes
    # for short strings — match that rather than re-deriving the formatting.
    assert "export const Button = _p['Button'];" in pkg
    assert "export const Card = _p['Card'];" in pkg

    # Platform names NOT in imported_names must not appear as proxies.
    # Pick a representative sample across the table to avoid a one-off.
    for absent in ("cn", "toast", "useState", "useEffect", "Dialog", "Badge"):
        assert absent not in imported  # sanity check
        assert f'export const {absent} =' not in pkg, (
            f"{absent!r} should not appear as a proxy when user code does "
            f"not import it from 'bifrost'"
        )


def test_write_bifrost_package_emits_nothing_when_no_bifrost_imports(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    pkg = _build_pkg_with_bifrost_imports(bundler, tmp_path, set())

    # No platform proxies at all — no `export const <Name> = _p[...]`.
    for name in _PLATFORM_EXPORT_NAMES:
        assert f'export const {name} =' not in pkg, (
            f"{name!r} should not appear as a proxy when no user code "
            f"imports from 'bifrost'"
        )


def test_write_bifrost_package_proxy_count_matches_imported_subset(
    bundler: BundlerService, tmp_path: pathlib.Path
) -> None:
    # Smoke test: the number of `export const <x> = _p[...]` lines tracks the
    # size of imported_names (minus router primitives which come from
    # react-router-dom regardless).
    imported = {"Button", "Card", "useState", "toast"}
    pkg = _build_pkg_with_bifrost_imports(bundler, tmp_path, imported)

    proxy_line_count = sum(
        1 for line in pkg.splitlines()
        if line.startswith("export const ") and " = _p[" in line
    )
    assert proxy_line_count == len(imported), (
        f"expected {len(imported)} proxies, got {proxy_line_count}:\n{pkg}"
    )


# ---------------------------------------------------------------------------
# build_with_migrate + SCHEMA_VERSION — the deploy-time auto-heal contract.
#
# These pin two guarantees relied on by app_code_files.get_bundle_manifest:
#   1. build_with_migrate always calls the migrator BEFORE the bundler and
#      returns whatever `migrated` the migrator reported — even when the
#      build itself fails. This is what lets a failed first-build still
#      surface the "your source was rewritten, pull on next sync" banner.
#   2. The bundler writes the current SCHEMA_VERSION into every successful
#      manifest.json. Readers compare against this and trigger a fresh
#      migrate+build when the value is missing or older than current.
# ---------------------------------------------------------------------------


async def test_build_with_migrate_runs_migration_before_bundle() -> None:
    """Migration must be called strictly before the bundler, and the
    `migrated` flag bubbles up unchanged.

    Regression: before the schema_version fix, file saves + publishes called
    `bundler.build()` directly, skipping auto-migration entirely. An app
    whose first bundle was produced by the save path never had its imports
    rewritten, so <Outlet />, <LayoutDashboard />, <QuillEditor />, etc.
    used-but-unimported in the legacy auto-scope runtime all failed with
    ReferenceError at render time.
    """
    call_order: list[str] = []

    async def fake_migrate(
        app_id: str, repo_prefix: str
    ) -> tuple[bool, list[object]]:
        call_order.append("migrate")
        return True, []

    async def fake_build(
        self, app_id, repo_prefix, mode, dependencies=None
    ) -> BundleResult:
        call_order.append("build")
        return BundleResult(
            success=True,
            manifest=BundleManifest(
                entry="entry.js",
                css=None,
                outputs=["entry.js"],
                duration_ms=5,
                warnings=[],
                dependencies={},
            ),
            duration_ms=5,
        )

    with patch(
        "src.services.app_bundler.auto_migrate.auto_migrate_repo_prefix",
        new=fake_migrate,
    ), patch.object(BundlerService, "build", new=fake_build):
        result, migrated = await build_with_migrate(
            app_id="app-id",
            repo_prefix="apps/test/",
            mode="preview",
            dependencies={},
        )

    assert call_order == ["migrate", "build"]
    assert migrated is True
    assert result.success is True


async def test_build_writes_current_schema_version_into_manifest(
    tmp_path: pathlib.Path,
) -> None:
    """Every successful build must stamp `schema_version` into manifest.json
    so readers can detect staleness after a deploy that bumps the constant.
    """
    import json

    from src.services.app_bundler import BundlerService as _BundlerService

    bundler = _BundlerService()

    # Mock the subprocess and storage layers — we're asserting the manifest
    # dict shape, not exercising esbuild.
    async def fake_materialize(src_dir: pathlib.Path, repo_prefix: str) -> list[str]:
        (src_dir / "_layout.tsx").write_text("export default function Layout(){}")
        return ["_layout.tsx"]

    async def fake_run_esbuild(cfg: dict) -> dict:
        out_dir = pathlib.Path(cfg["out_dir"])
        out_dir.mkdir(exist_ok=True)
        (out_dir / "entry.js").write_bytes(b"// fake entry\n")
        return {
            "success": True,
            "outputs": [{"path": "entry.js"}],
            "entry_file": "entry.js",
            "css_file": None,
            "duration_ms": 1,
            "warnings": [],
        }

    written: dict[str, bytes] = {}

    async def fake_write_preview_file(app_id: str, rel: str, data: bytes) -> None:
        written[rel] = data

    with patch.object(bundler, "_materialize_source", new=fake_materialize), \
         patch.object(bundler, "_run_esbuild", new=fake_run_esbuild), \
         patch.object(
             bundler._app_storage, "write_preview_file",
             new=AsyncMock(side_effect=fake_write_preview_file),
         ):
        result = await bundler.build(
            app_id="app-id",
            repo_prefix="apps/test/",
            mode="preview",
            dependencies={},
        )

    assert result.success is True
    assert "manifest.json" in written, "manifest.json must be written"
    manifest = json.loads(written["manifest.json"].decode())
    assert manifest["schema_version"] == SCHEMA_VERSION, (
        "manifest must record the bundler's current SCHEMA_VERSION so readers "
        "can detect stale manifests and trigger a rebuild"
    )
