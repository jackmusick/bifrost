"""Phase 2 integration tests — full Tailwind v4 pipeline against the real
@tailwindcss/node compiler. Covers @apply / @layer in user CSS and per-app
tailwind.config.{ts,js,mjs,cjs}.

If these pass, every reasonable Tailwind feature a developer expects from
"a normal React app with Tailwind" works inside the v2 Bifrost bundler.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from src.services.app_bundler import (
    TAILWIND_OUTPUT_CSS,
    BundlerService,
)


@pytest.mark.asyncio
async def test_apply_in_user_css_compiles_to_real_rules() -> None:
    """`@apply` in app styles.css must produce real declarations. Without
    the pipeline, esbuild passes @apply through verbatim and the browser
    rejects it as an invalid at-rule."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(
            'export default () => <div className="ops-pill" />;\n',
            encoding="utf-8",
        )
        (src_dir / "styles.css").write_text(
            """
            .ops-pill {
              @apply inline-flex items-center rounded-full px-3 py-1 text-xs font-medium;
            }
            """,
            encoding="utf-8",
        )
        sources = ["_layout.tsx", "styles.css"]

        added, consumed = await bundler._generate_app_tailwind(src_dir, sources)
        assert added is True
        assert consumed == {"styles.css"}, (
            "user CSS files must be reported as consumed so the caller "
            "removes them from the entry import list"
        )
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    # Real declarations from the @apply chain must appear in the output
    assert "display: inline-flex" in css, "@apply inline-flex must compile"
    assert "align-items: center" in css, "@apply items-center must compile"
    # The @apply directive itself must NOT remain in the output
    assert "@apply" not in css, "@apply must be processed away"


@pytest.mark.asyncio
async def test_layer_components_with_apply_chain() -> None:
    """`@layer components { .x { @apply ... } }` is the canonical pattern
    for shared component styles in a real Tailwind project."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(
            'export default () => <div className="card-shell" />;\n',
            encoding="utf-8",
        )
        (src_dir / "styles.css").write_text(
            """
            @layer components {
              .card-shell {
                @apply rounded-lg p-6 bg-white shadow-md;
              }
            }
            """,
            encoding="utf-8",
        )

        added, _ = await bundler._generate_app_tailwind(
            src_dir, ["_layout.tsx", "styles.css"]
        )
        assert added is True
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    assert "@layer components" in css, "the components layer must be preserved"
    assert "border-radius" in css, "@apply rounded-lg must compile"
    assert ".card-shell" in css


@pytest.mark.asyncio
async def test_per_app_tailwind_config_extends_theme() -> None:
    """Per-app tailwind.config.ts can add custom theme tokens — those
    tokens must be available to the app's class names."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(
            'export default () => <div className="bg-brand-500" />;\n',
            encoding="utf-8",
        )
        # Tailwind v4 config files use CommonJS or ESM. Use .js/CJS for the
        # broadest compatibility in the test (no Node ESM loader hassle).
        (src_dir / "tailwind.config.js").write_text(
            """
            module.exports = {
              theme: {
                extend: {
                  colors: {
                    brand: {
                      500: '#facc15',
                    },
                  },
                },
              },
            };
            """,
            encoding="utf-8",
        )

        added, _ = await bundler._generate_app_tailwind(
            src_dir, ["_layout.tsx", "tailwind.config.js"]
        )
        assert added is True
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    assert "#facc15" in css.lower() or "facc15" in css.lower(), (
        "custom brand-500 color from per-app config must compile to a rule"
    )
    assert ".bg-brand-500" in css


@pytest.mark.asyncio
async def test_user_css_with_root_variables_passes_through() -> None:
    """Plain CSS variables in :root must survive the pipeline unchanged —
    these are how apps define theme tokens."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(
            'export default () => <div className="bg-[color:var(--ops-paper)]" />;\n',
            encoding="utf-8",
        )
        (src_dir / "styles.css").write_text(
            """
            :root {
              --ops-paper: oklch(1 0 0);
              --ops-fg: oklch(0.145 0 0);
            }
            .dark {
              --ops-paper: oklch(0.205 0 0);
            }
            """,
            encoding="utf-8",
        )

        added, _ = await bundler._generate_app_tailwind(
            src_dir, ["_layout.tsx", "styles.css"]
        )
        assert added is True
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    assert "--ops-paper" in css, "user CSS variables must pass through"
    assert "--ops-fg" in css
    assert ".dark" in css, "user selectors must pass through"
    assert "var(--ops-paper)" in css, "the bg-[color:var(--ops-paper)] arbitrary utility must reference the variable"


@pytest.mark.asyncio
async def test_apply_with_arbitrary_value_in_user_css() -> None:
    """`@apply` with an arbitrary value (e.g. @apply bg-[color:var(--x)])
    is a real-world pattern when migrating shadcn-style theming. Should
    compile cleanly through the pipeline."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "_layout.tsx").write_text(
            'export default () => <div className="themed" />;\n',
            encoding="utf-8",
        )
        (src_dir / "styles.css").write_text(
            """
            :root { --paper: oklch(1 0 0); }
            .themed {
              @apply bg-[color:var(--paper)] p-4 rounded;
            }
            """,
            encoding="utf-8",
        )

        added, _ = await bundler._generate_app_tailwind(
            src_dir, ["_layout.tsx", "styles.css"]
        )
        assert added is True
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    assert "var(--paper)" in css, "arbitrary @apply must compile"
    assert "@apply" not in css
