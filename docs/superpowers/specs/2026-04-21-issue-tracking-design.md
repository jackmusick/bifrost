# Issue & Feature Tracking Design

**Date:** 2026-04-21
**Status:** Design approved, pending implementation plan

## Problem

Trackable work on `jackmusick/bifrost` currently lives in several places: local notes, external tickets, browser tabs left open until a task completes, and a handful of GitHub Issues (only four filed to date, all bug-like). There is no central surface where bugs, features, chores, and ideas coexist, which makes it impossible for outside contributors to see what needs doing or to pick up work when the maintainer doesn't get to it. There is also no guardrail preventing work from starting without a corresponding issue, so context for *why* something was built leaks out of the project over time.

## Goals

- **Single source of truth.** All trackable work — bugs, features, chores, ideas, personal todos — lives in GitHub Issues on `jackmusick/bifrost`.
- **Contributor-friendly surface.** Outside contributors can filter for takeable work using GitHub-native conventions (`help wanted`, `good first issue`, unassigned).
- **Lightweight enforcement.** A Claude Code skill nudges toward creating/linking issues when it detects work intent, but does not block. Escape hatches are explicit.
- **Batch triage.** The skill can ingest a pasted list of todos/notes and convert them into properly-templated issues in one shot.

## Non-goals

- No priority labels, milestones, projects, or status labels. These are ceremony until the pain is felt.
- No migration of existing notes/tabs up front. New rules apply going forward; old notes become issues opportunistically or quietly die.
- No parallel tracking system (no Linear, no Jira, no in-repo todo.md).
- No hard gates on PR creation or work start. Light-touch only.

## Architecture

Three pieces:

1. **Issue templates** in `.github/ISSUE_TEMPLATE/` — YAML Issue Forms (not markdown) for field validation and better picker UX.
2. **Label taxonomy** — minimal additions to the existing label set. Keep what's there; add `chore` and `idea`.
3. **`issue-tracking` skill** at `.claude/skills/issue-tracking/SKILL.md` — project-level, checked into the repo so contributors using Claude Code get the same behavior.

Assignee field signals ownership. `help wanted` signals "I'm inviting help." `good first issue` signals ramp-up-friendly. No status-label lifecycle.

## Component: Issue Templates

Three YAML Issue Forms under `.github/ISSUE_TEMPLATE/`, plus a `config.yml` that preserves the blank-issue option for rapid capture.

### `bug.yml`

Auto-applies label: `bug`.

Fields:
- **Summary** (required, short text)
- **Steps to reproduce** (required, multiline)
- **Expected behavior** (required, multiline)
- **Actual behavior** (required, multiline)
- **Environment** (optional, multiline) — branch/commit, browser if UI, relevant container
- **Logs / screenshots** (optional, multiline)

### `feature.yml`

Auto-applies label: `enhancement`.

Fields:
- **Problem** (required, multiline) — what's painful today, or what opportunity exists
- **Proposed solution** (required, multiline) — rough, not a spec
- **Acceptance criteria** (required, multiline) — how we know it's done
- **Design doc link** (optional, short text) — filled in once a spec lands in `docs/superpowers/specs/`

### `chore.yml`

Auto-applies label: `chore`.

Fields:
- **What** (required, multiline)
- **Why** (required, multiline) — why now / what it unblocks

### `config.yml`

```yaml
blank_issues_enabled: true
contact_links: []
```

Keeps the blank-issue option for rapid capture; no external contact links for now.

## Component: Label Taxonomy

Existing labels (keep unchanged): `bug`, `documentation`, `duplicate`, `enhancement`, `good first issue`, `help wanted`, `invalid`, `question`, `wontfix`.

New labels to add:
- **`chore`** — maintenance, tooling, deps, CI, refactors without user-visible change.
- **`idea`** — unformed thoughts worth keeping but not ready to act on. Lower priority than `enhancement`.

That's the full taxonomy. No priority, no milestones, no status.

## Component: `issue-tracking` Skill

Lives at `.claude/skills/issue-tracking/SKILL.md`. Project-scoped (checked in).

### Activation

The skill's frontmatter `description` triggers it when Claude detects:
- User expresses work intent ("let's build/add/fix X", "I want to X", "work on X")
- User pastes a list of todos/notes for triage
- User is about to open a PR
- User asks about existing issues or what to work on

### Behaviors

**Pre-work nudge.** When work intent is detected on non-trivial changes:
1. Check for existing relevant issues via `gh issue list --search "<keywords>"`.
2. If none, ask once: "Is there an issue for this? I can create one, or skip if it's trivial."
3. If user wants one: draft the body from conversation context, show it, then file with `gh issue create --template <type>.yml` once approved.
4. If user skips: proceed without further prompting.

