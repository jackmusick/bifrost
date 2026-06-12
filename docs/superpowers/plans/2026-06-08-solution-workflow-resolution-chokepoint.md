# Solution Workflow Resolution Chokepoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a Solution-managed form or agent resolve and run the *install's own* `path::function` workflow (not the bare `_repo/` one), and consolidate install-fact derivation into a single last-DB-grab.

**Architecture:** Two surgical changes at the workflow execution chokepoint. **Fix A**: the `/api/workflows/execute` router derives `solution_scope` from the caller's install — today only `app_id` does this; add `form_id → Form.solution_id` and an explicit `solution_id` request field (for agents / direct callers). The own-first resolver (`WorkflowRepository._resolve_by_path_ref`) is already correct and unchanged. **Fix B**: `get_workflow_for_execution` (the last DB touch before the engine, which has no DB access) enriches the resolved workflow with `can_access_global_repo` in the **same** query via a LEFT JOIN to `Solution`, and the execution consumer drops its redundant second `SolutionRepository.get_by_id` lookup.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic, pytest (`./test.sh`), TypeScript/React client (app-sdk).

**Spec:** `docs/superpowers/specs/2026-06-08-solution-workflow-resolution-chokepoint-design.md`

---

## Background the engineer needs

- **`/api/workflows/execute`** (`api/src/routers/workflows.py:707` `execute_workflow`) is the single chokepoint every UI workflow trigger hits — app SDK (`use-workflow.ts`), form submit (`FormRenderer.tsx`, `ExecuteForms.tsx`), agents. The request model is `WorkflowExecutionRequest` (`api/src/models/contracts/executions.py:110`).
- The request **already has `form_id`** (line 114, used only for execution tracking today) and **`app_id`** (line 115, used to derive `solution_scope`). It does **not** have `solution_id`.
- **`Form.solution_id`** exists directly on the ORM (`api/src/models/orm/forms.py:116`), same as `Application.solution_id`. No join needed — `form_id → Form.solution_id` mirrors `app_id → Application.solution_id`.
- **`WorkflowRepository.resolve(identifier, *, solution_scope=None)`** (`api/src/repositories/workflows.py:86`) already does own-first-then-`_repo/` disambiguation given a `solution_scope`. It is **correct and fully tested** at `api/tests/unit/repositories/test_workflow_pathref_solution_scope.py`. **Do not modify it.**
- **`get_workflow_for_execution(workflow_id, db=None)`** (`api/src/services/execution/service.py:126`) is the last DB read before dispatch. Returns a metadata dict already containing `solution_id` (line 187). The engine subprocess cannot touch the DB — everything it needs must come from this dict.
- **The redundancy** (`api/src/jobs/consumers/workflow_execution.py:570–577`): after calling `get_workflow_for_execution`, the consumer opens a *second* DB session to fetch `SolutionRepository(db).get_by_id(solution_id).global_repo_access`. Fix B folds that into the first grab.
- **Test commands:** `./test.sh stack up` once per worktree, then `./test.sh tests/unit/...::TestName -v` for a single test. Backend e2e tests are marked `@pytest.mark.e2e` and use the `db_session` fixture.

---

## File Structure

| File | Responsibility | Change |
| ---- | -------------- | ------ |
| `api/src/models/contracts/executions.py` | execute request DTO | add `solution_id` field |
| `api/src/routers/workflows.py` | execute chokepoint | derive `solution_scope` from `solution_id` → `form_id` → `app_id` |
| `api/src/services/execution/service.py` | last-DB-grab enrichment | `get_workflow_for_execution` LEFT JOINs `Solution`, returns `can_access_global_repo` |
| `api/src/jobs/consumers/workflow_execution.py` | execution consumer | read enriched field; delete redundant `SolutionRepository` grab |
| `client/src/lib/app-sdk/use-workflow.ts` (+ form renderer) | client callers | send `solution_id` when solution-managed (Task 7) |
| `api/tests/unit/...` / `api/tests/e2e/...` | coverage | new tests per task |

---

## Task 1: Add `solution_id` to the execute request DTO

