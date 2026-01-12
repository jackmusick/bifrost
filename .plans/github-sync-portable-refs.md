# GitHub Sync Portable Refs Integration

## Status: PHASE 4 IN PROGRESS (Virtual Platform Files)

## Goal

Complete the integration of portable refs (workflow UUID <-> `path::function_name`) into the GitHub sync flow so that:
1. **Push**: Forms/agents/apps are serialized with portable refs (not UUIDs)
2. **Pull**: Portable refs from GitHub are resolved back to local UUIDs

This enables true portability - entities can be synced between environments where UUIDs differ but workflow paths are the same.

### Critical Missing Piece (Phase 4)

**Platform entities (apps, forms, agents) don't exist in `workspace_files` table.** They live in their own database tables. The current sync flow only compares files in `workspace_files` against GitHub.

**Solution:** Treat platform entities as "virtual files" that participate in sync:
- Serialize on-the-fly to compute content and SHA
- Include in sync preview alongside real workspace files
- Push: Serialize from DB → GitHub
- Pull: Deserialize from GitHub → DB

**Matching Strategy:**
- Primary: Match by entity ID (stable across environments)
- Fallback: Match by name with user confirmation (for imports without matching ID)

---

## Phase 1: COMPLETE

Forms and Agents now have:
- `@field_serializer` decorators for workflow refs
- `model_dump()` based serialization
- `_export` metadata handling in indexers
- Unit tests (11 tests in `test_portable_refs.py`)

---

## Phase 2: Model Consolidation & App Serialization

### Design Decisions

#### 1. App Model Strategy

**REST API** (keep as-is):
- `ApplicationPublic` for metadata in list/detail endpoints
- `ApplicationDefinition` wraps definition as `dict[str, Any]` for app viewer/builder
- This is how the app builder and renderers consume apps - DO NOT CHANGE

**File Serialization (GitHub)**:
- Delete `ApplicationExport` - uses untyped `pages: list[dict[str, Any]]`
- The `.app.json` file IS the full export format
- Use typed `PageDefinition` models with `model_dump(context={"workflow_map": map})`

**Key insight**: `app_components.py` already has typed models:
- `PageDefinition.layout: LayoutContainer` (not dict)
- `LayoutContainer.children: list[LayoutContainerOrComponent]` (typed components)
- `@field_serializer` decorators throughout for workflow refs

The problem: `ApplicationExport.pages: list[dict[str, Any]]` bypasses all of this.

#### 2. ApplicationDefinition - NO CHANGES NEEDED

`ApplicationDefinition` wraps definition as `dict[str, Any]` intentionally:
- App builder sends/receives raw JSON for maximum flexibility
- TypeScript client already has typed definitions
- Validation happens client-side for builder, server-side for import

**DO NOT change `ApplicationDefinition`** - it's the correct pattern for the REST API.

#### 3. PageDefinition Already Has Typed Components

`PageDefinition` in `app_components.py` already uses:
```python
class PageDefinition(BaseModel):
    layout: LayoutContainer  # NOT dict[str, Any]
    data_sources: list[DataSourceConfig]
    # ...
```

And `LayoutContainer.children` is typed:
```python
LayoutContainerOrComponent = Union["LayoutContainer", AppComponent, AppComponentNode]
```

This means `PageDefinition.model_dump(context={"workflow_map": map})` will correctly transform all nested workflow refs via the existing `@field_serializer` decorators.

#### 4. Unresolved Refs Handling

When importing a file with portable refs that can't be resolved:
1. Detect unresolved refs during `transform_path_refs_to_uuids()`
2. Return a structured result with the list of missing refs
3. Log warning - do not fail silently
4. Refs that can't be resolved stay as portable ref strings (graceful degradation)

---

### Tasks

#### Task 2.1: Delete ApplicationExport model

`ApplicationExport` uses `pages: list[dict[str, Any]]` which bypasses typed models.

**Files:**
- `api/src/models/contracts/applications.py` - Remove `ApplicationExport` class
- `api/src/models/contracts/__init__.py` - Remove from exports

#### Task 2.2: Simplify ApplicationImport

