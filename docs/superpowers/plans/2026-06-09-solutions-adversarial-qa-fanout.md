# Solutions Adversarial UI/CLI QA Fan-out Implementation Plan

> ## ✅ STATUS: COMPLETE (2026-06-09) — read this before the plan body
>
> All 7 tasks built, committed, and the workflow was run live (smoke + full 6-axis). The rest of the plan below is the original implementation spec, kept for reference; checkboxes are ticked. What a fresh session needs to know:
>
> **Deliverable shipped:** `.claude/workflows/solutions-qa-fanout.mjs` exists and works. Invoke by path (`Workflow({ scriptPath: ".claude/workflows/solutions-qa-fanout.mjs" })`) — the named-workflow registry does NOT pick up `.claude/workflows/` from this worktree, so `Workflow({ name: "solutions-qa-fanout" })` fails with "not found". Use the path form.
>
> **Two plan instructions turned out WRONG and were corrected during execution:**
> 1. **`env -u NETBIRD_SETUP_KEY ./debug.sh up` does NOT force port mode** — `debug.sh load_env_files` re-sources `~/.config/bifrost/debug.env` under `set -a`, re-introducing the key. The fix (committed): a `BIFROST_FORCE_PORT=1` opt-out in `debug.sh`. The workflow BOOTSTRAP + CLAUDE.md now use `BIFROST_FORCE_PORT=1`, not `env -u`. Anywhere the plan body still says `env -u NETBIRD_SETUP_KEY`, it is superseded by `BIFROST_FORCE_PORT=1`.
> 2. **`node --check` is the wrong validator** for the finished file — the workflow body has a top-level `return`, which `node --check` rejects (the known-good `solutions-scope-shakeout.mjs` fails it identically). Validate by wrapping the body in an async function instead (see Task 5 note). Steps 1–4's `node --check` calls were fine (no `return` yet).
>
> **Bugs the run surfaced + their disposition (all resolved):**
> - **C1 (CRITICAL, FIXED):** `/api/sdk/download` 500'd on fresh dev/test stacks — the `:ro` `./api/src` bind-mount masks the image-baked `sdk_package/node_modules` (esbuild) + `sdk_src`. Fix (commits `5411f13f`): anonymous-volume preservation in both `docker-compose.debug.yml` + `docker-compose.test.yml` across all 4 service blocks, plus tracked `.gitkeep` mountpoint dirs (Docker can't mkdir a mountpoint under a `:ro` parent → must pre-exist on a fresh worktree). Verified: fresh worktree → valid 6KB npm tarball.
> - **Bootstrap port-mode (FIXED):** the `BIFROST_FORCE_PORT=1` fix above (commit `54cd95d3`).
> - **Original H1 "sealed install reads decrypted global secrets" (RETRACTED — not a bug):** it's the intended org→global config cascade. `merged_for_sdk()` unions only the caller's own org + the global (NULL-org) tier, never another org's data; a NULL-org config is a deliberately-global operator value; the consumer is the server-side workflow (engine sentinel), not a user. `global_repo_access` seals `_repo/` CODE imports, not data. Verify a flagged security finding against the actual resolver scope before believing it.
> - **Original H2 → export-scrub finding (RESOLVED by REMOVAL):** `bifrost export --portable` didn't actually scrub org IDs. Rather than fix it, `bifrost export` / `import` were REMOVED outright (commit `2502e8ac`, `BREAKING CHANGE`) — they predated Solutions, which supersedes them. `portable.py` + their tests deleted too.
>
> **Net findings outcome:** 0 critical / 0 high open. Confirmed backlog = 1 medium + 6 low, in `docs/plans/2026-06-09-solutions-qa-fanout-findings.md` (the run's output doc). Also confirmed FIXED by the run: C1 and D3 (BifrostHeader standalone renders styled).
>
> **Commit trail:** `ed262430`→`bd3397c6` (build), `9969a8ce` (throttle), `30280191`/`2d34e751` (findings), plus the four fix/triage/removal commits named above. Memory: `project_solutions_qa_fanout_findings.md`.
>
> **If re-running the workflow:** it's idempotent-ish (its own cleanup phase prunes stray stacks + merged `worktree-agent-*`; it protects named worktrees and this worktree's stacks). Each axis now boots a clean fresh stack with the C1 + port-mode fixes baked into HEAD, so all 6 axes get real coverage (the smoke, pre-fix, had 4 axes starved by C1).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **(All tasks below are DONE — see the STATUS block above. Checkboxes ticked.)**

