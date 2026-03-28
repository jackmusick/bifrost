---
name: bifrost-ci-debugging
description: Diagnose and fix Bifrost CI failures. Use when a GitHub Actions run is failing, when local results disagree with CI, when tests depend on container layout or missing mounts, or when reproducing failures through `test.sh`, workflow logs, and targeted sanity checks.
---

# Bifrost CI Debugging

Treat CI failures as either a real code/test regression or a harness/environment regression. Determine which one it is before editing code.

If the failing behavior comes from local drift away from upstream conventions, prefer restoring the upstream pattern over teaching CI about a fork-local assumption.

## Workflow

1. Identify the exact failing job and step.
   - Inspect `.github/workflows/ci.yml`.
   - Determine the command CI actually runs.

2. Pull the real failure output.
   - Prefer GitHub Actions logs over guessing from annotations.
   - If available, use a GitHub token to fetch the job log directly.

3. Map the failure to the repo workflow.
   - Most backend CI failures route through `./test.sh`.
   - Reproduce with the narrowest matching command.

4. Classify the failure.
   - real code/test regression
   - missing dependency or mount in the test harness
   - brittle path/import assumption
   - environment-only failure that cannot be reproduced locally

5. Fix the right layer.
   - test logic if the assertions are wrong
   - code if behavior regressed
   - CI/test harness if local-only assets are missing from the container
   - prefer removing hidden repo-layout coupling over permanently mounting more of the checkout into unit-test containers
   - avoid masking a harness problem by weakening the test

## Rules

- Do not summarize a failing CI run from annotations alone when logs are accessible.
- Do not move a unit test to E2E just to hide path or import mistakes.
- Do not assume host-local visibility matches the container test runner.
- If Docker is unavailable locally, run at least syntax/import sanity checks and say the reproduction is partial.

## Reference

Read [references/bifrost-ci-debugging-playbook.md](./references/bifrost-ci-debugging-playbook.md) for the concrete playbook and [references/bifrost-ci-failure-patterns.md](./references/bifrost-ci-failure-patterns.md) for common Bifrost-specific failure modes.