Keep for input validation but change to typed pages:
- Change `pages: list[dict[str, Any]]` -> `pages: list[PageDefinition]`
- This ensures imports are validated against the typed schema

**Files:**
- `api/src/models/contracts/applications.py` - Update `ApplicationImport.pages` type

#### Task 2.3: Create app file serialization function

Create `_serialize_app_to_json()` in app indexer that:
1. Converts app to typed `PageDefinition` models
2. Uses `model_dump(context={"workflow_map": map})`
3. Adds `_export` metadata

**Pattern:**
```python
def _serialize_app_to_json(
    app: Application,
    pages: list[AppPage],
    workflow_map: dict[str, str] | None = None
) -> bytes:
    # Convert pages to typed PageDefinition models
    page_definitions = [PageDefinition.model_validate(p) for p in pages]

    # Serialize with context for portable refs
    context = {"workflow_map": workflow_map} if workflow_map else None
    pages_data = [p.model_dump(mode="json", context=context) for p in page_definitions]

    app_data = {
        "name": app.name,
        "slug": app.slug,
        # ... other fields
        "pages": pages_data,
    }

    if workflow_map:
        app_data["_export"] = {
            "workflow_refs": [
                "pages.*.layout..*.props.workflow_id",
                "pages.*.data_sources.*.workflow_id",
                "pages.*.launch_workflow_id",
            ],
            "version": "1.0"
        }

    return json.dumps(app_data, indent=2).encode("utf-8")
```

**Files:**
- `api/src/services/file_storage/indexers/app.py`

#### Task 2.4: Add `_export` handling to app indexer

Update `AppIndexer.index_app()` to:
1. Check for `_export` metadata
2. Call `transform_path_refs_to_uuids()` for portable ref resolution
3. Log unresolved refs

**Files:**
- `api/src/services/file_storage/indexers/app.py`

#### Task 2.5: Update export/import endpoints

**Export endpoint** (`/api/applications/{app_id}/export`):
- Return typed JSON using `_serialize_app_to_json()`
- Include `_export` metadata when workflow_map provided

**Import endpoint** (`/api/applications/import`):
- Use `ApplicationImport` with typed `pages: list[PageDefinition]`
- Validate against typed schema
- Handle `_export` metadata for ref resolution

**Files:**
- `api/src/routers/applications.py`

---

### Phase 2C: Round-Trip Testing

#### Task 2C.1: Form round-trip test
- Create form with all field types including data_provider_id
- Export with workflow_map
- Import to new environment (simulate with different ref_to_uuid map)
- Verify all fields match (name, workflow_id, form_schema, etc.)

#### Task 2C.2: Agent round-trip test
- Create agent with tool_ids, delegated_agent_ids
- Export with workflow_map
- Import to new environment
- Verify all fields match

#### Task 2C.3: App round-trip test
- Create app with multiple pages and components
- Include components with workflow_id (Button, DataTable, etc.)
- Export with workflow_map
- Import to new environment
- Verify all pages, components, and props match

#### Task 2C.4: Missing refs test
- Export entity with workflow refs
- Import to environment missing some workflows
- Verify:
  - Import logs warning with list of unresolved refs
  - Unresolved refs stay as portable strings (graceful degradation)
  - Resolved refs become UUIDs

**Files:**
- `api/tests/unit/contracts/test_portable_refs.py` - Add round-trip tests

---

## Files to Modify

| File | Changes |
|------|---------|
| `api/src/models/contracts/applications.py` | Remove `ApplicationExport`, update `ApplicationImport.pages` type |
| `api/src/models/contracts/__init__.py` | Remove `ApplicationExport` export |
| `api/src/routers/applications.py` | Update export/import endpoints |
| `api/src/services/file_storage/indexers/app.py` | Add `_serialize_app_to_json()`, `_export` handling |
| `api/tests/unit/contracts/test_portable_refs.py` | Add round-trip tests |

---

## Verification

1. **Type check**: `cd api && pyright`
2. **Lint**: `cd api && ruff check .`
3. **Unit tests**: `./test.sh tests/unit/contracts/`
4. **Integration**: `./test.sh tests/integration/`
5. **Manual test**:
   - Create app with button that triggers workflow
   - Export to `.app.json` file
   - Verify JSON has portable ref like `"workflows/my_module.py::my_function"`
   - Re-import and verify UUID is restored

