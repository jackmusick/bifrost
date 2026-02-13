# Manifest & Indexer Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move manifest generation from per-CRUD to JIT (sync + maintenance only), make workflow registration explicit, and add on-demand preflight.

**Architecture:** Remove 8 `regenerate_manifest()` callsites from CRUD routers. Add manifest generation as a step inside `desktop_commit()`. Change WorkflowIndexer from create-or-update to enrich-only. Add `POST /api/workflows/register` + MCP tool. Add `POST /api/maintenance/preflight` with unregistered function detection.

**Tech Stack:** Python/FastAPI, SQLAlchemy (async), PostgreSQL, AST parsing, Redis caching

---

### Task 1: Remove `regenerate_manifest()` from Form CRUD

**Files:**
- Modify: `api/src/routers/forms.py:338,534,602`
- Test: `api/tests/e2e/api/test_forms.py` (existing tests should still pass)

**Step 1: Remove the three `regenerate_manifest()` calls**

In `api/src/routers/forms.py`, remove these lines (keep the `writer.write_form(form)` calls — those write the content file to S3, which is correct):

Line 338: `await writer.regenerate_manifest()`
Line 534: `await writer.regenerate_manifest()`
Line 602: `await writer.regenerate_manifest()`

Each callsite looks like:
```python
    writer = RepoSyncWriter(db)
    await writer.write_form(form)
    await writer.regenerate_manifest()  # DELETE THIS LINE
```

**Step 2: Run form E2E tests to verify nothing broke**

Run: `./test.sh tests/e2e/api/test_forms.py -v`
Expected: All existing form tests pass (forms still created/updated/deleted correctly, content files still written to S3)

**Step 3: Commit**

```bash
git add api/src/routers/forms.py
git commit -m "refactor: remove regenerate_manifest() from form CRUD"
```

---

### Task 2: Remove `regenerate_manifest()` from Agent CRUD

**Files:**
- Modify: `api/src/routers/agents.py:422,700,744`

**Step 1: Remove the three `regenerate_manifest()` calls**

Line 422: `await writer.regenerate_manifest()`
Line 700: `await writer.regenerate_manifest()`
Line 744: `await writer.regenerate_manifest()`

Same pattern as forms — keep `writer.write_agent(agent)`, remove `writer.regenerate_manifest()`.

**Step 2: Run agent E2E tests**

Run: `./test.sh tests/e2e/api/test_agents.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add api/src/routers/agents.py
git commit -m "refactor: remove regenerate_manifest() from agent CRUD"
```

---

### Task 3: Remove `regenerate_manifest()` from Workflow Indexing

**Files:**
- Modify: `api/src/services/file_storage/service.py:454-457,503-506`

**Step 1: Remove two `regenerate_manifest()` blocks**

In `_index_python_file_full()` around line 454-457, remove:
```python
        # Regenerate manifest so .bifrost/workflows.yaml reflects the new/updated workflow
        from src.services.repo_sync_writer import RepoSyncWriter
        writer = RepoSyncWriter(self.db)
        await writer.regenerate_manifest()
```

In `_remove_metadata()` around line 503-506, remove:
```python
            # Regenerate manifest so .bifrost/workflows.yaml reflects the deletion
            from src.services.repo_sync_writer import RepoSyncWriter
            writer = RepoSyncWriter(self.db)
            await writer.regenerate_manifest()
```

**Step 2: Run E2E tests**

Run: `./test.sh tests/e2e/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add api/src/services/file_storage/service.py
git commit -m "refactor: remove regenerate_manifest() from workflow indexing"
```

---

### Task 4: Add Manifest Generation to `desktop_commit()`

**Files:**
- Modify: `api/src/services/github_sync.py:279-320`

**Step 1: Write the failing test**

Create `api/tests/unit/services/test_manifest_jit.py`:

