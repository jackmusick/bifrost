# Codebase Review Findings

Issues discovered during the high-level codebase review session. Staged for follow-up.

---

## SDK Fixes Applied

| Issue | Location | Fix Applied |
|-------|----------|-------------|
| `ai.py` knowledge search wrong parameter | `ai.py:125` | Changed `org_id=org_id` → `scope=org_id` |
| Dead code `_internal.py` | `bifrost/_internal.py` | Deleted file |
| `tables.count()` fake `where` parameter | `bifrost/tables.py` | Removed parameter |
| Non-atomic upsert | `cli.py:2484-2545` | Implemented `INSERT ... ON CONFLICT DO UPDATE` |
| Table lookup MultipleResultsFound | `cli.py:2243` | Two-step lookup: org-specific first, then global fallback |

---

## File Upload Fixes Applied

| Issue | Location | Fix Applied |
|-------|----------|-------------|
| Docs showed `sas_uri` instead of `path` | `bifrost-docs/.../creating-forms.mdx` | Fixed docs with correct path format |
| No server-side file type validation | `routers/forms.py` | Added `field_name` param and validation |
| MCP tool missing file field properties | `mcp_server/tools/forms.py` | Added `allowed_types`, `multiple`, `max_size_mb` |

---

## Issues To Address

### HIGH Priority

#### 1. Role Sync is Additive Only (Forms/Apps/Agents → Workflows)
**Location**: `services/workflow_role_service.py`

**Problem**: When forms/apps/agents are updated, roles are synced to referenced workflows but never removed. This leads to over-permissioning over time.

**Example**: Form1 uses WorkflowA. Form1 is updated to use WorkflowB instead. Form1's roles remain on WorkflowA even though Form1 no longer uses it.

**Recommendation**: Track source of role assignments (form_id, app_id, agent_id) and clean up when entity is updated.

---

#### 2. Dual-Write Consistency (Forms to DB + S3)
**Location**: `routers/forms.py:547-554`

**Problem**: Forms are written to PostgreSQL first, then S3. If S3 write fails, DB has the data but S3 doesn't. Current handling logs and continues.

**Recommendation**: Implement async retry queue using existing RabbitMQ infrastructure:
- On S3 failure, queue message to `file-sync-retry`
- Consumer retries with exponential backoff
- Dead letter queue for permanent failures
- Add `sync_status` column to track state

---

#### 3. Cascade Scoping Uses OR Instead of Two-Step Lookup
**Location**: `repositories/org_scoped.py`, `routers/cli.py`, various repositories

**Problem**: `filter_cascade()` uses `WHERE org_id = X OR org_id IS NULL` which returns multiple rows when both org-specific and global entities exist with the same name. This causes `MultipleResultsFound` errors.

**Root Cause**: The pattern is correct for **listing** (return both), but wrong for **get by name** (should prioritize org, fallback to global).

**Fix Applied**:
- Added `get_one_cascade()` method to `OrgScopedRepository` for proper two-step lookup
- Fixed `_find_table_for_sdk()` in `cli.py`

**Remaining Work**: Audit all usages of `filter_cascade() + scalar_one_or_none()` and migrate to `get_one_cascade()`:
- `routers/applications.py` - `get_by_slug()`
- MCP tools (agents, forms) - already use ORDER BY hack
- Any other single-entity lookups with cascade scoping

---

### MEDIUM Priority

#### 4. CSRF Middleware Returns 500 for Anonymous Requests
**Location**: `src/core/csrf.py:115`

**Problem**: Anonymous POST requests get `403: CSRF token missing` but it's thrown as HTTPException that becomes 500 due to middleware exception handling.

**Test affected**: `test_file_uploads.py::TestFileUploadAccessControl::test_anonymous_cannot_generate_upload_url`

**Expected**: 401 or 403
**Actual**: 500

---

#### 4. Execution `success=false` Ambiguity
**Location**: `services/execution/engine.py:364-368`

**Problem**: If a workflow returns `{"success": false}`, it's marked as `COMPLETED_WITH_ERRORS`. This is a magic convention that may conflict with legitimate business logic.

**Recommendation**: Document the convention clearly. Consider explicit API like `raise UserError()` for error cases.

---

### LOW Priority

#### 5. Stuck Execution Cleanup Endpoint is Legacy
**Location**: `routers/executions.py` - `/cleanup/stuck` and `/cleanup/trigger`

**Problem**: These endpoints are legacy - cleanup now runs on schedule via `schedulers/execution_cleanup.py` every 5 minutes.

**Recommendation**: Remove or deprecate the manual cleanup endpoints.

---

#### 6. Form Field Position Gaps
**Location**: `routers/forms.py` form field creation

**Problem**: Field `position` column has no contiguity check. If fields are deleted and re-added, gaps may occur.

**Recommendation**: Add validation or explicit reordering endpoint.

---

## Documentation Created

| File | Purpose |
|------|---------|
| `api/src/services/execution/README.md` | Execution engine architecture |
| `api/src/routers/README.md` | Forms section added |
| `api/src/services/app_builder/README.md` | App Builder architecture and component system |

---

## Test Failures (2026-01-15)

**Test Run Summary**: 149 failures, 2102 passed, 12 skipped, 111 errors

### Failure Categories

