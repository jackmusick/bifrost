# Solutions Adversarial QA Fan-Out — Findings Backlog

_Date: 2026-06-09 · Worktree: solutions-success-criteria · Branch HEAD: 9969a8ce_

## STATUS (CONFIRMED only)

- **critical: 1**
- **high: 3**
- **medium: 1**
- **low: 1**
- **Total confirmed: 6**

All six findings were independently reproduced by a second verifier. Two additional candidate findings were investigated and could not be confirmed (see REFUTED). One axis was blocked from full end-to-end coverage by the critical SDK-download blocker.

---

## CONFIRMED

### CRITICAL

#### C1 — `/api/sdk/download` returns HTTP 500 on a fresh port-mode dev stack (blocks deploy, start, and any standalone_v2 `npm install`)

- **did**: Booted a fresh port-mode dev stack. Installed the API-matched CLI, logged in. `bifrost solution init` + `bifrost solution scaffold-app`, then `bifrost deploy` and `bifrost solution start qa-app --port 3300`. Also `curl http://<host>/api/sdk/download`.
- **observed**: `bifrost deploy` → `Deploy failed: 500`. `bifrost solution start` → `npm error 500 Internal Server Error - GET .../api/sdk/download`. curl → HTTP 500. API logs: `subprocess.CalledProcessError` from `build_sdk.js`. Running the builder directly in-container → `Error: Cannot find module 'esbuild'` and `Could not resolve '/app/src/services/sdk_package/sdk_src/index.ts'`. Root cause: the dev compose bind-mounts `./api/src:/app/src:ro`, masking the image-baked `sdk_package/node_modules` (esbuild) and the COPYied `sdk_package/sdk_src/`. The compose preserves anonymous volumes for `app_compiler/node_modules` and `app_bundler/node_modules` but **omits `sdk_package/node_modules` and `sdk_package/sdk_src`**.
- **expected**: On a freshly-booted dev stack, `/api/sdk/download` serves the bundled SDK so `solution start` / `solution deploy` / app `npm install` work.
- **code_ref**: `docker-compose.debug.yml:111-113` (and the api/worker/scheduler blocks ~152-153, 200-201, 241-242); `api/Dockerfile.dev:84-96`. Endpoint chain: `src/routers/cli.py:2598` `download_sdk` → `sdk_package/__init__.py:74` `build_sdk_tarball` → `:56` `_bundle`.
- **proposed fix**: Add `/app/src/services/sdk_package/node_modules` and `/app/src/services/sdk_package/sdk_src` to the anonymous-volume preservation list in all four service blocks of the dev compose, mirroring the existing `app_compiler` / `app_bundler` overrides — so the image-baked SDK build assets are not shadowed by the read-only bind-mount.

### HIGH

#### H1 — `bifrost deploy` raises an uncaught `RuntimeError` traceback when not logged in

- **did**: From a Solution root with no credentials in cwd (scaffold output + llm.txt both say "Deploy with `bifrost deploy` from the solution root"), ran `bifrost deploy`.
- **observed**: Full Python traceback ending in `RuntimeError: Not logged in. Run 'bifrost login' to authenticate.` Verified: `deploy_cmd` wraps `asyncio.run(_run())` with no try/except; inside the running loop the interactive-login branch is skipped, so the bare `raise RuntimeError(...)` propagates uncaught through Click. The sibling non-Solution-dir guard, by contrast, raises a clean `ClickException`.
- **expected**: A clean one-line `Error: Not logged in. Run 'bifrost login'.` with exit code 1, no traceback.
- **code_ref**: `bifrost/commands/solution.py:719` (and `:789`) → `bifrost/client.py:455`.
- **proposed fix**: Catch the not-logged-in case in `deploy_cmd` (or in `_run`) and re-raise as `click.ClickException`, matching the existing non-Solution-dir guard.

#### H2 — `bifrost solution start` raises an uncaught `CalledProcessError` traceback when `npm install` fails