---

## Success Criteria

- [x] `ApplicationExport` model deleted
- [x] `ApplicationImport.pages` uses typed `PageDefinition`
- [x] App export produces JSON with portable refs (not UUIDs)
- [x] App import resolves portable refs to local UUIDs
- [x] Unresolved refs are logged and stay as portable strings
- [x] All existing tests pass (22 unit tests)
- [x] Round-trip tests verify complete model fidelity
- [x] App builder and renderers still work (no breaking changes)
- [x] E2E tests for push/pull/missing refs added

---

## Phase 3: E2E Integration Tests (BLOCKED - Requires Phase 4)

**Status:** Test files created but tests cannot pass until Phase 4 (Virtual Platform Files) is complete.

**Why blocked:** The E2E tests assume that apps/forms/agents participate in GitHub sync. Currently, platform entities are invisible to the sync flow because they're not in `workspace_files`. Phase 4 adds virtual file support to make these tests work.

### Files Created

| File | Purpose |
|------|---------|
| `api/tests/e2e/fixtures/entity_setup.py` | Fixtures for creating workflows, apps, forms, agents |
| `api/tests/e2e/api/test_portable_refs_sync.py` | E2E tests for GitHub sync with portable refs |

### Test Coverage

**Push Tests** (3 tests):
- App push exports portable refs
- Form push exports portable refs
- Agent push exports portable refs

**Pull Tests** (3 tests):
- App pull resolves portable refs to UUIDs
- Form pull resolves portable refs to UUIDs
- Agent pull resolves portable refs to UUIDs

**Missing Refs Tests** (4 tests):
- App with missing workflow imports gracefully
- Form with missing workflow imports gracefully
- Agent with missing tools imports gracefully
- Partial ref resolution (some resolve, others stay portable)

### Running E2E Tests

```bash
# Requires GITHUB_TEST_PAT environment variable
# NOTE: Tests will fail until Phase 4 is complete
GITHUB_TEST_PAT=xxx ./test.sh tests/e2e/api/test_portable_refs_sync.py -v
```

---

## Notes

- Entity IDs (`id` field) stay as UUIDs - they're the upsert key
- Only workflow references get transformed to portable refs
- `_export` metadata tracks which fields were transformed (for import)
- `ApplicationDefinition` is NOT changed - it's the correct REST API pattern
- `PageDefinition` already has typed components via `LayoutContainer`

---

## Phase 4: Virtual Platform Files in Sync Flow

### Background

The current GitHub sync (`GitHubSyncService` in `github_sync.py`) only syncs files tracked in the `workspace_files` table. Platform entities (apps, forms, agents) live in separate database tables and are **not** in `workspace_files`.

**Current sync flow:**
1. `get_sync_preview()` queries `workspace_files` for local file SHAs
2. Compares against GitHub tree
3. Returns `to_push`, `to_pull`, `conflicts`

**Problem:** Apps, forms, agents are invisible to sync because they're not in `workspace_files`.

**Solution:** Augment the file listing with "virtual" platform files:
- Serialize each entity on-the-fly
- Compute git blob SHA from serialized content
- Include in comparison alongside real workspace files
- Use existing indexers for push/pull operations

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GET /api/github/sync                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Query workspace_files for local SHAs                        │
│                                                                  │
│  2. Query platform entities (NEW):                              │
│     - Applications → serialize → compute SHA                     │
│     - Forms → serialize → compute SHA                           │
│     - Agents → serialize → compute SHA                          │
│                                                                  │
│  3. Merge into unified local file map:                          │
│     {                                                            │
│       "workflows/auth.py": "abc123...",      # workspace_file   │
│       "apps/dashboard.app.json": "def456...", # virtual         │
│       "forms/contact.form.json": "789ghi...", # virtual         │
│     }                                                            │
│                                                                  │
│  4. Compare against GitHub tree → to_push, to_pull, conflicts   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Path Conventions