```python
"""Tests for JIT manifest generation before git commit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


@pytest.mark.asyncio
async def test_desktop_commit_regenerates_manifest_before_staging():
    """desktop_commit() should regenerate manifest into working tree before git add."""
    from src.services.github_sync import GitHubSyncService

    # Track call order
    call_order = []

    mock_db = AsyncMock()
    service = GitHubSyncService.__new__(GitHubSyncService)
    service.db = mock_db
    service.branch = "main"

    mock_work_dir = MagicMock(spec=Path)
    mock_repo = MagicMock()
    mock_repo.head.is_valid.return_value = True
    mock_repo.index.diff.return_value = [MagicMock()]  # Has changes
    mock_repo.untracked_files = []
    mock_repo.index.commit.return_value = MagicMock(hexsha="abc12345")

    with patch.object(service, 'repo_manager') as mock_rm, \
         patch.object(service, '_open_or_init', return_value=mock_repo), \
         patch.object(service, '_regenerate_manifest_to_dir') as mock_regen, \
         patch.object(service, '_run_preflight') as mock_preflight:

        mock_rm.checkout.return_value.__aenter__ = AsyncMock(return_value=mock_work_dir)
        mock_rm.checkout.return_value.__aexit__ = AsyncMock(return_value=False)

        # Track call order
        async def regen_side_effect(db, work_dir):
            call_order.append("regenerate_manifest")
        mock_regen.side_effect = regen_side_effect

        def add_side_effect(*args, **kwargs):
            call_order.append("git_add")
        mock_repo.git.add.side_effect = add_side_effect

        mock_preflight.return_value = MagicMock(valid=True)

        result = await service.desktop_commit("test commit")

        # Manifest must be regenerated BEFORE git add
        assert call_order == ["regenerate_manifest", "git_add"]
        mock_regen.assert_called_once_with(mock_db, mock_work_dir)
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/test_manifest_jit.py -v`
Expected: FAIL — `_regenerate_manifest_to_dir` doesn't exist yet

**Step 3: Implement `_regenerate_manifest_to_dir()` and hook into `desktop_commit()`**

Add method to `GitHubSyncService`:

```python
    @staticmethod
    async def _regenerate_manifest_to_dir(db: AsyncSession, work_dir: Path) -> None:
        """Generate manifest from DB and write split files to work_dir/.bifrost/."""
        from src.services.manifest import serialize_manifest_dir, MANIFEST_FILES
        from src.services.manifest_generator import generate_manifest

        manifest = await generate_manifest(db)
        files = serialize_manifest_dir(manifest)

        bifrost_dir = work_dir / ".bifrost"
        bifrost_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            (bifrost_dir / filename).write_text(content)

        # Remove files for now-empty entity types
        for filename in MANIFEST_FILES.values():
            path = bifrost_dir / filename
            if filename not in files and path.exists():
                path.unlink()
```

Modify `desktop_commit()` — add manifest regeneration before `repo.git.add(A=True)`:

```python
    async def desktop_commit(self, message: str) -> "CommitResult":
        from src.models.contracts.github import CommitResult
        try:
            async with self.repo_manager.checkout() as work_dir:
                repo = self._open_or_init(work_dir)

                # Regenerate manifest from DB before staging
                await self._regenerate_manifest_to_dir(self.db, work_dir)

                # Stage everything (now includes fresh manifest)
                repo.git.add(A=True)
                # ... rest unchanged
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/test_manifest_jit.py -v`
Expected: PASS

