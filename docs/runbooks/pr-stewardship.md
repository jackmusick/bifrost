# PR Stewardship Runbook

This runbook defines the attended agent lane for keeping Bifrost pull requests moving. GitHub is the source of truth for PR state, CI, reviews, and merge gates. Codex may fix PRs, update branches, answer review feedback, and enable auto-merge when policy allows it, but it does not merge from an unattended laptop job.

## Operating Model

- Use `scripts/pr-steward.ps1` to produce the queue before touching a PR.
- Work one PR at a time from an isolated worktree or a fresh branch from current `main`.
- Treat branch protection, required checks, review decisions, and unresolved review threads as authoritative.
- Leave final policy exceptions to a human: sensitive paths, major dependencies, Docker base images, workflow changes, auth, execution, secrets, migrations, and multi-tenant boundaries.
- Prefer GitHub auto-merge over local merge commands. The agent may enable auto-merge only after checks are green and the PR is in an allowed lane.

## Steward Loop

1. Refresh state:
   ```powershell
   .\scripts\pr-steward.ps1 -Repo jackmusick/bifrost -Limit 20
   ```
2. Pick the first PR with a mechanical next action: behind branch, failing check, stale generated artifact, or unresolved review thread with an obvious code fix.
3. Create or reuse an isolated worktree for that PR. Do not mutate the shared checkout if it has unrelated local changes.
4. Inspect the PR diff, comments, checks, and relevant logs before editing.
5. Make the smallest fix that clears the blocker. If the fix expands scope or touches a sensitive path, stop at a ready-for-review update.
6. Run the narrowest local verification that proves the fix, then push.
7. Post or update a PR summary that includes what changed, what was verified, and anything still requiring human review.
8. Enable auto-merge only when the PR is green, non-draft, policy-eligible, and has no unresolved review threads.

## Policy Lanes

Allowed auto-fix lanes:

- Branch update from `main`.
- CI failures with a clear mechanical fix.
- Review feedback that is local, low-risk, and already agreed in the thread.
- Documentation or test-only fixes that do not change release behavior.

Auto-merge eligible after green checks:

- Dependabot security advisory bumps.
- Non-major, non-Docker Dependabot patch or minor updates.
- Documentation-only PRs with no sensitive path changes.
- Low-risk chores explicitly labeled or approved by a maintainer.

Human approval required:

- Major dependency updates.
- Docker base images or GitHub workflow changes.
- Sensitive paths listed in `CONTRIBUTING.md` and `.claude/skills/reviewing-prs/sensitive-paths.md`.
- Any PR with unclear branch protection, missing checks, unresolved review threads, or external deployment impact.

## Commands

Queue all open PRs:

```powershell
.\scripts\pr-steward.ps1 -Repo jackmusick/bifrost -Limit 20
```

Inspect one PR:

```powershell
.\scripts\pr-steward.ps1 -Repo jackmusick/bifrost -Pr 87
```

Machine-readable queue:

```powershell
.\scripts\pr-steward.ps1 -Repo jackmusick/bifrost -Limit 20 -Json
```

Enable auto-merge only after the runbook says it is eligible:

```powershell
gh pr merge <number> --repo jackmusick/bifrost --auto --squash
```

## Failure Behavior

- If branch protection cannot be read, do not merge. Report the inaccessible gate and continue with fix-only work.
- If a check is flaky, rerun once and record the run URL. If it fails again, treat it as real.
- If a PR is draft, keep it draft until the author or steward explicitly marks it ready after a clean summary.
- If the local checkout is dirty or on another task branch, create an isolated worktree before editing.
- If the steward cannot identify a safe next action, leave a concise status comment instead of improvising.