| Entity | Path Pattern | Example |
|--------|-------------|---------|
| Application | `apps/{slug}.app.json` | `apps/dashboard.app.json` |
| Form | `forms/{id}.form.json` | `forms/550e8400-e29b-41d4-a716-446655440000.form.json` |
| Agent | `agents/{id}.agent.json` | `agents/123e4567-e89b-12d3-a456-426614174000.agent.json` |

**Note:** Apps use `slug` (human-readable), forms/agents use `id` (UUID). This matches current file naming conventions.

### Matching Strategy

**On Pull (GitHub → DB):**

1. Parse filename to extract identifier:
   - Apps: `apps/dashboard.app.json` → slug = "dashboard"
   - Forms: `forms/{uuid}.form.json` → id = UUID
   - Agents: `agents/{uuid}.agent.json` → id = UUID

2. Load JSON content, extract `id` field

3. **Match by ID (primary):**
   - Query: `SELECT * FROM {table} WHERE id = json_id`
   - If found: Update existing entity
   - If not found: Create new entity with that ID

4. **Match by name (fallback, requires confirmation):**
   - If ID not found and `confirm_name_match=true` in request
   - Query: `SELECT * FROM {table} WHERE name = json_name`
   - If found: Update existing entity (preserve local ID)
   - User must explicitly confirm this behavior

### Tasks

#### Task 4.1: Add `github_sha` Column to Platform Entities

Platform entities need to track their last-synced SHA for efficient comparison.

**Database migrations:**
```sql
-- Add github_sha to applications
ALTER TABLE applications ADD COLUMN github_sha VARCHAR(40);

-- Add github_sha to forms
ALTER TABLE forms ADD COLUMN github_sha VARCHAR(40);

-- Add github_sha to agents
ALTER TABLE agents ADD COLUMN github_sha VARCHAR(40);
```

**ORM updates:**
- `api/src/models/orm/applications.py` - Add `github_sha: Mapped[str | None]`
- `api/src/models/orm/forms.py` - Add `github_sha: Mapped[str | None]`
- `api/src/models/orm/agents.py` - Add `github_sha: Mapped[str | None]`

**Files:**
- `api/alembic/versions/xxx_add_github_sha_to_platform_entities.py` (new)
- `api/src/models/orm/applications.py`
- `api/src/models/orm/forms.py`
- `api/src/models/orm/agents.py`

---

#### Task 4.2: Create Virtual File Provider

Create a service that generates virtual platform file entries for sync comparison.

**New file:** `api/src/services/github_sync_virtual_files.py`

```python
from dataclasses import dataclass
from src.services.file_storage.indexers import (
    _serialize_app_to_json,
    _serialize_form_to_json,
    _serialize_agent_to_json,
)
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.file_storage.ref_translation import build_workflow_ref_map


@dataclass
class VirtualFile:
    """Represents a platform entity as a virtual file for sync."""
    path: str                    # e.g., "apps/dashboard.app.json"
    entity_type: str             # "app", "form", "agent"
    entity_id: str               # UUID of the entity
    content: bytes               # Serialized JSON content
    computed_sha: str            # Git blob SHA of content
    stored_sha: str | None       # Last synced SHA from DB (for comparison)


class VirtualFileProvider:
    """Generates virtual file entries for platform entities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_virtual_files(
        self,
        include_content: bool = False
    ) -> list[VirtualFile]:
        """
        Get all platform entities as virtual files.

        Args:
            include_content: If True, serialize full content (expensive).
                            If False, only include path and stored_sha.

        Returns:
            List of VirtualFile entries for sync comparison.
        """
        workflow_map = await build_workflow_ref_map(self.db) if include_content else None

        virtual_files = []
        virtual_files.extend(await self._get_app_files(workflow_map, include_content))
        virtual_files.extend(await self._get_form_files(workflow_map, include_content))
        virtual_files.extend(await self._get_agent_files(workflow_map, include_content))

        return virtual_files

    async def _get_app_files(self, workflow_map, include_content) -> list[VirtualFile]:
        """Generate virtual files for all applications."""
        # Query all apps with pages
        # For each app:
        #   path = f"apps/{app.slug}.app.json"
        #   if include_content:
        #     content = _serialize_app_to_json(app, pages, workflow_map)
        #     computed_sha = compute_git_blob_sha(content)
        #   stored_sha = app.github_sha
        pass

    async def _get_form_files(self, workflow_map, include_content) -> list[VirtualFile]:
        """Generate virtual files for all forms."""
        pass

    async def _get_agent_files(self, workflow_map, include_content) -> list[VirtualFile]:
        """Generate virtual files for all agents."""
        pass

    async def get_virtual_file_content(
        self,
        path: str
    ) -> tuple[bytes, str] | None:
        """
        Get serialized content for a specific virtual file.

        Returns:
            Tuple of (content_bytes, entity_id) or None if not found.
        """
        # Parse path to determine entity type and identifier
        # Serialize and return content
        pass

    async def update_entity_github_sha(
        self,
        entity_type: str,
        entity_id: str,
        sha: str
    ) -> None:
        """Update the github_sha for a platform entity after sync."""
        pass
```