- **did**: `bifrost solution start qa-app` with the app's `bifrost` SDK dependency pointing at an unreachable URL (same failure class as the C1 500). Drove the real shipped `handle_solution(["start", ...])` dispatcher.
- **observed**: npm error block followed by a full traceback ending `subprocess.CalledProcessError: Command '['npm', 'install']' returned non-zero exit status 1.` at `solution.py:894` (`subprocess.run(["npm","install"], cwd=..., check=True)`). The only try block in `start_cmd` begins at `:914` (around `_serve`), after install; `handle_solution` catches only Click exceptions, so `CalledProcessError` escapes.
- **expected**: Catch the subprocess failure and print a clean actionable message (e.g. `npm install failed — could not fetch the bifrost SDK from <url>; is the dev API reachable?`) with exit 1, no traceback.
- **code_ref**: `bifrost/commands/solution.py:894`; dispatcher `:978-994`.
- **proposed fix**: Wrap the `npm install` subprocess in try/except `CalledProcessError` and raise `click.ClickException` with the SDK URL and a reachability hint.

#### H3 — Portable export/import round-trip of a Solution workspace recreates ZERO entities

- **did**: `bifrost export --portable` from a scaffolded Solution workspace (had `.bifrost/apps.yaml` + `.bifrost/workflows.yaml`). Created a target org, ran `bifrost import --org <uuid> --role-mode name` (dry-run and `--force`).
- **observed**: Export bundle `.bifrost/` contained ONLY `organizations.yaml` — the Solution's `apps.yaml` and `workflows.yaml` were absent. Only raw source carried (8 code files). Import: `Importing manifest (0 file(s))…`, `Manifest import completed (no changes)`, warning `No .bifrost/ manifest files found in repo`. Post-import `bifrost apps list` / `workflows list` → empty. The round-tripped "solution" is not installable/runnable via this path.
- **expected**: Either export carries the Solution's apps/workflows manifest so import recreates the registrations, OR export/import clearly states it only handles `_repo/` workspaces and is NOT the Solution share path (which is the workspace zip + `solution install`).
- **code_ref**: `api/bifrost/manifest.py` / export dump + import apply manifest handling.
- **proposed fix**: Decide the intended contract. If export should carry a Solution: include `apps.yaml`/`workflows.yaml` in the portable bundle and have import resolve them. If not: emit an explicit "this is a Solution workspace — use `bifrost solution install <zip>` to share it" message instead of silently producing an empty round-trip.

### MEDIUM

#### M1 — Re-running `scaffold-app` for a slug whose dir was deleted appends a DUPLICATE slug entry to `.bifrost/apps.yaml`

- **did**: Scaffolded `qa-app`, `rm -rf apps/qa-app`, re-ran `bifrost solution scaffold-app qa-app`. Inspected `.bifrost/apps.yaml`.
- **observed**: Two manifest blocks, two distinct UUIDs, both `slug: qa-app`, identical `path: apps/qa-app`. The guard is DIRECTORY-only (with the dir present, a 3rd scaffold correctly errors "already exists and is not empty"), so the dir-deleted/manifest-retained state silently yields a duplicate-slug manifest — ambiguous for start/deploy slug resolution.
- **expected**: `scaffold-app` should upsert by slug, or refuse when the slug already exists in `.bifrost/apps.yaml`, regardless of whether the dir is present.
- **code_ref**: scaffold-app manifest registration in `solution.py`.
- **proposed fix**: Before registering, check the manifest for an existing slug; upsert the existing entry (reuse its UUID) or error with a clear message.

### LOW

#### L1 — A bare `functions/hello.py` `@workflow` is NOT discovered by `deploy` without a `.bifrost/workflows.yaml` registration

- **did**: Hand-built a Solution (`init` + a `functions/hello.py` with `@workflow async def main`) WITHOUT `scaffold-app`, then `bifrost deploy`.
- **observed**: `0 workflow(s) upserted, 0 deleted.` Silently ignored. `deploy_cmd` → `_collect_workflows` reads only `.bifrost/workflows.yaml` (returns `[]` if absent) and does not scan `functions/*.py` or warn. Only `scaffold-app` creates that manifest. llm.txt (L132/L138) documents file-based discovery for `start` ("discovers @workflow functions anywhere under the root") but not the asymmetry with `deploy`.
- **expected**: Either `deploy` discovers `@workflow` functions under the root (consistent with `start`), or it warns that `functions/*.py` exist but are unregistered in `.bifrost/workflows.yaml`.
- **code_ref**: `api/bifrost/commands/solution.py` `_collect_workflows` (~L456-460), `deploy_cmd` (~L701); `docs/llm.txt:132,138`.
- **proposed fix**: Add a warning in `deploy` when unregistered `functions/*.py` `@workflow`s exist, or unify discovery with `start`. (Lowest priority — scaffold-app is the documented happy path.)

---

## REFUTED (do not re-investigate as confirmed bugs — could not be reproduced)