Trivial edits skip the prompt entirely. "Trivial" means any of: a typo fix, a comment-only change, a formatting/whitespace-only change, a ≤3-line edit to a single file with no behavior change, or a rename that doesn't cross a public boundary. Anything else (multi-file, multi-line, new behavior, test changes, migrations, dependency bumps) is non-trivial and triggers the nudge.

**PR linking.** When a PR is about to be opened:
1. Scan the branch name, commit messages, and recent conversation for an issue number.
2. If found, ensure the PR body includes `Closes #N` (or `Fixes #N` for bugs).
3. If none found, ask once: "No linked issue — want one, or is this standalone?" Don't block on the answer.

**Batch triage.** When the user pastes a list of todos/ideas:
1. Sort into bug / feature / chore / idea based on content.
2. Draft each as an issue (title + body using the relevant template schema).
3. Present the full batch grouped by type for user review.
4. On approval, file all via `gh issue create --template`.
5. Self-assign per user instruction (e.g., "assign me the first 3 bugs").
6. Print the resulting issue numbers.

**Label management.** The skill can apply `help wanted`, `good first issue`, and close/reopen issues on request, using `gh issue edit`.

### Escape hatches

Light-touch was an explicit design choice; the skill respects it:
- User says "skip issue" / "just do it" / "no issue needed" → skill steps aside for that request.
- Trivial changes → skill does not activate.
- If `gh` isn't authenticated, the skill surfaces the error and offers to proceed without an issue rather than blocking.

### Out of scope for this skill

- Blocking any action.
- Filing issues without showing the draft first.
- Managing milestones, projects, priority, or status labels.
- Touching closed issues (reopening is a human decision).
- Cross-repo operations.

## Component: `CONTRIBUTING.md` update

Add a new section — `## How to pick up work` — with roughly this content (~15 lines):

- How to find takeable work: link to the `help wanted` and `good first issue` filters.
- How to signal you're taking it: self-assign via the issue sidebar.
- How to file a new issue: pointer to the three templates and when to use each.
- How to escalate an idea into a feature: add a design doc link once one exists in `docs/superpowers/specs/`.

No other edits to `CONTRIBUTING.md` — the rest is good as-is.

## Data flow

```
User intent → Skill activates → gh CLI → GitHub Issues API
                                      ↓
                           Issue filed with template, labels, optional assignee
                                      ↓
                           PR body references `Closes #N` at open time
                                      ↓
                           Merge closes the issue automatically
```

The skill never holds state. GitHub is the only store.

## Error handling

- **`gh` not authenticated** — skill reports the error, offers to proceed without filing and records a TODO in the response so the user can file manually later.
- **Template validation failure** — skill shows the validation error from `gh`, lets the user edit the draft, retries.
- **Duplicate detection** — before filing, skill runs `gh issue list --search` on the drafted title's key terms; if a plausible match exists, shows it and asks whether to proceed, link instead, or cancel.
- **Network failure** — skill reports the failure; the user can retry or defer.

## Testing

This project ships behavioral changes (a skill and templates), not runtime code. Acceptance is end-to-end:

- Each of the four workflow flows (pre-work, batch triage, trivial-skip, label management) is exercised at least once against real issues on the repo before the project is declared complete.
- Issue templates are validated by filing one of each type via the GitHub web UI.
- `CONTRIBUTING.md` section is reviewed for accuracy against the live labels/filters.

No unit tests for the skill itself — skills are markdown instructions to Claude, not executable code.

## Acceptance criteria

- [ ] `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `chore.yml`, and `config.yml` exist and are valid YAML Issue Forms.
- [ ] GitHub labels `chore` and `idea` exist on the repo.
- [ ] `.claude/skills/issue-tracking/SKILL.md` exists with frontmatter that activates on the triggers listed above.
- [ ] The skill has been exercised end-to-end at least once per flow (pre-work nudge, PR linking, batch triage, trivial-skip).
- [ ] `CONTRIBUTING.md` has a `## How to pick up work` section.
- [ ] No priority/milestone/status labels were added.

## Open questions

None at spec time. Decisions deferred until pain materializes:
- Whether to enable GitHub Discussions for open-ended questions (currently redirected to blank issue).
- Whether `idea` should live as a label on issues or as a Discussions category later.
- Whether to add `CODEOWNERS` for routing — not needed at single-maintainer scale.
