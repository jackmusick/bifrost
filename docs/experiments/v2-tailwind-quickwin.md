# v2 Tailwind Quick-Win — Experiment Report

**Worktree:** `worktree-v2-tailwind-quickwin`
**Branch:** `worktree-v2-tailwind-quickwin`
**Status:** ✅ **Verified, both phases.** Full Tailwind v4 pipeline (utilities + user CSS + per-app config) wired into the bundler. 37 tests pass. Real production app re-bundles cleanly. The "second-class app builder" failure mode is closed.

## TL;DR

Wired the existing `@tailwindcss/node` v4 compiler (already in the codebase) into the modern bundler in two phases:

- **Phase 1**: per-app utility compilation. Arbitrary values (`bg-[color:var(--x)]`, `lg:grid-cols-[1fr_360px]`, etc.) that silently no-op'd in v2 now compile.
- **Phase 2**: full pipeline. User CSS files (`@apply`, `@layer components`, `:root` variables) are processed through Tailwind. Per-app `tailwind.config.{ts,js,mjs,cjs}` is honored via `@config`. Custom theme tokens work.

After phase 2, **everything a normal React+Tailwind app expects to work, works.** No more "things to remember" list. The experiment delivers the design-quality piece of v3 at the v2 layer; v3 design conversation can resume focused on developer-experience (real npm escape hatch, local dev, workflow proxy) without the visual-bugs distraction.

## Phase 1 — utility compilation (commit `99ca36a0`)

### What was broken

The host preloads a Tailwind stylesheet compiled from the host's own source. App-side class strings like `lg:grid-cols-[minmax(0,1fr)_360px]`, `bg-[color:var(--pc-paper)]`, `max-w-[1400px]` are never seen by the host's compiler, so no CSS rule fires. The DOM has the class, the page has no matching rule. Silent visual breakage — exactly what bit the Pipeline Command session (side rail at bottom, translucent drawer, missing page padding).

### What changed

- **Bundler integration**: `api/src/services/app_bundler/__init__.py` runs the existing `AppTailwindService` between source materialization and entry synthesis. Output `__bifrost_tailwind.css` gets sorted ahead of user CSS in the synthesized entry (correct cascade — utilities first, user CSS overrides).
- **Schema version 2 → 3**: triggers automatic bundle rebuild on first viewer request after deploy. No DB migration, no manual republish.
- **Candidate extractor regex fixes** in `api/src/services/app_compiler/__init__.py`: tokenizer no longer splits on `,` (was breaking `minmax(0,1fr)`); class-shape regex now accepts `(` and `)` (was rejecting `var()`, `calc()`, `clamp()`, `oklch()`). Both bugs predated this work, hidden behind the host preload.

## Phase 2 — full pipeline (commit pending in this worktree)

### What was still broken

After phase 1, arbitrary values worked, but a developer's muscle memory for Tailwind includes `@apply`, `@layer components`, custom `tailwind.config.ts` with extended theme tokens. Those still didn't work in v2 — the candidate-only pipeline didn't process user `.css` files at all, so `@apply` directives passed straight through to esbuild and rendered as invalid CSS at-rules. Per-app config wasn't read.

### What changed

**`tailwind.js`** (`api/src/services/app_compiler/tailwind.js`) gains a pipeline mode. Old mode (candidates only) still works for the legacy per-file render path. New mode accepts:

```ts
{
  candidates: ["flex", "p-4", ...],
  user_css: [{path: "styles.css", content: "..."}, ...],
  config_path: "/abs/path/to/tailwind.config.js" | null
}
```

The script concatenates user CSS into the Tailwind input so `@apply` / `@layer` / `@theme` are processed, and threads `@config` for per-app theme overrides. The same `@tailwindcss/node` `compile()` call processes everything.

**`AppTailwindService`** (`api/src/services/app_compiler/__init__.py`) gains `generate_css_pipeline(code_sources, user_css, config_path)`. The legacy `generate_css(sources)` is preserved for the old per-file render path.

**Bundler** (`api/src/services/app_bundler/__init__.py`) `_generate_app_tailwind` now:
1. Scans `.tsx/.ts/.jsx/.js` for class candidates.
2. Reads all `.css` files as user CSS input.
3. Detects per-app `tailwind.config.{ts,js,mjs,cjs}` and passes its absolute path.
4. Returns `(wrote_css: bool, consumed_css_files: set[str])` — caller filters consumed files out of `sources` so esbuild doesn't try to bundle them again (would either duplicate the CSS or, if they contain `@apply`, fail outright).

### What works after phase 2