Both were **BLOCKED rather than disproven**: the verifier could not boot/keep a healthy stack long enough to run the empirical repro, so per protocol they default to `confirmed=false`. They are NOT verified-false; they are unverified. They may be worth a clean re-run on an isolated, non-colliding worktree.

- **"scaffold-app bakes wrong SDK URL (`http://localhost:8000`) when run without `--api-url`"** — Verifier reached a healthy port-mode API on a random port (confirming the premise that port mode != 8000) but a concurrent process kept deleting the worktree and the init container hit an overlayfs read-only error, so `scaffold-app` was never run live. Code reading (hypothesis only) suggests the CLI auto-loads a cwd `.env` at import time and `bifrost login` writes `BIFROST_API_URL=<actual-url>` into it — which, if scaffold runs in the same dir, would resolve `os.getenv("BIFROST_API_URL")` to the real port and NOT hit the 8000 default, potentially refuting the finding. Needs a live re-run to settle.
- **"`bifrost export --portable` does NOT scrub the env-specific SDK URL from app `package.json`"** — Verifier never reached `export`: repeated host docker instability (transient "No such container", network-not-found, postgres flapping), a corrupted CLI venv during pip build-isolation, and finally a hard OCI "read-only file system" mount error that corrupted the worktree. Neither confirmed nor refuted empirically.

---

## DATA-FALLBACK VERDICT (global-repo-data-fallback axis)

**No verdict available — the global-repo-data-fallback axis produced no coverage in this fan-out.** No verifier exercised the ungated tables/configs data fallback (whether a Solution-managed table/config read honors `global_repo_access` the way the module loader does). The only axis with reported coverage was `cli-docs-literalism`, and its end-to-end paths (running app, `solution start` behind one origin, browser-driving) were all gated behind the C1 `/api/sdk/download` 500 and never reached.

**Consequence**: The deferred global-fallback gate follow-up **remains open and undecided**. We cannot say whether the ungated data fallback "actually bit," because it was never tested. This should be re-run as a dedicated axis once C1 is fixed (the SDK build blocker was the common cause that starved every runtime path, including any that would have surfaced a data-fallback leak).

---

## COVERAGE / GAPS

**axis: cli-docs-literalism** — Booted a healthy port-mode dev stack (required overriding HOME to a temp dir with a netbird-key-stripped `debug.env`, because `env -u NETBIRD_SETUP_KEY` is defeated by `debug.sh` re-sourcing `~/.config/bifrost/debug.env` under `set -a`; the shared global config was correctly left unmodified). Installed the API-matched CLI and logged in.

Fully verified empirically:
- `solution init` (works), `scaffold-app` (works; surfaced the cwd-creds trap, baked SDK URL, and duplicate-slug bug)
- `bifrost watch` refusal inside a Solution workspace (confirmed working, correctly points at `solution start`, and correctly still works in a non-Solution dir)
- `export --portable` + `import --org` round-trip (recreates zero entities — H3)
- stale-pattern / error handling (clean)

NOT reached empirically (all gated by the C1 SDK-download 500):
- a successful `solution deploy`
- a working `solution start` Vite + local-workflows-behind-one-origin session
- browser-driving the running app (no Playwright screenshots — every UI/app path depends on the same SDK endpoint)
- `solution install <zip>`
- confirming an imported solution INSTALLS and WORKS end-to-end

In-container patching of the masked `node_modules` was impossible (mount is `:ro`); editing the compose file was out of scope for the verifier.

**Other axes** (global-repo-data-fallback, UI/UX, scope/cascade/readonly) produced no reported coverage in this fan-out.

---

## BLOCKED

No axis reported a hard "could not boot any stack" block. However:

- The **runtime half of cli-docs-literalism** (deploy success, `solution start`, browser drive, `solution install`, install-and-works) is effectively blocked until **C1** is fixed.
- The **global-repo-data-fallback axis** has no coverage and should be re-run as a dedicated pass post-C1.
- Recurring environment friction to fix before the next fan-out: (1) `env -u NETBIRD_SETUP_KEY` does not force port mode because `debug.sh` re-sources the global `debug.env`; (2) the per-worktree compose-v5.1.4 / api-exits-0 churn flake; (3) deterministic Compose project-name collisions between concurrent verifiers on the same worktree path; (4) overlayfs read-only mount errors on repeated boots. Several verifiers also observed the global `~/.config/bifrost/debug.env` NETBIRD_SETUP_KEY line being changed mid-run by a parallel agent — restore the key if needed.