**Step 5: Run git sync E2E tests**

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add api/src/services/github_sync.py api/tests/unit/services/test_manifest_jit.py
git commit -m "feat: JIT manifest generation in desktop_commit()"
```

---

### Task 5: Add Manifest Generation to Maintenance Reimport

**Files:**
- Modify: `api/src/services/github_sync.py:945-965`

**Step 1: Write the failing test**

Add to `api/tests/unit/services/test_manifest_jit.py`:

```python
@pytest.mark.asyncio
async def test_reimport_regenerates_manifest_and_reindexes_workflows():
    """reimport_from_repo() should regenerate manifest and re-run workflow indexer."""
    from src.services.github_sync import GitHubSyncService

    mock_db = AsyncMock()
    service = GitHubSyncService.__new__(GitHubSyncService)
    service.db = mock_db
    service.branch = "main"

    mock_work_dir = MagicMock(spec=Path)

    with patch.object(service, 'repo_manager') as mock_rm, \
         patch.object(service, '_regenerate_manifest_to_dir') as mock_regen, \
         patch.object(service, '_reindex_registered_workflows') as mock_reindex, \
         patch.object(service, '_import_all_entities', return_value=5) as mock_import, \
         patch.object(service, '_delete_removed_entities') as mock_delete, \
         patch.object(service, '_update_file_index') as mock_fi, \
         patch.object(service, '_sync_app_previews') as mock_apps:

        mock_rm.checkout.return_value.__aenter__ = AsyncMock(return_value=mock_work_dir)
        mock_rm.checkout.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested.return_value.__aenter__ = AsyncMock()
        mock_db.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.commit = AsyncMock()

        result = await service.reimport_from_repo()

        mock_regen.assert_called_once()
        mock_reindex.assert_called_once()
        assert result == 5
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/test_manifest_jit.py::test_reimport_regenerates_manifest_and_reindexes_workflows -v`
Expected: FAIL — `_reindex_registered_workflows` doesn't exist

**Step 3: Implement `_reindex_registered_workflows()` and update `reimport_from_repo()`**

Add method to `GitHubSyncService`:

```python
    async def _reindex_registered_workflows(self, work_dir: Path) -> int:
        """Re-run WorkflowIndexer on all registered workflow .py files.

        This catches missed enrichment (type mismatches, stale params, etc.)
        by re-reading each registered workflow's source file and updating DB.
        """
        from src.services.file_storage.indexers.workflow import WorkflowIndexer

        indexer = WorkflowIndexer(self.db)
        result = await self.db.execute(
            select(Workflow.path).where(Workflow.is_active.is_(True)).distinct()
        )
        paths = [row[0] for row in result.all()]
        count = 0

        for py_path in paths:
            full_path = work_dir / py_path
            if full_path.exists():
                content = full_path.read_bytes()
                await indexer.index_python_file(py_path, content)
                count += 1

        logger.info(f"Re-indexed {count} registered workflow files")
        return count
