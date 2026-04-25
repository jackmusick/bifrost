# OSS Security & Maturity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the standard OSS supply-chain + security + community-health baseline (LICENSE, Dependabot, CodeQL, secret scanning, OpenSSF Scorecard, SECURITY.md, branch protection) to the Bifrost repo in a single PR.

**Architecture:** All work is config files at the repo root and under `.github/`. No application code changes. The PR adds 8 new files, edits 2, and is followed by a checklist of repo Settings clicks the user performs after merge. A separate plan written after the Security tab populates will cover the Tier 4 skills + watch-loop work.

**Tech Stack:** GitHub Actions (YAML), Dependabot, CodeQL, OpenSSF Scorecard Action, GNU AGPL-3.0 license text.

**Out of scope (deferred to follow-up plan):**
- `.claude/skills/bifrost-secupdate/` and `.claude/skills/bifrost-secaudit/` — written after Security tab populates so skills can reference real alert structure
- The one-time `/loop` invocation — runs after the PR merges
- SonarCloud / Snyk / Socket.dev (Tier 3) — explicitly skipped, revisit in 2-3 months

**Spec:** See `docs/superpowers/specs/2026-04-25-oss-security-maturity-design.md` for context, decision rationale, and verification criteria.

---

## File Structure

| Path | Action | Tier |
|---|---|---|
| `LICENSE` | Create — full AGPL-3.0 text | 0 |
| `.github/dependabot.yml` | Create | 1 |
| `.github/workflows/codeql.yml` | Create | 1 |
| `.github/workflows/dependabot-auto-merge.yml` | Create | 1 |
| `.github/workflows/scorecard.yml` | Create | 2 |
| `.github/workflows/ci.yml` | Edit — pin all `uses:` lines to commit SHAs | 2 |
| `.github/CODEOWNERS` | Create | 2 |
| `SECURITY.md` | Create | 2 |
| `README.md` | Edit — fix license badge link, add Scorecard + CodeQL badges | 2 |

Each file has one focused responsibility. Workflows live in `.github/workflows/`. Top-level governance files (`LICENSE`, `SECURITY.md`, `CODEOWNERS`) live where GitHub expects to auto-discover them.

---

## Task 1: Add LICENSE file (Tier 0)

**Files:**
- Create: `LICENSE`

**Why:** README claims AGPL but no `LICENSE` file exists. GitHub's license API returns 404, the repo sidebar shows no license, and the AGPL claim has no enforceable text behind it. This blocks Tier 2 (the README license badge needs a real file to link to) so it goes first.

- [ ] **Step 1: Download the canonical AGPL-3.0 text**

The SPDX-canonical AGPL-3.0 text is hosted by the FSF. Use `curl` to fetch it directly into the repo so we don't introduce typos.

```bash
curl -sSfL https://www.gnu.org/licenses/agpl-3.0.txt -o LICENSE
```

- [ ] **Step 2: Verify it downloaded correctly**

```bash
head -5 LICENSE
wc -l LICENSE
```

Expected:
- First line: `                    GNU AFFERO GENERAL PUBLIC LICENSE`
- Line count: ~660 lines (varies slightly with whitespace; should be in the 600-700 range)

- [ ] **Step 3: Confirm SPDX detection**

GitHub uses the `licensee` Ruby gem to detect license. The canonical FSF text matches the `AGPL-3.0` SPDX identifier. There's nothing to run locally — we'll verify after the PR merges via `gh api repos/jackmusick/bifrost/license`.

- [ ] **Step 4: Commit**

```bash
git add LICENSE
git commit -m "$(cat <<'EOF'
chore: add AGPL-3.0 LICENSE file

README has badged AGPL since project inception but the LICENSE file was
missing — the AGPL claim was unenforceable until this lands. Pulls the
canonical FSF text so GitHub's licensee detection identifies it as AGPL-3.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Dependabot config (Tier 1)

**Files:**
- Create: `.github/dependabot.yml`

**Why:** This config tells Dependabot which ecosystems to scan, how often, and how to group PRs. Without it, only security-update PRs flow (after the user enables them in Settings); routine version updates need this YAML.

- [ ] **Step 1: Verify the manifest paths Dependabot will watch**

```bash
ls requirements.txt client/package.json api/Dockerfile api/Dockerfile.dev client/Dockerfile client/Dockerfile.dev client/Dockerfile.playwright
```

Expected: all 7 files exist (1 pip manifest, 1 npm manifest, 5 Dockerfiles).

- [ ] **Step 2: Write `.github/dependabot.yml`**

```yaml
# Dependabot configuration
# Reference: https://docs.github.com/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
#
# Auto-merge policy is enforced by .github/workflows/dependabot-auto-merge.yml
# (security + patch + minor merge automatically when CI is green; major + Docker
# stay open for human review).