**Files:**
- `api/src/services/github_sync_virtual_files.py` (new)

---

#### Task 4.3: Integrate Virtual Files into Sync Preview

Modify `GitHubSyncService.get_sync_preview()` to include virtual platform files.

**Current flow (lines 580-755 in `github_sync.py`):**
```python
async def get_sync_preview(self) -> SyncPreview:
    # 1. Clone repo
    # 2. Walk clone for remote files
    # 3. Query workspace_files for local SHAs  ← MODIFY HERE
    # 4. Compare and categorize
```

**Modified flow:**
```python
async def get_sync_preview(self) -> SyncPreview:
    # 1. Clone repo
    # 2. Walk clone for remote files
    # 3. Get local file SHAs:
    #    a. Query workspace_files (existing)
    #    b. Query virtual platform files (NEW)
    #    c. Merge into single dict
    # 4. Compare and categorize (existing logic works unchanged)
```

**Key modification in `_get_local_file_shas()` (lines 508-528):**

```python
async def _get_local_file_shas(self) -> dict[str, str | None]:
    """Get SHA for all local files (workspace + virtual platform files)."""

    # Existing: workspace files
    stmt = select(WorkspaceFile.path, WorkspaceFile.github_sha).where(
        WorkspaceFile.is_deleted.is_(False)
    )
    result = await self.db.execute(stmt)
    local_shas = {row.path: row.github_sha for row in result}

    # NEW: virtual platform files
    virtual_provider = VirtualFileProvider(self.db)
    virtual_files = await virtual_provider.get_all_virtual_files(include_content=False)

    for vf in virtual_files:
        # Use stored SHA for comparison (fast path)
        # If stored_sha is None, we need to compute it
        if vf.stored_sha:
            local_shas[vf.path] = vf.stored_sha
        else:
            # Entity was never synced - need to compute SHA
            # This is expensive but only happens once per entity
            content = await virtual_provider.get_virtual_file_content(vf.path)
            if content:
                local_shas[vf.path] = compute_git_blob_sha(content[0])

    return local_shas
```

**Files:**
- `api/src/services/github_sync.py` - Modify `_get_local_file_shas()`, add virtual file provider

---

#### Task 4.4: Handle Virtual File Content for Conflicts

When comparing files, if there's a conflict, the sync needs to read local content for display.

**Current (lines 663-681):**
```python
try:
    file_storage = FileStorageService(self.db)
    local_content, _ = await file_storage.read_file(path)
except Exception:
    local_content = None
```

**Problem:** `FileStorageService.read_file()` only handles workspace files, not virtual platform files.

**Solution:** Add virtual file handling to content reads:

```python
async def _get_local_content(self, path: str) -> bytes | None:
    """Get local content for a file path (workspace or virtual)."""

    # Check if this is a virtual platform file
    if path.startswith("apps/") and path.endswith(".app.json"):
        return await self._get_virtual_content(path, "app")
    elif path.startswith("forms/") and path.endswith(".form.json"):
        return await self._get_virtual_content(path, "form")
    elif path.startswith("agents/") and path.endswith(".agent.json"):
        return await self._get_virtual_content(path, "agent")

    # Regular workspace file
    try:
        file_storage = FileStorageService(self.db)
        content, _ = await file_storage.read_file(path)
        return content
    except Exception:
        return None

async def _get_virtual_content(self, path: str, entity_type: str) -> bytes | None:
    """Get serialized content for a virtual platform file."""
    virtual_provider = VirtualFileProvider(self.db)
    result = await virtual_provider.get_virtual_file_content(path)
    return result[0] if result else None
```

