---
name: bifrost-test-authoring
description: Create or update tests that follow Bifrost upstream conventions. Use when adding or fixing tests in this repo, choosing whether coverage belongs in `api/tests/unit/` or `api/tests/e2e/`, selecting fixtures and mocking strategy, avoiding hidden environment or filesystem coupling, and validating new tests with the repo's `test.sh` workflow.
---

# Bifrost Test Authoring

Write tests the same way the upstream repo expects them to be written: fast unit tests in isolation, E2E tests only when real services are required, and no accidental dependence on a specific checkout or container layout.

When local tests have drifted from upstream conventions, align the tests to upstream first. Do not preserve the drift by broadening the local harness unless that surface is genuinely part of the upstream-supported unit-test contract.

## Workflow

1. Classify the test before writing code.
   - Put the test in `api/tests/unit/` when it exercises business logic, parsing, shaping, or wrapper behavior with mocked dependencies.
   - Put the test in `api/tests/e2e/` only when correctness depends on the live API, worker, DB, Redis, RabbitMQ, process execution, or cross-service behavior.

2. Prefer controlled inputs over repo-environment assumptions.
   - Use `tmp_path`, factories, and `monkeypatch` for unit tests.
   - Patch lookup functions or inject paths instead of hard-coding parent-depth path traversal.
   - Avoid tests that only pass because the host checkout happens to expose extra directories or a specific `PYTHONPATH`.

3. Use real checked-in fixtures only when source-backed behavior is the thing under test.
   - If a unit test must load repo files such as `integrations/*/integration.yaml` or `workflows/*`, make the dependency explicit.
   - Resolve repo root by searching for the required directory, not by assuming a fixed number of parents.
   - Prefer synthetic fixtures under `tmp_path` when they cover the behavior just as well.
   - Update the test harness mounts only when the upstream-supported unit-test surface truly includes those repo-root files.

4. Match the repo's test style.
   - Keep assertions focused on behavior, not implementation trivia.
   - Mock external systems in unit tests.
   - Reuse shared fixtures when they fit; otherwise keep fixtures local to the test module.
   - Prefer factory/helper functions over large data fixtures when only a few fields matter.

5. Validate with the repo workflow.
   - Run targeted commands through `./test.sh`, not raw `pytest`, unless you are doing a very narrow local probe and understand the limitation.
   - For unit-only changes, prefer `./test.sh tests/unit/...`.
   - For E2E changes, use `./test.sh tests/e2e/...` or the narrowest relevant target.

## Anti-Patterns

- Do not choose `e2e` just because a unit test needs a file. Most file-driven tests should still be unit tests with controlled inputs.
- Do not use brittle repo-root logic like `Path(__file__).parents[N]` when the test can run in different mount layouts.
- Do not import repo-root modules in a unit test unless the test runner exposes them explicitly.
- Do not add hidden dependencies on Docker-only service hostnames in unit tests.
- Do not assert on broad snapshots when a few behavioral assertions would pin the contract more clearly.

## Reference

Read [references/bifrost-testing-conventions.md](./references/bifrost-testing-conventions.md) when you need the concrete repo conventions, examples, or validation commands.