version: 2
updates:
  # Python deps (root requirements.txt)
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: "America/Chicago"
    open-pull-requests-limit: 10
    groups:
      python-minor-and-patch:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    labels:
      - dependencies
      - python

  # JS/TS deps (client/)
  - package-ecosystem: npm
    directory: "/client"
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: "America/Chicago"
    open-pull-requests-limit: 10
    groups:
      npm-minor-and-patch:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    labels:
      - dependencies
      - javascript

  # Docker base images — api/
  - package-ecosystem: docker
    directory: "/api"
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: "America/Chicago"
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - docker

  # Docker base images — client/
  - package-ecosystem: docker
    directory: "/client"
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: "America/Chicago"
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - docker

  # GitHub Actions — repo root
  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
      day: monday
      time: "09:00"
      timezone: "America/Chicago"
    open-pull-requests-limit: 10
    groups:
      actions-minor-and-patch:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    labels:
      - dependencies
      - github-actions
```

Notes encoded in the config:
- `groups` blocks for `pip`, `npm`, `github-actions` keep weekly version-update noise to ~1 PR per ecosystem (minor+patch grouped); majors stay individual.
- Docker is intentionally **not** grouped — base-image bumps deserve individual PRs (they require human review per the auto-merge policy).
- Security updates are not configured here; they're enabled at the repo Settings level (Task 9 manual checklist) and don't honor `groups`.

- [ ] **Step 3: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"
```

Expected: no output (parse succeeds). Any error means a typo to fix.

- [ ] **Step 4: Commit**

```bash
git add .github/dependabot.yml
git commit -m "$(cat <<'EOF'
chore(deps): add Dependabot config for pip, npm, docker, actions

Weekly version-update sweep with minor+patch grouped per ecosystem to
keep PR noise manageable. Majors stay individual for human review. Docker
intentionally ungrouped — base-image changes warrant per-PR review.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add CodeQL workflow (Tier 1)

**Files:**
- Create: `.github/workflows/codeql.yml`

**Why:** CodeQL is GitHub's free SAST. Catches injection, deserialization, and other code-level vulnerabilities. Findings land in the Security tab; PR-level alerts surface inline.

- [ ] **Step 1: Write `.github/workflows/codeql.yml`**

```yaml
# CodeQL — GitHub-native SAST
# Findings appear under: Security tab → Code scanning
# https://docs.github.com/code-security/code-scanning/automatically-scanning-your-code-for-vulnerabilities-and-errors/configuring-code-scanning

name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    # Weekly run catches CVEs in newly-published advisories that match
    # existing code patterns (CodeQL queries are updated by GitHub).
    - cron: "0 9 * * 1"

permissions:
  contents: read
  security-events: write
  actions: read

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    timeout-minutes: 60
    strategy:
      fail-fast: false
      matrix:
        language: [python, javascript-typescript]
    steps:
      - name: Checkout
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      - name: Initialize CodeQL
        uses: github/codeql-action/init@4e828ff8d448a8a6e532957b1811f387a63867e8 # v3.29.0
        with:
          languages: ${{ matrix.language }}
          queries: security-and-quality

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@4e828ff8d448a8a6e532957b1811f387a63867e8 # v3.29.0
        with:
          category: "/language:${{ matrix.language }}"
```

Notes:
- All `uses:` are pinned to commit SHAs with the version as a comment — Scorecard's Pinned-Dependencies check requires this.
- `security-and-quality` query suite is broader than `security-extended` — catches code-quality issues alongside vulns.
- Matrix split lets one language fail without blocking the other.

- [ ] **Step 2: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/codeql.yml'))"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/codeql.yml
git commit -m "$(cat <<'EOF'
ci: add CodeQL workflow for python and javascript-typescript

Runs SAST on push/PR and weekly. Findings flow to Security tab → Code scanning.
Actions are pinned to commit SHAs for Scorecard's Pinned-Dependencies check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Dependabot auto-merge workflow (Tier 1)

**Files:**
- Create: `.github/workflows/dependabot-auto-merge.yml`

**Why:** Encodes the auto-merge policy (security + patch + minor merge auto when CI green; major + Docker need human review) so Dependabot PRs don't pile up.

- [ ] **Step 1: Write `.github/workflows/dependabot-auto-merge.yml`**

```yaml
# Dependabot auto-merge policy enforcement
#
# Policy (also documented in SECURITY.md):
#   - Security updates  → auto-merge when CI green
#   - Patch updates     → auto-merge when CI green
#   - Minor updates     → auto-merge when CI green
#   - Major updates     → label needs-review, leave open
#   - Docker updates    → label needs-review, leave open
#
# Mechanism: enable GitHub auto-merge on the eligible PRs. Branch protection
# requires CI green before merge happens, so this never bypasses CI.