**Files:**
- `api/src/services/github_sync.py` - Add `_get_local_content()` helper, update conflict handling

---

#### Task 4.5: Handle Push for Virtual Files

When pushing, virtual files need to be serialized from DB.

**Current (lines 1232-1238):**
```python
content, _ = await file_storage.read_file(action.path)
blob_sha = await self.github.create_blob(self.repo, content)
```

**Modified:**
```python
content = await self._get_local_content(action.path)
if content is None:
    logger.warning(f"File to push not found: {action.path}")
    continue
blob_sha = await self.github.create_blob(self.repo, content)
```

**After successful push, update entity's github_sha:**
```python
# After creating commit successfully
for path, sha in blob_shas.items():
    if self._is_virtual_file(path):
        await self._update_virtual_file_sha(path, sha)
    else:
        await self._update_github_sha(path, sha)  # existing
```

**Files:**
- `api/src/services/github_sync.py` - Modify push logic

---

#### Task 4.6: Handle Pull for Virtual Files

When pulling, virtual files need to be deserialized to DB using indexers.

**Current (lines 1051-1060):**
```python
await file_storage.write_file(
    path=action.path,
    content=content,
    updated_by="github_sync",
)
```

**Modified:**
```python
if self._is_virtual_file(action.path):
    await self._import_virtual_file(action.path, content, action.sha)
else:
    await file_storage.write_file(
        path=action.path,
        content=content,
        updated_by="github_sync",
    )

async def _import_virtual_file(
    self,
    path: str,
    content: bytes,
    github_sha: str
) -> None:
    """Import a virtual platform file from GitHub."""

    if path.startswith("apps/") and path.endswith(".app.json"):
        indexer = AppIndexer(self.db)
        await indexer.index_app(path, content)
        # Update github_sha on the app
        slug = path[5:-9]  # Extract slug from "apps/{slug}.app.json"
        await self._update_app_sha_by_slug(slug, github_sha)

    elif path.startswith("forms/") and path.endswith(".form.json"):
        indexer = FormIndexer(self.db)
        await indexer.index_form(path, content)
        # Update github_sha on the form
        form_id = self._extract_id_from_path(path)
        await self._update_form_sha(form_id, github_sha)

    elif path.startswith("agents/") and path.endswith(".agent.json"):
        indexer = AgentIndexer(self.db)
        await indexer.index_agent(path, content)
        # Update github_sha on the agent
        agent_id = self._extract_id_from_path(path)
        await self._update_agent_sha(agent_id, github_sha)
```

**Files:**
- `api/src/services/github_sync.py` - Add `_import_virtual_file()`, `_is_virtual_file()` helpers

---

#### Task 4.7: Add Path/ID Extraction Helpers

Helper functions to parse virtual file paths.

```python
def _is_virtual_file(self, path: str) -> bool:
    """Check if path is a virtual platform file."""
    return (
        (path.startswith("apps/") and path.endswith(".app.json")) or
        (path.startswith("forms/") and path.endswith(".form.json")) or
        (path.startswith("agents/") and path.endswith(".agent.json"))
    )

def _extract_entity_type(self, path: str) -> str | None:
    """Extract entity type from virtual file path."""
    if path.startswith("apps/"):
        return "app"
    elif path.startswith("forms/"):
        return "form"
    elif path.startswith("agents/"):
        return "agent"
    return None

def _extract_id_from_path(self, path: str) -> str | None:
    """Extract entity ID from virtual file path."""
    # forms/{uuid}.form.json → uuid
    # agents/{uuid}.agent.json → uuid
    import re
    match = re.match(r"(?:forms|agents)/([a-f0-9-]+)\.\w+\.json$", path)
    return match.group(1) if match else None

def _extract_slug_from_path(self, path: str) -> str | None:
    """Extract app slug from virtual file path."""
    # apps/{slug}.app.json → slug
    import re
    match = re.match(r"apps/(.+)\.app\.json$", path)
    return match.group(1) if match else None
```

