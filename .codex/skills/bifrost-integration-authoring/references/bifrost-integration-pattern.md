# Bifrost Integration Pattern

## Standard File Layout

1. `modules/{vendor}.py`
   - async `httpx` client
   - auth handling
   - normalized customer/entity helpers
   - `get_client(scope: str | None = None)` when config-backed access is needed

2. `features/{vendor}/workflows/data_providers.py`
   - return sorted `{value, label}` options for org/entity mapping

3. `features/{vendor}/workflows/sync_*.py`
   - list vendor entities
   - match or create Bifrost orgs
   - upsert `IntegrationMapping`

4. `.bifrost/integrations.yaml`
   - integration entry
   - config schema

5. `.bifrost/workflows.yaml`
   - workflow and data provider metadata

6. Tests
   - `api/tests/unit/test_{vendor}_integration.py` or adjacent unit tests
   - add E2E tests only when real platform behavior is required

## Design Guidance

- Keep transport, auth, retries, and normalization in `modules/{vendor}.py`.
- Keep workflows thin and orchestration-focused.
- Return stable, sorted labels in data providers.
- Make sync workflows idempotent.

## Validation Targets

- targeted unit tests through `./test.sh tests/unit/...`
- syntax/import sanity if Docker is unavailable
- any required platform verification through CLI/API, not in-app GitHub sync
