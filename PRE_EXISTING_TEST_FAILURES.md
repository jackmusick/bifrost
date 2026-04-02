# Pre-Existing E2E Test Failures

These failures exist on clean `main` (commit `0dd699c3`) before any memory optimization changes. Confirmed by running tests on stashed clean state.

## 1. test_import_bifrost_executions

**File:** `api/tests/e2e/platform/test_sdk_from_workflow.py:88`

**Error:**
```
AssertionError: assert False
  where False = hasattr(<module 'bifrost.executions' from '/app/bifrost/executions.py'>, 'list')
```

**Root cause:** Python submodule name collision. `bifrost/executions.py` defines a class called `executions`. When `bifrost/__init__.py` does `from .executions import executions`, it sets the package attribute to the class. But Python's import system also registers `sys.modules['bifrost.executions']` as the **module**. When pytest later does `from bifrost import executions`, under certain import ordering (when `sys.modules['bifrost.executions']` is already populated), Python returns the module object instead of the class.

**Fix:** Either:
- Rename the class inside `bifrost/executions.py` to something different (e.g., `class Executions:`) and update `__init__.py` to `from .executions import Executions as executions`
- Or add `sys.modules[__name__ + '.executions'] = executions` in `__init__.py` after the import to force sys.modules to point to the class
- This affects `executions` specifically because something in the test suite triggers the submodule import before this test runs. Other modules (organizations, files, forms, roles) don't hit this because their import order is different.

## 2. test_agent_run_steps_persisted

**File:** `api/tests/e2e/platform/test_agent_connection_pressure.py:176`

**Error:**
```
KeyError: 0
  runs[0]["id"]
```

**Root cause:** The preceding test `test_concurrent_agent_runs_succeed` fails with `"LLM provider not configured"` — the test environment doesn't have AI provider credentials configured. Since that test fails, no agent runs are created, so `test_agent_run_steps_persisted` finds an empty `runs` dict and fails with KeyError trying to access `runs[0]`.

**Fix:** Either:
- Skip `test_agent_run_steps_persisted` if the preceding test failed (add a dependency/skip marker)
- Or configure AI provider credentials in the test environment
- Or mock the LLM provider for these tests

## Previously seen failures (intermittent, may not reproduce every run)

- `test_oauth::test_org_user_cannot_access_oauth_admin` — expects 403 but gets 404. OAuth routing may not be registered.
- `test_cli_push_pull::test_incremental_import_skips_unchanged` — second import reports an entity update when it should be a no-op. Idempotency issue in manifest import.
