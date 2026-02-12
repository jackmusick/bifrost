# Two-Tier Test Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collapse the test suite from three tiers (unit/integration/e2e) to two tiers (unit/e2e), eliminating the `tests/integration/` directory entirely.

**Architecture:** Unit tests mock everything and run without Docker. E2E tests need the Docker stack (DB, Redis, RabbitMQ, and optionally API+worker). The existing two-phase `test.sh` runner maps cleanly: Phase 1 = `tests/unit/`, Phase 2 = `tests/e2e/`.

**Tech Stack:** pytest, SQLAlchemy async, Docker Compose, bash

---

### Task 1: Move engine unit tests to tests/unit/engine/

5 engine test files don't use any Docker infrastructure (no DB, no Redis, no HTTP). They test in-memory objects, decorators, and module loading.

**Files:**
- Move: `api/tests/integration/engine/test_sdk_scoping.py` -> `api/tests/unit/engine/test_sdk_scoping.py`
- Move: `api/tests/integration/engine/test_helper_module_reload.py` -> `api/tests/unit/engine/test_helper_module_reload.py`
- Move: `api/tests/integration/engine/test_workflow_execution.py` -> `api/tests/unit/engine/test_workflow_execution.py`
- Move: `api/tests/integration/engine/test_optional_context.py` -> `api/tests/unit/engine/test_optional_context.py`
- Move: `api/tests/integration/engine/test_workspace_execution.py` -> `api/tests/unit/engine/test_workspace_execution.py`

**Step 1: Create target directory and move files**

```bash
mkdir -p api/tests/unit/engine
touch api/tests/unit/engine/__init__.py
git mv api/tests/integration/engine/test_sdk_scoping.py api/tests/unit/engine/
git mv api/tests/integration/engine/test_helper_module_reload.py api/tests/unit/engine/
git mv api/tests/integration/engine/test_workflow_execution.py api/tests/unit/engine/
git mv api/tests/integration/engine/test_optional_context.py api/tests/unit/engine/
git mv api/tests/integration/engine/test_workspace_execution.py api/tests/unit/engine/
```

**Step 2: Run moved tests to verify they pass without Docker infra**

```bash
./test.sh tests/unit/engine/ -v
```

Expected: All tests pass. These files use only in-memory fixtures (`tmp_path`, mock objects, ContextVar operations).

**Step 3: Commit**

```bash
git add -A api/tests/unit/engine/
git commit -m "refactor: move 5 engine unit tests from integration/ to unit/engine/"
```

---

### Task 2: Move remaining engine tests to tests/e2e/engine/

3 engine test files call `execute()` from the execution engine, which needs Docker infrastructure.

**Files:**
- Move: `api/tests/integration/engine/test_script_logging.py` -> `api/tests/e2e/engine/test_script_logging.py`
- Move: `api/tests/integration/engine/test_list_return_value.py` -> `api/tests/e2e/engine/test_list_return_value.py`
- Move: `api/tests/integration/engine/test_variable_capture_on_error.py` -> `api/tests/e2e/engine/test_variable_capture_on_error.py`

**Step 1: Create target directory and move files**

```bash
mkdir -p api/tests/e2e/engine
touch api/tests/e2e/engine/__init__.py
git mv api/tests/integration/engine/test_script_logging.py api/tests/e2e/engine/
git mv api/tests/integration/engine/test_list_return_value.py api/tests/e2e/engine/
git mv api/tests/integration/engine/test_variable_capture_on_error.py api/tests/e2e/engine/
```

**Step 2: Clean up empty integration/engine/ directory**

```bash
rm api/tests/integration/engine/__init__.py
rmdir api/tests/integration/engine
```

**Step 3: Run moved tests to verify they pass**

```bash
./test.sh tests/e2e/engine/ -v
```

Expected: All 3 tests pass (they run in the e2e phase with Docker infra available).

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move 3 engine integration tests to e2e/engine/"
```

---

### Task 3: Move platform tests to tests/e2e/platform/

12 platform test files use `db_session` for real database access. The target directory `tests/e2e/platform/` does not yet exist.

Note: `test_form_indexer.py` and `test_agent_indexer.py` were already moved here from `unit/services/` in prior work on this branch.

**Files:**
- Move: all files in `api/tests/integration/platform/` -> `api/tests/e2e/platform/`

**Step 1: Create target directory and move files**

```bash
mkdir -p api/tests/e2e/platform
touch api/tests/e2e/platform/__init__.py
git mv api/tests/integration/platform/test_app_portable_refs.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_deactivation_protection.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_git_sync_local.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_large_file_memory.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_sdk_from_workflow.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_storage_integrity.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_virtual_import_integration.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_workers_api.py api/tests/e2e/platform/
git mv api/tests/integration/platform/test_workspace_reindex.py api/tests/e2e/platform/
```

**Step 2: Clean up empty integration/platform/ directory**

The `__pycache__` dir may remain; force-remove it.

```bash
rm -rf api/tests/integration/platform
```

**Step 3: Run moved tests to verify they pass**

```bash
./test.sh tests/e2e/platform/ -v
```

Expected: All platform tests pass (they use `db_session` from root conftest, which is available everywhere).

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move platform integration tests to e2e/platform/"
```

