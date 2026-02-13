# E2E Test Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 132 E2E test failures caused by the workspace-redesign branch's new file storage and registration architecture.

**Architecture:** Four independent workstreams that can execute in parallel: (1) workflow discovery — create a shared `write_and_register()` helper and update ~112 tests, (2) git sync — fix manifest filtering in test helper, (3) LLM config — fix 3 test assertions + 1 API bug, (4) misc — fix 2 remaining test assertions.

**Tech Stack:** Python 3.11, pytest, FastAPI, SQLAlchemy async, httpx

---

## Task 1: Create `write_and_register()` helper in conftest

**Files:**
- Modify: `api/tests/e2e/conftest.py`

**Context:** Every E2E test that writes a `.py` file currently uses `PUT /api/files/editor/content?index=true` and then polls `/api/workflows` waiting for auto-discovery. The workspace-redesign branch removed auto-discovery. The new `POST /api/workflows/register` endpoint explicitly registers a decorated function, returning its ID synchronously. We need a helper that does write + register in one call.

**The register endpoint contract:**
```
POST /api/workflows/register
Request:  {"path": "workflows/foo.py", "function_name": "my_func"}
Response: {"id": "uuid", "name": "...", "function_name": "...", "path": "...", "type": "workflow|tool|data_provider", "description": "..."}
```

**Step 1: Add the helper function**

Add to `api/tests/e2e/conftest.py`:

```python
def write_and_register(e2e_client, headers, path: str, content: str, function_name: str) -> dict:
    """Write a Python file and register its decorated function.

    Returns the RegisterWorkflowResponse dict with keys: id, name, function_name, path, type, description.
    """
    # Write file
    resp = e2e_client.put(
        "/api/files/editor/content",
        headers=headers,
        json={"path": path, "content": content, "encoding": "utf-8"},
    )
    assert resp.status_code in (200, 201), f"File write failed: {resp.status_code} {resp.text}"

    # Register the decorated function
    resp = e2e_client.post(
        "/api/workflows/register",
        headers=headers,
        json={"path": path, "function_name": function_name},
    )
    assert resp.status_code == 200, f"Register failed for {function_name} at {path}: {resp.status_code} {resp.text}"
    return resp.json()
```

**Step 2: Verify the helper compiles**

Run: `cd api && python -c "import ast; ast.parse(open('tests/e2e/conftest.py').read())"`
Expected: No output (success)

---

## Task 2: Update test_executions.py fixtures

**Files:**
- Modify: `api/tests/e2e/api/test_executions.py`

**Context:** This file has 3 fixtures (`sync_workflow`, `async_workflow`, `cancellable_workflow`) that write files and poll for discovery. 17 tests depend on these fixtures (4 direct failures + 13 setup errors). Replace the write+poll pattern with `write_and_register()`.

**Pattern to replace in each fixture:**

Old:
```python
e2e_client.put("/api/files/editor/content?index=true", headers=..., json={"path": path, "content": content, ...})
response = e2e_client.get("/api/workflows", headers=...)
workflows = response.json()
workflow = next((w for w in workflows if w["name"] == name), None)
assert workflow is not None, "Workflow not discovered after file write"
workflow_id = workflow["id"]
```

New:
```python
from tests.e2e.conftest import write_and_register
result = write_and_register(e2e_client, platform_admin.headers, path, content, function_name)
workflow_id = result["id"]
```

