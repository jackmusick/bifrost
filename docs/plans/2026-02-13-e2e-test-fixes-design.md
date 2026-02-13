# E2E Test Fixes Design

**Date:** 2026-02-13
**Branch:** feat/workspace-redesign
**Status:** 2189 unit tests passing, 132 E2E failures (65 failures + 67 errors)

## Problem

The workspace-redesign branch changed how file writes and workflow registration work.
Files are now written to S3 + file_index, but the indexer only enriches existing DB
records — it no longer auto-creates them. A new `POST /api/workflows/register` endpoint
exists for explicit registration, but E2E tests still use the old "write file, poll for
discovery" pattern.

## Categories

### 1. Workflow Not Discovered (~112 tests)

**Root cause:** Tests write a `.py` file and poll `/api/workflows` expecting auto-discovery.
The indexer now only enriches existing records; it doesn't create new ones.

**Fix:** Create a shared `write_and_register()` helper in `tests/e2e/conftest.py`:
- Write file via `PUT /api/files/editor/content`
- Register via `POST /api/workflows/register`
- Return workflow metadata (id, name, type)

Update all affected fixtures to use this helper. No polling needed — register returns
the ID synchronously.

Affected test files:
- test_data_providers.py (5 failures)
- test_db_first_storage.py (3 failures)
- test_duplicate_detection.py (5 failures)
- test_executions.py (4 failures + 17 errors in fixtures)
- test_file_transitions.py (5 failures)
- test_file_uploads.py (1 failure)
- test_files.py (2 failures)
- test_workflows.py (4 failures)
- test_platform_validation.py (3 failures)
- test_deactivation_protection.py (8 failures)
- test_form_*.py (23 errors in fixtures)
- test_events*.py (8 errors in fixtures)
- test_websocket.py (1 error)
- test_mcp_scoped_lookups.py (2 errors)

### 2. Git Sync Push/Pull Failures (14 tests)

**Root cause:** `generate_manifest()` queries ALL active entities from the shared E2E
database and writes split YAML files under `.bifrost/` (apps.yaml, workflows.yaml, etc.).
Preflight validation checks that every path referenced in these manifests exists on disk.
Stale entities from other E2E tests appear in the manifest, referencing files that don't
exist in the git sync test's working directory.

**Fix:** Update the `cleanup_test_data` fixture to aggressively clean the DB *before*
each test class (not just after), removing all workflows/forms/agents/etc. so the
manifest only contains test-specific data. Alternatively, scope `generate_manifest()`
to accept an org_id filter.

### 3. LLM Config (4 tests)

| Test | Root Cause | Fix |
|------|-----------|-----|
| `test_set_custom_provider_config` | API only accepts `"openai"` or `"anthropic"` | Change to `provider: "openai"` + `endpoint` field |
| `test_test_anthropic_connection` | Message format changed to include URL | Assert `"Connected to"` + `"available"` |
| `test_test_openai_connection` | Same message format change | Same flexible assertion |
| `test_test_connection_invalid_key` | API bug: auth error caught by wrong handler | Fix `_test_anthropic()` to re-raise 401/403 |

### 4. Remaining (2 tests)

- `test_preflight_detects_unregistered_functions` — assertion string mismatch
- `test_register_non_python_file_fails` — expects 400, gets 404

## Execution Strategy

Four parallel agents:
1. **Discovery agent** — create helper, update all ~112 affected tests
2. **Git sync agent** — fix cleanup fixture and/or manifest scoping
3. **LLM agent** — fix 4 test assertions + 1 API bug
4. **Misc agent** — fix preflight + register assertions

Single test run after all agents complete to verify.
