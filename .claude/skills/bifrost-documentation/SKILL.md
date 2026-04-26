---
name: bifrost-documentation
description: Refresh the bifrost-integrations-docs site by re-capturing screenshots and (optionally) authoring missing pages. Trigger phrases - "refresh docs", "update screenshots", "/bifrost-documentation", "rebuild docs site". Has three modes - bootstrap (one-shot manifest generation, mandatory first run), diff (default - only refresh entries whose Bifrost source changed), full (re-capture and re-author everything).
---

# Bifrost Documentation Pipeline

Refresh `bifrost-integrations-docs` programmatically: re-capture screenshots, author missing Diátaxis-shaped pages, open a docs PR with a TL;DR.

The docs repo is at `~/GitHub/bifrost-integrations-docs` (or clone it from `git@github.com:jackmusick/bifrost-integrations-docs.git` if missing). The bifrost repo's worktree is the source of truth for the running app.

## Modes

| Mode | When | What it does |
|------|------|--------------|
| `bootstrap` | First run, or after major doc reorganization. **Aborts if `screenshots.yaml` exists** unless `--force`. | Generates `screenshots.yaml` and `bootstrap-report.md` from MDX inventory + bifrost router walk. No captures. |
| `diff` (default) | Daily refresh. | Short-lists entries whose `source_globs` changed since `captured_at.bifrost_sha`. Captures and pixel-diffs. Commits only PNGs that actually changed. |
| `full` | Major UI shift, theme change, or post-bootstrap first run. | Bypasses the source-glob shortlist. Pixel diff still gates commits, so identical re-renders don't churn git. Also runs the authoring pass for any pages without screenshots. |
| `lint` | After hand-editing the manifest. | Validates `screenshots.yaml` against schema, MDX cross-references, file existence. No captures. |

## Workflow

1. **Preflight**
   - Locate docs repo. Try `~/GitHub/bifrost-integrations-docs` then `/tmp/bifrost-integrations-docs`. If missing, clone to `~/GitHub/`.
   - Verify clean tree (`git status --porcelain` empty). If dirty, ask the user to commit/stash before continuing.
   - Pull `main` (`git pull --ff-only origin main`).
   - Cut a fresh branch: `docs/screenshot-refresh-YYYY-MM-DD-<short-sha>`.
   - Verify bifrost test stack is up: `./test.sh stack status` in the bifrost worktree. If down, `./test.sh stack up`. The boot is ~2-5 minutes; warn the user up front.
   - Set `DOCS_REPO_PATH=<absolute path to docs repo>` for downstream tools.

2. **Mode dispatch**

   - **`bootstrap`**:
     ```bash
     node $BIFROST/scripts/docs/bootstrap-manifest.mjs \
         --docs-repo $DOCS_REPO --bifrost-repo $BIFROST $FORCE
     ```
     Then `cd $DOCS_REPO && npm run lint:manifest` to confirm schema validity. Commit `screenshots.yaml` + `bootstrap-report.md`. Open PR titled "Bootstrap docs screenshot manifest" with body = `bootstrap-report.md`. Stop here — do not continue to capture in the same run.

   - **`diff` / `full`**:
     ```bash
     $BIFROST/scripts/docs/run-pipeline.sh \
         --docs-repo $DOCS_REPO --bifrost-repo $BIFROST $MODE_FLAG
     ```
     Reads JSON output for the TL;DR.

   - **`lint`**: `cd $DOCS_REPO && npm run lint:manifest`. Print result. No PR.

3. **Authoring pass** (full mode only)
   For each MDX page in `bootstrap-report.md`'s "Pages without screenshots" list that the user wants documented, generate a Diátaxis-templated stub. Use `templates/` as starting points.
   - **Apply the anti-bloat self-review (below) before committing.**
   - The skill must NOT silently overwrite hand-written prose; only fills empty/stub pages.

4. **Anti-bloat self-review** (every prose change)
   After writing or editing any MDX, sweep for these patterns and cut them:
   - "In this section, we'll explore..."
   - "It's important to note that..."
   - "Let's dive into..."
   - "As we mentioned earlier..."
   - Any paragraph longer than 80 words in a tutorial or how-to (split, condense, or move to an explanation page).
   - Preamble before numbered steps (just start the steps).
   Reference + explanation pages can be denser. Tutorials and how-tos are terse by Diátaxis discipline.

5. **Finalize**
   - Run `cd $DOCS_REPO && npm run lint:manifest` to confirm.
   - Optionally `npm run build` for a smoke build.
   - Stage and commit. Title: `Refresh screenshots and docs (<N> changed, <M> authored)`.
   - Push branch.
   - Open PR via `gh pr create`. Body = TL;DR (template below).

## TL;DR template

```
## Mode
<bootstrap | diff | full>

## Bifrost SHA range
`<old>..<HEAD>` (or `<HEAD>` if bootstrap)

## Counts
- Candidates short-listed: <N>
- Captures attempted: <N>
- PNGs committed (passed pixel diff): <N>
- Entries unchanged (visual no-op): <N>
- Authored pages (full mode): <N>

## Manual review needed
<list any low-confidence flags from bootstrap-report.md or capture errors>

## Failures
<list any entries that errored, with route + reason>
```

## Diátaxis quadrant rules

When authoring or editing prose, pick the right quadrant and stay in it:

- **Tutorial** (`getting-started/`, `*first-*`): goal-oriented, a single happy path, no detours. Numbered steps, ≤2 sentences each.
- **How-to** (`how-to-guides/**`): one specific task. "How to <verb> <noun>" title. No teaching — assume the reader already understands the concept.
- **Reference** (`sdk-reference/**`): describe, don't explain. Tables of params, signatures, return values, one minimal example per item. Reference is the only quadrant where bloat is permitted, and only when needed for disambiguation.
- **Explanation** (`core-concepts/`, `about/`): why-shaped. Cross-link to tutorials/how-tos rather than repeating their content.

If the user asks for a doc and you can't pick a quadrant in one sentence, ask them.

## When NOT to use this skill

- The user wants to write a single targeted doc page from scratch — write it directly.
- The user is debugging or fixing a typo — direct edit.
- The bifrost test stack is broken — fix that first; this skill cannot work without it.

## Hard rules

1. Never edit prose without running anti-bloat self-review.
2. Never bypass `npm run lint:manifest` before committing.
3. Never commit `.tmp-captures/` — it's gitignored.
4. Never run capture mode against a dirty docs tree — abort and ask.
5. The skill writes to a branch, never directly to `main`.