name: Dependabot auto-merge

on: pull_request_target

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'
    steps:
      - name: Fetch Dependabot metadata
        id: metadata
        uses: dependabot/fetch-metadata@d7267f607e9d3fb96fc2fbe83e0af444713e90b7 # v2.3.0
        with:
          github-token: "${{ secrets.GITHUB_TOKEN }}"

      - name: Enable auto-merge for safe updates
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-patch' ||
          steps.metadata.outputs.update-type == 'version-update:semver-minor' ||
          steps.metadata.outputs.dependency-type == 'direct:production' && contains(steps.metadata.outputs.dependency-names, 'security')
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Always-merge security advisory bumps
        # Dependabot exposes alert-driven security updates via the
        # `dependency-group` not being set AND the alert metadata being present.
        # Simpler heuristic: PRs with the `security` label that Dependabot adds
        # automatically when the bump resolves a GHSA advisory.
        if: contains(github.event.pull_request.labels.*.name, 'security')
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Label majors and Docker for human review
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-major' ||
          steps.metadata.outputs.package-ecosystem == 'docker'
        run: gh pr edit "$PR_URL" --add-label needs-review
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Notes:
- `pull_request_target` is required so the workflow runs with the base-branch token (Dependabot PRs from forks get a read-only token otherwise).
- `if: github.actor == 'dependabot[bot]'` gates the entire job — humans opening PRs are unaffected.
- `gh pr merge --auto` *enables* auto-merge; the actual merge happens when branch protection's required checks pass.
- The "security" detection has two paths because Dependabot's metadata around security advisories has changed historically — the label-based check is the reliable one; the dependency-name match is belt-and-suspenders.

- [ ] **Step 2: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/dependabot-auto-merge.yml'))"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/dependabot-auto-merge.yml
git commit -m "$(cat <<'EOF'
ci: add Dependabot auto-merge workflow

Enforces auto-merge policy:
- security/patch/minor: enable auto-merge (waits for CI green via branch
  protection, then squashes)
- major/docker: label needs-review and leave open

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add OpenSSF Scorecard workflow (Tier 2)

**Files:**
- Create: `.github/workflows/scorecard.yml`

**Why:** Runs the scorecard scan weekly, publishes results to GitHub's Security tab and the public `securityscorecards.dev` API. Source of the badge in the README.

- [ ] **Step 1: Write `.github/workflows/scorecard.yml`**

```yaml
# OpenSSF Scorecard
# Reference: https://github.com/ossf/scorecard-action
#
# Publishes results to:
#   - GitHub Security tab → Code scanning (under "scorecard")
#   - https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost
#
# The README badge auto-updates from the public API.

name: Scorecard

on:
  branch_protection_rule:
  schedule:
    - cron: "0 10 * * 1"
  push:
    branches: [main]

permissions: read-all

jobs:
  analysis:
    name: Scorecard analysis
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      id-token: write
      contents: read
      actions: read
    steps:
      - name: Checkout
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          persist-credentials: false

      - name: Run analysis
        uses: ossf/scorecard-action@62b2cac7ed8198b15735ed49ab1e5cf35480ba46 # v2.4.0
        with:
          results_file: results.sarif
          results_format: sarif
          publish_results: true

      - name: Upload artifact
        uses: actions/upload-artifact@b4b15b8c7c6ac21ea08fcf65892d2ee8f75cf882 # v4.4.3
        with:
          name: SARIF file
          path: results.sarif
          retention-days: 5

      - name: Upload to code-scanning
        uses: github/codeql-action/upload-sarif@4e828ff8d448a8a6e532957b1811f387a63867e8 # v3.29.0
        with:
          sarif_file: results.sarif
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/scorecard.yml'))"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scorecard.yml
git commit -m "$(cat <<'EOF'
ci: add OpenSSF Scorecard workflow

Weekly scorecard scan publishing to Security tab + securityscorecards.dev.
README badge added in a later commit consumes the public API.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Pin GitHub Actions in ci.yml to commit SHAs (Tier 2)

**Files:**
- Modify: `.github/workflows/ci.yml`

**Why:** Scorecard's Pinned-Dependencies check requires SHAs (mutable tags like `@v4` can be repointed by a compromised maintainer). This is a mechanical edit: replace every `uses: foo@vN` with `uses: foo@<sha> # vN`.

