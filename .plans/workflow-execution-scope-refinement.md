# Workflow Execution Scope Refinement

## Status: In Progress

## Summary

Simplify the execution engine's scope resolution to follow these clear rules:
1. **Explicit scope** - If SDK call passes `scope` parameter, use it (developer intent)
2. **Global workflows** - Use caller's org (caller context matters for multi-tenant logic)
3. **Org-scoped workflows** - Use workflow's org (workflow owns the context)

## Background

The current implementation always uses the caller's org first, with the workflow's org only as a fallback when the caller has no org. This means when a platform admin executes a client's workflow, it runs under the Platform org instead of the client's org.

**Current (incorrect):**
```python
# workflow_execution.py:514-520
workflow_org_id = workflow_data.get("organization_id")
if org_id is None and workflow_org_id:
    org_id = workflow_org_id  # Only fallback when caller has no org
```

**Desired:**
- Org-scoped workflow → always use workflow's org
- Global workflow → always use caller's org

---

## Tasks

### Phase 1: Core Scope Resolution

- [ ] **Modify scope resolution logic in consumer**
  - File: `api/src/jobs/consumers/workflow_execution.py` (lines 514-520)
  - Replace fallback logic with new rule-based resolution
  - Add logging to indicate which scope was chosen and why

- [ ] **Update Redis pending execution with resolved scope**
  - After scope resolution, call `update_pending_execution` with resolved `org_id`
  - This ensures result handlers have correct scope context

### Phase 2: Test Fixtures

- [ ] **Create scoped test resources**
  - Tables: `test_scope_table` in Org A, Org B, and Global
  - Config: `test_scope_config` key in Org A, Org B, and Global
  - Knowledge: `test_scope_namespace` in Org A, Org B, and Global
  - Each with unique data identifying its scope (e.g., `{"scope": "org_a"}`)

- [ ] **Create scope test workflow fixture**
  - Workflow that reads from tables, config, and knowledge
  - Returns what scope's data it found
  - Used by all test cases

### Phase 3: Integration Tests

- [ ] **Create `api/tests/integration/engine/test_sdk_scoping.py`**
  - Test matrix covering all caller/workflow scope combinations
  - Verify SDK operations return data from correct scope

Test Matrix:
| Test Case | Workflow Scope | Caller | Expected SDK Scope |
|-----------|---------------|--------|-------------------|
| Org workflow + org user (same org) | Org A | User in Org A | Org A |
| Org workflow + superuser (different org) | Org A | Superuser in Platform | Org A |
| Org workflow + superuser (no org) | Org A | Superuser, no org | Org A |
| Global workflow + org user | Global | User in Org A | Org A |
| Global workflow + superuser (with org) | Global | Superuser in Org B | Org B |
| Global workflow + superuser (no org) | Global | Superuser, no org | GLOBAL |

### Phase 4: Authorization Verification

- [ ] **Review and expand authorization tests**
  - Verify `test_execution_auth.py` has comprehensive coverage
  - Users can only execute via forms/apps/agents they have access to
  - Add any missing edge cases

### Phase 5: Verification

- [ ] **Run full test suite**
  ```bash
  ./test.sh tests/unit/services/test_execution_auth.py
  ./test.sh tests/integration/engine/
  cd api && pyright
  ```

- [ ] **Manual verification**
  - Create org-scoped workflow for Org A
  - Create table data in Org A and Org B
  - Execute workflow as platform admin
  - Verify SDK operations use Org A data (workflow's org)

---

## Implementation Details

### Consumer Scope Resolution Change

**File:** `api/src/jobs/consumers/workflow_execution.py`

**Location:** After `workflow_data = await get_workflow_for_execution(workflow_id)` (around line 504)

```python
# Get workflow's organization (None for global workflows)
workflow_org_id = workflow_data.get("organization_id")

# Resolve scope based on workflow type:
# - Org-scoped workflows: always use workflow's org (workflow owns context)
# - Global workflows: use caller's org (multi-tenant context)
if workflow_org_id:
    # Org-scoped workflow: always use workflow's org regardless of caller
    org_id = workflow_org_id
    logger.info(
        f"Scope resolved to workflow org: {org_id}",
        extra={"scope_type": "workflow_org", "workflow_id": workflow_id}
    )
else:
    # Global workflow: use caller's org (already set from pending["org_id"])
    logger.info(
        f"Scope resolved to caller org: {org_id or 'GLOBAL'}",
        extra={"scope_type": "caller_org", "workflow_id": workflow_id}
    )
```

### Test Workflow Fixture

```python
@workflow(name="scope_test_workflow")
async def scope_test_workflow(context):
    """Returns scoped data to verify correct scope resolution."""
    from bifrost import tables, config, knowledge

    # Read from each scoped resource (using defaults - no explicit scope)
    table_data = await tables.query("test_scope_table", limit=1)
    config_data = await config.get("test_scope_config")
    knowledge_data = await knowledge.search(
        "test query",
        namespace="test_scope_namespace",
        limit=1
    )

    return {
        "table_scope": table_data[0]["scope"] if table_data else None,
        "config_scope": config_data.get("scope") if config_data else None,
        "knowledge_scope": knowledge_data[0]["scope"] if knowledge_data else None,
        "context_org_id": context.org_id,
        "context_scope": context.scope,
    }
```

---

## Critical Files

| File | Change Type | Purpose |
|------|-------------|---------|
| `api/src/jobs/consumers/workflow_execution.py` | Modify | Core scope resolution (lines 514-520) |
| `api/tests/integration/engine/test_sdk_scoping.py` | Create | SDK scoping integration tests |
| `api/src/routers/cli.py` | No change | SDK scope handling already correct |
| `api/src/services/execution_auth.py` | Verify tests | Authorization coverage |

---

## Notes

- SDK's `_get_cli_org_id` already handles explicit scope overrides correctly (no changes needed)
- Authorization is already enforced by `ExecutionAuthService` before execution
- The engine authenticates as superuser for SDK access - this is intentional and unchanged

---

## Bonus: Engine Cleanup Tasks

### Dead Code Removal

- [ ] **Delete `memory_monitor.py` and its tests**
  - File: `api/src/services/execution/memory_monitor.py` (74 lines)
  - Tests: `api/tests/unit/execution/test_memory_monitor.py`
  - Status: Never imported by any runtime code

### Code Quality

- [ ] **Extract log parsing function in `engine.py`**
  - Lines 332-358 and 399-421 have duplicate log parsing logic
  - Create `_parse_log_line()` helper function
  - Reduces ~30 lines of duplication

### Security: Wire in `import_restrictor` (DEFERRED)

- [ ] **Enable import restrictions in worker startup** *(Separate task)*
  - File: `api/src/services/execution/simple_worker.py`
  - The `import_restrictor.py` was designed to prevent workflows from importing `src/` platform code
  - Currently NOT wired in due to architecture mismatch:
    - `import_restrictor` uses `inspect.stack()` to check caller's `__file__` against workspace paths
    - Virtual imports from Redis set `__file__` to relative paths like `"shared/halopsa.py"`
    - These don't match any filesystem workspace paths
  - **Needs design work** to integrate with the virtual import system
  - Security note: Virtual import isolation provides some protection, but workflows could still attempt `from src.core import ...`
