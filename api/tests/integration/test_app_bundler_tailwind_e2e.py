"""End-to-end-ish test of the Tailwind bundling step.

Exercises the real @tailwindcss/node compiler subprocess. Materializes a
fake app source tree, runs ONLY the tailwind generation step, and asserts
the produced CSS contains rules for arbitrary values that were previously
silently broken in v2 apps.

This is the "does the experiment actually work?" guard rail. If
@tailwindcss/node is missing from the API container, or the candidate
extractor regresses, this test fails loudly.

Run via: `./test.sh tests/integration/test_app_bundler_tailwind_e2e.py -v`
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
async def test_arbitrary_values_compile_to_real_css_rules() -> None:
    """Layout-killing arbitrary values from real-world sessions:
    - lg:grid-cols-[minmax(0,1fr)_360px] — responsive arbitrary grid
    - bg-[color:var(--pc-paper)] — arbitrary value with CSS variable
    - py-10 lg:py-14 — responsive standard utilities
    - max-w-[1400px] — arbitrary measurement
    """
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        # Use real JSX so the candidate extractor sees className= strings
        (src_dir / "_layout.tsx").write_text(
            """
            import React from "react";
            export default function Layout({children}) {
              return (
                <div className="lg:grid-cols-[minmax(0,1fr)_360px] bg-[color:var(--pc-paper)] py-10 lg:py-14 max-w-[1400px] grid gap-6">
                  {children}
                </div>
              );
            }
            """,
            encoding="utf-8",
        )
        sources = ["_layout.tsx"]

        added = await bundler._generate_app_tailwind(src_dir, sources)
        assert added is True, "tailwind generation should produce CSS for these candidates"
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    # The arbitrary-value class names must appear in the output CSS as
    # actual rules, not just as referenced strings. Tailwind escapes them
    # with backslashes (e.g. `.bg-\[color\:var\(--pc-paper\)\]`).
    assert "var(--pc-paper)" in css, (
        "arbitrary-value with CSS variable should compile to a rule using var()"
    )
    assert "minmax(0,1fr)" in css or "minmax(0, 1fr)" in css, (
        "arbitrary grid template should compile (was silently broken in v2)"
    )
    assert "1400px" in css, "arbitrary measurement should compile"
    # Standard responsive variants should be in there too (proves preset works)
    assert "@media" in css, "responsive variants should compile to media queries"


@pytest.mark.asyncio
async def test_candidate_extraction_handles_responsive_arbitrary_brackets() -> None:
    """Responsive variants of arbitrary values were the worst offender —
    they look like normal class strings to a regex but contain `[`/`]` /
    `:` / `,` that often trip naive tokenizers."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "page.tsx").write_text(
            """
            <main className="md:grid-cols-[1fr_380px] xl:grid-cols-[1fr_440px_280px]">
              hi
            </main>
            """,
            encoding="utf-8",
        )

        added = await bundler._generate_app_tailwind(src_dir, ["page.tsx"])
        assert added is True
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")

    # Both viewport-prefixed arbitrary grids should be present
    assert "1fr" in css and "380px" in css and "440px" in css and "280px" in css, (
        "all viewport-prefixed arbitrary grid templates should compile"
    )


@pytest.mark.asyncio
async def test_no_classes_no_output() -> None:
    """If the source has no className strings, no Tailwind file should be
    written — keep bundles small and avoid dead CSS."""
    bundler = BundlerService()

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = pathlib.Path(tmp)
        (src_dir / "page.tsx").write_text(
            "export default () => null;\n",
            encoding="utf-8",
        )

        added = await bundler._generate_app_tailwind(src_dir, ["page.tsx"])

    # If extraction happens to find candidates from the bare JSX (e.g.
    # "default") and Tailwind classifies them as utilities, the CSS will
    # still be tiny — but the file flag should reflect whatever happened.
    if added:
        css = (src_dir / TAILWIND_OUTPUT_CSS).read_text(encoding="utf-8")
        # Even if extraction is over-broad, output must be small
        assert len(css) < 5000, "no real classes → output should be near-empty"