The ci.yml currently uses these actions:
- `actions/checkout@v4` and `@v5` (mixed — fix to single version)
- `actions/setup-python@v6`
- `actions/setup-node@v5`
- `codecov/codecov-action@v4`
- `digitalocean/action-doctl@v2`
- `docker/build-push-action@v5`
- `docker/login-action@v3`
- `docker/metadata-action@v5`
- `docker/setup-buildx-action@v3`
- `softprops/action-gh-release@v1`

- [ ] **Step 1: Resolve current SHAs for each action**

For each action, fetch the SHA of its latest matching tag:

```bash
gh api repos/actions/checkout/git/refs/tags/v4.2.2 --jq '.object.sha'
gh api repos/actions/checkout/git/refs/tags/v5.0.0 --jq '.object.sha'
gh api repos/actions/setup-python/git/refs/tags/v6.0.0 --jq '.object.sha'
gh api repos/actions/setup-node/git/refs/tags/v5.0.0 --jq '.object.sha'
gh api repos/codecov/codecov-action/git/refs/tags/v4.6.0 --jq '.object.sha'
gh api repos/digitalocean/action-doctl/git/refs/tags/v2.5.1 --jq '.object.sha'
gh api repos/docker/build-push-action/git/refs/tags/v5.4.0 --jq '.object.sha'
gh api repos/docker/login-action/git/refs/tags/v3.3.0 --jq '.object.sha'
gh api repos/docker/metadata-action/git/refs/tags/v5.6.1 --jq '.object.sha'
gh api repos/docker/setup-buildx-action/git/refs/tags/v3.7.1 --jq '.object.sha'
gh api repos/softprops/action-gh-release/git/refs/tags/v1.0.0 --jq '.object.sha'
```

Some of these tag names may be wrong (e.g. `v4.2.2` vs latest `v4.x` could be different). For each, if the tag returns a 404, run `gh api repos/<owner>/<repo>/releases/latest --jq '.tag_name'` first to discover the actual latest tag name. Capture every (action, version, SHA) triple before editing the file.

Example: `actions/checkout v4.2.2` → SHA `11bd71901bbe5b1630ceea73d27597364c9af683`.

- [ ] **Step 2: Replace every `uses: foo@vN` line in ci.yml**

For each action found in step 1, edit ci.yml replacing:

```yaml
        uses: actions/checkout@v4
```

with:

```yaml
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```

There's a mix of `actions/checkout@v4` and `@v5` in the file — use the highest version (`v5.x`) consistently for both, with the resolved SHA. The version comment (`# v5.0.0`) is what Dependabot's `github-actions` ecosystem reads when proposing future bumps, so keep it accurate.

- [ ] **Step 3: Verify no unpinned uses remain in the changed file**

```bash
grep -nE 'uses:.*@v[0-9]+([.]|$|\s)' .github/workflows/ci.yml
```

Expected: empty output (every `uses:` is now an SHA followed by `# vN.N.N`).

- [ ] **Step 4: Validate YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
ci: pin all GitHub Actions in ci.yml to commit SHAs