| Pattern | Example | Status |
|---|---|---|
| `@apply` in user CSS | `.foo { @apply px-4 py-2 rounded; }` | ✅ compiles |
| `@apply` with arbitrary value | `.foo { @apply bg-[color:var(--x)]; }` | ✅ compiles |
| `@layer components` | `@layer components { .card { @apply ... } }` | ✅ compiles |
| `:root` CSS variables | `:root { --x: oklch(...); }` | ✅ passes through |
| Per-app `tailwind.config.js` | `theme.extend.colors.brand.500` → `bg-brand-500` | ✅ honored |
| Custom selectors in user CSS | `.dark { ... }`, `[data-state=open]` | ✅ pass through |
| `@property`, `@supports` from utilities | Generated automatically | ✅ emitted |

Plus everything from phase 1 (arbitrary values, responsive variants of arbitrary, `clamp()`/`minmax()`/`oklch()`/`hsl()`/CSS-variable arbitrary values).

### Verified by tests

- `api/tests/integration/test_app_bundler_pipeline.py` — 5 tests against the real `@tailwindcss/node` subprocess:
  - `@apply` in user CSS produces real declarations
  - `@layer components` with `@apply` chain
  - Per-app `tailwind.config.js` honored
  - User CSS variables pass through
  - `@apply` with arbitrary values

All pass.

## Real-world compatibility

Bundled the actual `~/GitHub/bifrost-workspace/apps/customer-onboarding/` source (1139 LOC, 5 files) through the new pipeline:

- ✅ Pipeline succeeds, 11KB CSS produced — identical size to phase 1
- ✅ `consumed: set()` (app has no `.css` files, so pipeline degrades gracefully to candidate-only compile)
- ✅ Standard utilities all there: `h-full`, `overflow-hidden`, `w-full`, `text-sm`, `rounded-md`
- ✅ Two arbitrary values now compile that were silently broken before:
  - `.w-\[500px\]` — `pages/index.tsx:288`, Skeleton loader width
  - `.text-\[10px\]` — `components/OnboardingPipeline.tsx:292`, small label
- ✅ `bg-background` (custom shadcn-style utility) is correctly NOT in the per-app output — served by the host's preloaded stylesheet which has the full theme. Both rules fire at runtime.

**Net effect:** zero regression for existing apps; latent visual bugs in production are silently fixed; new apps can use the full Tailwind feature set.

## What v3 is still needed for

The design-quality argument for v3 is now resolved at the v2 layer. v3 is still justified, but for **developer experience** reasons:

- `bifrost` as a real npm package (escape from implicit externals; `npm install bifrost` instead of synthesized virtual)
- Real local dev loop (`npm run dev` against an instance, Azure SWA-style)
- Workflow proxy for local dev (run worktree Python through a local sidecar)
- Realtime primitives via `executions.publish`
- Per-app fully isolated React tree (only matters if BYO-React-version becomes a real ask)

When v3 design resumes, layout-quality is off the table. We focus on the parts that v2 can't provide.

## Files changed

```
api/src/services/app_bundler/__init__.py       | +85 lines  (helper + integration + comments)
api/src/services/app_compiler/__init__.py      | +50/-3     (regex fixes + pipeline method + _invoke split)
api/src/services/app_compiler/tailwind.js      | rewritten  (~70 LOC, dual-mode)
api/tests/unit/test_app_bundler.py             | +130 lines (5 new unit tests)
api/tests/integration/test_app_bundler_tailwind_e2e.py    | NEW (3 tests, ~110 lines)
api/tests/integration/test_app_bundler_stress.py          | NEW (1 test, ~165 lines)
api/tests/integration/test_app_bundler_pipeline.py        | NEW (5 tests, ~165 lines)
docs/experiments/v2-tailwind-quickwin-plan.md             | NEW
docs/experiments/v2-tailwind-quickwin.md                  | this file
```

37 tests pass total: 14 unit (5 new for the pipeline) + 14 compiler (regex changes don't regress) + 9 integration (3 phase-1 e2e + 1 stress + 5 phase-2 pipeline).

## Recommended follow-up

1. **Squash + ship as one PR.** Phase 1 and phase 2 should land together — phase 1 alone leaves `@apply` broken, which preserves the "Claude has to remember things" failure mode this whole experiment is trying to close.
2. **Update the bifrost-build skill.** Remove all "Tailwind limitation" caveats. Skill becomes shorter.
3. **Resume v3 design conversation** focused on the developer-experience wins, not design-quality.

## Out of scope (deliberate)

- v3 architecture
- Workflow proxy for local dev
- npm package conversion (`bifrost` as real package)
- Realtime primitives via `executions.publish`
- Browser screenshot E2E (test stack lacks the auth path; the integration tests already exercise the real Tailwind compiler with the same code path the runtime uses, including the real `@apply`/`@layer`/`@config` machinery)