**Files:**
- `api/src/services/github_sync.py` - Add helper methods

---

#### Task 4.8: Update SHA After Sync Operations

Methods to update `github_sha` on platform entities.

```python
async def _update_app_sha_by_slug(self, slug: str, sha: str) -> None:
    """Update github_sha for an application by slug."""
    stmt = (
        update(Application)
        .where(Application.slug == slug)
        .values(github_sha=sha)
    )
    await self.db.execute(stmt)

async def _update_form_sha(self, form_id: str, sha: str) -> None:
    """Update github_sha for a form by ID."""
    stmt = (
        update(Form)
        .where(Form.id == form_id)
        .values(github_sha=sha)
    )
    await self.db.execute(stmt)

async def _update_agent_sha(self, agent_id: str, sha: str) -> None:
    """Update github_sha for an agent by ID."""
    stmt = (
        update(Agent)
        .where(Agent.id == agent_id)
        .values(github_sha=sha)
    )
    await self.db.execute(stmt)
```

**Files:**
- `api/src/services/github_sync.py` - Add SHA update methods

---

#### Task 4.9: Unit Tests for Virtual File Provider

Test the virtual file serialization and SHA computation.

```python
# api/tests/unit/services/test_github_sync_virtual_files.py

class TestVirtualFileProvider:

    async def test_get_app_virtual_files(self, db_session, test_app):
        """Test that apps are serialized as virtual files."""
        provider = VirtualFileProvider(db_session)
        files = await provider.get_all_virtual_files(include_content=True)

        app_files = [f for f in files if f.entity_type == "app"]
        assert len(app_files) == 1
        assert app_files[0].path == f"apps/{test_app.slug}.app.json"
        assert app_files[0].computed_sha is not None

    async def test_get_form_virtual_files(self, db_session, test_form):
        """Test that forms are serialized as virtual files."""
        provider = VirtualFileProvider(db_session)
        files = await provider.get_all_virtual_files(include_content=True)

        form_files = [f for f in files if f.entity_type == "form"]
        assert len(form_files) == 1
        assert form_files[0].path == f"forms/{test_form.id}.form.json"

    async def test_portable_refs_in_virtual_content(self, db_session, test_form_with_workflow):
        """Test that workflow refs are converted to portable refs."""
        provider = VirtualFileProvider(db_session)
        content, _ = await provider.get_virtual_file_content(
            f"forms/{test_form_with_workflow.id}.form.json"
        )

        data = json.loads(content)
        # workflow_id should be portable ref, not UUID
        assert "::" in data["workflow_id"]
        assert "_export" in data

    async def test_sha_computed_from_serialized_content(self, db_session, test_app):
        """Test that SHA is correctly computed from serialized JSON."""
        provider = VirtualFileProvider(db_session)
        files = await provider.get_all_virtual_files(include_content=True)

        app_file = [f for f in files if f.entity_type == "app"][0]

        # Manually compute SHA and verify it matches
        expected_sha = compute_git_blob_sha(app_file.content)
        assert app_file.computed_sha == expected_sha
```

**Files:**
- `api/tests/unit/services/test_github_sync_virtual_files.py` (new)

---

#### Task 4.10: Integration Tests for Virtual File Sync

Test full sync flow with virtual platform files.