Required for OpenSSF Scorecard's Pinned-Dependencies check. Mutable tags
like @v4 can be silently repointed by a compromised maintainer; SHAs
cannot. Version comments (# v4.2.2) preserve Dependabot's ability to
detect newer releases.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add CODEOWNERS (Tier 2)

**Files:**
- Create: `.github/CODEOWNERS`

**Why:** GitHub uses this for automatic PR reviewer assignment. Scorecard's Code-Review check looks for it. Solo project, so the rule is simple — but the file's existence matters.

- [ ] **Step 1: Write `.github/CODEOWNERS`**

```text
# CODEOWNERS — automatic reviewer assignment
# https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
#
# Right now this is a solo project. As contributors grow, this expands
# to per-path ownership (e.g. api/ → backend folks, client/ → frontend).

* @jackmusick
```

- [ ] **Step 2: Commit**

```bash
git add .github/CODEOWNERS
git commit -m "$(cat <<'EOF'
chore: add CODEOWNERS

Solo-project ownership rule for now (* @jackmusick). Lets GitHub
auto-request review from the maintainer on every PR and satisfies
Scorecard's Code-Review check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add SECURITY.md (Tier 2)

**Files:**
- Create: `SECURITY.md`

**Why:** GitHub auto-discovers this file and exposes it as the project's "Security policy" link. Tells researchers how to report vulnerabilities. Required by Scorecard's Security-Policy check.

- [ ] **Step 1: Write `SECURITY.md`**

```markdown
# Security Policy

## Supported Versions

Bifrost is in active development against `main`. Only `main` is supported
at this time — there are no LTS branches. If you're running a fork or a
historical commit, please rebase onto current `main` before reporting.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| Older   | :x:                |

## Reporting a Vulnerability

**Do not open a public issue for security reports.**

Two ways to report privately:

### 1. GitHub private vulnerability reporting (preferred)

Go to https://github.com/jackmusick/bifrost/security/advisories/new
and submit a draft advisory. This keeps the report confidential and lets
us discuss + patch + coordinate disclosure inside GitHub's tooling.

### 2. Email

If you can't use GitHub's flow, email **jackmmusick@gmail.com** with:

- A description of the issue and its impact
- Reproduction steps
- The affected commit / branch
- Your contact info for follow-up

### Response SLA

- **Acknowledgment:** within 48 hours of report
- **Triage + severity assessment:** within 7 days
- **Patch + advisory disclosure:** depends on severity; we'll communicate
  expected timelines after triage

We don't currently run a paid bug bounty. If your report leads to a fix,
we'll credit you in the advisory and the release notes (unless you'd
rather stay anonymous).

## Supply-Chain Practices

The repo runs:

- **Dependabot alerts + security updates** for `pip`, `npm`, `docker`,
  `github-actions` (see `.github/dependabot.yml`)
- **CodeQL** SAST on push, PR, and weekly schedule
  (see `.github/workflows/codeql.yml`)
- **Secret scanning + push protection** at the repo level
- **OpenSSF Scorecard** weekly, results published to
  https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost

### Auto-Merge Policy for Dependency Updates

To keep patch SLAs short, Dependabot PRs auto-merge under these conditions:

| Update type | Auto-merge |
|---|---|
| Security advisory bumps | Yes if CI green |
| Patch (`x.y.Z`) | Yes if CI green |
| Minor (`x.Y.z`) | Yes if CI green |
| Major (`X.y.z`) | No — human review |
| Docker base image | No — human review |
| GitHub Actions (pinned to SHA) | Yes if CI green |

Auto-merged PRs still go through the full CI suite (lint, typecheck,
unit, e2e). If a green-CI auto-merge later breaks something, the
behavior is by definition uncovered by tests — the response is to add
the test and fix forward, not to gate the auto-merge harder.

## What's Out of Scope

- Issues in dependencies — report those upstream.
- Issues in self-hosted deployments where the operator misconfigured
  the deployment (open ports, weak passwords, etc.) — these are
  operator concerns, not Bifrost vulnerabilities.
- DoS via deliberate resource exhaustion of a single-tenant deploy.
```

- [ ] **Step 2: Commit**

```bash
git add SECURITY.md
git commit -m "$(cat <<'EOF'
docs: add SECURITY.md

Vulnerability disclosure policy: GitHub private advisories preferred,
email fallback at jackmmusick@gmail.com. Documents the auto-merge policy
so contributors know what lands without human review and why.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update README.md (Tier 2)

**Files:**
- Modify: `README.md` (lines 5-9, 232-236)