```

Update `reimport_from_repo()`:

```python
    async def reimport_from_repo(self) -> int:
        async with self.repo_manager.checkout() as work_dir:
            # Regenerate manifest from current DB state
            await self._regenerate_manifest_to_dir(self.db, work_dir)

            async with self.db.begin_nested():
                count = await self._import_all_entities(work_dir)
                await self._delete_removed_entities(work_dir)
                await self._update_file_index(work_dir)
            await self.db.commit()

            # Re-run indexers on all registered workflow files (catches missed enrichment)
            await self._reindex_registered_workflows(work_dir)

            await self._sync_app_previews(work_dir)
            logger.info(f"Reimport complete: {count} entities")
            return count
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/test_manifest_jit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/github_sync.py api/tests/unit/services/test_manifest_jit.py
git commit -m "feat: manifest regen + workflow reindex in maintenance reimport"
```

---

### Task 6: Lock `.bifrost/*` in Code Editor

**Files:**
- Modify: `api/src/services/file_storage/file_ops.py`

**Step 1: Write the failing test**

Create `api/tests/unit/services/test_bifrost_lock.py`:

```python
"""Test that .bifrost/ files cannot be written via file_ops."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_write_file_rejects_bifrost_paths():
    """write_file() should reject writes to .bifrost/ paths."""
    from src.services.file_storage.file_ops import FileOps

    mock_db = AsyncMock()
    mock_repo_storage = MagicMock()
    mock_file_index = MagicMock()

    ops = FileOps(mock_db, mock_repo_storage, mock_file_index)

    with pytest.raises(HTTPException) as exc_info:
        await ops.write_file(".bifrost/workflows.yaml", b"content")

    assert exc_info.value.status_code == 403
    assert ".bifrost" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_write_file_rejects_nested_bifrost_paths():
    """write_file() should reject writes to nested .bifrost/ paths."""
    from src.services.file_storage.file_ops import FileOps

    mock_db = AsyncMock()
    mock_repo_storage = MagicMock()
    mock_file_index = MagicMock()

    ops = FileOps(mock_db, mock_repo_storage, mock_file_index)

    with pytest.raises(HTTPException) as exc_info:
        await ops.write_file(".bifrost/forms.yaml", b"content")

    assert exc_info.value.status_code == 403
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/test_bifrost_lock.py -v`
Expected: FAIL — no guard exists yet

**Step 3: Add the guard to `write_file()`**

In `api/src/services/file_storage/file_ops.py`, at the top of `write_file()`, add:

```python
        # .bifrost/ files are generated artifacts, not user-editable
        if path.startswith(".bifrost/") or path == ".bifrost":
            raise HTTPException(
                status_code=403,
                detail=".bifrost/ files are system-generated and cannot be edited directly",
            )
```

Also add the same guard to `delete_file()` if it exists.

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/test_bifrost_lock.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/file_storage/file_ops.py api/tests/unit/services/test_bifrost_lock.py
git commit -m "feat: lock .bifrost/ files from editor writes"
```

---

### Task 7: Change WorkflowIndexer to Enrich-Only

**Files:**
- Modify: `api/src/services/file_storage/indexers/workflow.py:155-178,210-253`

**Step 1: Write the failing test**

Create `api/tests/unit/services/test_workflow_indexer_enrich.py`:

```python
"""Test WorkflowIndexer enrich-only behavior."""

import ast
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


SAMPLE_WORKFLOW = '''
from bifrost import workflow

@workflow(name="My Workflow")
def my_workflow(name: str, count: int = 5):
    """A sample workflow."""
    pass
'''


@pytest.mark.asyncio
async def test_indexer_skips_unregistered_workflow():
    """WorkflowIndexer should NOT create DB records for unregistered functions."""
    from src.services.file_storage.indexers.workflow import WorkflowIndexer

    mock_db = AsyncMock()

    # No existing workflow in DB for this path+function
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    indexer = WorkflowIndexer(mock_db)
    await indexer.index_python_file("workflows/new.py", SAMPLE_WORKFLOW.encode())

    # Should have queried for existing workflow but NOT inserted
    assert mock_db.execute.call_count >= 1
    # Verify no INSERT was issued (only SELECT)
    for call in mock_db.execute.call_args_list:
        stmt = call[0][0]
        stmt_str = str(stmt)
        assert "INSERT" not in stmt_str.upper(), f"Unexpected INSERT: {stmt_str}"


@pytest.mark.asyncio
async def test_indexer_enriches_registered_workflow():
    """WorkflowIndexer should UPDATE existing records with content-derived fields."""
    from src.services.file_storage.indexers.workflow import WorkflowIndexer
    from src.models import Workflow

    mock_db = AsyncMock()
    existing_wf = MagicMock()
    existing_wf.id = uuid4()
    existing_wf.endpoint_enabled = False

    # Return existing workflow on lookup
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_wf
    mock_db.execute.return_value = mock_result

    indexer = WorkflowIndexer(mock_db)
    # Patch refresh_workflow_endpoint to avoid FastAPI dependency
    indexer.refresh_workflow_endpoint = AsyncMock()

    await indexer.index_python_file("workflows/existing.py", SAMPLE_WORKFLOW.encode())

    # Should have issued an UPDATE (not INSERT)
    calls = mock_db.execute.call_args_list
    update_issued = any("UPDATE" in str(call[0][0]).upper() for call in calls)
    assert update_issued, "Expected an UPDATE statement for existing workflow"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/test_workflow_indexer_enrich.py -v`
Expected: FAIL — indexer still does INSERT...ON CONFLICT

**Step 3: Change the indexer to enrich-only**

In `api/src/services/file_storage/indexers/workflow.py`, in the `index_python_file()` method:

Replace the ID resolution + INSERT block (lines ~155-253) for `workflow`/`tool` decorators. The new logic:

```python
                    # Look up existing workflow by path + function_name
                    function_name = node.name
                    stmt = select(Workflow).where(
                        Workflow.path == path,
                        Workflow.function_name == function_name,
                        Workflow.is_active.is_(True),
                    )
                    result = await self.db.execute(stmt)
                    existing_workflow = result.scalar_one_or_none()

                    if not existing_workflow:
                        # Not registered — skip. Use register_workflow() to register.
                        logger.debug(
                            f"Skipping unregistered function {function_name} in {path}"
                        )
                        continue

                    workflow_uuid = existing_workflow.id
```

Then replace the `insert(...).on_conflict_do_update(...)` with a plain UPDATE:

```python
                    # Enrich existing record with content-derived fields
                    stmt = (
                        update(Workflow)
                        .where(Workflow.id == workflow_uuid)
                        .values(
                            name=workflow_name,
                            function_name=function_name,
                            path=path,
                            description=description,
                            category=category,
                            parameters_schema=parameters_schema,
                            tags=tags,
                            endpoint_enabled=endpoint_enabled,
                            allowed_methods=allowed_methods,
                            execution_mode=execution_mode,
                            type=workflow_type,
                            tool_description=tool_description,
                            timeout_seconds=timeout_seconds,
                            time_saved=time_saved,
                            value=value,
                            is_active=True,
                            last_seen_at=now,
                            updated_at=now,
                        )
                        .returning(Workflow)
                    )
                    result = await self.db.execute(stmt)
                    workflow = result.scalar_one()
```

Apply the same pattern for the `data_provider` branch (~line 300+).

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/test_workflow_indexer_enrich.py -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `./test.sh -v`
Expected: Some E2E tests that rely on auto-registration may fail — these will be fixed by Task 8. Note which tests fail.

**Step 6: Commit**

```bash
git add api/src/services/file_storage/indexers/workflow.py api/tests/unit/services/test_workflow_indexer_enrich.py
git commit -m "refactor: change WorkflowIndexer to enrich-only (no auto-create)"
```

---

### Task 8: Add `register_workflow()` API Endpoint

**Files:**
- Modify: `api/src/routers/workflows.py`
- Modify: `api/src/models/contracts/__init__.py` (add request/response models)

**Step 1: Write the failing test**

Create `api/tests/e2e/api/test_register_workflow.py`:

```python
"""E2E tests for workflow registration."""

import pytest


@pytest.mark.e2e
class TestRegisterWorkflow:
    """Test POST /api/workflows/register endpoint."""

    def test_register_workflow_from_existing_file(self, e2e_client, platform_admin):
        """Register a workflow function from an existing .py file."""
        # First, write a .py file (should NOT auto-register)
        file_content = '''
from bifrost import workflow

@workflow(name="Test Registration Workflow")
def test_reg_wf(message: str):
    """A test workflow for registration."""
    return {"message": message}
'''
        # Write file via content API
        write_resp = e2e_client.put(
            "/api/content",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg.py", "content": file_content},
        )
        assert write_resp.status_code in (200, 201), f"Write failed: {write_resp.text}"

        # Verify workflow was NOT auto-registered
        list_resp = e2e_client.get(
            "/api/workflows",
            headers=platform_admin.headers,
            params={"search": "Test Registration Workflow"},
        )
        assert list_resp.status_code == 200
        workflows = list_resp.json()
        auto_registered = [w for w in workflows if w.get("name") == "Test Registration Workflow"]
        assert len(auto_registered) == 0, "Workflow should NOT be auto-registered"

        # Register explicitly
        reg_resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg.py", "function_name": "test_reg_wf"},
        )
        assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
        data = reg_resp.json()
        assert data["name"] == "Test Registration Workflow"
        assert data["function_name"] == "test_reg_wf"
        assert "id" in data

    def test_register_nonexistent_file_fails(self, e2e_client, platform_admin):
        """Registration fails if .py file doesn't exist."""
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/nonexistent.py", "function_name": "foo"},
        )
        assert resp.status_code == 404

    def test_register_nonexistent_function_fails(self, e2e_client, platform_admin):
        """Registration fails if function doesn't exist in file."""
        # Write a file first
        e2e_client.put(
            "/api/content",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg2.py", "content": "x = 1"},
        )
        resp = e2e_client.post(
            "/api/workflows/register",
            headers=platform_admin.headers,
            json={"path": "workflows/test_reg2.py", "function_name": "missing_fn"},
        )
        assert resp.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/e2e/api/test_register_workflow.py -v`
Expected: FAIL — endpoint doesn't exist (404 on POST)

**Step 3: Add request/response models**

In `api/src/models/contracts/__init__.py`, add:

```python
class RegisterWorkflowRequest(BaseModel):
    path: str
    function_name: str

class RegisterWorkflowResponse(BaseModel):
    id: str
    name: str
    function_name: str
    path: str
    type: str
    description: str | None = None
```

**Step 4: Implement the endpoint**

In `api/src/routers/workflows.py`, add:

```python
@router.post(
    "/register",
    response_model=RegisterWorkflowResponse,
    status_code=201,
    summary="Register a workflow function",
    description="Register a decorated function from an existing .py file as a workflow.",
)
async def register_workflow(
    request: RegisterWorkflowRequest,
    db: DbSession,
    user: CurrentSuperuser,
) -> RegisterWorkflowResponse:
    """Register a workflow function from an existing Python file."""
    import ast
    from uuid import uuid4
    from src.services.file_storage import FileStorageService
    from src.services.file_storage.indexers.workflow import WorkflowIndexer

    service = FileStorageService(db)

    # 1. Verify file exists
    try:
        content = await service.read_file(request.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not request.path.endswith(".py"):
        raise HTTPException(status_code=400, detail="Path must be a .py file")

    # 2. AST parse and find the function with a decorator
    content_str = content.decode("utf-8", errors="replace")
    try:
        tree = ast.parse(content_str, filename=request.path)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error: {e}")

    # Find the target function
    target_node = None
    target_decorator_type = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != request.function_name:
            continue
        # Check for @workflow, @tool, or @data_provider decorator
        for dec in node.decorator_list:
            dec_name = None
            if isinstance(dec, ast.Name):
                dec_name = dec.id
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                dec_name = dec.func.id
            if dec_name in ("workflow", "tool", "data_provider"):
                target_node = node
                target_decorator_type = dec_name
                break
        if target_node:
            break

    if not target_node:
        raise HTTPException(
            status_code=404,
            detail=f"No decorated function '{request.function_name}' found in {request.path}",
        )

    # 3. Check if already registered
    existing = await db.execute(
        select(WorkflowORM).where(
            WorkflowORM.path == request.path,
            WorkflowORM.function_name == request.function_name,
            WorkflowORM.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Workflow already registered")

    # 4. Create minimal DB record
    workflow_id = uuid4()
    wf_type = "data_provider" if target_decorator_type == "data_provider" else (
        "tool" if target_decorator_type == "tool" else "workflow"
    )
    new_wf = WorkflowORM(
        id=workflow_id,
        name=request.function_name,  # Placeholder, indexer will update
        function_name=request.function_name,
        path=request.path,
        type=wf_type,
        is_active=True,
    )
    db.add(new_wf)
    await db.flush()

    # 5. Run indexer to enrich with content-derived fields
    indexer = WorkflowIndexer(db)
    await indexer.index_python_file(request.path, content)

    # 6. Re-fetch enriched record
    result = await db.execute(
        select(WorkflowORM).where(WorkflowORM.id == workflow_id)
    )
    workflow = result.scalar_one()

    return RegisterWorkflowResponse(
        id=str(workflow.id),
        name=workflow.name,
        function_name=workflow.function_name,
        path=workflow.path,
        type=workflow.type,
        description=workflow.description,
    )
```

**Step 5: Run test to verify it passes**

Run: `./test.sh tests/e2e/api/test_register_workflow.py -v`
Expected: PASS

**Step 6: Fix any E2E tests broken by enrich-only change**

Run: `./test.sh -v`

Tests that relied on auto-registration (writing a .py file and expecting it to appear as a workflow) need to be updated to call `register_workflow()` first. Likely candidates:
- `tests/e2e/platform/test_sdk_from_workflow.py`
- Any test that writes a .py file and immediately queries for the workflow

For each broken test: add a `register_workflow` call after writing the file.

**Step 7: Commit**

```bash
git add api/src/routers/workflows.py api/src/models/contracts/__init__.py api/tests/e2e/api/test_register_workflow.py
git commit -m "feat: add POST /api/workflows/register endpoint"
```

---

### Task 9: Add `register_workflow` MCP Tool

**Files:**
- Modify: `api/src/services/mcp_server/tools/workflow.py`

**Step 1: Write the failing test**

Add to `api/tests/unit/services/test_mcp_tools.py`:

```python
@pytest.mark.asyncio
async def test_register_workflow_tool():
    """register_workflow MCP tool creates a workflow from an existing file."""
    from src.services.mcp_server.tools.workflow import register_workflow

    mock_context = MagicMock()
    mock_context.org_id = None
    mock_context.user_id = None
    mock_context.is_platform_admin = True

    # This will fail because the tool doesn't exist yet
    result = await register_workflow(mock_context, "workflows/test.py", "my_function")
    assert result is not None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/services/test_mcp_tools.py::test_register_workflow_tool -v`
Expected: FAIL — `register_workflow` doesn't exist in module

**Step 3: Implement the MCP tool**

In `api/src/services/mcp_server/tools/workflow.py`, add:

```python
async def register_workflow(context: Any, path: str, function_name: str) -> ToolResult:
    """Register a decorated Python function as a workflow.

    Takes a file path and function name, validates the function has a
    @workflow/@tool/@data_provider decorator, and registers it in the system.
    """
    import ast
    from uuid import uuid4

    from src.core.database import get_db_context
    from src.models import Workflow as WorkflowORM
    from src.services.file_storage import FileStorageService
    from src.services.file_storage.indexers.workflow import WorkflowIndexer
    from sqlalchemy import select

    if not path:
        return error_result("path is required")
    if not function_name:
        return error_result("function_name is required")
    if not path.endswith(".py"):
        return error_result("path must be a .py file")

    try:
        async with get_db_context() as db:
            service = FileStorageService(db)

            # Read file
            try:
                content = await service.read_file(path)
            except FileNotFoundError:
                return error_result(f"File not found: {path}")

            # AST parse and find decorated function
            content_str = content.decode("utf-8", errors="replace")
            try:
                tree = ast.parse(content_str, filename=path)
            except SyntaxError as e:
                return error_result(f"Syntax error in {path}: {e}")

            found = False
            decorator_type = None
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != function_name:
                    continue
                for dec in node.decorator_list:
                    dec_name = None
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                        dec_name = dec.func.id
                    if dec_name in ("workflow", "tool", "data_provider"):
                        found = True
                        decorator_type = dec_name
                        break
                if found:
                    break

            if not found:
                return error_result(
                    f"No @workflow/@tool/@data_provider decorated function '{function_name}' found in {path}"
                )

            # Check already registered
            existing = await db.execute(
                select(WorkflowORM).where(
                    WorkflowORM.path == path,
                    WorkflowORM.function_name == function_name,
                    WorkflowORM.is_active.is_(True),
                )
            )
            if existing.scalar_one_or_none():
                return error_result(f"Workflow '{function_name}' in {path} is already registered")

            # Create record
            wf_type = "data_provider" if decorator_type == "data_provider" else (
                "tool" if decorator_type == "tool" else "workflow"
            )
            workflow_id = uuid4()
            new_wf = WorkflowORM(
                id=workflow_id,
                name=function_name,
                function_name=function_name,
                path=path,
                type=wf_type,
                is_active=True,
            )
            db.add(new_wf)
            await db.flush()

            # Enrich
            indexer = WorkflowIndexer(db)
            await indexer.index_python_file(path, content)

            # Re-fetch
            result = await db.execute(
                select(WorkflowORM).where(WorkflowORM.id == workflow_id)
            )
            workflow = result.scalar_one()

            return success_result(
                f"Registered {wf_type} '{workflow.name}' from {path}::{function_name}",
                {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "function_name": workflow.function_name,
                    "path": workflow.path,
                    "type": workflow.type,
                },
            )
    except Exception as e:
        logger.error(f"register_workflow failed: {e}", exc_info=True)
        return error_result(str(e))
```

Don't forget to register this tool in the MCP server's tool list (check `api/src/services/mcp_server/tool_access.py` for how tools are registered).

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/services/test_mcp_tools.py::test_register_workflow_tool -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/workflow.py api/tests/unit/services/test_mcp_tools.py
git commit -m "feat: add register_workflow MCP tool"
```

---

### Task 10: Add On-Demand Preflight Endpoint

**Files:**
- Modify: `api/src/routers/maintenance.py`
- Modify: `api/src/models/contracts/maintenance.py`

**Step 1: Write the failing test**

Create `api/tests/e2e/api/test_preflight.py`:

```python
"""E2E tests for on-demand preflight validation."""

import pytest


@pytest.mark.e2e
class TestPreflight:
    """Test POST /api/maintenance/preflight endpoint."""

    def test_preflight_returns_results(self, e2e_client, platform_admin):
        """Preflight endpoint returns validation results."""
        resp = e2e_client.post(
            "/api/maintenance/preflight",
            headers=platform_admin.headers,
        )
        assert resp.status_code == 200, f"Preflight failed: {resp.text}"
        data = resp.json()
        assert "valid" in data
        assert "issues" in data
        assert "warnings" in data

    def test_preflight_detects_unregistered_functions(self, e2e_client, platform_admin):
        """Preflight warns about decorated functions that aren't registered."""
        # Write a .py file with a decorator but don't register it
        file_content = '''
from bifrost import workflow

@workflow(name="Unregistered WF")
def unreg_wf():
    pass
'''
        e2e_client.put(
            "/api/content",
            headers=platform_admin.headers,
            json={"path": "workflows/unreg_preflight.py", "content": file_content},
        )

        resp = e2e_client.post(
            "/api/maintenance/preflight",
            headers=platform_admin.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        warnings = data.get("warnings", [])
        # Should have a warning about unregistered function
        unreg_warnings = [w for w in warnings if "unreg_wf" in w.get("detail", "")]
        assert len(unreg_warnings) > 0, f"Expected unregistered function warning, got: {warnings}"
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/e2e/api/test_preflight.py -v`
Expected: FAIL — endpoint doesn't exist

**Step 3: Add response models**

In `api/src/models/contracts/maintenance.py`, add:

```python
class PreflightIssueResponse(BaseModel):
    level: str  # "error" or "warning"
    category: str
    detail: str
    path: str | None = None

class PreflightResponse(BaseModel):
    valid: bool
    issues: list[PreflightIssueResponse]
    warnings: list[PreflightIssueResponse]
```

**Step 4: Implement the endpoint**

In `api/src/routers/maintenance.py`, add:

```python
@router.post(
    "/preflight",
    response_model=PreflightResponse,
    summary="Run preflight validation",
    description="Generate manifest JIT and run all validation checks including unregistered function detection.",
)
async def run_preflight(
    db: DbSession,
    user: CurrentSuperuser,
) -> PreflightResponse:
    """Run preflight validation on the current workspace state."""
    import ast
    import tempfile
    from pathlib import Path

    from src.services.github_sync import GitHubSyncService
    from src.services.file_storage import FileStorageService
    from src.models import Workflow as WorkflowORM

    issues = []
    warnings = []

    # 1. Generate manifest to temp dir and run existing preflight
    service = FileStorageService(db)
    # Read all .py files to check for unregistered functions
    all_files = await service.list_files("")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Generate manifest
        await GitHubSyncService._regenerate_manifest_to_dir(db, tmp_path)

        # Write all repo files to temp dir for preflight validation
        for file_entry in all_files:
            file_path = tmp_path / file_entry.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                content = await service.read_file(file_entry.path)
                file_path.write_bytes(content)
            except Exception:
                pass

        # Run existing preflight (reuse _run_preflight logic)
        # Note: may need to extract _run_preflight to be callable without GitHubSyncService instance

    # 2. Detect unregistered decorated functions
    py_files = [f for f in all_files if f.path.endswith(".py")]
    for py_file in py_files:
        try:
            content = await service.read_file(py_file.path)
            content_str = content.decode("utf-8", errors="replace")
            tree = ast.parse(content_str, filename=py_file.path)
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                dec_name = None
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                if dec_name in ("workflow", "tool", "data_provider"):
                    # Check if registered
                    result = await db.execute(
                        select(WorkflowORM).where(
                            WorkflowORM.path == py_file.path,
                            WorkflowORM.function_name == node.name,
                            WorkflowORM.is_active.is_(True),
                        )
                    )
                    if not result.scalar_one_or_none():
                        warnings.append(PreflightIssueResponse(
                            level="warning",
                            category="unregistered_function",
                            detail=f"Decorated function '{node.name}' in {py_file.path} is not registered as a workflow. Use register_workflow() to register it.",
                            path=py_file.path,
                        ))

    valid = len(issues) == 0
    return PreflightResponse(valid=valid, issues=issues, warnings=warnings)
```

**Step 5: Run test to verify it passes**

Run: `./test.sh tests/e2e/api/test_preflight.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add api/src/routers/maintenance.py api/src/models/contracts/maintenance.py api/tests/e2e/api/test_preflight.py
git commit -m "feat: add on-demand preflight endpoint with unregistered function detection"
```

---

### Task 11: Run Full Verification

**Step 1: Run all backend tests**

Run: `./test.sh -v`
Expected: All pass

**Step 2: Type checking**

Run: `cd api && pyright`
Expected: 0 errors

**Step 3: Linting**

Run: `cd api && ruff check .`
Expected: Clean

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address type checking and linting issues"
```
