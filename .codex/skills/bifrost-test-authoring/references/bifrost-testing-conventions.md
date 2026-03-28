# Bifrost Testing Conventions

## Tier Selection

- `api/tests/unit/`: fast tests that isolate business logic and mock external systems.
- `api/tests/e2e/`: tests that require the real DB, API, worker, Redis, RabbitMQ, subprocess execution, or end-to-end registration/discovery behavior.

## Commands

- Run all tests: `./test.sh`
- Run unit tests only: `./test.sh tests/unit/`
- Run one unit file: `./test.sh tests/unit/path/to/test_file.py`
- Run E2E tests only: `./test.sh tests/e2e/`
- Run one E2E file: `./test.sh tests/e2e/path/to/test_file.py`
- Run with coverage: `./test.sh --coverage`

Do not treat raw `pytest` as the canonical validation path. The repo expects `test.sh`.

## Unit Test Patterns To Follow

### Prefer local, explicit inputs

Use `tmp_path` to build file trees and `monkeypatch` or `patch()` to redirect lookups.

Common good pattern:

- Create a temporary workspace under `tmp_path`
- Write only the files needed for the test
- Patch the code under test to look at that workspace
- Assert on behavior

Examples in the repo:

- `api/tests/unit/engine/test_helper_module_reload.py`
- `api/tests/unit/services/test_docs_indexer.py`
- `api/tests/unit/test_manifest.py`

### Keep environment coupling visible

If code loads repo-backed assets such as `integrations/*/integration.yaml` or `workflows/*`, make that dependency explicit in one of these ways:

- Inject the root/path into the function under test
- Patch the lookup path in the test
- Search upward for the needed directory rather than assuming a fixed parent depth
- If the test runner must see repo-root files, mount them in `docker-compose.test.yml`

### Mock external dependencies

For unit tests, mock:

- DB access
- Redis
- RabbitMQ
- HTTP clients
- filesystem scanners outside the specific test scope

Reuse shared fixtures from `api/tests/conftest.py` and local `conftest.py` files when they help. Otherwise keep mocks close to the test.

## E2E Test Patterns To Follow

Choose E2E when the behavior depends on:

- API route wiring
- actual DB queries or migrations
- worker/execution engine behavior across processes
- entity registration/discovery through the platform
- real auth/session/cross-service integration

Do not move a test to E2E just to compensate for a brittle unit-test setup.

## Common Failure Modes

### Brittle repo-root discovery

Bad pattern:

```python
REPO_ROOT = Path(__file__).resolve().parents[4]
```

Why it fails:

- local checkout layout and CI container layout can differ
- the same test may resolve to repo root locally and `/` in CI

Preferred pattern:

```python
def find_repo_root(start: Path) -> Path:
    for parent in start.resolve().parents:
        if (parent / "integrations").is_dir():
            return parent
    raise RuntimeError("Could not locate repo root")
```

### Hidden import-path dependencies

Bad pattern:

- unit test imports `workflows.foo` successfully only because the host checkout is on `PYTHONPATH`

Preferred fixes:

- mount `workflows/` into the test container when that module is a real input
- or build the test around a temporary module tree under `tmp_path`

## Review Checklist

- Is the test in the correct tier?
- Does the test control its own filesystem inputs?
- Does it avoid assuming a fixed checkout or mount layout?
- Are external dependencies mocked in unit tests?
- Are assertions about behavior instead of incidental implementation details?
- Can the test be validated with a narrow `./test.sh ...` target?
