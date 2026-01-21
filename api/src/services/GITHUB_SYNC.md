# GitHub Sync Implementation Guide

This document provides a comprehensive technical reference for Bifrost's GitHub synchronization system. It covers the architecture, data flow, conflict detection, entity serialization, and all the nuances of bidirectional sync between the platform database and GitHub repositories.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Entity Types & File Patterns](#entity-types--file-patterns)
4. [Serialization & Portable References](#serialization--portable-references)
5. [Sync Direction Logic](#sync-direction-logic)
6. [SHA Tracking & Change Detection](#sha-tracking--change-detection)
7. [Conflict Detection](#conflict-detection)
8. [Virtual File System](#virtual-file-system)
9. [Sync Preview Flow](#sync-preview-flow)
10. [Sync Execution Flow](#sync-execution-flow)
11. [Orphan Detection & Protection](#orphan-detection--protection)
12. [WebSocket Integration](#websocket-integration)
13. [API Endpoints](#api-endpoints)
14. [Pydantic Models Reference](#pydantic-models-reference)
15. [Database Models](#database-models)
16. [Error Handling](#error-handling)

---

## Architecture Overview

### Design Principles

1. **API-based only** - No local git folder required. All GitHub operations use the REST API and temporary shallow clones.
2. **Database is source of truth** - Local state is read from PostgreSQL, not from a git working directory.
3. **Three-way comparison** - Compares local DB state with remote GitHub state using stored SHA markers.
4. **Lazy content reading** - Only fetches file content when needed (for conflicts), using SHA comparison for fast change detection.
5. **Virtual file abstraction** - Platform entities (forms, agents, apps) are serialized on-the-fly for GitHub sync.

### Key Files

| File | Purpose |
|------|---------|
| `github_sync.py` | Main sync service with preview and execute logic |
| `github_sync_virtual_files.py` | Virtual file provider for platform entities |
| `github_sync_entity_metadata.py` | Entity metadata extraction for UI display |
| `file_storage/ref_translation.py` | Portable workflow reference translation |
| `file_storage/indexers/form.py` | Form serialization and indexing |
| `file_storage/indexers/agent.py` | Agent serialization and indexing |
| `file_storage/indexers/app.py` | App serialization and indexing |
| `routers/github.py` | API endpoints for GitHub integration |
| `models/contracts/github.py` | Pydantic models for API requests/responses |
| `models/orm/workspace.py` | WorkspaceFile ORM model |

---

## Core Components

### GitHubSyncService

The main orchestrator class that handles all sync operations.

```python
class GitHubSyncService:
    def __init__(
        self,
        db: AsyncSession,
        github_token: str,
        repo: str,           # "owner/repo" format
        branch: str = "main",
    ):
```

**Key Methods:**
- `get_sync_preview()` - Compare local and remote, return categorized changes
- `execute_sync()` - Apply changes with user's conflict resolutions
- `get_local_content()` - Fetch serialized content for a file
- `get_remote_content()` - Fetch content from GitHub

### GitHubAPIClient

Low-level wrapper around GitHub's Git Data API.

```python
class GitHubAPIClient:
    BASE_URL = "https://api.github.com"
```

**Operations:**
- `get_tree()` - List files in a commit/tree
- `get_blob_content()` - Read file content by SHA
- `create_blob()` - Create a blob with content
- `create_tree()` - Create a new tree (file structure)
- `create_commit()` - Create a commit
- `get_ref()` / `update_ref()` - Read/update branch pointers

### VirtualFileProvider

Serializes platform entities to virtual files for sync.

```python
class VirtualFileProvider:
    def __init__(self, db: AsyncSession):

    async def get_all_virtual_files(self) -> VirtualFileResult:
        """Returns all forms, agents, and apps as virtual files."""
```

---

## Entity Types & File Patterns

### Syncable Entities

| Entity Type | File Pattern | Storage | Matching Strategy |
|-------------|--------------|---------|-------------------|
| **Form** | `forms/{uuid}.form.json` | `forms` table | UUID in filename |
| **Agent** | `agents/{uuid}.agent.json` | `agents` table | UUID in filename |
| **App** | `apps/{slug}/app.json` | `applications` table | Slug from path |
| **App File** | `apps/{slug}/**/*.tsx` | `app_files` table | Full path |
| **Workflow** | `workflows/*.py` | `workspace_files` + `workflows` | Path |
| **Data Provider** | `data_providers/*.py` | `workspace_files` + `workflows` | Path |
| **Module** | `modules/*.py` | `workspace_files` (content column) | Path |

### Virtual vs Regular Files

**Virtual Files** (platform entities):
- Don't exist in `workspace_files` table
- Stored in their own tables (`forms`, `agents`, `applications`)
- Serialized on-the-fly during sync
- Matched by entity ID, not by path

**Regular Files** (workspace files):
- Stored in `workspace_files` table with S3 content
- Tracked with `github_sha` and `git_status` columns
- Matched by file path

---

## Serialization & Portable References

### The Portability Problem

Platform entities reference workflows by UUID. When syncing to GitHub, these UUIDs must be converted to portable references that work across environments.

### Portable Reference Format

```
{file_path}::{function_name}

Examples:
- workflows/billing.py::process_payment
- data_providers/customers.py::get_customer_list
```

### Translation Maps

**Export (DB → Git):**
```python
async def build_workflow_ref_map(db: AsyncSession) -> dict[str, str]:
    """UUID → 'path::function_name'"""
```

**Import (Git → DB):**
```python
async def build_ref_to_uuid_map(db: AsyncSession) -> dict[str, str]:
    """'path::function_name' → UUID"""
```

### Form Serialization Example

```python
def _serialize_form_to_json(form: Form, workflow_map: dict[str, str]) -> bytes:
    # 1. Convert ORM to Pydantic model
    form_public = FormPublic.model_validate(form)

    # 2. Dump to dict, excluding env-specific fields
    form_data = form_public.model_dump(
        mode="json",
        exclude={"organization_id", "access_level", "created_at", "updated_at"},
    )

    # 3. Transform workflow UUIDs to portable refs
    form_data = transform_refs_for_export(form_data, FormPublic, workflow_map)

    # 4. Return as JSON bytes
    return json.dumps(form_data, indent=2).encode("utf-8")
```

### App Source Code Transformation

For app files (`.tsx`), workflow references in `useWorkflow()` calls are transformed:

```typescript
// Before (in DB):
const workflow = useWorkflow('550e8400-e29b-41d4-a716-446655440000');

// After (in Git):
const workflow = useWorkflow('workflows/billing.py::process_payment');
```

**Implementation:**
```python
USE_WORKFLOW_PATTERN = re.compile(r"useWorkflow\((['\"])([^'\"]+)\1\)")

def transform_app_source_uuids_to_refs(source: str, workflow_map: dict) -> tuple[str, list[str]]:
    """Transform useWorkflow('{uuid}') to useWorkflow('{ref}')"""
```

---

## Sync Direction Logic

### Decision Matrix for Regular Files

The sync algorithm uses `git_status` to make intelligent decisions:

| Local State | Remote State | Local Status | Action |
|-------------|--------------|--------------|--------|
| Exists | Not exists | UNTRACKED | **Push** (new local file) |
| Exists | Not exists | SYNCED | **Pull DELETE** (remote deleted) |
| Exists | Not exists | MODIFIED | **Conflict** (local modified, remote deleted) |
| Not exists | Exists | - | **Pull ADD** (new remote file) |
| Deleted | Exists (same SHA) | DELETED | **Push DELETE** (safe to delete remote) |
| Deleted | Exists (diff SHA) | DELETED | **Conflict** (remote modified after we synced) |
| Same SHA | Same SHA | any | No action |
| Diff SHA | Diff SHA | SYNCED | **Pull MODIFY** (safe, not modified locally) |
| Diff SHA | Diff SHA | MODIFIED | **Conflict** (both sides changed) |

### Virtual File Comparison

Virtual files are compared by **entity ID**, not path:

```python
# Entity ID determination:
- Forms/Agents: UUID from filename (e.g., "abc123" from "abc123.form.json")
- Apps: Slug-based path (e.g., "apps/my-app")
- App Files: Full file path (e.g., "apps/my-app/pages/index.tsx")
```

| Local | Remote | Action |
|-------|--------|--------|
| Exists | Not exists | **Push** |
| Not exists | Exists | **Pull** |
| Same SHA | Same SHA | No action |
| Diff SHA | Diff SHA | **Conflict** |

---

## SHA Tracking & Change Detection

### Git Blob SHA Computation

To compare with GitHub's native SHAs, we compute git blob SHAs locally:

```python
def compute_git_blob_sha(content: bytes) -> str:
    """Compute SHA-1 hash using git's blob format."""
    # Git blob format: "blob {size}\0{content}"
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()
```

### WorkspaceFile SHA Fields

```python
class WorkspaceFile(Base):
    github_sha: str | None    # Git blob SHA when last synced
    git_status: GitStatus     # SYNCED, MODIFIED, DELETED, UNTRACKED
    content_hash: str         # SHA-256 for local change detection
```

### GitStatus Enum

```python
class GitStatus(str, Enum):
    UNTRACKED = "untracked"  # New file, never synced
    SYNCED = "synced"        # Content matches GitHub
    MODIFIED = "modified"    # Changed locally since last sync
    DELETED = "deleted"      # Soft-deleted locally
```

### SHA Update Flow

After successfully syncing a file:

```python
async def _update_github_sha(self, path: str, sha: str) -> None:
    stmt = (
        update(WorkspaceFile)
        .where(WorkspaceFile.path == path)
        .values(github_sha=sha, git_status=GitStatus.SYNCED)
    )
    await self.db.execute(stmt)
```

---

## Conflict Detection

### Conflict Types

1. **Content Conflicts** - Both local and remote modified the same file
2. **Delete Conflicts** - One side deleted, other side modified
3. **Path Collisions** - Same path appears in both pull and push lists

### ConflictInfo Model

```python
class ConflictInfo(BaseModel):
    path: str                          # File path
    local_content: str | None          # Local content (None if deleted)
    remote_content: str | None         # Remote content (None if deleted)
    local_sha: str                     # SHA of local content
    remote_sha: str                    # SHA of remote content
    display_name: str | None           # Human-readable name
    entity_type: str | None            # form, agent, app, workflow, etc.
    parent_slug: str | None            # For app_file: parent app slug
```

### Conflict Resolution

Users resolve conflicts by choosing:
- `keep_local` - Push local version to GitHub
- `keep_remote` - Pull remote version from GitHub
- `skip` - Exclude entity from sync (for serialization errors)

```python
class SyncExecuteRequest(BaseModel):
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote", "skip"]]
    confirm_orphans: bool
    confirm_unresolved_refs: bool
```

---

## Virtual File System

### VirtualFile Dataclass

```python
@dataclass
class VirtualFile:
    path: str              # e.g., "forms/{uuid}.form.json"
    entity_type: str       # "form", "agent", "app", "app_file"
    entity_id: str         # UUID or slug or path
    content: bytes | None  # Serialized JSON/source
    computed_sha: str | None  # Git blob SHA
```

### Path Matching Functions

```python
@staticmethod
def is_virtual_file_path(path: str) -> bool:
    """Check if path matches virtual file pattern."""
    return (
        (path.startswith("forms/") and path.endswith(".form.json"))
        or (path.startswith("agents/") and path.endswith(".agent.json"))
        or path.startswith("apps/")
    )

@staticmethod
def get_entity_type_from_path(path: str) -> str | None:
    """Determine entity type from path."""
    if path.startswith("forms/") and path.endswith(".form.json"):
        return "form"
    elif path.startswith("agents/") and path.endswith(".agent.json"):
        return "agent"
    elif path.startswith("apps/"):
        if path.endswith("/app.json"):
            return "app"
        return "app_file"
    return None
```

### Entity ID Extraction

```python
# UUID from filename (forms, agents)
UUID_FILENAME_PATTERN = re.compile(
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"\.(form|agent)\.json$"
)

# Slug from app path
def extract_app_slug_from_path(path: str) -> str | None:
    # "apps/my-app/app.json" → "my-app"
    parts = path.split("/")
    return parts[1] if len(parts) >= 2 else None
```

---

## Sync Preview Flow

### Phase Overview

```
1. Clone      → Shallow clone repo to temp directory
2. Scan       → Walk clone, compute SHAs, extract entity IDs
3. Load       → Query DB for local file SHAs
4. Serialize  → Generate virtual files from platform entities
5. Compare    → SHA-based comparison with git_status awareness
6. Analyze    → Detect orphans and unresolved refs
7. Return     → SyncPreview with categorized changes
```

### Preview Algorithm

```python
async def get_sync_preview(self) -> SyncPreview:
    # 1. Clone repo to temp directory (shallow clone for speed)
    clone_dir = self._clone_to_temp()

    # 2. Walk clone to get remote files and compute SHAs
    remote_files: dict[str, str] = {}  # path → sha
    for file_path in clone_path.rglob("*"):
        if file_path.is_file() and not excluded:
            content = file_path.read_bytes()
            remote_files[rel_path] = compute_git_blob_sha(content)

    # 2b. Extract virtual files from remote
    remote_virtual_files: dict[str, tuple] = {}  # entity_id → (path, sha, type)
    for path, sha in remote_files.items():
        if VirtualFileProvider.is_virtual_file_path(path):
            entity_id = extract_entity_id(path)
            remote_virtual_files[entity_id] = (path, sha, entity_type)
            del remote_files[path]  # Handle separately

    # 3. Get local file SHAs from DB (no S3 read!)
    local_shas = await self._get_local_file_shas()
    # Returns: {path: (github_sha, git_status, is_deleted)}

    # 4. Serialize virtual files
    virtual_shas, serialization_errors = await self._get_virtual_file_shas()

    # 5. Compare and categorize
    to_pull, to_push, conflicts = compare_files(
        remote_files, local_shas, remote_virtual_files, virtual_shas
    )

    # 6. Detect orphans and unresolved refs
    will_orphan = await self._detect_orphans(to_pull)
    unresolved_refs = await self._detect_unresolved_refs(to_pull)

    # 7. Return preview
    return SyncPreview(
        to_pull=to_pull,
        to_push=to_push,
        conflicts=conflicts,
        will_orphan=will_orphan,
        unresolved_refs=unresolved_refs,
        serialization_errors=serialization_errors,
    )
```

### SyncPreview Model

```python
class SyncPreview(BaseModel):
    to_pull: list[SyncAction]              # Files to pull from GitHub
    to_push: list[SyncAction]              # Files to push to GitHub
    conflicts: list[ConflictInfo]          # Conflicts requiring resolution
    will_orphan: list[OrphanInfo]          # Workflows becoming orphaned
    unresolved_refs: list[UnresolvedRefInfo]  # Refs that can't be resolved
    serialization_errors: list[SerializationError]  # Entities that failed to serialize
    is_empty: bool                         # True if nothing to sync
```

---

## Sync Execution Flow

### Phase Overview

```
1. Validate   → Check conflict resolutions, orphan confirmation
2. Clone      → Shallow clone for reading remote content
3. Pull       → Apply remote changes to database
4. Resolve    → Apply conflict resolutions
5. Orphan     → Mark orphaned workflows
6. Push       → Push local changes to GitHub via API
7. Commit     → Update branch ref
```

### Execution Algorithm

```python
async def execute_sync(
    self,
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote"]],
    confirm_orphans: bool,
    confirm_unresolved_refs: bool,
) -> SyncResult:
    # Get fresh preview
    preview = await self.get_sync_preview()

    # Validate
    if preview.will_orphan and not confirm_orphans:
        raise OrphanError(...)
    if preview.unresolved_refs and not confirm_unresolved_refs:
        raise UnresolvedRefsError(...)
    if preview.conflicts:
        for conflict in preview.conflicts:
            if conflict.path not in conflict_resolutions:
                raise ConflictError(...)

    # Clone for pulling
    clone_dir = self._clone_to_temp()

    # 1. Pull remote changes
    for action in preview.to_pull:
        if action.action == SyncActionType.DELETE:
            if is_virtual_file:
                await self._delete_virtual_file(action.path)
            else:
                await file_storage.delete_file(action.path)
        else:
            content = (Path(clone_dir) / action.path).read_bytes()
            if is_virtual_file:
                await self._import_virtual_file(action.path, content)
            else:
                await file_storage.write_file(action.path, content)
                await self._update_github_sha(action.path, action.sha)

    # 2. Apply conflict resolutions
    for path, resolution in conflict_resolutions.items():
        if resolution == "keep_remote":
            # Pull remote version
            content = (Path(clone_dir) / path).read_bytes()
            # ... write to DB
        # keep_local: will be pushed below

    # 3. Mark orphaned workflows
    for orphan in preview.will_orphan:
        await self._mark_workflow_orphaned(orphan.workflow_id)

    # 4. Push local changes
    if files_to_push:
        commit_sha = await self._push_changes(files_to_push)
```

### Push Algorithm

```python
async def _push_changes(self, to_push: list[SyncAction]) -> str:
    # 1. Get current commit SHA
    current_sha = await self.github.get_ref(self.repo, f"heads/{self.branch}")
    current_commit = await self.github.get_commit(self.repo, current_sha)
    base_tree_sha = current_commit["tree"]["sha"]

    # 2. Pre-fetch all virtual files
    virtual_files_by_path = {vf.path: vf for vf in all_virtual_files}

    # 3. Create blobs for each file
    tree_items = []
    for action in to_push:
        if action.action == SyncActionType.DELETE:
            tree_items.append({"path": path, "sha": None, ...})
        else:
            content = get_content(action.path)  # From virtual files or S3
            blob_sha = await self.github.create_blob(self.repo, content)
            tree_items.append({"path": path, "sha": blob_sha, ...})

    # 4. Create new tree
    new_tree_sha = await self.github.create_tree(self.repo, tree_items, base_tree_sha)

    # 5. Create commit
    commit_sha = await self.github.create_commit(
        self.repo, "Sync from Bifrost", new_tree_sha, [current_sha]
    )

    # 6. Update branch ref
    await self.github.update_ref(self.repo, f"heads/{self.branch}", commit_sha)

    # 7. Update github_sha for pushed files
    for path, blob_sha in blob_shas.items():
        if not is_virtual_file(path):
            await self._update_github_sha(path, blob_sha)

    return commit_sha
```

---

## Orphan Detection & Protection

### What is an Orphan?

A workflow becomes **orphaned** when:
1. Its file is deleted (remotely)
2. Its file is modified and the function definition is removed

### Why It Matters

Orphaned workflows may still be referenced by forms, apps, or agents. Deleting them without warning could break production functionality.

### Detection Algorithm

```python
async def _detect_orphans(self, to_pull: list[SyncAction]) -> list[OrphanInfo]:
    orphans = []

    # Files being deleted
    for action in to_pull:
        if action.action == SyncActionType.DELETE and path.endswith(".py"):
            workflows = await self._get_workflows_in_file(path)
            for wf in workflows:
                used_by = await self._get_workflow_references(wf.id)
                orphans.append(OrphanInfo(
                    workflow_id=wf.id,
                    workflow_name=wf.name,
                    function_name=wf.function_name,
                    last_path=path,
                    used_by=used_by,
                ))

    # Files being modified - check if functions removed
    for action in to_pull:
        if action.action == SyncActionType.MODIFY and path.endswith(".py"):
            new_content = read_from_clone(path)
            workflows = await self._get_workflows_in_file(path)
            for wf in workflows:
                if not self._file_contains_function(new_content, wf.function_name):
                    orphans.append(...)

    return orphans
```

### OrphanInfo Model

```python
class OrphanInfo(BaseModel):
    workflow_id: str
    workflow_name: str
    function_name: str
    last_path: str
    used_by: list[WorkflowReference]  # Forms, apps, agents using this workflow
```

---

## WebSocket Integration

### Architecture

```
Client → HTTP POST /sync → Returns job_id
Client → WebSocket subscribe to git:{job_id}
Scheduler → Processes job
Scheduler → Publishes progress to git:{job_id}
Client → Receives real-time updates
```

### Message Types

**Progress Update:**
```json
{
  "type": "git_progress",
  "phase": "scanning",
  "current": 150,
  "total": 500,
  "path": "workflows/billing.py"
}
```

**Preview Complete:**
```json
{
  "type": "git_preview_complete",
  "data": { /* SyncPreviewResponse */ }
}
```

**Execute Complete:**
```json
{
  "type": "git_sync_complete",
  "data": { /* SyncExecuteResponse */ }
}
```

### Progress Phases

| Phase | Description |
|-------|-------------|
| `cloning` | Shallow cloning repository |
| `scanning` | Walking clone, computing SHAs |
| `loading_local` | Querying DB for local state |
| `serializing` | Generating virtual files |
| `comparing` | Comparing local vs remote |
| `analyzing_orphans` | Detecting orphan workflows |
| `analyzing_refs` | Checking workflow references |
| `pulling` | Applying remote changes |
| `resolving` | Applying conflict resolutions |
| `pushing` | Pushing local changes |

---

## API Endpoints

### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/github/config` | GET | Get current configuration |
| `/api/github/status` | GET | Get sync status overview |
| `/api/github/validate` | POST | Validate token, list repos, save token |
| `/api/github/configure` | POST | Save repo URL and branch |
| `/api/github/repositories` | GET | List accessible repos |
| `/api/github/branches` | GET | List branches in a repo |
| `/api/github/create-repository` | POST | Create new GitHub repo |
| `/api/github/disconnect` | POST | Remove GitHub config |

### Sync Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/github/sync` | GET | Queue preview job → returns job_id |
| `/api/github/sync` | POST | Queue execute job with resolutions |
| `/api/github/sync/content` | POST | Fetch local/remote content for diff |
| `/api/github/commits` | GET | Get commit history (paginated) |

---

## Pydantic Models Reference

### Request Models

```python
class SyncExecuteRequest(BaseModel):
    conflict_resolutions: dict[str, Literal["keep_local", "keep_remote", "skip"]]
    confirm_orphans: bool = False
    confirm_unresolved_refs: bool = False

class SyncContentRequest(BaseModel):
    path: str
    source: Literal["local", "remote"]
```

### Response Models

```python
class SyncPreviewJobResponse(BaseModel):
    job_id: str
    status: str = "queued"

class SyncPreviewResponse(BaseModel):
    to_pull: list[SyncAction]
    to_push: list[SyncAction]
    conflicts: list[SyncConflictInfo]
    will_orphan: list[OrphanInfo]
    unresolved_refs: list[SyncUnresolvedRefInfo]
    serialization_errors: list[SyncSerializationError]
    is_empty: bool

class SyncExecuteResponse(BaseModel):
    success: bool
    job_id: str | None
    status: str
    pulled: int
    pushed: int
    orphaned_workflows: list[str]
    commit_sha: str | None
    error: str | None
```

### Entity Models

```python
class SyncAction(BaseModel):
    path: str
    action: SyncActionType  # add, modify, delete
    sha: str | None
    display_name: str | None
    entity_type: str | None
    parent_slug: str | None

class SyncConflictInfo(BaseModel):
    path: str
    local_content: str | None
    remote_content: str | None
    local_sha: str
    remote_sha: str
    display_name: str | None
    entity_type: str | None
    parent_slug: str | None

class OrphanInfo(BaseModel):
    workflow_id: str
    workflow_name: str
    function_name: str
    last_path: str
    used_by: list[WorkflowReference]

class SyncUnresolvedRefInfo(BaseModel):
    entity_type: str
    entity_path: str
    field_path: str
    portable_ref: str

class SyncSerializationError(BaseModel):
    entity_type: str
    entity_id: str
    entity_name: str
    path: str
    error: str
```

---

## Database Models

### WorkspaceFile

```python
class WorkspaceFile(Base):
    __tablename__ = "workspace_files"

    id: UUID
    path: str                    # Unique file path
    content_hash: str            # SHA-256 for local changes
    size_bytes: int

    # Git sync state
    git_status: GitStatus        # UNTRACKED, SYNCED, MODIFIED, DELETED
    github_sha: str | None       # Git blob SHA when last synced

    # Soft delete
    is_deleted: bool

    # Entity routing
    entity_type: str | None      # workflow, form, app, agent, module
    entity_id: UUID | None

    # Module content (only for entity_type='module')
    content: str | None
```

### Key Indexes

```sql
-- Path lookups (filtered for active files)
CREATE INDEX ix_workspace_files_path ON workspace_files(path) WHERE NOT is_deleted;

-- Git status tracking
CREATE INDEX ix_workspace_files_git_status ON workspace_files(git_status) WHERE NOT is_deleted;

-- Module content lookups
CREATE INDEX ix_workspace_files_modules ON workspace_files(path)
    WHERE entity_type = 'module' AND NOT is_deleted;
```

---

## Error Handling

### Sync Errors

```python
class SyncError(Exception):
    """Base error for sync operations."""

class ConflictError(SyncError):
    """Unresolved conflicts exist."""
    def __init__(self, conflicts: list[str]):
        self.conflicts = conflicts

class OrphanError(SyncError):
    """User must confirm orphan workflows."""
    def __init__(self, orphans: list[str]):
        self.orphans = orphans

class UnresolvedRefsError(SyncError):
    """User must confirm unresolved workflow refs."""
    def __init__(self, unresolved_refs: list[UnresolvedRefInfo]):
        self.unresolved_refs = unresolved_refs
```

### GitHub API Errors

```python
class GitHubAPIError(Exception):
    """Error from GitHub API."""
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
```

### Error Flow

1. **Preview errors** - Returned in `serialization_errors` list, allows user to skip
2. **Validation errors** - Raised during `execute_sync()`, blocks execution
3. **Execution errors** - Returned in `SyncResult.error`, partial work may be committed

---

## Appendix: Complete Sync Flowchart

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SYNC PREVIEW                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Clone repo (shallow)                                                │
│         ↓                                                               │
│  2. Scan remote files, compute SHAs                                     │
│         ↓                                                               │
│  3. Extract virtual files from remote (by entity ID)                    │
│         ↓                                                               │
│  4. Query DB for local file SHAs + git_status                          │
│         ↓                                                               │
│  5. Serialize local virtual files                                       │
│         ↓                                                               │
│  6. Compare regular files using git_status decision matrix             │
│         ↓                                                               │
│  7. Compare virtual files by entity ID + SHA                           │
│         ↓                                                               │
│  8. Detect path collisions between pull/push                           │
│         ↓                                                               │
│  9. Detect orphan workflows                                            │
│         ↓                                                               │
│ 10. Detect unresolved workflow refs                                     │
│         ↓                                                               │
│ 11. Return SyncPreview                                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                         [User reviews preview]
                         [User resolves conflicts]
                         [User confirms orphans]
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                           SYNC EXECUTE                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Validate conflict resolutions, orphan confirmation                  │
│         ↓                                                               │
│  2. Clone repo for pulling                                              │
│         ↓                                                               │
│  3. PULL: For each to_pull action:                                      │
│     - DELETE → delete from DB (or virtual file table)                   │
│     - ADD/MODIFY → read from clone, write to DB, update github_sha     │
│         ↓                                                               │
│  4. RESOLVE: For each conflict:                                         │
│     - keep_remote → pull from clone                                     │
│     - keep_local → will be pushed below                                │
│         ↓                                                               │
│  5. Mark orphaned workflows (is_orphaned=True)                         │
│         ↓                                                               │
│  6. PUSH: Create blobs for each local file                             │
│         ↓                                                               │
│  7. Create new tree based on current commit's tree                     │
│         ↓                                                               │
│  8. Create commit                                                       │
│         ↓                                                               │
│  9. Update branch ref to new commit                                     │
│         ↓                                                               │
│ 10. Update github_sha for pushed files                                  │
│         ↓                                                               │
│ 11. Return SyncResult                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

The GitHub sync system provides:

1. **Bidirectional sync** - Pull changes from GitHub, push local changes
2. **Intelligent conflict detection** - Uses git_status to differentiate safe pulls from conflicts
3. **Virtual file abstraction** - Platform entities (forms, agents, apps) participate seamlessly
4. **Portable references** - Workflow UUIDs converted to path-based refs for cross-environment compatibility
5. **Production protection** - Orphan detection warns before breaking references
6. **Async execution** - Background jobs with WebSocket progress streaming

The key insight is that **the database is the source of truth for local state**, not a git working directory. This enables a clean API-based sync without the complexity of managing a local git repository.