```python
# api/tests/integration/test_github_sync_virtual_files.py

class TestVirtualFileSyncPreview:

    async def test_preview_includes_local_apps(self, e2e_client, platform_admin, github_configured):
        """Test that sync preview includes apps in to_push when not on GitHub."""
        # Create app via API
        # GET /api/github/sync
        # Verify app appears in to_push
        pass

    async def test_preview_detects_remote_only_forms(self, e2e_client, platform_admin, github_configured):
        """Test that sync preview includes forms in to_pull when only on GitHub."""
        # Create form file on GitHub directly
        # GET /api/github/sync
        # Verify form appears in to_pull
        pass

    async def test_preview_detects_conflicts(self, e2e_client, platform_admin, github_configured):
        """Test that sync preview detects conflicts for modified entities."""
        # Create agent, sync to GitHub
        # Modify agent locally
        # Modify agent on GitHub
        # GET /api/github/sync
        # Verify agent appears in conflicts
        pass


class TestVirtualFileSyncExecute:

    async def test_push_serializes_app_with_portable_refs(self, e2e_client, platform_admin, github_configured):
        """Test that pushed app files have portable refs."""
        # Create app with workflow ref
        # POST /api/github/sync
        # Fetch file from GitHub
        # Verify workflow_id is portable ref format
        pass

    async def test_pull_deserializes_form_with_portable_refs(self, e2e_client, platform_admin, github_configured):
        """Test that pulled form files resolve portable refs to UUIDs."""
        # Create form file on GitHub with portable refs
        # POST /api/github/sync
        # GET /api/forms/{id}
        # Verify workflow_id is UUID
        pass

    async def test_github_sha_updated_after_push(self, e2e_client, platform_admin, github_configured):
        """Test that entity github_sha is updated after successful push."""
        # Create app
        # POST /api/github/sync (push)
        # Verify app.github_sha is set
        pass

    async def test_github_sha_updated_after_pull(self, e2e_client, platform_admin, github_configured):
        """Test that entity github_sha is updated after successful pull."""
        # Create agent file on GitHub
        # POST /api/github/sync (pull)
        # Verify agent.github_sha matches GitHub blob SHA
        pass
```

**Files:**
- `api/tests/integration/test_github_sync_virtual_files.py` (new)

---

#### Task 4.11: Update E2E Tests

Update existing E2E tests to work with virtual file sync.

The existing tests in `test_portable_refs_sync.py` should work once virtual files are integrated. May need minor adjustments to:
- Wait for sync preview to include virtual files
- Verify files on GitHub come from serialization (not workspace)

**Files:**
- `api/tests/e2e/api/test_portable_refs_sync.py` - Verify/update tests

---

### Files Summary

| File | Action | Description |
|------|--------|-------------|
| `api/alembic/versions/xxx_add_github_sha.py` | **Create** | Migration to add github_sha to apps/forms/agents |
| `api/src/models/orm/applications.py` | **Modify** | Add github_sha column |
| `api/src/models/orm/forms.py` | **Modify** | Add github_sha column |
| `api/src/models/orm/agents.py` | **Modify** | Add github_sha column |
| `api/src/services/github_sync_virtual_files.py` | **Create** | VirtualFileProvider class |
| `api/src/services/github_sync.py` | **Modify** | Integrate virtual files into sync flow |
| `api/tests/unit/services/test_github_sync_virtual_files.py` | **Create** | Unit tests for virtual file provider |
| `api/tests/integration/test_github_sync_virtual_files.py` | **Create** | Integration tests for virtual file sync |
| `api/tests/e2e/api/test_portable_refs_sync.py` | **Modify** | Update E2E tests if needed |

---

### Verification

1. **Database migration:**
   ```bash
   cd api && alembic upgrade head
   ```

2. **Type check:**
   ```bash
   cd api && pyright
   ```

3. **Lint:**
   ```bash
   cd api && ruff check .
   ```

4. **Unit tests:**
   ```bash
   ./test.sh tests/unit/services/test_github_sync_virtual_files.py -v
   ```

5. **Integration tests:**
   ```bash
   ./test.sh tests/integration/test_github_sync_virtual_files.py -v
   ```

6. **E2E tests:**
   ```bash
   GITHUB_TEST_PAT=xxx ./test.sh tests/e2e/api/test_portable_refs_sync.py -v
   ```

7. **Manual verification:**
   - Create app with workflow-triggering button
   - Run sync preview → app should appear in to_push
   - Execute sync → verify GitHub has `.app.json` with portable refs
   - Modify app on GitHub → run sync → verify changes pulled to DB

---

### Success Criteria

- [ ] `github_sha` column added to Application, Form, Agent tables
- [ ] VirtualFileProvider correctly serializes all entity types
- [ ] Sync preview includes virtual platform files
- [ ] Push serializes entities with portable workflow refs
- [ ] Pull deserializes entities and resolves portable refs to UUIDs
- [ ] `github_sha` is updated after successful push/pull
- [ ] Conflicts detected when local and remote both modified
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All E2E tests pass
- [ ] Manual verification successful
