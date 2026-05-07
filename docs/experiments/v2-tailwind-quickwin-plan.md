# v2 Tailwind Quick-Win — Experiment Plan

**Worktree:** `worktree-v2-tailwind-quickwin`
**Goal:** Add real Tailwind compilation to the v2 app bundler so app authors can use arbitrary values, responsive variants of arbitrary values, `@apply`, and custom CSS variables in `bg-[color:var(--...)]` patterns. Determine whether this fixes the "second-class app builder" feeling or whether v3 is still required for design quality.

## Hypothesis

Today the host preloads a Tailwind stylesheet at host build time, scanning only the host's source. App-side class strings like `lg:grid-cols-[minmax(0,1fr)_360px]`, `bg-[color:var(--pc-paper)]`, `py-10 lg:py-14` are NOT in that preload — so they silently no-op at render time. Standard utilities work, but anything off the beaten path doesn't.

Hypothesis: adding a per-app Tailwind compile step inside the bundler (JIT scanning the app's own source) eliminates the entire class of "Tailwind silently broken" bugs, making layout/design work reliable enough that v3 is justified by other concerns (npm escape hatch, workflow proxy, realtime primitives) rather than design-quality.

## Approach

**Pipeline change** (in `api/src/services/app_bundler/`):
1. Add `tailwindcss@^3` and `postcss@^8` to bundler `package.json`.
2. Create `bifrost-tailwind-preset.js` that mirrors the host's theme tokens, color extensions, safelist patterns, plugins. Ships as part of the bundler.
3. In `__init__.py:_build()`, between source materialization and esbuild invocation:
   - If app source has its own `tailwind.config.{ts,js,mjs}`, load it and merge on top of the preset (`presets: [bifrostPreset]`).
   - Else use the preset alone.
   - Run Tailwind CLI: scan `{src_dir}/**/*.{tsx,ts,jsx,js,css}`, output to `{src_dir}/__bifrost-tailwind.css`.
   - Append `import './__bifrost-tailwind.css'` to the synthesized entry.
4. esbuild's CSS pipeline picks it up automatically — bundles into `entry-[hash].css`.

**No client-side changes needed.** The bundle output shape stays identical.

**Hybrid config behavior** (matches user's "if it exists use it, else use system"):
- Preset always loads → app inherits host theme by default
- App can override or extend by adding `tailwind.config.ts` with `presets: [require('bifrost-tailwind-preset')]`
- Presets compose; app values win where they collide

## Test plan

### Phase 1: Compatibility test — customer-onboarding app

Existing real app at `~/GitHub/bifrost-workspace/apps/customer-onboarding/` (1139 LOC across 5 files). Approach:

1. Boot debug stack in this worktree.
2. Take v2-baseline screenshots of customer-onboarding running unchanged.
3. Apply the bundler change.
4. Re-publish customer-onboarding (with workflow calls stubbed out to mock data so we don't need the real backend integrations).
5. Take v2-with-tailwind screenshots.
6. Visual diff. Should be **identical** for an app that uses only standard utilities (the common case) — proving the change is non-breaking.

### Phase 2: Stress test — new app abusing every primitive

Build a fresh app, "MSP Operations Console," with:
- **Components:** Sheet, Popover, Command (cmd-k palette), HoverCard, Tabs, Tooltip, ContextMenu, Combobox, Calendar, AlertDialog, Sonner toast, Dialog, DropdownMenu
- **Charts:** Recharts ScatterChart, LineChart, BarChart with custom theme
- **Layout patterns that exercise the new pipeline:**
  - `lg:grid-cols-[minmax(0,1fr)_360px]` (arbitrary values + responsive)
  - `bg-[color:var(--ops-paper)]` (arbitrary + CSS variable)
  - `min-h-[calc(100vh-4rem)]` (arbitrary calc)
  - `@container` queries if Tailwind v3 supports them
  - Custom `tailwind.config.ts` overriding theme colors and extending fontFamily
  - Custom `styles.css` with `@layer components { .pc-card { @apply bg-card p-6 rounded-lg; } }`
  - CSS variable theme tokens (`--ops-bg`, `--ops-paper`, `--ops-fg`)
- **Goal:** identify limitations, document each, classify v2-fix-vs-v3-need

### Phase 3: Tests

- `./test.sh stack reset && ./test.sh unit` — bundler unit tests pass
- `./test.sh client unit` — vitest still passes
- Skip e2e unless something looks broken (saves time)

## Reporting

Final report at `docs/experiments/v2-tailwind-quickwin.md` with:
- Bundler changes summary (file:line)
- Compatibility test result + screenshots
- Stress test result + screenshots
- **Friction log:** every issue I hit, what I tried, what happened, classification (fixable in v2 / requires v3)
- Verdict: does Tailwind quick-win solve the design problem alone, or is v3 still needed for design?

## Constraints — what I will NOT do

- Won't merge to main
- Won't deploy to demo instance
- Won't change `DEFAULT_EXTERNALS` (stays scoped to "fix Tailwind only")
- Won't modify the bifrost-build skill (that's a follow-up after we know what works)
- Won't touch anything outside this worktree

## What's deliberately out of scope

- v3 architecture (proven need first via this experiment)
- Workflow proxy for local dev (separate from design-quality question)
- npm package conversion (requires v3 — not part of this experiment)
- Realtime primitives via executions.publish (separate concern)