**Goal:** Build a Workflow script that runs an adversarial QA fan-out on Solutions — 6 axis agents each in their own worktree + port-mode debug stack driving real UI/CLI, with an independent verify pass and a synthesized ranked findings backlog.

**Architecture:** A single `.claude/workflows/solutions-qa-fanout.mjs` Workflow with 4 phases: (1) pre-flight cleanup done as plain Bash orchestration in the script body, (2) 6 axis agents fanned out via `parallel()` each provisioning+driving+tearing-down its own port-mode stack from inside its prompt, (3) a verify pass via `pipeline()` that re-checks each reproduced finding with a fresh agent prompted to refute, (4) a synthesis agent that dedups/ranks and writes the findings doc. Extends the existing `solutions-scope-shakeout.mjs` pattern (meta/ENV/schema/axis-prompts) but replaces its single-shared-stack assumption with per-agent stacks and adds the verify pass.

**Tech Stack:** Workflow JS (the `Workflow` tool's runtime — plain JS, `agent()`/`parallel()`/`pipeline()`/`phase()`/`log()`), Bash (`debug.sh`, `git worktree`, `docker`), Playwright (UI driving inside agent prompts), the installable `bifrost` CLI.

**Spec:** `docs/superpowers/specs/2026-06-09-solutions-adversarial-qa-fanout-design.md`

---

## Background the engineer needs

- **The prior pattern to extend:** `.claude/workflows/solutions-scope-shakeout.mjs` already has the shape — `export const meta`, a shared `ENV` string, a `FINDING_SCHEMA` JSON schema, an `AXES` array of `{key, prompt}`, a `parallel()` fan-out, a critic, and a structured `return`. READ IT FIRST. The new workflow reuses the schema and axis-prompt style verbatim where possible.
- **The key difference:** the prior workflow assumed ONE pre-seeded shared stack (a single `localhost:37791` + one scratch CLI). The new design gives EACH agent its OWN worktree + port-mode debug stack. So the per-agent stack provisioning lives INSIDE each agent's prompt (the agent runs `git worktree add`, `env -u NETBIRD_SETUP_KEY ./debug.sh up`, installs the CLI, drives, then `./debug.sh down` + removes its worktree).
- **Why provisioning is in the prompt, not the script:** Workflow `agent()` sub-agents have Bash and can run these commands; the Workflow script body itself should stay deterministic orchestration (cleanup, fan-out, synthesis) and NOT try to manage 6 stacks itself.
- **Port mode is mandatory.** `debug.sh` chooses netbird mode iff `NETBIRD_SETUP_KEY` is set (`debug.sh:73`). Chrome/Playwright cannot drive netbird stacks (Vite HMR hangs — memory: `project_netbird_chrome_vite_hang`). Every stack boot in every agent prompt MUST use `env -u NETBIRD_SETUP_KEY ./debug.sh up`.
- **Per-worktree stack isolation is automatic.** `debug.sh` derives the Compose project name from the worktree path (`debug.sh:38`), so each agent's worktree gets an isolated stack with no manual project-name juggling.
- **The known stack flake:** the api container can exit-0 after becoming healthy (`project_test_stack_api_exit_flake`). Agent prompts must tell agents to retry boot a bounded number of times and report BLOCKED (not phantom findings) if a healthy stack never comes up.
- **How to invoke a saved workflow:** `Workflow({ name: "solutions-qa-fanout" })` once the file is in `.claude/workflows/`. During development, invoke by path: `Workflow({ scriptPath: ".claude/workflows/solutions-qa-fanout.mjs" })`.
- **Validating a workflow script without a full run:** the Workflow tool parses+persists the script on invocation; a syntax error surfaces immediately. For logic, a dry validation is a `--limit`-style smoke (see Task 7) — we gate the real run behind a 1-axis smoke first.

---

## File Structure

| File | Responsibility |
| ---- | -------------- |
| `.claude/workflows/solutions-qa-fanout.mjs` | The entire workflow: meta, ENV/per-agent-bootstrap text, FINDING_SCHEMA, VERDICT_SCHEMA, AXES (6), cleanup body, fan-out, verify pipeline, synthesis, return |
| `docs/plans/2026-06-09-solutions-qa-fanout-findings.md` | OUTPUT (written by the synthesis phase at run time) — not created by this plan |

One file. It is large but cohesive (it's a single orchestration script); splitting it would scatter the shared ENV/schema. This matches the existing `solutions-scope-shakeout.mjs` (one file, 15KB).

---

## Task 1: Scaffold the workflow file with meta + schemas

**Files:**
- Create: `.claude/workflows/solutions-qa-fanout.mjs`

- [x] **Step 1: Write the meta block and the two schemas**

Create `.claude/workflows/solutions-qa-fanout.mjs` with exactly this opening (the `meta` must be a pure literal):

```javascript
export const meta = {
  name: 'solutions-qa-fanout',
  description: 'Adversarial UI/CLI QA on Solutions: 6 axis agents (own worktree + port-mode stack) drive real UI/CLI, findings independently verified, then synthesized into a ranked backlog',
  phases: [
    { title: 'Cleanup', detail: 'kill stray stacks, prune merged worktree-agent-* branches' },
    { title: 'Find', detail: 'one agent per axis; each provisions its own port-mode debug stack and drives UI+CLI' },
    { title: 'Verify', detail: 'independent agent refutes/confirms each reproduced finding' },
    { title: 'Synthesize', detail: 'dedup, rank, write the findings backlog' },
  ],
}

// One finding produced by an axis agent.
const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    axis: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          surface: { type: 'string', enum: ['forms-ui', 'apps-ui', 'solutions-page', 'cli', 'mcp', 'export-import', 'other'] },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          did: { type: 'string', description: 'Exact steps/commands/URLs to reproduce' },
          observed: { type: 'string', description: 'What actually happened (note screenshot path for UI)' },
          expected: { type: 'string' },
          reproduced: { type: 'boolean', description: 'true only if actually run and observed' },
          code_ref: { type: 'string', description: 'file:line best guess at cause, if known' },
        },
        required: ['title', 'surface', 'severity', 'did', 'observed', 'expected', 'reproduced'],
      },
    },
    coverage_note: { type: 'string', description: 'What within the axis was tested and what was NOT reached' },
    blocked: { type: 'boolean', description: 'true if the agent could not boot a healthy stack' },
  },
  required: ['axis', 'findings', 'coverage_note'],
}

// One verifier verdict on a single finding.
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    confirmed: { type: 'boolean', description: 'true only if the verifier reproduced it' },
    note: { type: 'string', description: 'what the verifier observed when re-running the repro' },
  },
  required: ['title', 'confirmed', 'note'],
}
```

- [x] **Step 2: Verify the file parses as a workflow**

Run: `Workflow({ scriptPath: ".claude/workflows/solutions-qa-fanout.mjs" })` is NOT run yet (no body). Instead syntax-check with node:
`node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: no output (exit 0) — valid JS. (The file has no executable body yet; `node --check` only validates syntax, which is what we want here.)

- [x] **Step 3: Commit**

```bash
cd /home/jack/GitHub/bifrost/.claude/worktrees/solutions-success-criteria
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "feat(qa): scaffold solutions-qa-fanout workflow (meta + schemas)"
```

---

## Task 2: Add the per-agent bootstrap text (shared ENV)

Every axis agent needs identical instructions for provisioning+tearing-down its own port-mode stack. This is a shared string injected into each axis prompt.

**Files:**
- Modify: `.claude/workflows/solutions-qa-fanout.mjs`

- [x] **Step 1: Append the BOOTSTRAP constant**

After the schemas, add:

```javascript
// Injected into every axis agent. Each agent provisions its OWN isolated,
// port-mode debug stack (Chrome/Playwright cannot drive netbird stacks), drives
// it, and tears it down. Per-worktree Compose project name = automatic isolation.
const REPO = '/home/jack/GitHub/bifrost'
const BASE_WORKTREE = `${REPO}/.claude/worktrees/solutions-success-criteria`

const BOOTSTRAP = `
YOU PROVISION YOUR OWN STACK. Do this before any testing, and tear it down at the end.

1. Create an isolated worktree off the branch under test:
   AXIS=<your-axis-key>
   WT=/tmp/qa-$AXIS
   git -C ${BASE_WORKTREE} worktree add "$WT" HEAD
   cd "$WT"

2. Boot a PORT-MODE stack (MANDATORY — netbird stacks can't be driven by a browser):
   env -u NETBIRD_SETUP_KEY ./debug.sh up
   ./debug.sh status        # capture the http://localhost:<port> URL — call it $URL
   If the api container is not healthy within ~90s, retry \`env -u NETBIRD_SETUP_KEY ./debug.sh down && env -u NETBIRD_SETUP_KEY ./debug.sh up\` ONCE. If still unhealthy, set blocked=true in your output and STOP (do not invent findings).

3. Install the API-matched CLI in a scratch dir OUTSIDE the repo:
   mkdir -p /tmp/qa-cli-$AXIS && cd /tmp/qa-cli-$AXIS
   python3 -m venv .venv && .venv/bin/pip install --quiet --upgrade pip
   .venv/bin/pip install --quiet "$URL/api/cli/download"
   .venv/bin/bifrost login --url "$URL" --email dev@gobifrost.com --password password
   Run the CLI FROM /tmp/qa-cli-$AXIS (its .env carries the tokens). Default creds: dev@gobifrost.com / password (superuser, MFA off).

4. Drive the UI with Playwright against $URL (headless is fine). Capture screenshots
   to /tmp/qa-$AXIS/shots/ for any UI finding and put the path in observed.

5. TEARDOWN (always, even on failure): cd "$WT" && env -u NETBIRD_SETUP_KEY ./debug.sh down ; git -C ${BASE_WORKTREE} worktree remove --force "$WT"

RULES OF ENGAGEMENT:
- VERIFY EMPIRICALLY. Reading code forms hypotheses; driving the running stack concludes. A finding is REAL only if you reproduced it on your stack — include exact commands/URLs/clicks and observed-vs-expected.
- You MAY create solutions/workflows/tables/configs/forms/apps and install them to orgs to set up tests. Correctness findings matter more than tidiness.
- Do NOT modify product source. This is a drive/audit pass. Throwaway fixtures via CLI/API/UI are fine.
- If you could not boot a healthy stack, return blocked=true with an empty findings array — never fabricate.
`
```

- [x] **Step 2: Syntax check**

Run: `node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: exit 0, no output.

- [x] **Step 3: Commit**

```bash
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "feat(qa): per-agent port-mode stack bootstrap text"
```

---

## Task 3: Define the 6 axis prompts

**Files:**
- Modify: `.claude/workflows/solutions-qa-fanout.mjs`

- [x] **Step 1: Append the AXES array**

After `BOOTSTRAP`, add the 6 axes. Each prompt = `${BOOTSTRAP}` + the axis mission. Write them exactly:

```javascript
const AXES = [
  {
    key: 'scope-isolation',
    prompt: `${BOOTSTRAP}

YOUR AXIS: SCOPE / CROSS-ORG ISOLATION (the #1 fear). Set AXIS=scope-isolation in the bootstrap.
Drive empirically on your own stack:
1. Create two orgs (CLI: \`bifrost orgs create\`). Install a solution (workflow + table + config) to OrgA only.
2. As a principal in OrgB (use --org on execute, or impersonate as superuser), confirm OrgB CANNOT resolve/execute OrgA's install's workflow by path, CANNOT read its table, CANNOT see its config value.
3. Forge an X-Bifrost-App header naming OrgA's app while authenticated as an OrgB user; confirm it does NOT reach OrgA's table (curl the API with the OrgB bearer token from your scratch .env).
4. Superuser scope-override: confirm pinning scope to OrgA returns OrgA's entities and to OrgB returns OrgB's — never bleeding.
5. S3 isolation: confirm OrgA's _solutions/{id}/ content is not readable as OrgB.
Return structured findings, axis="scope-isolation".`,
  },
  {
    key: 'lifecycle',
    prompt: `${BOOTSTRAP}

YOUR AXIS: INSTALL / UNINSTALL / REDEPLOY LIFECYCLE. Set AXIS=lifecycle in the bootstrap.
Drive empirically:
1. Full install round-trip (CLI \`bifrost solution install\` AND the Solutions UI page) — both must work.
2. Seed rows into an installed solution table, UNINSTALL, confirm the table+rows are ORPHANED not destroyed (orphaned_at set, solution_id NULL'd; visible via "Show orphaned" in UI). RE-INSTALL the same slug; confirm orphaned data REATTACHES (origin_solution_slug/id provenance) and row data survived.
3. Redeploy with a CHANGED table schema; rows must survive (deploy upserts the Table row, never deletes Documents).
4. Same-slug independence: two different installs of solutions sharing a workflow path each resolve their OWN workflow.
5. Install with config values (\`--set KEY=VALUE\` and via the UI install dialog); confirm values land on the install and are readable at runtime, instance-owned (not in the export bundle).
Return structured findings, axis="lifecycle".`,
  },
  {
    key: 'readonly-enforcement',
    prompt: `${BOOTSTRAP}

YOUR AXIS: READ-ONLY / MANAGED-ENTITY ENFORCEMENT. Set AXIS=readonly-enforcement in the bootstrap.
Deploy is the SOLE writer of solution-managed entities. Try to MUTATE managed forms/agents/tables/configs through EVERY surface and confirm each is refused (409 / skipped), not silently applied:
1. UI: open a solution-managed form/agent/app in the builder and try to edit/save.
2. CLI: \`bifrost forms update\` / \`agents update\` / \`tables update\` / \`configs set\` against a managed entity.
3. API: PATCH/PUT the managed entity directly with a superuser token.
4. \`/api/workflows/{id}/remap\` pointed at a managed form/agent's workflow binding.
5. MCP tools (if reachable) that mutate forms/agents/tables.
For each: is it blocked with a clear error, or does it silently corrupt managed state? A silent mutation is a high/critical finding.
Return structured findings, axis="readonly-enforcement".`,
  },
  {
    key: 'global-repo-data-fallback',
    prompt: `${BOOTSTRAP}

YOUR AXIS: GLOBAL-REPO / DATA-FALLBACK. Set AXIS=global-repo-data-fallback in the bootstrap.
CODE fallback is gated by global_repo_access; DATA fallback (tables/configs/storage) is currently UNGATED by design — your job is to produce EVIDENCE on whether that asymmetry bites.
1. Install a solution with global_repo_access=FALSE that contains a workflow which \`from modules.x import y\` references a _repo/ module. Run it; confirm the _repo/ import does NOT resolve (sealed). Flip global_repo_access=TRUE, redeploy/re-run; confirm it now DOES resolve.
2. With a SEALED install (global_repo_access=FALSE): from its workflow, read a _repo/ TABLE by name and a _repo/ CONFIG by key that the install does NOT own. Document whether the sealed install can currently reach _repo/ DATA (expected: yes, ungated). Capture whether this serves surprising/wrong data (e.g. a _repo/ table shadowing an install-intended name).
3. Toggle global_repo_access OFF->ON and ON->OFF and re-run with a warm worker; confirm the per-execution import root reflects the current flag (no stale context bleed).
Return structured findings, axis="global-repo-data-fallback". In coverage_note, state plainly whether the ungated data fallback caused any real wrong-data outcome.`,
  },
  {
    key: 'ui-ux',
    prompt: `${BOOTSTRAP}

YOUR AXIS: UI/UX CORRECTNESS (drive the BROWSER with Playwright, screenshot everything). Set AXIS=ui-ux in the bootstrap.
1. Forms: render and SUBMIT a form (incl. a solution-managed form — confirm it runs the install's OWN workflow, not a _repo/ one). Watch for 404s/empty results.
2. Standalone v2 apps: open an installed solution's app; confirm it mounts and works.
3. BifrostHeader STANDALONE: a v2 app using the SDK BifrostHeader must render STYLED outside the platform theme (this was just fixed to use inline styles). Screenshot it; confirm it is NOT unstyled (has borders/spacing/colors, hover works).
4. Solutions install/manage page: install dialog, config-schema prompts (incl. secret-typed fields masked), "Show orphaned", uninstall confirm.
5. The Solutions page itself: list/preview/entity-summary chips render correctly.
Return structured findings, axis="ui-ux". Put screenshot paths in observed.`,
  },
  {
    key: 'cli-docs-literalism',
    prompt: `${BOOTSTRAP}

YOUR AXIS: CLI / DOCS-LITERALISM. Set AXIS=cli-docs-literalism in the bootstrap.
Be the user who copies the published docs VERBATIM and a user copying STALE patterns.
1. Follow CLAUDE.md's "Spinning up / connecting" and docs/llm.txt solution recipes exactly; note any step that doesn't work as written.
2. \`bifrost solution init\` -> \`scaffold-app\` -> \`deploy\` first-run path; confirm the scaffold's sample workflow actually deploys+runs (a prior bug dropped functions/).
3. \`bifrost watch\` INSIDE a solution workspace must REFUSE with the message pointing at \`bifrost solution start\` (just landed). Confirm. Then \`bifrost solution start\` local dev: app + local workflows behind one origin.
4. \`bifrost export --portable <dir>\` then \`bifrost import <dir> --org <uuid> --role-mode name\` into another org: clean round-trip? env-specific fields scrubbed? imported solution then INSTALLS and WORKS?
5. Try a stale pattern a user might copy from old docs (e.g. an old import flag, a removed subcommand) — does it fail with a helpful error or a confusing traceback?
Return structured findings, axis="cli-docs-literalism".`,
  },
]
```

- [x] **Step 2: Syntax check**

Run: `node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: exit 0.

- [x] **Step 3: Assert there are exactly 6 axes with unique keys**

Run:
```bash
node -e "import('./.claude/workflows/solutions-qa-fanout.mjs').catch(()=>{}); const s=require('fs').readFileSync('.claude/workflows/solutions-qa-fanout.mjs','utf8'); const keys=[...s.matchAll(/key: '([a-z-]+)'/g)].map(m=>m[1]); console.log(keys); if(new Set(keys).size!==6){process.exit(1)}"
```
Expected: prints the 6 keys; exit 0. (Plain text check — the file uses ESM `export` so a direct require would fail; we only grep the source for the 6 `key:` literals.)

- [x] **Step 4: Commit**

```bash
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "feat(qa): 6 adversarial axis prompts (scope/lifecycle/readonly/global-repo/ui/cli)"
```

---

## Task 4: Pre-flight cleanup body

**Files:**
- Modify: `.claude/workflows/solutions-qa-fanout.mjs`

The cleanup is deterministic orchestration. The Workflow script can't run Bash directly, so it delegates to a single `agent()` whose ONLY job is the cleanup (it has Bash). This keeps the script's intent explicit and the destructive ops auditable.

- [x] **Step 1: Append the cleanup phase + agent**

After `AXES`, add:

```javascript
const CLEANUP_PROMPT = `
You are the PRE-FLIGHT CLEANUP for a QA fan-out. Do EXACTLY these, then report what you freed. Be careful and conservative — when unsure, KEEP.

1. KILL STRAY STACKS. List running bifrost stacks:
   docker ps --format '{{.Names}}' | grep -E 'bifrost-(debug|test)' | sed -E 's/-(api|client|worker|scheduler|postgres|redis|rabbitmq|seaweedfs|pgbouncer|init)-[0-9]+$//' | sort -u
   For every project EXCEPT the one for ${BASE_WORKTREE} (its debug stack — KEEP it), tear it down with: \`docker compose -p <project> down\` (or stop its containers). Do NOT remove volumes you are unsure about; stopping is enough to free RAM.

2. PRUNE MERGED AGENT WORKTREES. For each branch matching 'worktree-agent-*' that is MERGED into main:
   git -C ${REPO} branch --merged main | grep -E 'worktree-agent-' | while read b; do
     wt=$(git -C ${REPO} worktree list | grep "\\[$b\\]" | awk '{print $1}')
     [ -n "$wt" ] && git -C ${REPO} worktree remove --force "$wt"
     git -C ${REPO} branch -d "$b"
   done
   NEVER touch named feature worktrees (entity-access, bridge-cse, pr-288-review, bifrost-plugin-testing, solutions-success-criteria, etc.). ONLY worktree-agent-* that are merged.

3. REPORT: RAM freed (free -m before/after), worktrees removed, branches deleted, what you KEPT and why. Return this as your text.
`

phase('Cleanup')
log('Pre-flight: killing stray stacks + pruning merged agent worktrees...')
const cleanupReport = await agent(CLEANUP_PROMPT, { label: 'cleanup', phase: 'Cleanup' })
log('Cleanup done.')
```

- [x] **Step 2: Syntax check**

Run: `node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: exit 0.

- [x] **Step 3: Commit**

```bash
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "feat(qa): pre-flight cleanup phase (stray stacks + merged agent worktrees)"
```

---

## Task 5: Fan-out, verify pipeline, synthesis, return

**Files:**
- Modify: `.claude/workflows/solutions-qa-fanout.mjs`

- [x] **Step 1: Append the fan-out + verify + synthesis + return**

After the cleanup phase, add:

```javascript
// PHASE 2 — FIND: 6 axes in parallel, each on its own port-mode stack.
phase('Find')
log(`Fanning out ${AXES.length} axis agents (each provisions its own port-mode stack)...`)
const axisReports = (await parallel(
  AXES.map((a) => () =>
    agent(a.prompt, { label: `find:${a.key}`, phase: 'Find', schema: FINDING_SCHEMA })
  )
)).filter(Boolean)

const blocked = axisReports.filter((r) => r.blocked)
const allFindings = axisReports.flatMap((r) =>
  (r.findings || []).map((f) => ({ ...f, axis: r.axis }))
)
const toVerify = allFindings.filter((f) => f.reproduced && f.severity !== 'info')
log(`Collected ${allFindings.length} findings; ${toVerify.length} reproduced non-info to verify. ${blocked.length} axes blocked on stack boot.`)

// PHASE 3 — VERIFY: independent refutation per finding (pipeline: each verifies
// as soon as it exists; verifier provisions its own stack via the same bootstrap).
phase('Verify')
const verdicts = await pipeline(
  toVerify,
  (f) => agent(
    `${BOOTSTRAP}

You are an INDEPENDENT VERIFIER. Set AXIS=verify-${(f.axis || 'x').slice(0,12)} in the bootstrap. Provision your own port-mode stack.
A prior agent reported this finding on the ${f.axis} axis. Your job is to REFUTE it: reproduce the EXACT steps and report whether it actually manifests. Default to confirmed=false if you cannot reproduce it.

FINDING TITLE: ${f.title}
SURFACE: ${f.surface}
STEPS THEY TOOK (did): ${f.did}
THEY OBSERVED: ${f.observed}
THEY EXPECTED: ${f.expected}

Run those steps on YOUR fresh stack. Set confirmed=true ONLY if you see the same wrong behavior; otherwise confirmed=false and explain what you saw instead. Tear your stack down.`,
    { label: `verify:${(f.title || '').slice(0, 32)}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  ).then((v) => ({ finding: f, verdict: v })).catch(() => null)
)
const checked = verdicts.filter(Boolean)
const confirmed = checked.filter((c) => c.verdict?.confirmed).map((c) => ({ ...c.finding, verify_note: c.verdict.note }))
const refuted = checked.filter((c) => !c.verdict?.confirmed).map((c) => ({ title: c.finding.title, axis: c.finding.axis, why: c.verdict?.note }))
log(`Verify: ${confirmed.length} confirmed, ${refuted.length} refuted.`)

