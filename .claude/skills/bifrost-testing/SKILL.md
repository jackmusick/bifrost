---
name: bifrost-testing
description: Run and write tests for Bifrost. Use when writing or running tests; adding or modifying React components, pages, or user-facing features; debugging failing or flaky tests; before declaring UI or backend work complete. Trigger phrases - "write a test", "run tests", "add a component", "ship this feature", "ready to merge", "test is failing", "flaky", "vitest", "pytest", "playwright".
---

# Bifrost Testing

Workflow for running and writing tests in Bifrost. Covers: stack lifecycle, which command to run when, what tests a new change must include, how to handle failing and flaky tests, and when to do a UX review of new UI.

## Hard Rules (Non-Negotiable)

1. **Never leave tests failing.** A red test means work is not done. Fix the test or fix the code under test. Never commit or claim completion with failing tests.

2. **Never skip tests as a shortcut.** No `@pytest.mark.skip`, `pytest.skip()`, `test.skip()`, `test.only()`, `it.skip()`, `xfail`, or commenting a test out to silence it. A skipped test must be either **fixed** or **deleted** — and delete only if the test is genuinely no longer useful (feature removed, behavior moved, truly redundant). "I'll come back to it" is not a valid reason to skip.

3. **Flaky ≠ add retries.** Per the user's memory on flaky tests (`feedback_flaky_tests.md`), E2E flakes are always state pollution from a prior test. Find the dirty state. Do not add retries, do not increase timeouts, do not re-run until green.

4. **No silencing.** If a test is noisy, fix the source or delete the test. Don't filter output, don't swallow the failure.

## Test Authoring Rules (Definition of Done for New Work)

### React components → sibling `*.test.tsx`

Every non-trivial React component has a sibling vitest test in the same directory: `Foo.tsx` → `Foo.test.tsx`.

- Test behavior: validation, state transitions, conditional rendering, event handlers.
- Mock hooks and external modules with `vi.mock()` at module level. Don't render the whole app.
- Use `userEvent.setup()` + `screen.getByRole()` / `getByLabel()`. No `data-testid`.
- Reference patterns: `client/src/components/applications/AppReplacePathDialog.test.tsx`, `client/src/components/workflows/WorkflowSidebar.test.tsx`.
- **Exempt:** pure presentational wrappers (`<Card>`, `<PageHeader>`, static icon components, re-exports).

### User-facing features → happy-path Playwright spec

Every user-facing feature has exactly one Playwright spec in `client/e2e/` covering the primary user journey end-to-end against live services.

- Name: `<feature>.<audience>.spec.ts` where audience is `admin`, `user`, or `unauth`.
- Happy path only. Validation errors, permission-denied paths, edge cases belong in vitest.
- Semantic selectors: `page.getByRole()`, `page.getByLabel()`, `page.getByPlaceholder()`. No `data-testid`.
- Condition-based waits: `waitForURL`, `getByRole().waitFor()`, `Promise.race([...])`. Never `page.waitForTimeout()`.

### Backend → unit and/or e2e tests

Already in `CLAUDE.md`:
- Pure logic → `api/tests/unit/`
- Anything hitting API / DB / queue / S3 → `api/tests/e2e/`

See also `authoring-rules.md` alongside this file for expanded examples.

## Workflow

### 1. Is the stack up?

```bash
./test.sh stack status
```

If `DOWN` → `./test.sh stack up`. Each worktree runs its own isolated stack (Compose project name derives from the worktree path), so two worktrees can have stacks up simultaneously without conflict.

### 2. Which test command?

- Backend logic only → `./test.sh unit` (or `./test.sh tests/unit/test_foo.py -v` for one file)
- Backend with live services → `./test.sh e2e` (or `./test.sh tests/e2e/test_foo.py -v`)
- React component behavior → `./test.sh client unit` (vitest on host, no stack needed)
- Full user flow through UI → `./test.sh client e2e`
- Everything (like CI) → `./test.sh all` (backend) + `./test.sh client unit` + `./test.sh client e2e`

State is auto-reset before every test subcommand. If migrations changed, run `./test.sh stack reset` once — that rebuilds the template DB.

### 3. Before declaring done

Run the broader suite to catch regressions outside your targeted area:

- Backend change → `./test.sh all`
- UI change → `./test.sh client unit && ./test.sh client e2e`

Verify the authoring rules above are satisfied for any new code.

### 4. UX review (conditional, conversation-driven)

**Trigger:** The user is in "I just built a new UI feature, let's write the first Playwright spec and make sure the UX is solid" mode. Signal comes from conversation, not from `git diff`. If unsure, ask once.

**Process:**
1. Write the Playwright spec covering the happy path.
2. `./test.sh client e2e --screenshots <spec-file>`
3. After the spec passes, Read each screenshot under `client/playwright-results/` (or `client/test-results/` — check the Playwright config) and report layout / spacing / contrast / alignment issues.
4. Iterate: tweak the component → rerun → re-review until the user signs off.

**Skip when:** bugfixes, backend changes, routine pre-merge sanity checks. Most runs do not need a UX review.

### 5. Flaky / failing tests

Before anything else, read the user's memory on this: flaky E2E tests are always **state pollution** from a prior test, not resource saturation. Do not add retries or raise timeouts.

Diagnostics:
- Logs per service: `/tmp/bifrost-<project-name>/*.log` (per-worktree).
- JUnit: `/tmp/bifrost/test-results.xml`.
- To isolate a test, run it alone: `./test.sh tests/e2e/path/test_foo.py::TestClass::test_method -v`.

If a test is genuinely broken:
- Fix it, or
- Delete it (and document why in the commit message).

No third option.

## Definition-of-Done Checklist

Before declaring work complete, every box must be checked:

- [ ] New non-trivial React component has a sibling `*.test.tsx`
- [ ] New user-facing feature has a happy-path Playwright spec
- [ ] Backend logic has a unit test; endpoint/workflow changes have an e2e test
- [ ] No new `skip`, `xfail`, `.only`, or commented-out tests introduced
- [ ] Targeted suite green
- [ ] Broader suite green (`./test.sh all` for backend, `./test.sh client e2e` for UI)
- [ ] UX review done if new UI was built

If any box is unchecked, keep working. Do not declare done.

## What This Skill Is Not

Not a coverage-threshold enforcer. Not a pixel-diff tool. Not a lint for pure refactors. It's a workflow guide with hard rules on what matters: red tests, skipped tests, and missing coverage on new code.