---

### Task 4: Move mcp and root-level integration tests to tests/e2e/

The remaining integration files: 1 mcp test and 3 root-level test files (plus `__init__.py` and `conftest.py`).

**Files:**
- Move: `api/tests/integration/mcp/test_mcp_scoped_lookups.py` -> `api/tests/e2e/mcp/test_mcp_scoped_lookups.py`
- Move: `api/tests/integration/test_datetime_roundtrip.py` -> `api/tests/e2e/test_datetime_roundtrip.py`
- Move: `api/tests/integration/test_metrics.py` -> `api/tests/e2e/test_metrics.py`
- Move: `api/tests/integration/test_pre_migration_backfill.py` -> `api/tests/e2e/test_pre_migration_backfill.py`

**Step 1: Create target directory and move files**

```bash
mkdir -p api/tests/e2e/mcp
touch api/tests/e2e/mcp/__init__.py
git mv api/tests/integration/mcp/test_mcp_scoped_lookups.py api/tests/e2e/mcp/
git mv api/tests/integration/test_datetime_roundtrip.py api/tests/e2e/
git mv api/tests/integration/test_metrics.py api/tests/e2e/
git mv api/tests/integration/test_pre_migration_backfill.py api/tests/e2e/
```

**Step 2: Delete the integration/ directory entirely**

```bash
rm -rf api/tests/integration
git add -A api/tests/integration
```

**Step 3: Run moved tests to verify they pass**

```bash
./test.sh tests/e2e/mcp/ -v
./test.sh tests/e2e/test_datetime_roundtrip.py tests/e2e/test_metrics.py tests/e2e/test_pre_migration_backfill.py -v
```

Expected: All pass.

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move remaining integration tests to e2e/, delete integration/"
```

---

### Task 5: Fix integration_db_session reference

One file (`tests/e2e/api-integration/test_ai_usage.py`) uses `integration_db_session` which was defined in the now-deleted `integration/conftest.py`. Replace with `db_session` (from root conftest).

**Files:**
- Modify: `api/tests/e2e/api-integration/test_ai_usage.py`

**Step 1: Replace all occurrences**

In `api/tests/e2e/api-integration/test_ai_usage.py`, replace every `integration_db_session` with `db_session` (there are ~15 occurrences). This is a simple find-and-replace across the file.

**Step 2: Run the test to verify it passes**

```bash
./test.sh tests/e2e/api-integration/test_ai_usage.py -v
```

Expected: All tests pass. `db_session` is provided by root conftest and available everywhere.

**Step 3: Commit**

```bash
git add api/tests/e2e/api-integration/test_ai_usage.py
git commit -m "refactor: replace integration_db_session with db_session"
```

---

### Task 6: Replace @pytest.mark.integration with @pytest.mark.e2e

All moved files that had `@pytest.mark.integration` should use `@pytest.mark.e2e` instead. Files affected (check each for occurrences):

- `api/tests/e2e/mcp/test_mcp_scoped_lookups.py` (14 occurrences)
- `api/tests/e2e/test_metrics.py` (1)
- `api/tests/e2e/platform/test_agent_indexer.py` (1)
- `api/tests/e2e/platform/test_form_indexer.py` (1)
- `api/tests/e2e/platform/test_virtual_import_integration.py` (3)
- `api/tests/e2e/platform/test_storage_integrity.py` (5)
- `api/tests/e2e/platform/test_git_sync_local.py` (9)
- `api/tests/e2e/platform/test_workspace_reindex.py` (1)
- `api/tests/e2e/platform/test_deactivation_protection.py` (1)
- `api/tests/e2e/platform/test_workers_api.py` (5)
- `api/tests/e2e/api-integration/test_mcp_protocol.py` (2)
- `api/tests/e2e/api-integration/test_mcp_endpoints.py` (21)
- `api/tests/e2e/test_execution_logs_list_endpoint.py` (1)

**Step 1: Bulk replace across all affected files**

```bash
cd api
find tests/e2e -name "*.py" -exec grep -l "pytest.mark.integration" {} \; | \
  xargs sed -i 's/pytest\.mark\.integration/pytest.mark.e2e/g'
