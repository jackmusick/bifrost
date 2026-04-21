---
name: issue-tracking
description: Track work on Bifrost via GitHub Issues. Use when the user expresses work intent ("let's build/fix/add X", "work on Y"), pastes a list of todos/notes to triage, is about to open a PR, or asks about existing issues. Light-touch — nudges and helps, never blocks. Trigger phrases - "let's build", "let's fix", "work on", "add a feature", "triage", "todo", "what should I work on", "open a PR", "create an issue", "help wanted".
---

# Issue Tracking

All trackable work on `jackmusick/bifrost` lives in **GitHub Issues**. That includes bugs, features, chores, ideas, and personal todos. There is no parallel tracking system.

This skill helps the user create issues, link PRs to issues, and triage batches of notes — without blocking work.

## Core Principles

1. **Light-touch, never block.** Nudge once, respect the answer. If the user skips, proceed without guilt.
2. **Show drafts before filing.** Never call `gh issue create` without showing the drafted body first.
3. **GitHub conventions only.** Use `assignee`, `help wanted`, `good first issue` — not custom status/priority/milestone labels.
4. **Trivial edits don't need issues.** See the trivial-edit definition below.

## When to Activate

Activate on any of these:

- User expresses work intent: "let's build/add/fix X", "I want to X", "work on X", "implement X"
- User pastes a list of todos, notes, or ideas for triage
- User is about to open a PR (proactively check for issue linkage)
- User asks about existing issues or what to work on next
- User wants to label an issue as `help wanted` or `good first issue`

Do **not** activate for:

- Trivial edits (see below)
- Pure questions about code/architecture with no intent to change anything
- Debugging sessions where the scope isn't yet clear (wait until it is)

## The Trivial-Edit Exception

A change is **trivial** and does not need an issue if it meets any of these:

- Typo fix
- Comment-only change
- Formatting or whitespace-only change
- ≤3-line edit to a single file with no behavior change
- Rename that doesn't cross a public API boundary

Anything else — multi-file, multi-line, new behavior, test changes, migrations, dependency bumps — is **non-trivial** and triggers the nudge.

## Behavior: Pre-Work Nudge

When work intent is detected on a non-trivial change:

1. **Search for existing issues first.**
   ```bash
   gh issue list --search "<2-3 key terms>" --state open --limit 5
   ```
   Also check closed issues if it sounds like something that's come up before.

2. **If a plausible existing issue matches**, surface it and ask: "This looks related to #N — is that the same thing, or a new one?"

3. **If no match, ask once:** "Is there an issue for this? I can create one, or skip if it's trivial."

4. **If user wants one:**
   - Pick the right template (`bug`, `feature`, or `chore`) based on the work description.
   - Draft the body using conversation context — fill every required field from what you already know, ask the user to fill gaps.
   - Show the draft (title + body + labels + assignee).
   - On approval, file via `gh issue create --title "..." --body "..." --label "..."`. (Don't use `--template` — it opens an editor; build the body yourself.)
   - Report the resulting issue number and URL.

5. **If user skips**, proceed without further prompting. Do not re-ask later in the same session.

## Behavior: PR Linking

When a PR is about to be opened:

1. Scan for an issue number in: branch name, commit messages, the current conversation.
2. If found, ensure the PR body includes `Closes #N` (use `Fixes #N` if the linked issue has the `bug` label).
3. If none found, ask once: "No linked issue — want one, or is this standalone?" Accept the answer without follow-up.

## Behavior: Batch Triage

When the user pastes a list of todos, notes, or ideas:

1. **Parse and sort** each item into one of: `bug`, `feature` (→ `enhancement` label), `chore`, or `idea`.
2. **Draft each** as an issue with a good title and a template-shaped body. For `idea` items that are too vague to fit `feature.yml`, use a blank issue with the `idea` label.
3. **Present the batch** grouped by type, e.g.:
   ```
   ## Bugs (3)
   1. [title] — [one-line summary]
   2. ...

   ## Features (2)
   ...

   ## Chores (1)
   ...

   ## Ideas (4)
   ...
   ```
4. **Ask before filing**: "File all of these? Any to drop or edit? Assign yourself to any?"
5. **On approval**, file each via `gh issue create`. Assign as instructed. Print the resulting issue numbers.

## Behavior: Label & Assignment Management

On user request:

- **Mark as takeable:** `gh issue edit N --add-label "help wanted"`
- **Mark as beginner-friendly:** `gh issue edit N --add-label "good first issue"`
- **Self-assign:** `gh issue edit N --add-assignee "@me"`
- **Assign to another contributor:** `gh issue edit N --add-assignee <login>`

Do **not** add priority labels, milestones, or status labels — they aren't part of the taxonomy.

## Escape Hatches

Respect these explicitly:

- User says "skip issue", "just do it", "no issue needed" → step aside for that request.
- `gh` not authenticated → surface the error and offer to proceed without an issue. Don't block the real work.
- User indicates the change is actually trivial after you prompted → drop the nudge immediately.

## The `gh issue create` Pattern

Use this shape for all creations:

```bash
gh issue create \
  --title "[bug]: <summary>" \
  --body "$(cat <<'EOF'
## Summary
...

## Steps to reproduce
...

## Expected behavior
...

## Actual behavior
...

## Environment
...
EOF
)" \
  --label "bug" \
  --assignee "@me"   # only if user asked to self-assign
```

The body should mirror the fields from the relevant template in `.github/ISSUE_TEMPLATE/`. Use `[bug]:`, `[feature]:`, or `[chore]:` title prefixes to match the templates.

## What This Skill Does NOT Do

- Block any action. All nudges are cancellable.
- File issues without showing the draft first.
- Manage milestones, projects, priority, or status labels.
- Touch closed issues (reopening is a human decision).
- Work across repos — this skill is scoped to `jackmusick/bifrost`.