// PHASE 4 — SYNTHESIZE: dedup, rank, write the backlog doc.
phase('Synthesize')
const synthDoc = await agent(
  `You are the SYNTHESIS agent for a Solutions adversarial QA fan-out. Produce the final findings backlog and WRITE it to ${BASE_WORKTREE}/docs/plans/2026-06-09-solutions-qa-fanout-findings.md (use your Write tool).

CONFIRMED findings (already independently verified — these are REAL), JSON:
${JSON.stringify(confirmed, null, 2)}

REFUTED (a verifier could not reproduce — list these separately so they are not re-investigated), JSON:
${JSON.stringify(refuted, null, 2)}

BLOCKED axes (could not boot a stack — note for re-run), JSON:
${JSON.stringify(blocked.map((b) => ({ axis: b.axis, note: b.coverage_note })), null, 2)}

COVERAGE NOTES per axis, JSON:
${JSON.stringify(axisReports.map((r) => ({ axis: r.axis, note: r.coverage_note })), null, 2)}

The doc must have: a STATUS line (counts by severity of CONFIRMED only); a CONFIRMED section grouped by severity (critical first), each item with did/observed/expected/code_ref and a one-line proposed fix shape; a REFUTED section (title + why); a DATA-FALLBACK VERDICT section (pull from the global-repo-data-fallback axis coverage_note: did the ungated data fallback actually bite? this decides whether the deferred gate becomes a real follow-up); a COVERAGE/GAPS section; and a BLOCKED section if any. Return a 5-line summary as your text.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return {
  axes: axisReports.map((r) => r.axis),
  blocked_axes: blocked.map((r) => r.axis),
  total_findings: allFindings.length,
  confirmed: confirmed.length,
  refuted: refuted.length,
  by_severity_confirmed: ['critical', 'high', 'medium', 'low'].reduce((acc, s) => {
    acc[s] = confirmed.filter((f) => f.severity === s).length
    return acc
  }, {}),
  cleanup: cleanupReport,
  synthesis: synthDoc,
  findings_doc: `${BASE_WORKTREE}/docs/plans/2026-06-09-solutions-qa-fanout-findings.md`,
}
```

- [x] **Step 2: Syntax check the complete file**

Run: `node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: exit 0.

- [x] **Step 3: Commit**

```bash
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "feat(qa): fan-out + independent verify pipeline + synthesis"
```

---

## Task 6: Static review of the workflow against the spec

No code — a focused read-through to catch logic errors before a live run (a live run costs real stacks + tokens).

**Files:**
- Read: `.claude/workflows/solutions-qa-fanout.mjs`, the spec

- [x] **Step 1: Verify each spec requirement maps to code**

Read the spec and confirm in the script:
- Pre-flight cleanup kills stray stacks + prunes ONLY merged `worktree-agent-*` (Task 4 prompt). ✓ keeps named worktrees.
- 6 axes present, each injects `BOOTSTRAP` (port-mode boot via `env -u NETBIRD_SETUP_KEY`). ✓
- `parallel()` fan-out is capped — confirm the runtime cap (min(16, cores-2)) is ≤ our intended 6 OR add an explicit note. **If the host has >8 cores the cap exceeds 6.** Add a guard: slice/throttle to 6. Edit the fan-out to cap explicitly:

```javascript
// Cap concurrency at 6 stacks regardless of core count (each stack ~2.2GB).
async function throttle(thunks, limit) {
  const out = []; const running = new Set()
  for (const t of thunks) {
    const p = Promise.resolve().then(t); out.push(p)
    running.add(p); p.finally(() => running.delete(p))
    if (running.size >= limit) await Promise.race(running)
  }
  return Promise.all(out)
}
```
Replace the `await parallel(AXES.map(...))` find call with `await throttle(AXES.map((a)=>()=>agent(...)), 6)` (keep the same agent call inside). Apply the SAME `throttle(..., 6)` to the verify pipeline if `toVerify.length > 6` — wrap the per-item thunks. (The base matrix is 6 so the find phase is one wave; verify may exceed 6.)

- [x] **Step 2: Apply the throttle guard, re-syntax-check**

Run: `node --check .claude/workflows/solutions-qa-fanout.mjs`
Expected: exit 0.

- [x] **Step 3: Commit**

```bash
git add .claude/workflows/solutions-qa-fanout.mjs
git commit -m "fix(qa): cap fan-out + verify concurrency at 6 stacks (RAM ceiling)"
```

---

## Task 7: One-axis smoke run (gated), then full run

Validate the workflow end-to-end on ONE axis before committing 6 stacks. This is the real test — the deliverable is a workflow that actually runs.

**Files:** none (operational)

- [x] **Step 1: Temporary 1-axis smoke**

Make a throwaway copy limited to one cheap axis to validate the full pipeline (cleanup → 1 find → verify → synth) without 6 stacks:
```bash
cp .claude/workflows/solutions-qa-fanout.mjs /tmp/qa-smoke.mjs
# Edit /tmp/qa-smoke.mjs: in AXES keep ONLY the 'cli-docs-literalism' axis (cheapest, no browser).
```
Run it: `Workflow({ scriptPath: "/tmp/qa-smoke.mjs" })`
Expected: cleanup runs; 1 axis agent boots a port-mode stack, produces findings (or blocked=true); verify runs on any reproduced finding; synthesis writes the findings doc. Watch `/workflows` for live progress.

- [x] **Step 2: Triage the smoke result**

Confirm: the findings doc was written, the agent actually booted a stack (not blocked), and the structured return has the expected shape. If the agent reported BLOCKED on stack boot, debug the bootstrap (port-mode flag, CLI install URL) before the full run — do NOT proceed to 6 stacks with a broken bootstrap.

- [x] **Step 3: Full run**

Run: `Workflow({ name: "solutions-qa-fanout" })`
Expected: all 4 phases complete; `docs/plans/2026-06-09-solutions-qa-fanout-findings.md` written with confirmed/refuted/data-fallback-verdict/gaps sections. Monitor `/workflows`.

- [x] **Step 4: Commit the findings doc**

```bash
git add docs/plans/2026-06-09-solutions-qa-fanout-findings.md
git commit -m "docs(qa): Solutions adversarial QA fan-out findings"
```

- [x] **Step 5: Clean up the smoke file**

```bash
rm -f /tmp/qa-smoke.mjs
```

---

## Self-review notes

- **Spec coverage:** Workflow orchestration → Tasks 1–5. Pre-flight cleanup → Task 4. 6 axes → Task 3. Per-agent port-mode stacks → Task 2 (BOOTSTRAP). Verify pass → Task 5 (pipeline). Synthesis + findings doc → Task 5. Data-fallback evidence → axis 4 prompt + synthesis "DATA-FALLBACK VERDICT" section. Resource cap (6) → Task 6 throttle. Netbird-port constraint → BOOTSTRAP `env -u NETBIRD_SETUP_KEY`. Flake handling → BOOTSTRAP retry+blocked.
- **No production code / no unit tests:** correct — the deliverable is an orchestration script; its "test" is the gated smoke run (Task 7) before the full run. This is intentional and matches the artifact type.
- **Throttle vs parallel:** `parallel()` is a barrier capped at min(16,cores-2); on an 8+-core host that exceeds our 6-stack RAM ceiling, hence the explicit `throttle(...,6)` in Task 6. The base find phase is exactly 6 (one wave); verify may exceed 6 and is also throttled.
- **Destructive ops are agent-driven + conservative:** cleanup only stops stacks and prunes MERGED worktree-agent-* branches; named worktrees are explicitly protected. The prompt says "when unsure, KEEP."
