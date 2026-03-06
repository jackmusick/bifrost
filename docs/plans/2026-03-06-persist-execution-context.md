# Persist Execution Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist the runtime `ExecutionContext` as a JSONB column on the execution record, so the UI can display it directly instead of manually reconstructing it from scattered fields.

**Architecture:** Add a `to_public_dict()` method on `ExecutionContext` that serializes all non-private fields. Persist this dict alongside `variables` when execution completes. Return it in the API response. Simplify the UI sidebar to pass it straight to `VariablesTreeView`.

**Tech Stack:** Python (SQLAlchemy, Alembic, Pydantic), TypeScript (React)

---

### Task 1: Add `to_public_dict()` to ExecutionContext

**Files:**
- Modify: `api/src/sdk/context.py:64-294`
- Test: `api/tests/unit/test_execution_context.py` (create)

**Step 1: Write the failing test**

```python
# api/tests/unit/test_execution_context.py
from src.sdk.context import ExecutionContext, Organization, ROIContext


class TestToPublicDict:

    def test_includes_all_public_fields(self):
        ctx = ExecutionContext(
            user_id="u-123",
            email="jack@test.com",
            name="Jack",
            scope="org-456",
            organization=Organization(id="org-456", name="Acme Corp", is_active=True, is_provider=False),
            is_platform_admin=True,
            is_function_key=False,
            execution_id="exec-789",
            workflow_name="my_workflow",
            is_agent=False,
            public_url="https://bifrost.example.com",
            parameters={"ticket_id": 42},
            startup={"preloaded": True},
            roi=ROIContext(time_saved=15, value=100.0),
        )
        result = ctx.to_public_dict()

        assert result["user_id"] == "u-123"
        assert result["email"] == "jack@test.com"
        assert result["name"] == "Jack"
        assert result["scope"] == "org-456"
        assert result["organization"] == {"id": "org-456", "name": "Acme Corp", "is_active": True, "is_provider": False}
        assert result["is_platform_admin"] is True
        assert result["is_function_key"] is False
        assert result["execution_id"] == "exec-789"
        assert result["workflow_name"] == "my_workflow"
        assert result["is_agent"] is False
        assert result["public_url"] == "https://bifrost.example.com"
        assert result["parameters"] == {"ticket_id": 42}
        assert result["startup"] == {"preloaded": True}
        assert result["roi"] == {"time_saved": 15, "value": 100.0}

    def test_excludes_private_fields(self):
        ctx = ExecutionContext(
            user_id="u-1", email="a@b.com", name="A",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="e-1",
            _config={"secret_key": {"type": "secret", "value": "encrypted"}},
        )
        result = ctx.to_public_dict()
        assert "_config" not in result
        assert "_db" not in result
        assert "_config_resolver" not in result
        assert "_integration_cache" not in result
        assert "_integration_calls" not in result
        assert "_dynamic_secrets" not in result
        assert "_scope_override" not in result

    def test_organization_none_for_global(self):
        ctx = ExecutionContext(
            user_id="u-1", email="a@b.com", name="A",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="e-1",
        )
        result = ctx.to_public_dict()
        assert result["organization"] is None
        assert result["scope"] == "GLOBAL"

    def test_startup_none_when_not_set(self):
        ctx = ExecutionContext(
            user_id="u-1", email="a@b.com", name="A",
            scope="GLOBAL", organization=None,
            is_platform_admin=False, is_function_key=False,
            execution_id="e-1",
        )
        result = ctx.to_public_dict()
        assert result["startup"] is None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_execution_context.py -v`
Expected: FAIL — `AttributeError: 'ExecutionContext' object has no attribute 'to_public_dict'`

**Step 3: Write implementation**

Add to `api/src/sdk/context.py`, inside `ExecutionContext` class, after the `executed_by_name` property (around line 198):

```python
def to_public_dict(self) -> dict[str, Any]:
    """Serialize all non-private fields for persistence/API responses."""
    return {
        "user_id": self.user_id,
        "email": self.email,
        "name": self.name,
        "scope": self.scope,
        "organization": {
            "id": self.organization.id,
            "name": self.organization.name,
            "is_active": self.organization.is_active,
            "is_provider": self.organization.is_provider,
        } if self.organization else None,
        "is_platform_admin": self.is_platform_admin,
        "is_function_key": self.is_function_key,
        "execution_id": self.execution_id,
        "workflow_name": self.workflow_name,
        "is_agent": self.is_agent,
        "public_url": self.public_url,
        "parameters": self.parameters,
        "startup": self.startup,
        "roi": {
            "time_saved": self.roi.time_saved,
            "value": self.roi.value,
        },
    }
```