```

**Step 2: Verify no remaining references**

```bash
grep -r "pytest.mark.integration" api/tests/
```

Expected: No matches (only `README.md` if anything, which we update in Task 8).

**Step 3: Run the full suite to verify markers work**

```bash
./test.sh tests/unit/ -v
```

Expected: Pass (unit tests don't use these markers). Full e2e verification happens in Task 9.

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: replace @pytest.mark.integration with @pytest.mark.e2e"
```

---

### Task 7: Update pytest configuration and conftest markers

Remove the `integration` marker from pytest.ini and conftest.py since it's no longer used.

**Files:**
- Modify: `api/pytest.ini`
- Modify: `api/tests/conftest.py`

**Step 1: Update pytest.ini**

In `api/pytest.ini`, remove the integration marker line. The markers section should go from:

```ini
markers =
    unit: Unit tests (fast, mocked dependencies)
    integration: Integration tests (real database, message queue)
    e2e: End-to-end tests (full API stack with all services)
    slow: Tests that take >1 second
```

To:

```ini
markers =
    unit: Unit tests (fast, no Docker required)
    e2e: End-to-end tests (Docker stack with database, message queue, and services)
    slow: Tests that take >1 second
```

**Step 2: Update conftest.py marker registration**

In `api/tests/conftest.py`, in the `pytest_configure` function, remove the `integration` marker line. Change:

```python
config.addinivalue_line("markers", "integration: Integration tests (real database, message queue)")
```

Remove that line entirely. Keep the `unit`, `e2e`, and `slow` marker registrations.

**Step 3: Commit**

```bash
git add api/pytest.ini api/tests/conftest.py
git commit -m "refactor: remove integration marker from pytest config"
```

---

### Task 8: Update test.sh and documentation

Update `test.sh` echo messages and `CLAUDE.md` to reflect the two-tier structure.

**Files:**
- Modify: `test.sh`
- Modify: `CLAUDE.md`
- Modify: `api/tests/README.md`

**Step 1: Update test.sh**

In `test.sh`, find the Phase 1 echo message (around line 558):

```bash
echo "Phase 1: Running unit + integration tests..."
```

Change to:

```bash
echo "Phase 1: Running unit tests..."
```

**Step 2: Update CLAUDE.md**

In `CLAUDE.md`, update these references:

1. Line 76: `└── tests/            # Unit and integration tests` -> `└── tests/            # Unit and E2E tests`
2. Line 123: `**Tests**: All work requires unit and integration tests in \`api/tests/\`` -> `**Tests**: All work requires unit and e2e tests in \`api/tests/\``
3. Lines 127-128: Update the example paths from `tests/integration/platform/...` to `tests/e2e/platform/...`
4. Lines 142-145: Update the test commands section:
   - `./test.sh tests/integration/              # Run integration tests` -> `./test.sh tests/e2e/                    # Run E2E tests`
   - `./test.sh tests/integration/platform/test_sdk.py  # Run specific file` -> `./test.sh tests/e2e/platform/test_sdk_from_workflow.py  # Run specific file`
   - Remove or update the `--e2e` line (it's now redundant)

**Step 3: Update tests/README.md**

Replace the content of `api/tests/README.md` to describe the two-tier structure. Key changes:
- Remove all references to "integration" as a separate tier
- Describe unit tests (no Docker) and e2e tests (Docker stack)
- Update example commands
- Update directory structure description

**Step 4: Commit**

```bash
git add test.sh CLAUDE.md api/tests/README.md
git commit -m "docs: update test documentation for two-tier structure"
```

---

### Task 9: Full verification

Run the complete test suite to verify everything works end-to-end.

**Step 1: Run unit tests only**

```bash
./test.sh tests/unit/ -v
```

Expected: ~2066 tests pass (original 2061 + 5 moved engine tests).

**Step 2: Run full default suite (two-phase)**

```bash
./test.sh
```

Expected: Phase 1 runs unit tests only (no `integration/` directory exists). Phase 2 starts API+worker, runs all e2e tests. No hangs, no timeouts.

**Step 3: Verify no integration/ directory remains**

```bash
test ! -d api/tests/integration && echo "PASS: integration/ deleted" || echo "FAIL: integration/ still exists"
```

**Step 4: Verify no stale references**

```bash
grep -r "tests/integration" CLAUDE.md test.sh api/pytest.ini api/tests/conftest.py
```

Expected: No matches.

**Step 5: Final commit if any fixups needed, otherwise done**