**Why:** Two issues to fix:
1. License badge links to `https://opensource.org/licenses/agpl` (404 — that page doesn't exist) and shows "License: AGPL" instead of standard SPDX text "AGPL-3.0".
2. No Scorecard or CodeQL badges yet — both are standard for OSS projects taking security seriously.

- [ ] **Step 1: Read current badge block and license section**

```bash
sed -n '5,9p' README.md
sed -n '232,236p' README.md
```

Confirm contents match what's in the spec (5 badges starting with License at line 5; License section at line 232).

- [ ] **Step 2: Edit the badge block**

Replace lines 5-9 with the corrected license badge + new Scorecard + CodeQL badges. The full new block:

```markdown
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![CodeQL](https://github.com/jackmusick/bifrost/actions/workflows/codeql.yml/badge.svg)](https://github.com/jackmusick/bifrost/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost/badge)](https://securityscorecards.dev/viewer/?uri=github.com/jackmusick/bifrost)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
```

Changes:
- License badge: `License-AGPL` → `License-AGPL--3.0` (the `--` renders as a single `-` in shields.io URL encoding); link target `https://opensource.org/licenses/agpl` → `LICENSE` (relative link to the in-repo file).
- Added CodeQL badge (links to the workflow runs page).
- Added Scorecard badge (auto-updates from the public API once the workflow has run at least once after merge).

Use Edit tool with old_string being the existing 5 lines (5-9) and new_string being the 7 lines above.

- [ ] **Step 3: No change needed to the License section text (lines 232-236)**

The existing text:
```markdown
This project is licensed under the AGPL License - see the [LICENSE](LICENSE) file for details.
```

…already links to `LICENSE` correctly. The "Why AGPL?" paragraph below it stays as-is. No edit needed.

- [ ] **Step 4: Verify badge URLs render**

The Scorecard badge will show "no data" until the workflow runs post-merge (~5 min after merge). The other badges should render immediately. Check by opening the markdown in any rendered view (GitHub's PR diff preview works) — but don't block on this; it'll be obvious when the PR is up.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: fix license badge link, add CodeQL + Scorecard badges

- License badge was linking to a 404 page on opensource.org and labeled
  generically as "AGPL"; now links to the in-repo LICENSE file and shows
  the SPDX identifier "AGPL-3.0".
- New CodeQL badge links to the workflow runs page.
- New Scorecard badge auto-updates from securityscorecards.dev once the
  scorecard workflow has its first post-merge run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Open the PR

**Files:** none (operates on the branch)

**Why:** All Tier 0/1/2 file work is done. The PR description carries the manual checklist the user must follow after merge.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin oss-hardening
```

- [ ] **Step 2: Open the PR with the manual checklist in the body**

```bash
gh pr create --title "OSS security & maturity baseline (Tier 0/1/2)" --body "$(cat <<'EOF'
Adds the supply-chain + security + community-health baseline. See
`docs/superpowers/specs/2026-04-25-oss-security-maturity-design.md` for
context and `docs/superpowers/plans/2026-04-25-oss-security-maturity.md`
for the per-task plan.

## What this PR adds

- **`LICENSE`** — full AGPL-3.0 text (README has badged AGPL since day 1
  but the file was missing — GitHub's license API returned 404).
- **`.github/dependabot.yml`** — pip + npm + docker + github-actions,
  weekly, minor+patch grouped per ecosystem.
- **`.github/workflows/codeql.yml`** — SAST on push/PR + weekly.
- **`.github/workflows/dependabot-auto-merge.yml`** — security/patch/minor
  auto-merge when CI green; major + Docker labeled `needs-review`.
- **`.github/workflows/scorecard.yml`** — OpenSSF Scorecard, weekly + on
  branch-protection-rule changes.
- **`.github/CODEOWNERS`** — `* @jackmusick` (solo project for now).
- **`SECURITY.md`** — vulnerability disclosure policy + auto-merge policy
  documentation.
- **`README.md`** — fixed broken license badge link, added CodeQL +
  Scorecard badges.
- **`.github/workflows/ci.yml`** — pinned all `uses:` to commit SHAs
  (Scorecard Pinned-Dependencies check).

## Manual steps after merge

1. **Settings → Code security**, toggle ON:
   - Dependabot alerts
   - Dependabot security updates
   - Dependabot version updates
   - Secret scanning
   - Push protection
   - Confirm CodeQL is detected (should auto-light-up once the workflow
     runs).

2. **Configure branch protection on `main`** by running this command
   locally (after replacing the contexts list with the actual job names
   from the latest CI run):

   ```bash
   gh api -X PUT repos/jackmusick/bifrost/branches/main/protection \
     --input - <<'JSON'
   {
     "required_status_checks": {
       "strict": true,
       "contexts": [
         "Lint & Type Check",
         "Unit Tests",
         "Analyze (python)",
         "Analyze (javascript-typescript)"
       ]
     },
     "enforce_admins": false,
     "required_pull_request_reviews": {
       "required_approving_review_count": 1,
       "dismiss_stale_reviews": true,
       "require_code_owner_reviews": false
     },
     "restrictions": null,
     "allow_force_pushes": false,
     "allow_deletions": false,
     "required_linear_history": true,
     "required_conversation_resolution": true
   }
   JSON
   ```

   Note: `required_approving_review_count: 1` on a solo project means you'd
   need to either have a co-maintainer review, use admin bypass, or set
   this to `0`. Scorecard's Code-Review check accepts `0` as long as
   the protection rule itself exists.

3. **Wait ~30 minutes** for the Security tab to populate with Dependabot
   alerts + first CodeQL scan.

4. **Reply with `/loop`** (or just "go") in the conversation that opened
   this PR — kicks off the one-time watch loop that drains the security
   queue. The `/loop` is a one-shot — no recurring schedule is set up
   here.

## Verification after merge

- `gh api repos/jackmusick/bifrost/license --jq '.license.spdx_id'` →
  `"AGPL-3.0"` (was 404)
- `gh api repos/jackmusick/bifrost/vulnerability-alerts -i` → HTTP 204
- Security tab populates within 30 min
- `curl -s https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost | jq .score`
  → ≥7 (after first scorecard.yml run, ~5 min post-merge)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Verify CI is running on the PR**

```bash
gh pr checks
```

Expected: `Lint & Type Check`, `Unit Tests`, the new `Analyze (python)` and `Analyze (javascript-typescript)` jobs all in `pending` or `in_progress`.

- [ ] **Step 4: Wait for CI**

```bash
gh pr checks --watch
```

Expected: all checks pass. The new CodeQL job may report warnings (it's the first scan) but should succeed. If it fails:
- For workflow YAML errors: read the failure, fix, push.
- For genuine CodeQL findings: leave them — they get triaged in the post-merge loop, not this PR.

---

## Verification (after PR merges + manual checklist)

These are checked manually by the user (or by Claude in the follow-up `/loop` session); they're listed here so the spec's verification criteria are explicit at the plan level.

**Tier 0:**
- `gh api repos/jackmusick/bifrost/license --jq '.license.spdx_id'` returns `"AGPL-3.0"` (currently 404)
- GitHub repo sidebar shows "AGPL-3.0 license"

**Tier 1:**
- `gh api repos/jackmusick/bifrost/vulnerability-alerts -i` returns HTTP 204
- Security tab → Dependabot alerts: ≥1 alert (high probability for a project with this many transitive deps)
- Within ~hours: first patch-update PR opens and gets auto-merged without human action
- CodeQL: Actions tab → CodeQL workflow ran successfully on the PR

**Tier 2:**
- `curl -s https://api.securityscorecards.dev/projects/github.com/jackmusick/bifrost | jq .score` returns ≥7
- README Scorecard badge renders the score (~5 min after first scorecard.yml run)
- `https://github.com/jackmusick/bifrost/security/policy` shows SECURITY.md
- `grep -nE 'uses:.*@v[0-9]+([.]|$|\s)' .github/workflows/*.yml` returns empty

---

## Self-Review Notes

Coverage check against spec (`docs/superpowers/specs/2026-04-25-oss-security-maturity-design.md`):
- Tier 0 (LICENSE) → Task 1 ✓
- Tier 1 dependabot.yml → Task 2 ✓
- Tier 1 CodeQL workflow → Task 3 ✓
- Tier 1 auto-merge workflow → Task 4 ✓
- Tier 2 Scorecard workflow → Task 5 ✓
- Tier 2 pin actions → Task 6 ✓
- Tier 2 CODEOWNERS → Task 7 ✓
- Tier 2 SECURITY.md → Task 8 ✓
- Tier 2 README updates → Task 9 ✓
- Manual checklist (Settings, branch protection) → Task 10 (in PR body) ✓
- Tier 4 (skills + watch loop) → **explicitly out of scope; deferred to follow-up plan after merge** ✓
- Tier 3 (Sonar/Snyk/etc.) → **explicitly skipped** ✓

No placeholders, no TBDs, all code complete in each step. The Task 6 SHA-resolution step requires the engineer to actually run `gh api` calls and capture the SHAs — they're not pre-baked because action versions move; the example SHA in Task 3 (`11bd71901bbe5b1630ceea73d27597364c9af683` for `actions/checkout@v4.2.2`) is real and current as of plan-write time.