| Category | Count | Type | Priority |
|----------|-------|------|----------|
| UnboundLocalError in hooks.py | ~20+ | Code Bug | HIGH |
| CSRF middleware returns 500 | ~10+ | Code Bug | HIGH |
| httpx.ConnectError (flaky networking) | ~50+ | Environment | LOW |
| "Referenced resource not found" 409 errors | ~15+ | Test Data/Setup | MEDIUM |
| Event delivery failures | ~20+ | Code Bug | HIGH |

---

### HIGH Priority: Code Bugs

#### 1. UnboundLocalError in Webhook Event Queueing
**Location**: `api/src/routers/hooks.py:187-190`

**Error**: `UnboundLocalError: cannot access local variable 'event' where it is not associated with a value`

**Root Cause**: On line 180, `source_uuid` is checked and if invalid, it becomes `None`. On line 180-187, `event` is only assigned inside the `if source_uuid:` block. However, on line 189, `if event:` is checked outside that block, causing `UnboundLocalError` when `source_uuid` is `None`.

**Code Pattern**:
```python
if source_uuid:
    event_result = await db.execute(...)
    event = event_result.scalar_one_or_none()  # Only assigned here

if event:  # ERROR: 'event' may not be defined if source_uuid was None
    queued = await processor.queue_event_deliveries(event.id)
```

**Fix**: Initialize `event = None` before the conditional block, or nest the second `if event:` inside the `if source_uuid:` block.

**Tests Affected**: All webhook delivery tests in `test_events.py`

---

#### 2. CSRF Middleware HTTPException Becomes 500
**Location**: `api/src/core/csrf.py:115` + `api/src/main.py` exception handling

**Error**: `starlette.exceptions.HTTPException: 403: CSRF token missing` results in 500 response

**Root Cause**: The CSRF middleware raises `HTTPException` but middleware exceptions are not caught by FastAPI's exception handlers. When the HTTPException propagates up from middleware (not from route handlers), it becomes an unhandled exception and returns 500.

**Tests Affected**:
- `test_admin.py::TestAdminLLMConfig::test_non_admin_cannot_get_llm_config` (expects 403, gets 500)
- `test_admin.py::TestAdminLLMConfig::test_non_admin_cannot_update_llm_config` (expects 403, gets 500)
- `test_file_uploads.py::TestFileUploadAccessControl::test_anonymous_cannot_generate_upload_url`

**Fix**: Either:
1. Return `Response(status_code=403)` directly from middleware instead of raising HTTPException
2. Add middleware-level exception handling for HTTPException

---

### MEDIUM Priority: Test Setup/Data Issues

#### 3. "Referenced resource not found" 409 Conflicts
**Tests Affected**:
- `test_permissions.py::TestRoleBasedFormAccess::*`
- `test_permissions.py::TestAuthenticatedFormAccess::*`
- `test_scope_execution.py::TestComprehensiveSdkScoping::*`
- `test_scope_execution.py::TestExplicitScopeOverride::*`

**Error Pattern**: `409 Conflict: Referenced resource not found`

**Root Cause**: Tests are creating forms or documents that reference workflows or organizations that don't exist (or haven't been created yet). This is a test fixture ordering issue where:
1. Test tries to create a form referencing a workflow_id
2. The referenced workflow doesn't exist
3. Foreign key constraint fails with 409

**Fix**: Review test fixtures to ensure proper dependency ordering. Forms that reference workflows need the workflow created first.

---

#### 4. Organization Not Found in Scope Tests
**Tests Affected**:
- `test_scope_execution.py::TestComprehensiveSdkScoping::test_org_workflow_sees_org1_data_in_all_modules`

**Error**: `Organization with ID 'xxx' not found` (400 Bad Request)

**Root Cause**: Test is trying to set workflow organization to an org that doesn't exist in the test database.

**Fix**: Ensure org fixtures are properly created before workflow assignment.

---

### LOW Priority: Environment/Networking Issues

#### 5. httpx.ConnectError (Name or Service Not Known)
**Tests Affected**: ~50+ tests across multiple files

**Error**: `httpx.ConnectError: [Errno -2] Name or service not known`

**Root Cause**: These are intermittent Docker networking failures where the test container cannot resolve the API hostname. This happens when:
1. API container restarts during tests
2. Docker DNS resolution fails temporarily
3. Network partition between test and API containers

**Recommendation**: These are flaky environment issues, not code bugs. Consider:
- Adding retry logic in test client
- Ensuring API is healthy before running dependent tests
- Using `--reruns` pytest plugin for flaky tests

---

### Test Files Most Affected

| File | Failures | Primary Issue |
|------|----------|---------------|
| `test_events.py` | 30+ | UnboundLocalError in hooks.py |
| `test_permissions.py` | 15+ | Resource not found (fixture order) |
| `test_scope_execution.py` | 10+ | Org not found + fixture issues |
| `test_admin.py` | 5+ | CSRF middleware 500 |
| `test_oauth.py` | 10+ | Connection errors (flaky) |
| `test_apps.py` | 5+ | Connection errors (flaky) |
| `test_users.py` | 5+ | Connection errors (flaky) |

---

### Recommended Fix Order

1. **Fix hooks.py UnboundLocalError** - Single line fix, affects many tests
2. **Fix CSRF middleware exception handling** - Architectural fix needed
3. **Review test fixture ordering** - Test infrastructure improvement
4. **Add test retry logic** - Optional for flaky network tests

---

## Areas Still To Review

- [x] App Builder (complete - component validation via Pydantic discriminated union is solid)
- [x] Form Builder (complete)
- [x] Execution Engine (complete)
- [x] SDK (complete)
- [x] Scoping (complete)
