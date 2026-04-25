# Bifrost OSS Security & Maturity Setup

## Context

Bifrost is a public OSS project (jackmusick/bifrost) at the "engineering hygiene basics work, but no OSS-maturity layer yet" stage. CI runs lint/typecheck/unit/e2e tests, but there is no dependency scanning, no SAST, no security disclosure policy, no scorecard, and the README claims AGPL while the `LICENSE` file is missing entirely (GitHub's license API returns 404 — the AGPL claim is unenforceable until the file ships).

This work establishes the standard supply-chain + security + community-health baseline that public OSS projects are expected to have. The intended outcome:

- A populated GitHub **Security tab** that functions as a live TODO list (Dependabot CVEs, CodeQL findings, secret-scan hits)
- **Auto-PRs** for CVE patches and routine dependency staleness, grouped to avoid noise
- **Auto-merge** on the safe categories (security, patch, minor) so toil drops to ~zero for low-risk updates
- **OpenSSF Scorecard** publicly visible, scored ≥7/10, badge in README
- Two skills: `bifrost-secupdate` codifies the alert/PR resolution loop; `bifrost-secaudit` produces a current-state snapshot of the Security tab
- A **one-time `/loop`** kicked off after the Tier 1+2 PR merges that polls the Security tab until it populates, then drains the backlog, then exits. (A recurring schedule is intentionally out of scope for v1 — separate conversation later.)

User has granted full permission to execute commands autonomously where the tool allows it. A small list of clicks-only Settings toggles will be handed back to the user as a numbered checklist.

## Approach

Four tiers, executed in one PR (or two if Tier 1+2 grow large), then a second pass once GitHub has populated the Security tab.

### Tier 0 — License hygiene (blocker for everything else)

- **Add `LICENSE` file at repo root** with full GNU AGPL-3.0 text (verbatim from gnu.org / SPDX). README already badges and references AGPL — the file just isn't there.
- **Verify** with `gh api repos/jackmusick/bifrost/license` returning 200 (currently 404).

### Tier 1 — GitHub-native security & dependency tooling

All free, all built-in. Done as repo Settings toggles + workflow files.

**Dependabot — `.github/dependabot.yml`:**
- Ecosystems:
  - `pip` — directory `/` (root `requirements.txt`)
  - `npm` — directory `/client`
  - `docker` — directories `/api` and `/client` (covers 5 Dockerfiles total: `api/Dockerfile`, `api/Dockerfile.dev`, `client/Dockerfile`, `client/Dockerfile.dev`, `client/Dockerfile.playwright`)
  - `github-actions` — directory `/`
- Schedule: `weekly` for version updates (Monday morning)
- Grouping: minor + patch grouped per ecosystem; majors stay individual so they get human review
- Open-PR-limit: 10 per ecosystem (default 5 is too tight with grouping disabled for majors)
- Allow security updates always (separate from version-update grouping)

**CodeQL — `.github/workflows/codeql.yml`:**
- Use GitHub's "default setup" template via Actions
- Languages: `python`, `javascript-typescript`
- Triggers: `push: [main]`, `pull_request: [main]`, `schedule: weekly`

**Repo Settings (manual — user clicks):**
- Settings → Code security:
  - Dependabot alerts: ON
  - Dependabot security updates: ON
  - Dependabot version updates: ON (reads the YAML we commit)
  - Secret scanning: ON
  - Push protection: ON
  - CodeQL: confirm "Default" setup is active after the workflow lands

**Branch protection on `main`:**
- Require PR before merging
- Require ≥1 approving review (solo project — but this enforces the "you don't push directly to main" hygiene that Scorecard's Branch-Protection check looks for)
- Require status checks: `lint`, `test-unit`, the CodeQL job
- Require branches up to date before merging
- Configured via `gh api -X PUT repos/jackmusick/bifrost/branches/main/protection ...` — Claude provides the exact JSON payload, user runs it (faster than debugging API permission scopes against the user's token)

**Auto-merge policy:**

| PR type | Auto-merge |
|---|---|
| Security updates (any severity, any semver bump) | Yes if CI green |
| Version-update — patch (`x.y.Z`) | Yes if CI green |
| Version-update — minor (`x.Y.z`) | Yes if CI green |
| Version-update — major (`X.y.z`) | **No** — human review required |
| GitHub Actions updates (pinned to SHA) | Yes if CI green |
| Docker base image updates | **No** — human review required |

Rationale (codified in `SECURITY.md` so contributors know the policy): when CI passes and an auto-merge later breaks something, the broken behavior is itself an untested code path — the resolution is "write the test, fix the regression, ship." Faster patch SLA + clearer test coverage is worth more than the rare auto-merge regression.

**Mechanism:** `.github/workflows/dependabot-auto-merge.yml` — listens on Dependabot PRs, parses the metadata action's `update-type` output, calls `gh pr merge --auto --squash` only for the categories above. Major/Docker PRs get a label (`needs-review`) and stay open.

### Tier 2 — OSS community signals

- **`SECURITY.md`** at repo root — vuln disclosure email `jackmmusick@gmail.com`, response SLA (48 hrs ack), supported versions ("`main` only"), the auto-merge policy summarized so external contributors understand it.
- **`CODEOWNERS`** at `.github/CODEOWNERS` — `* @jackmusick` for now (solo project; adding a real reviewer matrix later is trivial).
- **Pin all GitHub Actions to commit SHAs.** Currently `ci.yml` uses `actions/checkout@v5`, `actions/setup-python@v6`, etc. Scorecard's Pinned-Dependencies check requires SHAs. Tooling: `pinact run` or `ratchet pin` — both auto-pin and leave a comment with the version. Manual pinning also fine for ~5 actions. Done across `ci.yml` and any new workflows in this PR.
- **OpenSSF Scorecard Action — `.github/workflows/scorecard.yml`:**
  - Use the official `ossf/scorecard-action` template
  - Triggers: `schedule: weekly`, `push: [main]`, `branch_protection_rule`
  - Publish results to GitHub Security tab + `securityscorecards.dev`
- **README updates:**
  - Add Scorecard badge (auto-updates)
  - Verify license badge URL/text matches the actual `LICENSE` file (currently links to a generic opensource.org page — should link to the in-repo `LICENSE`)
  - Add CodeQL badge (optional but standard)

### Tier 3 — Skipped for v1

**SonarCloud / Snyk / Socket.dev / Semgrep Cloud are not in scope.** Rationale: CodeQL covers ~80% of what these find for free, the marginal value at this project's size is small, and the marginal toil (triaging a second tool's alerts) is real. Revisit in 2–3 months — if CodeQL has missed real bugs that one of these would have caught, layer it in then with data justifying it.

This is documented in the plan but not implemented now.

### Tier 4 — Skills + one-time watch loop (after Security tab populates)

After the Tier 1+2 PR merges and the Security tab populates with real alerts (~30 min later), drain the backlog in the same session — driven by a one-time `/loop` — and codify the resolution loop as a skill.

**Skill: `bifrost-secupdate`** (reactive — invoked when alerts/PRs exist)
- Inputs: nothing (queries the repo state)
- Loop:
  1. `gh pr list --label dependencies` — find open Dependabot PRs
  2. For each: `gh pr checks <num>` — check CI status
  3. If CI green + auto-merge eligible: confirm it's set to auto-merge or call `gh pr merge --auto --squash`
  4. If CI failing: check out the branch in a worktree, read the failure, fix, push, re-run CI
  5. If failure-fix needs a code change beyond the bump: write the test that demonstrates the issue, then the fix
  6. For Dependabot alerts without a PR (no upstream fix yet): summarize and surface to user — do not auto-act
  7. For CodeQL alerts: triage real-vs-FP; for real ones, write fix + test + PR; for FPs, dismiss with reason via `gh api`
- Halt conditions: a PR fails CI 3 times in a row → stop and ask. A major bump or dep swap → stop and ask. A code-scanning alert that isn't clearly real or FP → stop and ask.

**Skill: `bifrost-secaudit`** (snapshot of current state — invoked manually or by the watch loop's "is it populated yet?" check)
- Inputs: nothing
- Output: a brief markdown summary
  - Open Dependabot alerts: count, severity breakdown
  - Open Dependabot PRs: count by category, oldest age
  - Open CodeQL alerts: count, severity breakdown
  - Secret-scanning alerts: count
  - Scorecard: current score, top-3 lowest-scoring checks
- Used both as the "queue is populated, time to drain" trigger inside the watch loop, and as a standalone "where do I stand?" command later.

**One-time watch loop (this session only):**
- Kicked off via `/loop` (self-paced) immediately after the user merges the Tier 1+2 PR and clicks the Settings checkboxes
- Each tick:
  1. Run `bifrost-secaudit`
  2. If queue is empty (no Dependabot alerts/PRs, no CodeQL alerts) AND <30 min have passed since the PR merged → wait, loop again
  3. If queue is populated → invoke `bifrost-secupdate`, drain everything possible, surface anything that needs human input, **exit the loop**
  4. If 60 min have passed with an empty queue → assume the repo is genuinely clean (no CVEs in current deps), report that, exit
- This is a one-shot — when it exits, no further automation runs. A recurring schedule is a separate decision for a later conversation.

## Files To Modify / Create

| Path | Action | Tier |
|---|---|---|
| `LICENSE` | **Create** — full AGPL-3.0 text from SPDX | 0 |
| `.github/dependabot.yml` | Create | 1 |
| `.github/workflows/codeql.yml` | Create | 1 |
| `.github/workflows/dependabot-auto-merge.yml` | Create | 1 |
| `.github/workflows/ci.yml` | **Edit** — pin all `uses:` to commit SHAs | 2 |
| `.github/workflows/scorecard.yml` | Create | 2 |
| `.github/CODEOWNERS` | Create | 2 |
| `SECURITY.md` | Create | 2 |
| `README.md` | **Edit** — fix license badge link, add Scorecard + CodeQL badges | 2 |
| `.claude/skills/bifrost-secupdate/SKILL.md` | Create | 4 |
| `.claude/skills/bifrost-secaudit/SKILL.md` | Create | 4 |
| `docs/superpowers/specs/2026-04-25-oss-security-maturity-design.md` | Create — committed spec, copy of this plan | execution |

## Manual Steps (consolidated checklist for user)

These cannot be done via the API reliably from this tool. Plan provides exact text to click / commands to paste.

1. **Settings → Code security** — toggle ON: Dependabot alerts, Dependabot security updates, Dependabot version updates, Secret scanning, Push protection. Confirm CodeQL "Default" setup activates after `codeql.yml` lands.
2. **Run the branch protection command** — Claude pastes the exact `gh api -X PUT ... /branches/main/protection` invocation in the PR description.
3. **Merge the PR.**
4. **Wait ~30 minutes** for Security tab to populate.
5. **Reply with `/loop`** (or just "go") — kicks off the one-time watch loop. Loop polls `bifrost-secaudit` until the Security tab populates, drains via `bifrost-secupdate`, exits. No recurring schedule is set up in this plan.

## Reusing Existing Patterns

- `.github/workflows/ci.yml` — extend with consistent `permissions:` blocks (already partly present). Pinned-action edits live here.
- `.claude/skills/bifrost-issues/SKILL.md` and `.claude/skills/reviewing-prs/` — skill structure model for the two new skills (frontmatter, sections, naming).
- `CONTRIBUTING.md` — already documents the test/lint/typecheck bar; new auto-merge policy referenced from `SECURITY.md` rather than duplicated.

## Verification

End-to-end check after each tier merges:

**Tier 0:**
- `gh api repos/jackmusick/bifrost/license` returns 200 with `license.spdx_id == "AGPL-3.0"`
- GitHub repo sidebar shows "AGPL-3.0 license"

**Tier 1:**
- `gh api repos/jackmusick/bifrost/vulnerability-alerts -i` returns HTTP 204 ("alerts enabled"; was 404 = disabled)
- Within 30 min: Security tab → Dependabot shows ≥1 alert (assuming any CVEs exist in current deps — almost certain on a project this size)
- Test the auto-merge workflow by waiting for the first patch-update PR and confirming it lands without manual action
- CodeQL: Actions tab shows the workflow ran successfully; Security tab → Code scanning has results (alerts or "no issues")

**Tier 2:**
- `curl -s https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost | jq .score` returns ≥7
- README Scorecard badge renders the score
- `SECURITY.md` is discoverable at `https://github.com/jackmusick/bifrost/security/policy`
- All `uses:` in workflows resolve to 40-char commit SHAs (`grep -E 'uses:.*@v[0-9]' .github/workflows/*.yml` returns empty)

**Tier 4:**
- `bifrost-secupdate` invoked manually: drives at least one Dependabot PR to merge end-to-end
- `bifrost-secaudit` invoked manually: produces a markdown report with current state
- One-time `/loop` runs to completion: polls until Security tab populates, drains the queue, exits cleanly with a summary

## Open Risks / Things To Watch

- **Auto-merge + green CI ≠ "safe."** If a patch-version bump silently changes behavior in a way our tests don't cover, it'll land. Mitigation: when a regression is found post-merge, the response is "add the test, fix forward" rather than "disable auto-merge." User has explicitly accepted this tradeoff.
- **Branch protection requiring 1 review on a solo project.** Workaround: GitHub allows admins to bypass; or set required reviewers to 0 if it gets in the way. Scorecard's Code-Review check accepts either as long as the protection rule itself is in place.
- **Pinned actions create maintenance overhead** — updating GitHub Actions now requires SHA bumps. Dependabot's `github-actions` ecosystem handles this automatically (it'll open PRs to bump the SHA when the action publishes a new version), so net toil is zero.
- **Scorecard score depends on activity.** The "Maintained" check expects recent commits. Going dark for a few months drops the score. Not a concern given current development pace.