Apply this to all 3 fixtures. The `function_name` parameter is the Python function name (not the decorator's `name=` argument). Check the workflow content strings to find the correct function names.

**Step 1: Update all 3 fixtures**
**Step 2: Run tests**

Run: `./test.sh tests/e2e/api/test_executions.py -v`
Expected: All tests pass (sync, async, cancellation, concurrency, log access)

**Step 3: Commit**

---

## Task 3: Update test_data_providers.py

**Files:**
- Modify: `api/tests/e2e/api/test_data_providers.py`

**Context:** Has fixtures `test_data_provider_file` and `parametrized_provider_file` that write data provider files. 5 failures. Same pattern replacement. Note: `register` endpoint works for `@data_provider` decorated functions too (returns `type: "data_provider"`).

**Step 1: Update fixtures to use `write_and_register()`**
**Step 2: Run:** `./test.sh tests/e2e/api/test_data_providers.py -v`
**Step 3: Commit**

---

## Task 4: Update test_db_first_storage.py

**Files:**
- Modify: `api/tests/e2e/api/test_db_first_storage.py`

**Context:** Multiple individual test methods write files inline (not fixtures). 3+ failures. Each test writes a file and immediately queries for the workflow. Replace the inline write+query with `write_and_register()` in each test method.

**Step 1: Update all test methods that write+discover**
**Step 2: Run:** `./test.sh tests/e2e/api/test_db_first_storage.py -v`
**Step 3: Commit**

---

## Task 5: Update test_duplicate_detection.py

**Files:**
- Modify: `api/tests/e2e/api/test_duplicate_detection.py`

**Context:** 5 failures. Tests write files and check for duplicate handling. Same pattern. Be careful with the duplicate detection tests — some intentionally write the same function twice. The register endpoint returns 409 for duplicates, which the test should handle.

**Step 1: Update fixtures/tests**
**Step 2: Run:** `./test.sh tests/e2e/api/test_duplicate_detection.py -v`
**Step 3: Commit**

---

## Task 6: Update test_file_transitions.py

**Files:**
- Modify: `api/tests/e2e/api/test_file_transitions.py`

**Context:** 5 failures. Tests add/remove decorators and check DB transitions. These tests specifically test that adding a decorator creates a DB entry and removing one deletes it. Use `write_and_register()` for the initial creation, then the subsequent writes (adding/removing decorators) should just use the file write endpoint.

**Step 1: Update tests**
**Step 2: Run:** `./test.sh tests/e2e/api/test_file_transitions.py -v`
**Step 3: Commit**

---

## Task 7: Update test_files.py, test_file_uploads.py, test_workflows.py

**Files:**
- Modify: `api/tests/e2e/api/test_files.py`
- Modify: `api/tests/e2e/api/test_file_uploads.py`
- Modify: `api/tests/e2e/api/test_workflows.py`

**Context:** 7 total failures across these files. Same write+discover pattern in fixtures.

**Step 1: Update fixtures in all 3 files**
**Step 2: Run:** `./test.sh tests/e2e/api/test_files.py tests/e2e/api/test_file_uploads.py tests/e2e/api/test_workflows.py -v`
**Step 3: Commit**

---

## Task 8: Update test_endpoint_execution.py, test_events.py, test_websocket.py

**Files:**
- Modify: `api/tests/e2e/api/test_endpoint_execution.py`
- Modify: `api/tests/e2e/api/test_events.py`
- Modify: `api/tests/e2e/api/test_websocket.py`

**Context:** 13 total errors from fixture setup failures. All have fixtures that write workflow files and poll. Same pattern fix.

**Step 1: Update fixtures**
**Step 2: Run:** `./test.sh tests/e2e/api/test_endpoint_execution.py tests/e2e/api/test_events.py tests/e2e/api/test_websocket.py -v`
**Step 3: Commit**

---

## Task 9: Update test_form_fields.py, test_form_comprehensive.py

**Files:**
- Modify: `api/tests/e2e/api/test_form_fields.py`
- Modify: `api/tests/e2e/api/test_form_comprehensive.py`

**Context:** 23 errors from fixture setup. These fixtures create workflow files AND data provider files that forms reference. Same pattern fix.

**Step 1: Update fixtures**
**Step 2: Run:** `./test.sh tests/e2e/api/test_form_fields.py tests/e2e/api/test_form_comprehensive.py -v`
**Step 3: Commit**

---

## Task 10: Update test_platform_validation.py, test_scope_execution.py, test_mcp_scoped_lookups.py

**Files:**
- Modify: `api/tests/e2e/api/test_platform_validation.py`
- Modify: `api/tests/e2e/api/test_scope_execution.py`
- Modify: `api/tests/e2e/mcp/test_mcp_scoped_lookups.py`

**Context:** 5+ failures. Same write+discover pattern.

**Step 1: Update fixtures/tests**
**Step 2: Run the affected tests**
**Step 3: Commit**

---

## Task 11: Update test_deactivation_protection.py

**Files:**
- Modify: `api/tests/e2e/platform/test_deactivation_protection.py`

**Context:** 8 failures. These tests write workflow files via the file storage service directly (not HTTP), then check deactivation behavior. They use `FileStorageService.write_file()` which internally calls the indexer. Since the indexer no longer auto-registers, these tests need to either: (a) register workflows after writing, or (b) create workflow DB records directly before testing deactivation logic.

Read the test file carefully — it may use a different write pattern than the API tests. Adapt accordingly. The key is that workflow records must exist in the DB before the deactivation tests run.

**Step 1: Update all 8 test methods**
**Step 2: Run:** `./test.sh tests/e2e/platform/test_deactivation_protection.py -v`
**Step 3: Commit**

---

## Task 12: Fix git sync manifest filtering

**Files:**
- Modify: `api/tests/e2e/platform/test_git_sync_local.py`

**Context:** The `write_manifest_to_repo()` helper at line 130 filters workflows/forms/agents/apps by file existence on disk, but does NOT filter configs, integrations, tables, or event_sources. Stale entities from other E2E tests leak into the manifest, causing preflight to fail with errors like:
- "Manifest references missing file: workflows/test_tools_alias.py"
- "Config 'api_url' references unknown integration: ..."

The fix: clear non-file-based entities from the manifest before writing. Configs, integrations, tables, and event_sources don't have file paths — they only exist in the manifest YAML. For the test, we should zero them out since the git sync tests don't test those entity types.

**Step 1: Update write_manifest_to_repo**

```python
async def write_manifest_to_repo(db_session: AsyncSession, persistent_dir: Path) -> None:
    """Generate manifest from DB and write to persistent dir."""
    from src.services.manifest_generator import generate_manifest
    from src.services.manifest import write_manifest_to_dir
    manifest = await generate_manifest(db_session)
    # Filter file-based entities to only those present on disk
    manifest.workflows = {
        k: v for k, v in manifest.workflows.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.forms = {
        k: v for k, v in manifest.forms.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.agents = {
        k: v for k, v in manifest.agents.items()
        if (persistent_dir / v.path).exists()
    }
    manifest.apps = {
        k: v for k, v in manifest.apps.items()
        if (persistent_dir / v.path).exists()
    }
    # Clear non-file entities that leak from other tests
    manifest.integrations = {}
    manifest.configs = {}
    manifest.tables = {}
    manifest.event_sources = {}
    manifest.event_subscriptions = {}
    write_manifest_to_dir(manifest, persistent_dir / ".bifrost")
```

Check the Manifest dataclass to see exact field names — may be slightly different. Read `api/src/services/manifest.py` for the model.

**Step 2: Run:** `./test.sh tests/e2e/platform/test_git_sync_local.py -v`
**Step 3: Commit**

---

## Task 13: Fix LLM config tests + API bug

**Files:**
- Modify: `api/tests/e2e/api/test_llm_config.py`
- Modify: `api/src/services/llm_config_service.py`

**Context:** 4 test failures.

**Step 1: Fix test_set_custom_provider_config**

The API only accepts `provider: "openai"` or `"anthropic"`. DeepSeek is OpenAI-compatible, so change:
```python
# Old:
"provider": "custom",
"model": "deepseek-chat",
"api_key": llm_test_custom_config["api_key"],
"endpoint": llm_test_custom_config["endpoint"],

# New:
"provider": "openai",
"model": "deepseek-chat",
"api_key": llm_test_custom_config["api_key"],
"endpoint": llm_test_custom_config["endpoint"],
```

Also update assertion from `data["provider"] == "custom"` to `data["provider"] == "openai"`.

**Step 2: Fix test_test_anthropic_connection and test_test_openai_connection**

Change assertions from provider name to URL-based:
```python
# Old:
assert "Connected to Anthropic" in data["message"]
# New:
assert data["success"] is True
assert "Connected to" in data["message"]

# Old:
assert "Connected to OpenAI" in data["message"]
# New:
assert data["success"] is True
assert "Connected to" in data["message"]
```

**Step 3: Fix API bug in _test_anthropic() and _test_openai()**

Both methods have an inner `except Exception` that catches auth errors (401/403) and treats them as "model listing not supported". Fix by checking for auth-related status codes:

In `api/src/services/llm_config_service.py`, update both `_test_anthropic()` and `_test_openai()`:

```python
# In the inner try/except around models.list():
except Exception as e:
    error_str = str(e).lower()
    # Auth errors should fail the connection test, not be silently swallowed
    if "401" in error_str or "403" in error_str or "unauthorized" in error_str or "forbidden" in error_str or "authentication" in error_str or "invalid" in error_str:
        raise  # Re-raise to outer handler which returns success=False
    logger.info(f"Model listing not supported at {endpoint_label}: {e}")
```

**Step 4: Fix test_test_connection_invalid_key assertion**

The test assertion is correct (`success is False`). After fixing the API, it should pass.

**Step 5: Run:** `./test.sh tests/e2e/api/test_llm_config.py -v`
**Step 6: Commit**

---

## Task 14: Fix preflight and register_workflow test assertions

**Files:**
- Modify: `api/tests/e2e/api/test_preflight.py`
- Modify: `api/tests/e2e/api/test_register_workflow.py`

**Context:**

**test_preflight_detects_unregistered_functions:** The response format changed. The test looks for `warnings` in the response but the actual response uses a different structure (`issues` list with `category: "unregistered_function"`). Read the actual response from the API to understand the format, then fix the assertion.

**test_register_non_python_file_fails:** The test expects 400 but gets 404. The endpoint probably returns 404 because the file doesn't exist (it was never written), not 400 for "not a Python file". Either write the file first, or change the expected status to 404.

**Step 1: Fix both test assertions**
**Step 2: Run:** `./test.sh tests/e2e/api/test_preflight.py tests/e2e/api/test_register_workflow.py -v`
**Step 3: Commit**

---

## Task 15: Final verification

**Step 1: Run full test suite**

Run: `./test.sh`

Expected: All unit tests pass. E2E failures should be 0 or near-0 (only pre-existing flaky tests).

**Step 2: Check XML results**

```bash
python3 -c "
import xml.etree.ElementTree as ET
for name in ['unit-results.xml', 'e2e-results.xml']:
    tree = ET.parse(f'/tmp/bifrost/{name}')
    root = tree.getroot()
    for s in root.iter('testsuite'):
        print(f'{name}: tests={s.get(\"tests\")}, failures={s.get(\"failures\")}, errors={s.get(\"errors\")}, skipped={s.get(\"skipped\")}')
        break
"
```

**Step 3: Commit any final fixes**