**Files:**
- Modify: `api/src/models/contracts/executions.py:110-115`
- Test: `api/tests/unit/test_execution_request_contract.py` (create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_execution_request_contract.py`:

```python
"""WorkflowExecutionRequest carries an explicit solution_id install scope."""
from src.models.contracts.executions import WorkflowExecutionRequest


def test_solution_id_defaults_to_none():
    req = WorkflowExecutionRequest(workflow_id="workflows/foo.py::main")
    assert req.solution_id is None


def test_solution_id_accepts_value():
    sid = "11111111-1111-1111-1111-111111111111"
    req = WorkflowExecutionRequest(workflow_id="workflows/foo.py::main", solution_id=sid)
    assert req.solution_id == sid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_execution_request_contract.py -v`
Expected: FAIL — `test_solution_id_accepts_value` errors (`solution_id` is not a field / ignored).

- [ ] **Step 3: Add the field**

In `api/src/models/contracts/executions.py`, immediately after the `app_id` field (line 115), add:

```python
    solution_id: str | None = Field(default=None, description="Optional install id of the calling Solution form/agent. Used to scope a path::function workflow ref to that install (so it resolves the install's own workflow, not a sibling install's or the bare _repo/ one). Takes precedence over form_id/app_id derivation.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_execution_request_contract.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: DTO parity check**

Run: `./test.sh tests/unit/test_dto_flags.py -v`
Expected: PASS. If it fails complaining `solution_id` is missing from CLI/MCP, add `solution_id` to `DTO_EXCLUDES` in `api/bifrost/dto_flags.py` with the comment `# execute-time install scope, not a stored field`.

- [ ] **Step 6: Commit**

```bash
git add api/src/models/contracts/executions.py api/tests/unit/test_execution_request_contract.py
git commit -m "feat(solutions): execute request carries explicit solution_id install scope"
```

---

## Task 2: Extract scope derivation into a testable helper

The current scope derivation is inline in `execute_workflow` and only handles `app_id`. Extract it to a named async helper so it can be unit-tested and extended cleanly.

**Files:**
- Modify: `api/src/routers/workflows.py` (the `solution_scope` block, currently ~755-768)
- Test: `api/tests/unit/test_execute_solution_scope.py` (create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/unit/test_execute_solution_scope.py`:

```python
"""_derive_solution_scope picks the install scope from solution_id > form_id > app_id."""
from uuid import uuid4

import pytest

from src.models.orm.organizations import Organization
from src.models.orm.solutions import Solution
from src.models.orm.applications import Application
from src.models.orm.forms import Form
from src.routers.workflows import _derive_solution_scope


async def _org(db):
    o = Organization(id=uuid4(), name=f"O-{uuid4().hex[:6]}", created_by="test")
    db.add(o); await db.flush(); return o


async def _sol(db, org_id):
    s = Solution(id=uuid4(), slug=f"s-{uuid4().hex[:8]}", name="S", organization_id=org_id)
    db.add(s); await db.flush(); return s


@pytest.mark.e2e
class TestDeriveSolutionScope:
    async def test_explicit_solution_id_wins(self, db_session):
        db = db_session
        sid = uuid4()
        got = await _derive_solution_scope(db, solution_id=str(sid), form_id=None, app_id=None)
        assert got == sid

    async def test_form_id_resolves_to_form_solution_id(self, db_session):
        db = db_session
        org = (await _org(db)).id
        sol = await _sol(db, org)
        form = Form(id=uuid4(), name="f", organization_id=org, solution_id=sol.id, workflow_id="workflows/foo.py::main")
        db.add(form); await db.flush()
        got = await _derive_solution_scope(db, solution_id=None, form_id=str(form.id), app_id=None)
        assert got == sol.id

    async def test_app_id_resolves_to_application_solution_id(self, db_session):
        db = db_session
        org = (await _org(db)).id
        sol = await _sol(db, org)
        app = Application(id=uuid4(), name="a", slug=f"a-{uuid4().hex[:6]}", organization_id=org, solution_id=sol.id)
        db.add(app); await db.flush()
        got = await _derive_solution_scope(db, solution_id=None, form_id=None, app_id=str(app.id))
        assert got == sol.id

    async def test_none_when_no_source(self, db_session):
        got = await _derive_solution_scope(db_session, solution_id=None, form_id=None, app_id=None)
        assert got is None

    async def test_invalid_uuid_yields_none(self, db_session):
        got = await _derive_solution_scope(db_session, solution_id="not-a-uuid", form_id=None, app_id=None)
        assert got is None
```

> Note: `Form`/`Application` constructor kwargs above must match the ORM. If a NOT NULL column is missing, the flush errors — add the column (check `api/src/models/orm/forms.py` / `applications.py`) with a trivial value. Do not change the assertions.

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_execute_solution_scope.py -v`
Expected: FAIL — `ImportError: cannot import name '_derive_solution_scope'`.

- [ ] **Step 3: Implement the helper**

In `api/src/routers/workflows.py`, add this module-level helper (near the other module-level helpers, e.g. above `execute_workflow`). Reuse the existing imports (`UUID`, `select`, `Application`); add `Form` import if not already present:

```python
async def _derive_solution_scope(
    db,
    *,
    solution_id: str | None,
    form_id: str | None,
    app_id: str | None,
) -> "UUID | None":
    """Resolve the calling install's scope for a path::fn workflow ref.

    Precedence: explicit solution_id (a Solution form/agent that knows its
    own install) > form_id (Form.solution_id) > app_id (Application.solution_id).
    A bad/foreign/missing reference yields None → no narrowing (the path ref
    resolves the _repo/ row, or 404s for a scoped caller). Each source is
    client-supplied; the resolver's own org gate (cascade scope) prevents a
    foreign scope from reaching another org's workflow.
    """
    from src.models.orm.forms import Form
    from src.models.orm.applications import Application

    if solution_id:
        try:
            return UUID(solution_id)
        except ValueError:
            return None
    if form_id:
        try:
            form_uuid = UUID(form_id)
        except ValueError:
            return None
        return (
            await db.execute(select(Form.solution_id).where(Form.id == form_uuid))
        ).scalar_one_or_none()
    if app_id:
        try:
            app_uuid = UUID(app_id)
        except ValueError:
            return None
        return (
            await db.execute(
                select(Application.solution_id).where(Application.id == app_uuid)
            )
        ).scalar_one_or_none()
    return None
```

Then **replace** the existing inline `solution_scope` block in `execute_workflow` (currently ~lines 750-768, the comment + `solution_scope: UUID | None = None` + `if request.app_id:` ... assignment) with:

```python
    # A Solution caller's path::fn ref carries no install id (it can't know the
    # per-install uuid5). Derive the install scope from the caller so a path ref
    # resolves to THIS install's own workflow, not a sibling install's that
    # shares the path (Codex #8 P1) nor the bare _repo/ one. solution_id (a
    # form/agent) > form_id > app_id. A bad/foreign ref yields no scope.
    solution_scope = await _derive_solution_scope(
        db,
        solution_id=request.solution_id,
        form_id=request.form_id,
        app_id=request.app_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_execute_solution_scope.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Verify no regression in the existing app-path behavior**

Run: `./test.sh tests/unit/repositories/test_workflow_pathref_solution_scope.py -v`
Expected: PASS (unchanged — resolver untouched).

- [ ] **Step 6: Commit**

```bash
git add api/src/routers/workflows.py api/tests/unit/test_execute_solution_scope.py
git commit -m "feat(solutions): execute derives install scope from solution_id/form_id/app_id"
```

---

## Task 3: End-to-end — a solution form resolves its own workflow at /execute

Prove the whole router path: a `WorkflowExecutionRequest` with `form_id` pointing at a solution-managed form resolves that install's workflow, not the `_repo/` one sharing the path.

**Files:**
- Test: `api/tests/e2e/platform/test_execute_solution_scope_e2e.py` (create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/e2e/platform/test_execute_solution_scope_e2e.py`. This calls the same `_derive_solution_scope` + `WorkflowRepository.resolve` sequence the router runs, end to end against the DB:

```python
"""A solution form's /execute resolves the install's own workflow, not _repo/."""
from uuid import uuid4

import pytest

from src.models.orm.organizations import Organization
from src.models.orm.solutions import Solution
from src.models.orm.forms import Form
from src.models.orm.workflows import Workflow
from src.repositories.workflows import WorkflowRepository
from src.routers.workflows import _derive_solution_scope


async def _org(db):
    o = Organization(id=uuid4(), name=f"O-{uuid4().hex[:6]}", created_by="test")
    db.add(o); await db.flush(); return o


@pytest.mark.e2e
class TestExecuteSolutionScopeE2E:
    async def test_form_resolves_own_install_workflow(self, db_session):
        db = db_session
        org = (await _org(db)).id
        sol = Solution(id=uuid4(), slug=f"s-{uuid4().hex[:8]}", name="S", organization_id=org)
        db.add(sol); await db.flush()

        # A _repo/ workflow and the install's own workflow share the path.
        repo_wf = Workflow(id=uuid4(), name="repo", function_name="main",
                           path="workflows/foo.py", type="workflow", is_active=True,
                           organization_id=None, solution_id=None)
        own_wf = Workflow(id=uuid4(), name="own", function_name="main",
                          path="workflows/foo.py", type="workflow", is_active=True,
                          organization_id=org, solution_id=sol.id)
        db.add_all([repo_wf, own_wf]); await db.flush()

        form = Form(id=uuid4(), name="f", organization_id=org, solution_id=sol.id,
                    workflow_id="workflows/foo.py::main")
        db.add(form); await db.flush()

        # Router sequence: derive scope from form_id, then resolve.
        scope = await _derive_solution_scope(db, solution_id=None, form_id=str(form.id), app_id=None)
        assert scope == sol.id
        repo = WorkflowRepository(db, org_id=org, is_superuser=True)
        got = await repo.resolve("workflows/foo.py::main", solution_scope=scope)
        assert got is not None
        assert got.id == own_wf.id, "form must resolve its install's workflow, not _repo/"

    async def test_non_solution_form_resolves_repo(self, db_session):
        db = db_session
        org = (await _org(db)).id
        repo_wf = Workflow(id=uuid4(), name="repo", function_name="main",
                           path="workflows/bar.py", type="workflow", is_active=True,
                           organization_id=None, solution_id=None)
        db.add(repo_wf); await db.flush()
        form = Form(id=uuid4(), name="f", organization_id=org, solution_id=None,
                    workflow_id="workflows/bar.py::main")
        db.add(form); await db.flush()

        scope = await _derive_solution_scope(db, solution_id=None, form_id=str(form.id), app_id=None)
        assert scope is None
        repo = WorkflowRepository(db, org_id=org, is_superuser=True)
        got = await repo.resolve("workflows/bar.py::main", solution_scope=scope)
        assert got is not None and got.id == repo_wf.id
```

- [ ] **Step 2: Run test to verify it fails (then passes)**

Run: `./test.sh tests/e2e/platform/test_execute_solution_scope_e2e.py -v`
Expected: PASS if Tasks 1-2 landed (this is the integration proof, not a new-code-first test). If `Form`/`Workflow` constructor kwargs are wrong (NOT NULL column), fix the kwargs to match the ORM — do not change assertions.

- [ ] **Step 3: Commit**

```bash
git add api/tests/e2e/platform/test_execute_solution_scope_e2e.py
git commit -m "test(solutions): e2e — solution form /execute resolves install workflow"
```

---

## Task 4: Enrich `get_workflow_for_execution` with `can_access_global_repo` (single query)

The last-DB-grab returns `can_access_global_repo` derived from the resolved workflow's install, in the **same** query via LEFT JOIN — no second round-trip.

**Files:**
- Modify: `api/src/services/execution/service.py:165-190` (the `_fetch` inner function)
- Test: `api/tests/e2e/platform/test_get_workflow_for_execution_global_repo.py` (create)

- [ ] **Step 1: Write the failing test**

Create `api/tests/e2e/platform/test_get_workflow_for_execution_global_repo.py`:

```python
"""get_workflow_for_execution returns the install's global_repo_access as
can_access_global_repo (one DB grab; the engine has no DB access)."""
from uuid import uuid4

import pytest

from src.models.orm.organizations import Organization
from src.models.orm.solutions import Solution
from src.models.orm.workflows import Workflow
from src.services.execution.service import get_workflow_for_execution


async def _org(db):
    o = Organization(id=uuid4(), name=f"O-{uuid4().hex[:6]}", created_by="test")
    db.add(o); await db.flush(); return o


@pytest.mark.e2e
class TestGlobalRepoEnrichment:
    async def test_solution_workflow_carries_flag_true(self, db_session):
        db = db_session
        org = (await _org(db)).id
        sol = Solution(id=uuid4(), slug=f"s-{uuid4().hex[:8]}", name="S",
                       organization_id=org, global_repo_access=True)
        db.add(sol); await db.flush()
        wf = Workflow(id=uuid4(), name="w", function_name="main", path="workflows/w.py",
                      type="workflow", is_active=True, organization_id=org, solution_id=sol.id)
        db.add(wf); await db.flush()

        data = await get_workflow_for_execution(str(wf.id), db=db)
        assert data["solution_id"] == str(sol.id)
        assert data["can_access_global_repo"] is True

    async def test_solution_workflow_carries_flag_false(self, db_session):
        db = db_session
        org = (await _org(db)).id
        sol = Solution(id=uuid4(), slug=f"s-{uuid4().hex[:8]}", name="S",
                       organization_id=org, global_repo_access=False)
        db.add(sol); await db.flush()
        wf = Workflow(id=uuid4(), name="w", function_name="main", path="workflows/w.py",
                      type="workflow", is_active=True, organization_id=org, solution_id=sol.id)
        db.add(wf); await db.flush()

        data = await get_workflow_for_execution(str(wf.id), db=db)
        assert data["can_access_global_repo"] is False

    async def test_repo_workflow_flag_false(self, db_session):
        db = db_session
        wf = Workflow(id=uuid4(), name="w", function_name="main", path="workflows/w.py",
                      type="workflow", is_active=True, organization_id=None, solution_id=None)
        db.add(wf); await db.flush()

        data = await get_workflow_for_execution(str(wf.id), db=db)
        assert data["solution_id"] is None
        assert data["can_access_global_repo"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./test.sh tests/e2e/platform/test_get_workflow_for_execution_global_repo.py -v`
Expected: FAIL — `KeyError: 'can_access_global_repo'`.

- [ ] **Step 3: Implement the enrichment**

In `api/src/services/execution/service.py`, modify the `_fetch` inner function of `get_workflow_for_execution`. Replace the `select(WorkflowORM)...scalar_one_or_none()` block + the return dict so it LEFT JOINs `Solution` and reads its flag in one query:

```python
    async def _fetch(session: AsyncSession) -> dict[str, Any]:
        from src.models.orm.solutions import Solution as SolutionORM

        stmt = (
            select(WorkflowORM, SolutionORM.global_repo_access)
            .outerjoin(SolutionORM, WorkflowORM.solution_id == SolutionORM.id)
            .where(
                WorkflowORM.id == workflow_id,
                WorkflowORM.is_active == True,  # noqa: E712
            )
        )
        result = await session.execute(stmt)
        row = result.one_or_none()

        if row is None:
            raise WorkflowNotFoundError(f"Workflow with ID '{workflow_id}' not found")

        workflow_record, global_repo_access = row
        logger.debug(f"Loaded workflow for execution: {workflow_id} -> {workflow_record.name}")

        return {
            "name": workflow_record.name,
            "function_name": workflow_record.function_name,
            "path": workflow_record.path,
            "timeout_seconds": workflow_record.timeout_seconds if workflow_record.timeout_seconds is not None else 1800,
            "time_saved": workflow_record.time_saved or 0,
            "value": float(workflow_record.value) if workflow_record.value else 0.0,
            "execution_mode": workflow_record.execution_mode or "async",
            "organization_id": str(workflow_record.organization_id) if workflow_record.organization_id else None,
            "solution_id": str(workflow_record.solution_id) if workflow_record.solution_id else None,
            "can_access_global_repo": bool(global_repo_access),
            "type": workflow_record.type or "workflow",
            "cache_ttl_seconds": workflow_record.cache_ttl_seconds or 0,
        }
```

> `bool(global_repo_access)` maps the JOIN's `None` (no solution) → `False`, exactly the spec's "False when not solution-managed."

- [ ] **Step 4: Run test to verify it passes**

Run: `./test.sh tests/e2e/platform/test_get_workflow_for_execution_global_repo.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Fix the existing single-query unit test**

The existing `api/tests/unit/services/execution/test_service.py::TestGetWorkflowForExecution` mocks `scalar_one_or_none` and asserts `call_count == 1`. The query now returns a `(Workflow, bool)` row, so it uses `result.one_or_none()`. Update those mocks: change `mock_wf_result.scalar_one_or_none.return_value = mock_workflow` to `mock_wf_result.one_or_none.return_value = (mock_workflow, True)` (and the `global_repo_access` is now asserted-able). Keep `call_count == 1` — that assertion is the *point* (one grab). Run:

Run: `./test.sh tests/unit/services/execution/test_service.py -v`
Expected: PASS (after mock update). The `call_count == 1` assertion must remain and pass — proving still one DB round-trip.

- [ ] **Step 6: Commit**

```bash
git add api/src/services/execution/service.py api/tests/e2e/platform/test_get_workflow_for_execution_global_repo.py api/tests/unit/services/execution/test_service.py
git commit -m "feat(solutions): get_workflow_for_execution enriches can_access_global_repo in one query"
```

---

## Task 5: Consumer reads the enriched field; delete the redundant grab

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py:566-577`

- [ ] **Step 1: Replace the redundant lookup**

In `api/src/jobs/consumers/workflow_execution.py`, find the block (currently ~566-577):

```python
                    solution_id = workflow_data.get("solution_id")
                    if solution_id:
                        from src.repositories.solutions import SolutionRepository

                        async with get_db_context() as db:
                            solution = await SolutionRepository(db).get_by_id(solution_id)
                        if solution is not None:
                            solution_global_repo_access = solution.global_repo_access
```

Replace it with (reads the fact the last-DB-grab already computed — no second session):

```python
                    solution_id = workflow_data.get("solution_id")
                    # global_repo_access now rides on workflow_data from the same
                    # DB grab as the metadata (get_workflow_for_execution). The
                    # engine subprocess has no DB; this is the last enrichment.
                    solution_global_repo_access = workflow_data.get(
                        "can_access_global_repo", False
                    )
```

- [ ] **Step 2: Verify the redundant import/lookup is fully gone**

Run: `grep -n "SolutionRepository" api/src/jobs/consumers/workflow_execution.py`
Expected: no output (the import was inline in the deleted block; if any other use remains, leave it — but this execution path's grab is gone).

- [ ] **Step 3: Type-check and lint**

Run: `cd api && ruff check src/jobs/consumers/workflow_execution.py && pyright src/jobs/consumers/workflow_execution.py`
Expected: pass (0 errors).

- [ ] **Step 4: Run the solution execution e2e suite**

Run: `./test.sh tests/e2e/platform/test_solution_table_e2e.py -v`
Expected: PASS — exercises a solution workflow execution end to end; confirms the consumer still sets the import root correctly from the new source.

- [ ] **Step 5: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py
git commit -m "refactor(solutions): consumer reads can_access_global_repo from the single grab (drop redundant DB lookup)"
```

---

## Task 6: Verify the `?solution=` SDK path still carries scope (regression guard)

The F2 fix (commit `7a8e7dab`) made a solution *workflow* calling the SDK append `?solution=` so it resolves its own table. That path is independent of Fix A but shares the `solution_id`-rides-context idea. Confirm nothing in Tasks 1-5 regressed it.

**Files:**
- Test: run existing `api/tests/e2e/platform/test_solution_table_e2e.py` (no new code)

- [ ] **Step 1: Run the full solution e2e set**

Run: `./test.sh tests/e2e/platform/test_solution_table_e2e.py tests/unit/test_solution_form_agent_deploy.py tests/unit/repositories/test_workflow_pathref_solution_scope.py -v`
Expected: PASS (all). This is the regression gate before touching the client.

- [ ] **Step 2: No commit** (verification only). If any fail, stop and diagnose before Task 7.

---

## Task 7: Client — solution forms/agents send `solution_id` on /execute

The backend now accepts `solution_id` and derives scope from `form_id`. Two client surfaces need to pass install scope. The app surface already sends `app_id` (`use-workflow.ts:64`); forms must send `form_id` (likely already do for tracking — verify) and solution standalone callers send `solution_id`.

**Files:**
- Inspect/modify: `client/src/lib/app-sdk/use-workflow.ts:55-64`
- Inspect/modify: `client/src/components/forms/FormRenderer.tsx`, `client/src/pages/ExecuteForms.tsx`
- Test: sibling `*.test.ts(x)` per the modified file

- [ ] **Step 1: Inspect what each surface already sends**

Run: `grep -n "app_id\|form_id\|solution_id\|workflows/execute" client/src/lib/app-sdk/use-workflow.ts client/src/components/forms/FormRenderer.tsx client/src/pages/ExecuteForms.tsx`
Expected output tells you which body fields are already present. **Decision:** if a form submit already POSTs `form_id`, the backend (Task 2) already derives scope from it — **no client change needed for forms**. Only add `solution_id` where a caller knows its install but sends neither `form_id` nor `app_id` (the solution standalone/agent case).

- [ ] **Step 2: Add `solution_id` to the body where applicable**

If `use-workflow.ts` (or the solution standalone runner) has the install id in scope, extend the request body. Mirror the existing `app_id` spread at line 64:

```typescript
            ...(appId ? { app_id: appId } : {}),
            ...(solutionId ? { solution_id: solutionId } : {}),
```

Wire `solutionId` from the same prop/context that already provides `appId`. If no surface lacks both `form_id` and `app_id`, **skip the code change** and record in the commit message that forms already carry `form_id`.

- [ ] **Step 3: Write/adjust the vitest sibling**

For the modified `.ts(x)`, add a test asserting the body includes `solution_id` when the install id is present. Example for `use-workflow.ts` (adapt to its existing test harness):

```typescript
it("includes solution_id in the execute body when set", async () => {
  const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  // ... render/run the hook with a solutionId, assert fetchSpy called with a
  // body whose parsed JSON has solution_id === "<the id>"
});
```

- [ ] **Step 4: Run client checks**

Run: `cd client && npm run tsc && npm run lint && cd .. && ./test.sh client unit`
Expected: tsc 0 errors, lint clean, vitest PASS.

- [ ] **Step 5: Commit**

```bash
git add client/
git commit -m "feat(solutions): solution forms/agents send install scope on /execute"
```

---

## Task 8: Full verification sweep

- [ ] **Step 1: Backend type + lint**

Run: `cd api && pyright && ruff check .`
Expected: 0 errors, clean.

- [ ] **Step 2: Regenerate client types (request DTO changed)**

Run (from `client/`, dev stack up — use the worktree URL from `./debug.sh status`): `npm run generate:types`
Then: `npm run tsc`
Expected: `v1.d.ts` gains `solution_id` on the execute request; tsc clean.

- [ ] **Step 3: Backend unit + e2e**

Run: `./test.sh all`
Expected: PASS. Parse `/tmp/bifrost-<project>/test-results.xml` for failures rather than grepping stdout.

- [ ] **Step 4: Commit any type regen**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore: regenerate types for execute solution_id field"
```

- [ ] **Step 5: Update the README gate-2 prose if needed**

The README already states code-gated/data-ungated correctly. Confirm no wording now implies forms/agents were always scoped (they weren't until this change). If the "first stop" prose needs a note that form/agent scope derivation landed here, add one sentence pointing at this plan. Commit if changed.

---

## Self-review notes

- **Spec coverage:** Fix A → Tasks 1-3, 7. Fix B → Tasks 4-5. Regression guards → Tasks 6, 8. The data-fallback open question is explicitly out of scope (spec) — no task, correct.
- **`_resolve_by_path_ref` untouched** — its own-first logic is already tested; the plan only feeds it scope. Verified.
- **One-grab invariant** — Task 4 uses a LEFT JOIN in the *existing* query and Task 5 deletes the second session; Task 4 Step 5 keeps the `call_count == 1` assertion as the guard.
- **Client task is conditional** — Task 7 Step 1 inspects before changing; forms may already send `form_id`, making part of A a pure backend win.