Also add `Any` to the typing import at line 19 (it's already there).

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_execution_context.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/sdk/context.py api/tests/unit/test_execution_context.py
git commit -m "feat: add to_public_dict() to ExecutionContext"
```

---

### Task 2: Add `execution_context` JSONB column to executions table

**Files:**
- Create: `api/alembic/versions/YYYYMMDD_HHMMSS_add_execution_context_column.py`
- Modify: `api/src/models/orm/executions.py:47` (add column after `variables`)

**Step 1: Add column to ORM model**

In `api/src/models/orm/executions.py`, after line 47 (`variables` column):

```python
execution_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

**Step 2: Create alembic migration**

```bash
cd api && alembic revision -m "add execution_context column"
```

Edit the generated migration:

```python
def upgrade() -> None:
    op.add_column('executions', sa.Column('execution_context', sa.dialects.postgresql.JSONB(), nullable=True))

def downgrade() -> None:
    op.drop_column('executions', 'execution_context')
```

**Step 3: Commit**

```bash
git add api/src/models/orm/executions.py api/alembic/versions/*add_execution_context*
git commit -m "feat: add execution_context JSONB column to executions table"
```

---

### Task 3: Persist context in `ExecutionResult` and through the worker pipeline

**Files:**
- Modify: `api/src/services/execution/engine.py:117-139` (add field to `ExecutionResult`)
- Modify: `api/src/services/execution/engine.py:405-426` (populate on success, ~line 415)
- Modify: `api/src/services/execution/engine.py:495-515` (populate on WorkflowExecutionException, ~line 505)
- Modify: `api/src/services/execution/engine.py:535-555` (populate on general Exception, ~line 545)
- Modify: `api/src/services/execution/engine.py:595-615` (populate on final Exception, ~line 605)
- Modify: `api/src/services/execution/worker.py:272-291` (serialize to dict)
- Modify: `api/src/services/execution/simple_worker.py:442-458` (serialize to dict)

**Step 1: Add `execution_context` to `ExecutionResult` dataclass**

In `api/src/services/execution/engine.py`, after `roi` field (line 131):

```python
execution_context: dict[str, Any] | None = None
```

**Step 2: Populate in all return paths of `execute()`**

In the success path (~line 415), add `execution_context=context.to_public_dict()` to the `ExecutionResult(...)` call.

In all error paths (WorkflowExecutionException, Exception, general), add the same — the context is still available in all `except` blocks since `context` is created before the `try`.

There are 4 `ExecutionResult(...)` calls total in `execute()` plus 1 in cache hit path. For the cache hit path (`_handle_cache_hit`, ~line 1164), set `execution_context=None` (no context for cached results).

**Step 3: Serialize in worker.py**

In `api/src/services/execution/worker.py` around line 280, add to the return dict:

```python
"execution_context": exec_result.execution_context,
```

**Step 4: Serialize in simple_worker.py**

In `api/src/services/execution/simple_worker.py` around line 453, add to the return dict:

```python
"execution_context": result.get("execution_context"),
```

**Step 5: Commit**

```bash
git add api/src/services/execution/engine.py api/src/services/execution/worker.py api/src/services/execution/simple_worker.py
git commit -m "feat: include execution_context in ExecutionResult pipeline"
```

---

### Task 4: Persist to database via `update_execution`

**Files:**
- Modify: `api/src/repositories/executions.py:144-229` (add param to `update_execution`, persist it)
- Modify: `api/src/repositories/executions.py:677-718` (standalone `update_execution` function)
- Modify: `api/src/jobs/consumers/workflow_execution.py:230-243` (pass through from result)

**Step 1: Add `execution_context` param to `ExecutionRepository.update_execution()`**

In `api/src/repositories/executions.py`, add parameter after `variables` (line 153):

```python
execution_context: dict | None = None,
```

And in the method body, after the `variables` block (line 205):

```python
if execution_context is not None:
    update_values["execution_context"] = _make_json_safe(execution_context)
```

**Step 2: Add to standalone `update_execution()` function**

Same parameter added to the standalone function signature (line 685) and passed through to `repo.update_execution()` (line 714).

**Step 3: Pass from consumer**

In `api/src/jobs/consumers/workflow_execution.py`, around line 238, add:

```python
execution_context=result.get("execution_context"),
```

**Step 4: Commit**

```bash
git add api/src/repositories/executions.py api/src/jobs/consumers/workflow_execution.py
git commit -m "feat: persist execution_context to database"
```

---

### Task 5: Return `execution_context` in API responses

**Files:**
- Modify: `api/src/models/contracts/executions.py:70-103` (`WorkflowExecution` model — add field)
- Modify: `api/src/routers/executions.py:243-252` (populate from DB, detail endpoint)
- Modify: `api/src/routers/executions.py:444` (populate from DB, list builder)
- Modify: `api/src/repositories/executions.py:413-435` (populate from DB, repository builder)

**Step 1: Add field to `WorkflowExecution` Pydantic model**

In `api/src/models/contracts/executions.py`, after `ai_totals` (line 103):

```python
# Persisted execution context (admin only)
execution_context: dict[str, Any] | None = None
```

Add `Any` to the typing imports at line 6 (already imported).

**Step 2: Populate in all 3 `WorkflowExecution(...)` construction sites**

In each of the 3 places that build `WorkflowExecution(...)`, add:

```python
execution_context=execution.execution_context if is_admin else None,
```

Gate behind `is_admin` like `variables` is (admin-only field).

The 3 sites:
1. `api/src/repositories/executions.py` — `get_execution_by_id()` (~line 432)
2. `api/src/routers/executions.py` — detail endpoint (~line 252)
3. `api/src/routers/executions.py` — `_build_execution_response()` (~line 444)

**Step 3: Commit**

```bash
git add api/src/models/contracts/executions.py api/src/routers/executions.py api/src/repositories/executions.py
git commit -m "feat: return execution_context in API responses (admin only)"
```

---

### Task 6: Simplify UI ExecutionSidebar

**Files:**
- Modify: `client/src/components/execution/ExecutionSidebar.tsx:44-102` (simplify props)
- Modify: `client/src/components/execution/ExecutionSidebar.tsx:292-310` (use execution_context directly)
- Modify: `client/src/pages/ExecutionDetails.tsx:606-635` (pass execution_context instead of individual props)

**Step 1: Regenerate TypeScript types**

```bash
cd client && npm run generate:types
```

Verify `execution_context` appears in `client/src/lib/v1.d.ts` on the `WorkflowExecution` schema.

**Step 2: Add `execution_context` prop to ExecutionSidebar, remove redundant ones**

In `ExecutionSidebarProps`, replace these individual context-card props:

```typescript
// Remove these:
executedBy?: string | null;
orgId?: string | null;
timeSaved?: number;
value?: number;

// Add this:
executionContext?: Record<string, unknown> | null;
```

Keep `executedByName`, `executedByEmail`, `orgName` — those are still used by the "Workflow Information" card above the context card.

**Step 3: Simplify the Execution Context card**

Replace the manually-assembled data object at lines 294-309:

```tsx
<VariablesTreeView
    data={executionContext as Record<string, unknown>}
/>
```

Add a guard: only show the card if `executionContext` is not null (replaces the current `isPlatformAdmin && isComplete` guard — `executionContext` is only returned for admins anyway, and only populated on complete executions).

**Step 4: Update ExecutionDetails.tsx**

Replace the individual prop passes:

```tsx
// Remove:
executedBy={execution.executed_by}
orgId={execution.org_id}
timeSaved={execution.time_saved}
value={execution.value}

// Add:
executionContext={execution.execution_context}
```

**Step 5: Commit**

```bash
git add client/src/components/execution/ExecutionSidebar.tsx client/src/pages/ExecutionDetails.tsx
git commit -m "feat: simplify ExecutionSidebar to use persisted execution_context"
```

---

### Task 7: Clean up unused `Caller` dataclass

**Files:**
- Modify: `api/src/sdk/context.py:43-48` (remove unused `Caller` dataclass)

The `Caller` dataclass was defined but never used by `ExecutionContext`. Remove it.

```bash
git add api/src/sdk/context.py
git commit -m "chore: remove unused Caller dataclass"
```

---

### Task 8: Verification

**Step 1: Run backend checks**

```bash
cd api && pyright && ruff check .
```

**Step 2: Regenerate types and run frontend checks**

```bash
cd client && npm run generate:types && npm run tsc && npm run lint
```

**Step 3: Run tests**

```bash
./test.sh
```

**Step 4: Manual verification**

1. Run a workflow execution
2. View execution details as platform admin
3. Confirm "Execution Context" card shows the full context object from the DB
4. Confirm non-admin users do NOT see the execution_context field

---

## Key files reference

| File | Role |
|------|------|
| `api/src/sdk/context.py` | `ExecutionContext` dataclass — add `to_public_dict()` |
| `api/src/models/orm/executions.py` | ORM — add `execution_context` JSONB column |
| `api/src/services/execution/engine.py` | Engine — capture context in `ExecutionResult` |
| `api/src/services/execution/worker.py` | Worker — serialize to dict |
| `api/src/services/execution/simple_worker.py` | Simple worker — serialize to dict |
| `api/src/repositories/executions.py` | Repo — persist and read from DB |
| `api/src/jobs/consumers/workflow_execution.py` | Consumer — pass through to `update_execution` |
| `api/src/models/contracts/executions.py` | API response model — add field |
| `api/src/routers/executions.py` | Router — populate from DB record |
| `client/src/components/execution/ExecutionSidebar.tsx` | UI — simplify to use persisted context |
| `client/src/pages/ExecutionDetails.tsx` | UI — pass `execution_context` prop |
