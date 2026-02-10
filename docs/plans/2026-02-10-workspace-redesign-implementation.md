# Workspace Architecture Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `workspace_files` table and `workflows.code` column with `_repo/` in S3 as durable file store, `file_index` table for search, and the virtual importer's Redis→S3 fallback for worker code loading.

**Architecture:** Single branch migration — all read/write paths are migrated to the new infrastructure, old columns and prewarming are removed, and git sync is updated to work without `workflows.code`. The branch must be internally consistent before merge.

**Tech Stack:** Python 3.11 (FastAPI, SQLAlchemy async, Pydantic), PostgreSQL, Redis, S3/MinIO, PyYAML

**Design Doc:** `docs/plans/2026-02-10-workspace-architecture-redesign.md`

---

## Progress

### Done (committed)

| Commit | Tasks | What |
|--------|-------|------|
| `036f0658` | 1-3 | PyYAML dep, `file_index` table, manifest parser |
| `9c03b40e` | 4-6 | Manifest generator, entity serializers, reserved prefix validation |
| `9a848a72` | 7-10 | RepoStorage, FileIndexService, S3 fallback, reconciler |
| `ebbe4e10` | 11, 15 | Dual-write in file_ops, sync lock |
| `22b4a846` | 12-14, 17a, 19 | Drop `workflows.code`, remove prewarming, migrate readers to `file_index` |

### Done (unstaged, needs commit)

| Tasks | What |
|-------|------|
| 16 | `workspace_files` table dropped — all refs removed, migration created, `ref_translation.py` + `git_tracker.py` deleted |
| 17c | `portable_ref` column dropped (included in Task 16 migration) |
| — | `code_editor.py` fully rewritten: modules/text use FileIndex, no WorkspaceFile |
| — | `reindex.py` rewritten: FileIndex upsert/hard-delete |
| — | `folder_ops.py` updated: returns `int` count, not `list[WorkspaceFile]` |
| — | `files.py` router updated: uses `FileEntry` dataclass |
| — | 14 test files updated, 2 test files removed (portable refs tests) |
| — | Storage integrity tests created (`test_storage_integrity.py`) |
| — | Git sync TDD tests created (`test_git_sync_local.py` — 19 stubs, all failing) |
| — | GitPython sync Pydantic models created (PreflightIssue, PreflightResult, updated SyncPreview) |

### Remaining work (this branch)

| Task | What | Status |
|------|------|--------|
| 18 | Implement GitPython sync (make `test_git_sync_local.py` pass) | TODO |
| — | Delete old E2E GitHub sync tests (`test_github.py`, `test_github_virtual_files.py`) | After Task 18 |
| — | Migrate entity files from JSON to YAML (`.form.json` → `.form.yaml`, `.agent.json` → `.agent.yaml`) | TODO |

### Current test status

**2852 pass, 23 fail.** All 23 failures are git sync tests waiting for Task 18:
- `test_git_sync_local.py` — 19 TDD stubs (need implementation)
- `test_github.py` — 1 old E2E test (will be deleted)
- `test_github_virtual_files.py` — 5 old E2E tests (will be deleted)

---

## Completed Tasks (reference only)

Tasks 1-15 and 19 are implemented. Their original specifications are preserved below for reference.

---

### Task 1: Add PyYAML and GitPython Dependencies ✅

**Status:** Committed in `036f0658`.

### Task 2: `file_index` Table and ORM Model ✅ — `036f0658`
Created `api/src/models/orm/file_index.py`, migration `20260210_file_index`, model exports.

### Task 3: Manifest Parser ✅ — `036f0658`
Created `api/src/services/manifest.py` with Pydantic models, parse/serialize/validate functions.

### Task 4: Manifest Generator ✅ — `9c03b40e`
Created `api/src/services/manifest_generator.py` — serializes DB state to Manifest object.

### Task 5: Entity File Serializers ✅ — `9c03b40e`
Created `api/src/services/entity_serializers.py` — form/agent/app to portable YAML.

### Task 6: Reserved Prefix Validation ✅ — `9c03b40e`
Created `api/src/core/reserved_prefixes.py` — blocks SDK access to `_repo/` and `_tmp/`.

### Task 7: RepoStorage Service ✅ — `9a848a72`
Created `api/src/services/repo_storage.py` — S3 operations scoped to `_repo/` prefix.

### Task 8: FileIndexService ✅ — `9a848a72`
Created `api/src/services/file_index_service.py` — dual-write facade (S3 + DB).

### Task 9: Virtual Importer S3 Fallback ✅ — `9a848a72`
Modified `api/src/core/module_cache_sync.py` — Redis miss → S3 `_repo/` fallback → cache to Redis.

### Task 10: File Index Reconciler ✅ — `9a848a72`
Created `api/src/services/file_index_reconciler.py` — heals drift between S3 and `file_index`.

### Task 11: Dual-Write in FileStorageService ✅ — `ebbe4e10`
Modified `api/src/services/file_storage/file_ops.py` — writes/deletes go to old path + `_repo/`/`file_index` via savepoint.

### Task 12: Execution Service Code Loading ✅ — unstaged
Modified `api/src/services/execution/service.py` — loads code from `file_index`, falls back to Redis→S3.

### Task 13: MCP + Editor Search Migration ✅ — unstaged
Modified `code_editor.py`, `editor/search.py`, `workflow_orphan.py`, `routers/workflows.py` — all read code from `file_index`.

### Task 14: Content Hash Pinning ✅ — unstaged
Modified `workflow_execution.py` consumer — queries `file_index` for `content_hash` at dispatch.

### Task 15: Sync Lock ✅ — `ebbe4e10`
Created `api/src/services/sync_lock.py` — Redis distributed lock for git sync.

### Task 19: Remove Module Cache Prewarming ✅ — unstaged
Removed `warm_cache_from_db` from `module_cache.py`, `_sync_module_cache` from consumer, module warming step from `init_container.py`.

<details>
<summary>Original detailed task specifications (click to expand)</summary>

### Task 2: Create `file_index` Table and ORM Model ✅

**Why:** Replaces `workspace_files` as the search index. Simple table: `path` (PK), `content`, `content_hash`, `updated_at`.

**Files:**
- Create: `api/src/models/orm/file_index.py`
- Modify: `api/src/models/orm/__init__.py` (export new model)
- Modify: `api/src/models/__init__.py` (export new model)
- Create: `api/alembic/versions/20260210_file_index.py`
- Create: `api/tests/unit/test_file_index_model.py`

**Step 1: Write the test**

Create `api/tests/unit/test_file_index_model.py`:

```python
"""Tests for FileIndex ORM model."""
import pytest
from datetime import datetime, timezone


def test_file_index_model_exists():
    """FileIndex model can be imported."""
    from src.models.orm.file_index import FileIndex
    assert FileIndex.__tablename__ == "file_index"


def test_file_index_columns():
    """FileIndex has expected columns."""
    from src.models.orm.file_index import FileIndex
    columns = {c.name for c in FileIndex.__table__.columns}
    assert "path" in columns
    assert "content" in columns
    assert "content_hash" in columns
    assert "updated_at" in columns


def test_file_index_primary_key():
    """Path is the primary key."""
    from src.models.orm.file_index import FileIndex
    pk_cols = [c.name for c in FileIndex.__table__.primary_key.columns]
    assert pk_cols == ["path"]
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_file_index_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'FileIndex'`

**Step 3: Create the ORM model**

Create `api/src/models/orm/file_index.py`:

```python
"""
FileIndex ORM model.

Search index for text content in _repo/. Populated via dual-write
whenever files are written to S3. Only indexes text-searchable files
(.py, .yaml, .md, .txt, etc.). No entity routing, no polymorphic references.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class FileIndex(Base):
    """Search index for workspace files in _repo/."""

    __tablename__ = "file_index"

    path: Mapped[str] = mapped_column(String(1000), primary_key=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

**Step 4: Add to model exports**

In `api/src/models/orm/__init__.py`, add:
```python
from src.models.orm.file_index import FileIndex
```

In `api/src/models/__init__.py`, add `FileIndex` to the imports from `src.models.orm`.

**Step 5: Create alembic migration**

Create `api/alembic/versions/20260210_file_index.py`:

```python
"""Create file_index table.

Revision ID: 20260210_file_index
Revises: <previous_head>
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20260210_file_index"
down_revision = None  # Set to actual previous head
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_index",
        sa.Column("path", sa.String(1000), primary_key=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("file_index")
```

**Note:** Set `down_revision` to the actual current head. Run `cd api && alembic heads` to find it.

**Step 6: Run test to verify it passes**

Run: `./test.sh tests/unit/test_file_index_model.py -v`
Expected: PASS

**Step 7: Apply migration and run full test suite**

Restart `bifrost-init` container to apply migration, then restart API:
```bash
docker restart bifrost-init-1 && sleep 5 && docker restart bifrost-dev-api-1
```

Run: `./test.sh`
Expected: All tests pass

**Step 8: Commit**

```bash
git add api/src/models/orm/file_index.py api/src/models/orm/__init__.py api/src/models/__init__.py api/alembic/versions/20260210_file_index.py api/tests/unit/test_file_index_model.py
git commit -m "feat: create file_index table for workspace search"
```

---

### Task 3: Manifest Parser — Read, Write, Validate ✅

**Status:** Committed in `036f0658`.

**Why:** Core library for reading/writing `.bifrost/metadata.yaml`. Used by every subsequent task. Stateless functions, no DB dependency.

**Files:**
- Create: `api/src/services/manifest.py`
- Create: `api/tests/unit/test_manifest.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_manifest.py`:

```python
"""Tests for manifest parser."""
import pytest
from uuid import uuid4

import yaml


@pytest.fixture
def sample_manifest():
    """A valid manifest dict."""
    org_id = str(uuid4())
    role_id = str(uuid4())
    wf_id = str(uuid4())
    form_id = str(uuid4())
    return {
        "organizations": [{"id": org_id, "name": "TestOrg"}],
        "roles": [{"id": role_id, "name": "admin", "organization_id": org_id}],
        "workflows": {
            "my_workflow": {
                "id": wf_id,
                "path": "workflows/my_workflow.py",
                "function_name": "my_workflow",
                "type": "workflow",
                "organization_id": org_id,
                "roles": [role_id],
                "access_level": "role_based",
                "endpoint_enabled": False,
                "timeout_seconds": 1800,
            },
        },
        "forms": {
            "my_form": {
                "id": form_id,
                "path": "forms/my_form.form.yaml",
                "organization_id": org_id,
                "roles": [role_id],
            },
        },
        "agents": {},
        "apps": {},
    }


def test_parse_manifest_from_yaml(sample_manifest):
    """Parse a YAML string into a Manifest object."""
    from src.services.manifest import parse_manifest

    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    assert "my_workflow" in manifest.workflows
    assert manifest.workflows["my_workflow"].path == "workflows/my_workflow.py"
    assert manifest.workflows["my_workflow"].function_name == "my_workflow"
    assert manifest.workflows["my_workflow"].type == "workflow"


def test_serialize_manifest(sample_manifest):
    """Serialize a Manifest back to YAML string."""
    from src.services.manifest import parse_manifest, serialize_manifest

    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    output = serialize_manifest(manifest)
    # Should be valid YAML
    reparsed = yaml.safe_load(output)
    assert "workflows" in reparsed
    assert "my_workflow" in reparsed["workflows"]


def test_validate_manifest_broken_ref(sample_manifest):
    """Detect broken cross-references."""
    from src.services.manifest import parse_manifest, validate_manifest

    # Form references a workflow UUID that exists — should be fine
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert len(errors) == 0


def test_validate_manifest_missing_org(sample_manifest):
    """Detect reference to non-existent organization."""
    from src.services.manifest import parse_manifest, validate_manifest

    sample_manifest["workflows"]["my_workflow"]["organization_id"] = str(uuid4())
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert any("organization" in e.lower() for e in errors)


def test_validate_manifest_missing_role(sample_manifest):
    """Detect reference to non-existent role."""
    from src.services.manifest import parse_manifest, validate_manifest

    sample_manifest["workflows"]["my_workflow"]["roles"] = [str(uuid4())]
    yaml_str = yaml.dump(sample_manifest, default_flow_style=False)
    manifest = parse_manifest(yaml_str)
    errors = validate_manifest(manifest)
    assert any("role" in e.lower() for e in errors)


def test_empty_manifest():
    """Empty manifest should parse without error."""
    from src.services.manifest import parse_manifest

    manifest = parse_manifest("")
    assert len(manifest.workflows) == 0
    assert len(manifest.forms) == 0


def test_get_entity_ids():
    """Get all entity UUIDs from manifest."""
    from src.services.manifest import parse_manifest, get_all_entity_ids

    yaml_str = """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
    type: workflow
forms:
  form1:
    id: "22222222-2222-2222-2222-222222222222"
    path: forms/form1.form.yaml
"""
    manifest = parse_manifest(yaml_str)
    ids = get_all_entity_ids(manifest)
    assert "11111111-1111-1111-1111-111111111111" in ids
    assert "22222222-2222-2222-2222-222222222222" in ids


def test_get_paths():
    """Get all file paths from manifest."""
    from src.services.manifest import parse_manifest, get_all_paths

    yaml_str = """
workflows:
  wf1:
    id: "11111111-1111-1111-1111-111111111111"
    path: workflows/wf1.py
    function_name: wf1
    type: workflow
forms:
  form1:
    id: "22222222-2222-2222-2222-222222222222"
    path: forms/form1.form.yaml
"""
    manifest = parse_manifest(yaml_str)
    paths = get_all_paths(manifest)
    assert "workflows/wf1.py" in paths
    assert "forms/form1.form.yaml" in paths
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_manifest.py -v`
Expected: FAIL — `ImportError`

**Step 3: Implement the manifest parser**

Create `api/src/services/manifest.py`:

```python
"""
Manifest parser for .bifrost/metadata.yaml.

Provides Pydantic models and functions for reading, writing, and validating
the workspace manifest. The manifest declares all platform entities,
their file paths, UUIDs, org bindings, roles, and runtime config.

Stateless — no DB or S3 dependency.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class ManifestOrganization(BaseModel):
    """Organization entry in manifest."""
    id: str
    name: str


class ManifestRole(BaseModel):
    """Role entry in manifest."""
    id: str
    name: str
    organization_id: str | None = None


class ManifestWorkflow(BaseModel):
    """Workflow entry in manifest."""
    id: str
    path: str
    function_name: str
    type: str = "workflow"  # workflow | tool | data_provider
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)  # Role UUIDs
    access_level: str = "role_based"
    endpoint_enabled: bool = False
    timeout_seconds: int = 1800
    public_endpoint: bool = False
    # Additional optional config
    category: str = "General"
    tags: list[str] = Field(default_factory=list)


class ManifestForm(BaseModel):
    """Form entry in manifest."""
    id: str
    path: str
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class ManifestAgent(BaseModel):
    """Agent entry in manifest."""
    id: str
    path: str
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class ManifestApp(BaseModel):
    """App entry in manifest."""
    id: str
    path: str
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    """The complete workspace manifest."""
    organizations: list[ManifestOrganization] = Field(default_factory=list)
    roles: list[ManifestRole] = Field(default_factory=list)
    workflows: dict[str, ManifestWorkflow] = Field(default_factory=dict)
    forms: dict[str, ManifestForm] = Field(default_factory=dict)
    agents: dict[str, ManifestAgent] = Field(default_factory=dict)
    apps: dict[str, ManifestApp] = Field(default_factory=dict)


# =============================================================================
# Parse / Serialize
# =============================================================================


def parse_manifest(yaml_str: str) -> Manifest:
    """Parse a YAML string into a Manifest object."""
    if not yaml_str or not yaml_str.strip():
        return Manifest()

    data = yaml.safe_load(yaml_str)
    if not data or not isinstance(data, dict):
        return Manifest()

    return Manifest(**data)


def serialize_manifest(manifest: Manifest) -> str:
    """Serialize a Manifest object to a YAML string."""
    data = manifest.model_dump(mode="json", exclude_none=False)
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


# =============================================================================
# Validation
# =============================================================================


def validate_manifest(manifest: Manifest) -> list[str]:
    """
    Validate cross-references within the manifest.

    Checks:
    - All organization_id references point to declared organizations
    - All role references point to declared roles

    Returns a list of human-readable error strings. Empty list = valid.
    """
    errors: list[str] = []

    org_ids = {org.id for org in manifest.organizations}
    role_ids = {role.id for role in manifest.roles}

    # Check organization references
    for name, wf in manifest.workflows.items():
        if wf.organization_id and wf.organization_id not in org_ids:
            errors.append(f"Workflow '{name}' references unknown organization: {wf.organization_id}")
        for role_id in wf.roles:
            if role_id not in role_ids:
                errors.append(f"Workflow '{name}' references unknown role: {role_id}")

    for name, form in manifest.forms.items():
        if form.organization_id and form.organization_id not in org_ids:
            errors.append(f"Form '{name}' references unknown organization: {form.organization_id}")
        for role_id in form.roles:
            if role_id not in role_ids:
                errors.append(f"Form '{name}' references unknown role: {role_id}")

    for name, agent in manifest.agents.items():
        if agent.organization_id and agent.organization_id not in org_ids:
            errors.append(f"Agent '{name}' references unknown organization: {agent.organization_id}")
        for role_id in agent.roles:
            if role_id not in role_ids:
                errors.append(f"Agent '{name}' references unknown role: {role_id}")

    for name, app in manifest.apps.items():
        if app.organization_id and app.organization_id not in org_ids:
            errors.append(f"App '{name}' references unknown organization: {app.organization_id}")
        for role_id in app.roles:
            if role_id not in role_ids:
                errors.append(f"App '{name}' references unknown role: {role_id}")

    return errors


# =============================================================================
# Utilities
# =============================================================================


def get_all_entity_ids(manifest: Manifest) -> set[str]:
    """Get all entity UUIDs declared in the manifest."""
    ids: set[str] = set()
    for wf in manifest.workflows.values():
        ids.add(wf.id)
    for form in manifest.forms.values():
        ids.add(form.id)
    for agent in manifest.agents.values():
        ids.add(agent.id)
    for app in manifest.apps.values():
        ids.add(app.id)
    return ids


def get_all_paths(manifest: Manifest) -> set[str]:
    """Get all file paths declared in the manifest."""
    paths: set[str] = set()
    for wf in manifest.workflows.values():
        paths.add(wf.path)
    for form in manifest.forms.values():
        paths.add(form.path)
    for agent in manifest.agents.values():
        paths.add(agent.path)
    for app in manifest.apps.values():
        paths.add(app.path)
    return paths
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_manifest.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/manifest.py api/tests/unit/test_manifest.py
git commit -m "feat: add manifest parser for .bifrost/metadata.yaml"
```

---

### Task 4: Manifest Generator — Serialize Platform State to Manifest ✅

**Status:** Committed in `9c03b40e`.

**Why:** Generates `.bifrost/metadata.yaml` from existing DB state. Required for first-time git connection and initial export.

**Files:**
- Create: `api/src/services/manifest_generator.py`
- Create: `api/tests/unit/test_manifest_generator.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_manifest_generator.py`:

```python
"""Tests for manifest generator — serializes DB state to manifest."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


@pytest.fixture
def mock_db():
    return AsyncMock()


def _mock_workflow(name="test_wf", org_id=None):
    wf = MagicMock()
    wf.id = uuid4()
    wf.name = name
    wf.function_name = name
    wf.path = f"workflows/{name}.py"
    wf.type = "workflow"
    wf.organization_id = org_id
    wf.access_level = "role_based"
    wf.endpoint_enabled = False
    wf.timeout_seconds = 1800
    wf.public_endpoint = False
    wf.category = "General"
    wf.tags = []
    wf.is_active = True
    wf.workflow_roles = []
    return wf


def _mock_form(name="test_form", org_id=None, workflow_id=None):
    form = MagicMock()
    form.id = uuid4()
    form.name = name
    form.organization_id = org_id
    form.workflow_id = str(workflow_id) if workflow_id else None
    form.is_active = True
    form.form_roles = []
    return form


@pytest.mark.asyncio
async def test_generate_manifest_with_workflow(mock_db):
    """Should include active workflows in manifest."""
    from src.services.manifest_generator import generate_manifest

    wf = _mock_workflow()

    # Mock: workflows query returns our workflow
    wf_result = MagicMock()
    wf_result.scalars.return_value.all.return_value = [wf]

    # Mock: other queries return empty
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[
        wf_result,     # workflows
        empty_result,  # forms
        empty_result,  # agents
        empty_result,  # apps
        empty_result,  # organizations
        empty_result,  # roles
    ])

    manifest = await generate_manifest(mock_db)

    assert "test_wf" in manifest.workflows
    assert manifest.workflows["test_wf"].id == str(wf.id)
    assert manifest.workflows["test_wf"].path == "workflows/test_wf.py"


@pytest.mark.asyncio
async def test_generate_manifest_empty_db(mock_db):
    """Empty DB should produce empty manifest."""
    from src.services.manifest_generator import generate_manifest

    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=empty_result)

    manifest = await generate_manifest(mock_db)

    assert len(manifest.workflows) == 0
    assert len(manifest.forms) == 0
    assert len(manifest.agents) == 0
    assert len(manifest.apps) == 0
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_manifest_generator.py -v`
Expected: FAIL

**Step 3: Implement the manifest generator**

Create `api/src/services/manifest_generator.py`:

```python
"""
Manifest Generator — serializes current platform DB state to a Manifest.

Used for:
- First-time git connection (export platform state)
- Manual "export to manifest" operations
- Reconciliation verification
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.orm.agents import Agent
from src.models.orm.applications import Application
from src.models.orm.forms import Form
from src.models.orm.organizations import Organization
from src.models.orm.users import Role
from src.models.orm.workflows import Workflow
from src.services.manifest import (
    Manifest,
    ManifestAgent,
    ManifestApp,
    ManifestForm,
    ManifestOrganization,
    ManifestRole,
    ManifestWorkflow,
)

logger = logging.getLogger(__name__)


async def generate_manifest(db: AsyncSession) -> Manifest:
    """
    Generate a Manifest from current DB state.

    Queries all active entities and builds a complete manifest
    with org bindings, role assignments, and runtime config.
    """
    # Fetch all active workflows
    wf_result = await db.execute(
        select(Workflow).where(Workflow.is_active == True)  # noqa: E712
    )
    workflows_list = wf_result.scalars().all()

    # Fetch all active forms
    form_result = await db.execute(
        select(Form).where(Form.is_active == True)  # noqa: E712
    )
    forms_list = form_result.scalars().all()

    # Fetch all active agents
    agent_result = await db.execute(
        select(Agent).where(Agent.is_active == True)  # noqa: E712
    )
    agents_list = agent_result.scalars().all()

    # Fetch all active apps
    app_result = await db.execute(
        select(Application).where(Application.is_active == True)  # noqa: E712
    )
    apps_list = app_result.scalars().all()

    # Fetch organizations
    org_result = await db.execute(select(Organization))
    orgs_list = org_result.scalars().all()

    # Fetch roles
    role_result = await db.execute(select(Role))
    roles_list = role_result.scalars().all()

    # Build manifest
    manifest = Manifest(
        organizations=[
            ManifestOrganization(id=str(org.id), name=org.name)
            for org in orgs_list
        ],
        roles=[
            ManifestRole(
                id=str(role.id),
                name=role.name,
                organization_id=str(role.organization_id) if role.organization_id else None,
            )
            for role in roles_list
        ],
        workflows={
            wf.name: ManifestWorkflow(
                id=str(wf.id),
                path=wf.path,
                function_name=wf.function_name,
                type=wf.type or "workflow",
                organization_id=str(wf.organization_id) if wf.organization_id else None,
                roles=[str(wr.role_id) for wr in wf.workflow_roles] if hasattr(wf, 'workflow_roles') and wf.workflow_roles else [],
                access_level=wf.access_level or "role_based",
                endpoint_enabled=wf.endpoint_enabled or False,
                timeout_seconds=wf.timeout_seconds or 1800,
                public_endpoint=wf.public_endpoint or False,
                category=wf.category or "General",
                tags=wf.tags or [],
            )
            for wf in workflows_list
        },
        forms={
            form.name: ManifestForm(
                id=str(form.id),
                path=f"forms/{form.id}.form.yaml",
                organization_id=str(form.organization_id) if form.organization_id else None,
                roles=[str(fr.role_id) for fr in form.form_roles] if hasattr(form, 'form_roles') and form.form_roles else [],
            )
            for form in forms_list
        },
        agents={
            agent.name: ManifestAgent(
                id=str(agent.id),
                path=f"agents/{agent.id}.agent.yaml",
                organization_id=str(agent.organization_id) if agent.organization_id else None,
                roles=[],
            )
            for agent in agents_list
        },
        apps={
            app.name: ManifestApp(
                id=str(app.id),
                path=f"apps/{app.slug or app.id}/app.yaml",
                organization_id=str(app.organization_id) if app.organization_id else None,
                roles=[],
            )
            for app in apps_list
        },
    )

    logger.info(
        f"Generated manifest: {len(manifest.workflows)} workflows, "
        f"{len(manifest.forms)} forms, {len(manifest.agents)} agents, "
        f"{len(manifest.apps)} apps"
    )

    return manifest
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_manifest_generator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/manifest_generator.py api/tests/unit/test_manifest_generator.py
git commit -m "feat: add manifest generator to serialize DB state to metadata.yaml"
```

---

### Task 5: Entity File Serializers — Form/Agent/App to YAML ✅

**Status:** Committed in `9c03b40e`.

**Why:** Serialize forms, agents, and apps to portable `.yaml` files. Used when exporting to `_repo/` and for git sync.

**Files:**
- Create: `api/src/services/entity_serializers.py`
- Create: `api/tests/unit/test_entity_serializers.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_entity_serializers.py`:

```python
"""Tests for entity serializers — DB entities to YAML files."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

import yaml


def _mock_form_with_fields():
    form = MagicMock()
    form.id = uuid4()
    form.name = "Test Form"
    form.description = "A test form"
    form.workflow_id = str(uuid4())
    form.launch_workflow_id = None

    field1 = MagicMock()
    field1.name = "email"
    field1.field_type = "text"
    field1.label = "Email Address"
    field1.required = True
    field1.default_value = None
    field1.options = None
    field1.sort_order = 0

    field2 = MagicMock()
    field2.name = "department"
    field2.field_type = "select"
    field2.label = "Department"
    field2.required = False
    field2.default_value = "Engineering"
    field2.options = ["Engineering", "Sales", "Support"]
    field2.sort_order = 1

    form.fields = [field1, field2]
    return form


def _mock_agent():
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Test Agent"
    agent.description = "A test agent"
    agent.system_prompt = "You are a helpful agent."
    agent.llm_model = "claude-sonnet-4-5-20250929"
    agent.llm_temperature = 0.7
    agent.llm_max_tokens = 4096

    tool1 = MagicMock()
    tool1.id = uuid4()
    agent.tools = [tool1]
    return agent


def test_serialize_form():
    """Serialize a form to YAML."""
    from src.services.entity_serializers import serialize_form_to_yaml

    form = _mock_form_with_fields()
    yaml_str = serialize_form_to_yaml(form)
    data = yaml.safe_load(yaml_str)

    assert data["name"] == "Test Form"
    assert data["description"] == "A test form"
    assert data["workflow"] == str(form.workflow_id)
    assert len(data["fields"]) == 2
    assert data["fields"][0]["name"] == "email"
    assert data["fields"][0]["type"] == "text"
    assert data["fields"][0]["required"] is True


def test_serialize_agent():
    """Serialize an agent to YAML."""
    from src.services.entity_serializers import serialize_agent_to_yaml

    agent = _mock_agent()
    yaml_str = serialize_agent_to_yaml(agent)
    data = yaml.safe_load(yaml_str)

    assert data["name"] == "Test Agent"
    assert data["system_prompt"] == "You are a helpful agent."
    assert len(data["tools"]) == 1
    assert data["tools"][0] == str(agent.tools[0].id)


def test_serialize_form_round_trip():
    """Serialized YAML should be valid and parseable."""
    from src.services.entity_serializers import serialize_form_to_yaml

    form = _mock_form_with_fields()
    yaml_str = serialize_form_to_yaml(form)
    # Should parse without error
    data = yaml.safe_load(yaml_str)
    assert isinstance(data, dict)
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_entity_serializers.py -v`
Expected: FAIL

**Step 3: Implement entity serializers**

Create `api/src/services/entity_serializers.py`:

```python
"""
Entity Serializers — convert DB entities to portable YAML files.

These YAML files contain no org, roles, or instance config.
Cross-references use UUIDs.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def serialize_form_to_yaml(form: Any) -> str:
    """Serialize a Form ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": form.name,
        "description": form.description,
        "workflow": str(form.workflow_id) if form.workflow_id else None,
        "launch_workflow": str(form.launch_workflow_id) if form.launch_workflow_id else None,
    }

    fields = []
    for field in sorted(form.fields, key=lambda f: f.sort_order):
        field_data: dict[str, Any] = {
            "name": field.name,
            "type": field.field_type,
            "label": field.label,
        }
        if field.required:
            field_data["required"] = True
        if field.default_value is not None:
            field_data["default"] = field.default_value
        if field.options:
            field_data["options"] = field.options
        fields.append(field_data)

    data["fields"] = fields

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def serialize_agent_to_yaml(agent: Any) -> str:
    """Serialize an Agent ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "llm_model": agent.llm_model,
    }

    if agent.llm_temperature is not None:
        data["llm_temperature"] = agent.llm_temperature
    if agent.llm_max_tokens is not None:
        data["llm_max_tokens"] = agent.llm_max_tokens

    # Tools are referenced by UUID
    if agent.tools:
        data["tools"] = [str(tool.id) for tool in agent.tools]
    else:
        data["tools"] = []

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def serialize_app_to_yaml(app: Any) -> str:
    """Serialize an Application ORM object to portable YAML."""
    data: dict[str, Any] = {
        "name": app.name,
        "description": getattr(app, "description", None),
    }

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_entity_serializers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/entity_serializers.py api/tests/unit/test_entity_serializers.py
git commit -m "feat: add entity serializers for form/agent/app YAML export"
```

---

### Task 6: SDK File Location — Free-form Strings with Reserved Prefix Validation ✅

**Status:** Committed in `9c03b40e`.

**Why:** Replace the static `Location = Literal["workspace", "temp", "uploads"]` enum with free-form strings validated against a reserved prefix blocklist. Protects `_repo/` and `_tmp/` from SDK access.

**Files:**
- Modify: `api/src/services/file_backend.py:19` (Location type)
- Modify: `api/src/routers/files.py:50` (Location type)
- Modify: `api/bifrost/files.py:33` (Location type)
- Create: `api/src/core/reserved_prefixes.py`
- Create: `api/tests/unit/test_reserved_prefixes.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_reserved_prefixes.py`:

```python
"""Tests for reserved prefix validation."""
import pytest


def test_repo_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_repo")


def test_repo_slash_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_repo/something")


def test_tmp_prefix_rejected():
    from src.core.reserved_prefixes import validate_sdk_location
    with pytest.raises(ValueError, match="reserved"):
        validate_sdk_location("_tmp")


def test_regular_location_accepted():
    from src.core.reserved_prefixes import validate_sdk_location
    # Should not raise
    validate_sdk_location("uploads")
    validate_sdk_location("exports")
    validate_sdk_location("my-custom-folder")
    validate_sdk_location("data/subfolder")


def test_empty_string_accepted():
    """Empty string = root of bucket (workspace), should be fine."""
    from src.core.reserved_prefixes import validate_sdk_location
    validate_sdk_location("")


def test_workspace_legacy_accepted():
    """Legacy 'workspace' location should still work."""
    from src.core.reserved_prefixes import validate_sdk_location
    validate_sdk_location("workspace")
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_reserved_prefixes.py -v`
Expected: FAIL

**Step 3: Implement reserved prefix validation**

Create `api/src/core/reserved_prefixes.py`:

```python
"""
Reserved S3 prefix validation.

Prevents SDK file operations from accessing platform-managed prefixes.
"""

RESERVED_PREFIXES = frozenset({"_repo", "_tmp"})


def validate_sdk_location(location: str) -> None:
    """
    Validate that an SDK file location is not a reserved prefix.

    Raises ValueError if the location starts with a reserved prefix.
    """
    normalized = location.strip("/")
    for prefix in RESERVED_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            raise ValueError(
                f"Location '{location}' is reserved for platform use. "
                f"Reserved prefixes: {', '.join(sorted(RESERVED_PREFIXES))}"
            )
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_reserved_prefixes.py -v`
Expected: PASS

**Step 5: Wire validation into file backend and router**

This is a wiring step — add `validate_sdk_location()` calls at the entry points of the file backend. The exact integration depends on how `Location` is used in the S3Backend. The key change is:

In `api/src/services/file_backend.py`, in the `S3Backend` methods (`read`, `write`, `delete`, `list`, `exists`), add at the top:
```python
from src.core.reserved_prefixes import validate_sdk_location
validate_sdk_location(location)
```

In `api/src/routers/files.py`, change the `Location` type from `Literal["workspace", "temp", "uploads"]` to `str` and add validation in each endpoint handler.

In `api/bifrost/files.py`, change `Location` from `Literal["workspace", "temp", "uploads"]` to `str`.

**Step 6: Run full test suite**

Run: `./test.sh`
Expected: All tests pass (existing tests may need minor updates if they hardcode the `Location` type)

**Step 7: Commit**

```bash
git add api/src/core/reserved_prefixes.py api/tests/unit/test_reserved_prefixes.py api/src/services/file_backend.py api/src/routers/files.py api/bifrost/files.py
git commit -m "feat: replace static Location enum with free-form strings and reserved prefix validation"
```

---

### Task 7: S3 Repo Service — Read/Write/List for `_repo/` Prefix ✅

**Status:** Committed in `9a848a72`.

**Why:** Dedicated service for `_repo/` operations. Wraps the existing S3 client with the `_repo/` prefix. Used by manifest operations, content tools, and virtual importer.

**Files:**
- Create: `api/src/services/repo_storage.py`
- Create: `api/tests/unit/test_repo_storage.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_repo_storage.py`:

```python
"""Tests for repo storage service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_s3_client():
    client = AsyncMock()
    client.put_object = AsyncMock()
    client.get_object = AsyncMock()
    client.delete_object = AsyncMock()
    client.list_objects_v2 = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_write_prepends_repo_prefix(mock_s3_client):
    """Writing to 'workflows/test.py' should write to '_repo/workflows/test.py' in S3."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    # Patch get_client to return our mock
    mock_s3_client.put_object = AsyncMock()

    await storage._write_to_s3(mock_s3_client, "workflows/test.py", b"print('hello')")

    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args[1]
    assert call_kwargs["Key"] == "_repo/workflows/test.py"


@pytest.mark.asyncio
async def test_read_prepends_repo_prefix(mock_s3_client):
    """Reading 'workflows/test.py' should read from '_repo/workflows/test.py' in S3."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    body_mock = AsyncMock()
    body_mock.read = AsyncMock(return_value=b"print('hello')")
    mock_s3_client.get_object = AsyncMock(return_value={"Body": body_mock})

    content = await storage._read_from_s3(mock_s3_client, "workflows/test.py")

    mock_s3_client.get_object.assert_called_once()
    call_kwargs = mock_s3_client.get_object.call_args[1]
    assert call_kwargs["Key"] == "_repo/workflows/test.py"
    assert content == b"print('hello')"


@pytest.mark.asyncio
async def test_list_prepends_and_strips_prefix(mock_s3_client):
    """Listing should use _repo/ prefix and strip it from results."""
    from src.services.repo_storage import RepoStorage

    storage = RepoStorage.__new__(RepoStorage)
    storage._bucket = "test-bucket"

    mock_s3_client.list_objects_v2 = AsyncMock(return_value={
        "Contents": [
            {"Key": "_repo/workflows/a.py"},
            {"Key": "_repo/workflows/b.py"},
            {"Key": "_repo/.bifrost/metadata.yaml"},
        ],
        "IsTruncated": False,
    })

    paths = await storage._list_from_s3(mock_s3_client, prefix="workflows/")

    assert "workflows/a.py" in paths
    assert "workflows/b.py" in paths
    assert ".bifrost/metadata.yaml" not in paths  # filtered by prefix
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_repo_storage.py -v`
Expected: FAIL

**Step 3: Implement repo storage**

Create `api/src/services/repo_storage.py`:

```python
"""
Repo Storage Service — S3 operations scoped to _repo/ prefix.

All paths are relative to _repo/. Callers pass "workflows/test.py"
and this service reads/writes "_repo/workflows/test.py" in S3.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager

from aiobotocore.session import get_session

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

REPO_PREFIX = "_repo/"


class RepoStorage:
    """S3 storage scoped to _repo/ prefix."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._bucket = self._settings.s3_bucket

    @asynccontextmanager
    async def _get_client(self):
        session = get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
            region_name=self._settings.s3_region,
        ) as client:
            yield client

    def _repo_key(self, path: str) -> str:
        """Convert relative path to S3 key with _repo/ prefix."""
        return f"{REPO_PREFIX}{path.lstrip('/')}"

    async def read(self, path: str) -> bytes:
        """Read a file from _repo/."""
        async with self._get_client() as client:
            return await self._read_from_s3(client, path)

    async def _read_from_s3(self, client, path: str) -> bytes:
        key = self._repo_key(path)
        response = await client.get_object(Bucket=self._bucket, Key=key)
        return await response["Body"].read()

    async def write(self, path: str, content: bytes) -> str:
        """Write a file to _repo/. Returns content hash."""
        async with self._get_client() as client:
            return await self._write_to_s3(client, path, content)

    async def _write_to_s3(self, client, path: str, content: bytes) -> str:
        key = self._repo_key(path)
        content_hash = hashlib.sha256(content).hexdigest()
        await client.put_object(Bucket=self._bucket, Key=key, Body=content)
        return content_hash

    async def delete(self, path: str) -> None:
        """Delete a file from _repo/."""
        async with self._get_client() as client:
            key = self._repo_key(path)
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def list(self, prefix: str = "") -> list[str]:
        """List files in _repo/ with optional sub-prefix. Returns relative paths."""
        async with self._get_client() as client:
            return await self._list_from_s3(client, prefix)

    async def _list_from_s3(self, client, prefix: str = "") -> list[str]:
        full_prefix = self._repo_key(prefix)
        paths: list[str] = []
        continuation_token = None

        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": full_prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = await client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                # Strip _repo/ prefix from key
                rel_path = obj["Key"][len(REPO_PREFIX):]
                paths.append(rel_path)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return paths

    async def exists(self, path: str) -> bool:
        """Check if a file exists in _repo/."""
        try:
            async with self._get_client() as client:
                key = self._repo_key(path)
                await client.head_object(Bucket=self._bucket, Key=key)
                return True
        except Exception:
            return False

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_repo_storage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/repo_storage.py api/tests/unit/test_repo_storage.py
git commit -m "feat: add RepoStorage service for _repo/ S3 operations"
```

---

### Task 8: File Index Service — Dual-Write Facade ✅

**Status:** Committed in `9a848a72`.

**Why:** Wraps RepoStorage and `file_index` DB table. Every write goes to both S3 and DB. Provides search/read via DB. This is the central write path all other components will use.

**Files:**
- Create: `api/src/services/file_index_service.py`
- Create: `api/tests/unit/test_file_index_service.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_file_index_service.py`:

```python
"""Tests for file index service — dual-write to S3 + DB."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_repo_storage():
    storage = AsyncMock()
    storage.write = AsyncMock(return_value="abc123hash")
    storage.read = AsyncMock(return_value=b"file content")
    storage.delete = AsyncMock()
    storage.list = AsyncMock(return_value=["workflows/a.py", "modules/b.py"])
    return storage


@pytest.mark.asyncio
async def test_write_updates_s3_and_db(mock_db, mock_repo_storage):
    """Write should write to S3 and upsert file_index."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.write("workflows/test.py", b"print('hello')")

    # S3 write happened
    mock_repo_storage.write.assert_called_once_with("workflows/test.py", b"print('hello')")
    # DB upsert happened
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_write_skips_binary_files(mock_db, mock_repo_storage):
    """Binary files should be written to S3 but not indexed in DB."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.write("images/logo.png", b"\x89PNG binary data")

    # S3 write happened
    mock_repo_storage.write.assert_called_once()
    # DB should NOT be updated for binary files
    assert not mock_db.execute.called


@pytest.mark.asyncio
async def test_delete_removes_from_s3_and_db(mock_db, mock_repo_storage):
    """Delete should remove from both S3 and file_index."""
    from src.services.file_index_service import FileIndexService

    service = FileIndexService(mock_db, mock_repo_storage)
    await service.delete("workflows/test.py")

    mock_repo_storage.delete.assert_called_once_with("workflows/test.py")
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_search_queries_db(mock_db, mock_repo_storage):
    """Search should query file_index table."""
    from src.services.file_index_service import FileIndexService

    mock_result = MagicMock()
    mock_result.all.return_value = [
        MagicMock(path="workflows/a.py", content="def hello(): pass"),
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    service = FileIndexService(mock_db, mock_repo_storage)
    results = await service.search("hello")

    assert mock_db.execute.called
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_file_index_service.py -v`
Expected: FAIL

**Step 3: Implement file index service**

Create `api/src/services/file_index_service.py`:

```python
"""
File Index Service — dual-write facade for _repo/ files.

Every write goes to both S3 (_repo/) and the file_index DB table.
Reads and searches go through the DB for performance.
Binary files are written to S3 only (not indexed).
"""

from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.file_index import FileIndex
from src.services.repo_storage import RepoStorage

logger = logging.getLogger(__name__)

# File extensions that should be indexed (text-searchable)
TEXT_EXTENSIONS = frozenset({
    ".py", ".yaml", ".yml", ".json", ".md", ".txt", ".rst",
    ".toml", ".ini", ".cfg", ".csv", ".tsx", ".ts", ".js",
    ".jsx", ".css", ".html", ".xml", ".sql", ".sh",
})


def _is_text_file(path: str) -> bool:
    """Check if a file should be indexed based on extension."""
    for ext in TEXT_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


class FileIndexService:
    """Dual-write facade for _repo/ files."""

    def __init__(self, db: AsyncSession, repo_storage: RepoStorage | None = None):
        self.db = db
        self.repo_storage = repo_storage or RepoStorage()

    async def write(self, path: str, content: bytes) -> str:
        """
        Write a file to S3 and index it in the DB.

        Returns the content hash.
        """
        # Always write to S3
        content_hash = await self.repo_storage.write(path, content)

        # Only index text files
        if _is_text_file(path):
            try:
                content_str = content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"Could not decode {path} as UTF-8, skipping index")
                return content_hash

            stmt = insert(FileIndex).values(
                path=path,
                content=content_str,
                content_hash=content_hash,
            ).on_conflict_do_update(
                index_elements=[FileIndex.path],
                set_={
                    "content": content_str,
                    "content_hash": content_hash,
                    "updated_at": text("NOW()"),
                },
            )
            await self.db.execute(stmt)

        return content_hash

    async def read(self, path: str) -> str | None:
        """Read file content from the DB index. Returns None if not found."""
        result = await self.db.execute(
            select(FileIndex.content).where(FileIndex.path == path)
        )
        row = result.scalar_one_or_none()
        return row

    async def read_bytes(self, path: str) -> bytes:
        """Read raw bytes from S3. Use for binary files or when DB index is insufficient."""
        return await self.repo_storage.read(path)

    async def delete(self, path: str) -> None:
        """Delete a file from S3 and the DB index."""
        await self.repo_storage.delete(path)
        await self.db.execute(
            delete(FileIndex).where(FileIndex.path == path)
        )

    async def search(self, pattern: str) -> list[dict]:
        """
        Search file contents for a pattern.

        Returns list of dicts with 'path' and 'content' keys.
        """
        result = await self.db.execute(
            select(FileIndex.path, FileIndex.content).where(
                FileIndex.content.ilike(f"%{pattern}%")
            )
        )
        return [{"path": row.path, "content": row.content} for row in result.all()]

    async def list_paths(self, prefix: str = "") -> list[str]:
        """List all indexed file paths, optionally filtered by prefix."""
        if prefix:
            result = await self.db.execute(
                select(FileIndex.path).where(FileIndex.path.like(f"{prefix}%"))
            )
        else:
            result = await self.db.execute(select(FileIndex.path))
        return [row[0] for row in result.all()]

    async def get_hash(self, path: str) -> str | None:
        """Get the content hash for a file."""
        result = await self.db.execute(
            select(FileIndex.content_hash).where(FileIndex.path == path)
        )
        return result.scalar_one_or_none()
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_file_index_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/file_index_service.py api/tests/unit/test_file_index_service.py
git commit -m "feat: add FileIndexService for dual-write S3 + DB file operations"
```

---

### Task 9: Virtual Importer — Add S3 Fallback ✅

**Status:** Committed in `9a848a72`.

**Why:** Workers currently load modules from Redis only (cache miss = failure). Add S3 fallback so the importer is self-sufficient: Redis → S3 → cache to Redis.

**Files:**
- Modify: `api/src/core/module_cache_sync.py:49-73` (`get_module_sync`)
- Create: `api/tests/unit/test_virtual_import_s3_fallback.py`

**Step 1: Write the test**

Create `api/tests/unit/test_virtual_import_s3_fallback.py`:

```python
"""Tests for virtual import S3 fallback."""
import pytest
from unittest.mock import MagicMock, patch
import json


def test_s3_fallback_on_redis_miss():
    """When Redis returns None, should try S3 and cache result."""
    from src.core.module_cache_sync import get_module_sync

    with patch("src.core.module_cache_sync._get_sync_client") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        # Redis returns None (cache miss)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_factory.return_value = mock_redis

        # S3 returns the module content
        mock_s3.return_value = b"def helper(): return 42"

        result = get_module_sync("shared/utils.py")

        # Should have tried S3
        mock_s3.assert_called_once_with("shared/utils.py")
        # Should have cached to Redis
        assert mock_redis.setex.called
        # Should return the module
        assert result is not None
        assert result.content == "def helper(): return 42"


def test_redis_hit_skips_s3():
    """When Redis has the module, should not touch S3."""
    from src.core.module_cache_sync import get_module_sync

    cached = json.dumps({"content": "cached content", "path": "shared/utils.py", "hash": "abc"})

    with patch("src.core.module_cache_sync._get_sync_client") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        mock_redis = MagicMock()
        mock_redis.get.return_value = cached.encode()
        mock_redis_factory.return_value = mock_redis

        result = get_module_sync("shared/utils.py")

        mock_s3.assert_not_called()
        assert result is not None
        assert result.content == "cached content"


def test_s3_miss_returns_none():
    """When both Redis and S3 miss, should return None."""
    from src.core.module_cache_sync import get_module_sync

    with patch("src.core.module_cache_sync._get_sync_client") as mock_redis_factory, \
         patch("src.core.module_cache_sync._get_s3_module") as mock_s3:

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis_factory.return_value = mock_redis
        mock_s3.return_value = None

        result = get_module_sync("shared/nonexistent.py")

        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_virtual_import_s3_fallback.py -v`
Expected: FAIL

**Step 3: Add S3 fallback to `get_module_sync`**

In `api/src/core/module_cache_sync.py`, modify `get_module_sync()` to:
1. Try Redis first (existing behavior)
2. On miss, call `_get_s3_module(path)` to fetch from S3
3. If S3 returns content, cache to Redis and return
4. If both miss, return None

Add a new function `_get_s3_module(path: str) -> bytes | None` that uses boto3 sync client to read from `_repo/{path}` in S3. This function handles `NoSuchKey` errors gracefully.

The exact implementation depends on the current structure of `module_cache_sync.py` — read lines 44-73 to see the Redis client setup, then add the S3 client alongside it. Use `boto3` (sync) since this runs in worker subprocesses, not the async API.

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_virtual_import_s3_fallback.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 6: Commit**

```bash
git add api/src/core/module_cache_sync.py api/tests/unit/test_virtual_import_s3_fallback.py
git commit -m "feat: add S3 fallback to virtual module importer"
```

---

### Task 10: Reconciler — Sync `file_index` from S3 ✅

**Status:** Committed in `9a848a72`.

**Why:** Background reconciler that heals drift between S3 and `file_index`. Runs on API startup and can be triggered manually. Ensures eventual consistency.

**Files:**
- Create: `api/src/services/file_index_reconciler.py`
- Create: `api/tests/unit/test_file_index_reconciler.py`

**Step 1: Write the tests**

Create `api/tests/unit/test_file_index_reconciler.py`:

```python
"""Tests for file_index reconciler."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_repo_storage():
    storage = AsyncMock()
    return storage


@pytest.mark.asyncio
async def test_reconciler_adds_missing_files(mock_db, mock_repo_storage):
    """Files in S3 but not in file_index should be added."""
    from src.services.file_index_reconciler import reconcile_file_index

    # S3 has two files
    mock_repo_storage.list.return_value = ["workflows/a.py", "workflows/b.py"]
    mock_repo_storage.read.return_value = b"print('hello')"

    # DB has only one
    db_result = MagicMock()
    db_result.all.return_value = [("workflows/a.py",)]
    mock_db.execute = AsyncMock(return_value=db_result)

    stats = await reconcile_file_index(mock_db, mock_repo_storage)

    assert stats["added"] >= 1


@pytest.mark.asyncio
async def test_reconciler_removes_orphaned_entries(mock_db, mock_repo_storage):
    """file_index entries with no corresponding S3 file should be removed."""
    from src.services.file_index_reconciler import reconcile_file_index

    # S3 has one file
    mock_repo_storage.list.return_value = ["workflows/a.py"]
    mock_repo_storage.read.return_value = b"print('hello')"

    # DB has two (one is orphaned)
    db_result = MagicMock()
    db_result.all.return_value = [("workflows/a.py",), ("workflows/deleted.py",)]
    mock_db.execute = AsyncMock(return_value=db_result)

    stats = await reconcile_file_index(mock_db, mock_repo_storage)

    assert stats["removed"] >= 1
```

**Step 2: Run test to verify it fails**

Run: `./test.sh tests/unit/test_file_index_reconciler.py -v`
Expected: FAIL

**Step 3: Implement reconciler**

Create `api/src/services/file_index_reconciler.py`:

```python
"""
File Index Reconciler — heals drift between S3 _repo/ and file_index DB.

Runs on API startup and can be triggered manually.
Lists all files in S3 _repo/, compares against file_index,
adds missing entries, removes orphaned entries, updates stale content.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.file_index import FileIndex
from src.services.file_index_service import _is_text_file
from src.services.repo_storage import RepoStorage

logger = logging.getLogger(__name__)


async def reconcile_file_index(
    db: AsyncSession,
    repo_storage: RepoStorage | None = None,
) -> dict[str, int]:
    """
    Reconcile file_index with S3 _repo/ contents.

    Returns stats dict with counts of added, removed, updated entries.
    """
    repo = repo_storage or RepoStorage()
    stats = {"added": 0, "removed": 0, "updated": 0, "unchanged": 0}

    # Get all files from S3
    s3_paths = set(await repo.list())
    # Filter to text files only
    s3_text_paths = {p for p in s3_paths if _is_text_file(p)}

    # Get all paths from file_index
    result = await db.execute(select(FileIndex.path))
    db_paths = {row[0] for row in result.all()}

    # Files in S3 but not in DB → add
    to_add = s3_text_paths - db_paths
    for path in to_add:
        try:
            content = await repo.read(path)
            content_str = content.decode("utf-8")
            content_hash = hashlib.sha256(content).hexdigest()

            stmt = insert(FileIndex).values(
                path=path,
                content=content_str,
                content_hash=content_hash,
            ).on_conflict_do_nothing()
            await db.execute(stmt)
            stats["added"] += 1
        except Exception as e:
            logger.warning(f"Failed to index {path}: {e}")

    # Files in DB but not in S3 → remove
    to_remove = db_paths - s3_text_paths
    if to_remove:
        await db.execute(
            delete(FileIndex).where(FileIndex.path.in_(to_remove))
        )
        stats["removed"] = len(to_remove)

    await db.commit()

    logger.info(
        f"Reconciliation complete: {stats['added']} added, "
        f"{stats['removed']} removed, {stats['updated']} updated"
    )

    return stats
```

**Step 4: Run test to verify it passes**

Run: `./test.sh tests/unit/test_file_index_reconciler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/services/file_index_reconciler.py api/tests/unit/test_file_index_reconciler.py
git commit -m "feat: add file_index reconciler for S3-to-DB consistency"
```

---

### Task 11: Dual-Write — FileStorageService Writes to Both Old and New ✅

**Why:** When a workflow file is written via the existing `FileStorageService.write_file()`, also write to `_repo/` via `FileIndexService`. This keeps both systems in sync during migration.

**Files:**
- Modify: `api/src/services/file_storage/service.py` (add dual-write in `write_file`)
- Create: `api/tests/unit/test_dual_write.py`

**Step 1: Write the test**

Create `api/tests/unit/test_dual_write.py`:

```python
"""Tests for dual-write during migration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_write_file_also_writes_to_file_index():
    """FileStorageService.write_file should also update file_index."""
    # This test validates the dual-write integration.
    # The exact implementation depends on how FileStorageService is structured.
    # Key assertion: after write_file(), the content should be in both
    # the old system (workspace_files/workflows tables) AND the new file_index.
    pass  # Implementation-specific — fill in after reading write_file code
```

This is a wiring task. The key change is:

In `api/src/services/file_storage/service.py`, in the `write_file` method, after the existing write logic completes, add:

```python
# Dual-write to new file_index (migration)
try:
    from src.services.file_index_service import FileIndexService
    from src.services.repo_storage import RepoStorage
    file_index = FileIndexService(self.db, RepoStorage(self.settings))
    await file_index.write(path, content)
except Exception as e:
    logger.warning(f"Dual-write to file_index failed for {path}: {e}")
```

Similarly for `delete_file`. This is best-effort — if the new path fails, the old path still works.

**Step 2: Run full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 3: Commit**

```bash
git add api/src/services/file_storage/service.py api/tests/unit/test_dual_write.py
git commit -m "feat: add dual-write to file_index during file operations"
```

---

### Task 12: Migrate Worker Code Loading — S3 via Redis Instead of DB ✅

**Status:** Unstaged. `execution/service.py` loads from `file_index` with graceful fallback. Worker falls back to Redis→S3 if file_index returns None.

**Why:** Workers currently receive `workflow_code` from the consumer (which reads it from `workflows.code` in DB). Migrate to loading from S3 via Redis cache, matching the module import pattern.

**Files:**
- Modify: `api/src/services/execution/worker.py:164-181` (code loading)
- Modify: `api/src/services/execution/service.py:126-191` (`get_workflow_for_execution`)
- Modify: `api/src/jobs/consumers/workflow_execution.py:796-802` (context_data)
- Create: `api/tests/unit/test_worker_s3_code_loading.py`

**Step 1: Write the test**

Create `api/tests/unit/test_worker_s3_code_loading.py`:

```python
"""Tests for worker loading code from S3 via Redis cache."""
import pytest
from unittest.mock import MagicMock, patch


def test_worker_loads_code_from_cache():
    """Worker should load workflow code from Redis/S3 cache using path."""
    from src.core.module_cache_sync import get_module_sync

    with patch("src.core.module_cache_sync._get_sync_client") as mock_redis_factory:
        import json
        cached = json.dumps({
            "content": "from bifrost import workflow\n@workflow\ndef test(): return {}",
            "path": "workflows/test.py",
            "hash": "abc123",
        })
        mock_redis = MagicMock()
        mock_redis.get.return_value = cached.encode()
        mock_redis_factory.return_value = mock_redis

        result = get_module_sync("workflows/test.py")
        assert result is not None
        assert "@workflow" in result.content
```

**Step 2: Implementation approach**

The key changes:

1. In `get_workflow_for_execution()` (`service.py:126`): Stop returning `workflow_record.code`. Return `path` and `function_name` only. Keep the field in the dict but set it to `None`.

2. In consumer (`workflow_execution.py:801`): `workflow_code` will be `None`. That's fine.

3. In worker (`worker.py:176`): When `workflow_code` is `None`, load code from Redis/S3 via `get_module_sync(file_path)`:

```python
if not workflow_code and file_path:
    # Load from Redis/S3 cache (new path)
    cached = get_module_sync(file_path)
    if cached:
        workflow_code = cached.content
```

This is backwards-compatible — if `workflow_code` is provided (old path), use it. If not, try the cache. This allows gradual migration.

**Step 3: Run full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 4: Commit**

```bash
git add api/src/services/execution/worker.py api/src/services/execution/service.py api/src/jobs/consumers/workflow_execution.py api/tests/unit/test_worker_s3_code_loading.py
git commit -m "feat: worker loads workflow code from S3/Redis cache with DB fallback"
```

---

### Task 13: Migrate MCP Content Tools — Read from `file_index` ✅

**Status:** Unstaged. `code_editor.py` loads workflow code from `file_index` with `_try_file_index_fallback()`. `editor/search.py` queries `file_index` for workflow code search. `workflow_orphan.py` and `routers/workflows.py` also migrated.

**Why:** MCP tools (`get_content`, `search_content`, `list_content`) currently route through `entity_type` + polymorphic DB lookups. Migrate reads to use `file_index` directly.

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`
- Create: `api/tests/unit/test_mcp_tools_file_index.py`

**Step 1: Implementation approach**

Add new code paths in the MCP tools that use `FileIndexService`:

- `get_content(path)` → try `file_index` first, fall back to old path
- `search_content(pattern)` → try `file_index` first, fall back to old path
- `list_content()` → try `file_index` first, fall back to old path

The `entity_type` parameter becomes optional/ignored when `file_index` has the content. This is backwards-compatible — old callers still work.

**Step 2: Run full test suite**

Run: `./test.sh`
Expected: All tests pass

**Step 3: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py api/tests/unit/test_mcp_tools_file_index.py
git commit -m "feat: MCP content tools read from file_index with old path fallback"
```

---

### Task 14: Execution Pinning — Content Hash on Dispatch ✅

**Status:** Unstaged. Consumer queries `file_index` for `content_hash` at dispatch, passes in `context_data`.

**Why:** Pin workflow execution to a content hash so code changes mid-dispatch don't cause inconsistent runs.

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py` (record content_hash at dispatch)
- Modify: `api/src/services/execution/worker.py` (validate hash at load)
- Create: `api/tests/unit/test_execution_pinning.py`

**Step 1: Implementation approach**

In the consumer, after looking up the workflow, query `file_index` for the `content_hash`:

```python
from src.models.orm.file_index import FileIndex
hash_result = await db.execute(
    select(FileIndex.content_hash).where(FileIndex.path == file_path)
)
content_hash = hash_result.scalar_one_or_none()
context_data["content_hash"] = content_hash
```

In the worker, after loading code, validate:

```python
import hashlib
if content_hash and workflow_code:
    actual_hash = hashlib.sha256(workflow_code.encode()).hexdigest()
    if actual_hash != content_hash:
        logger.warning(f"Code changed during dispatch for {file_path}, re-fetching from S3")
        # Re-fetch from S3 directly, bypassing cache
        # ... retry logic ...
```

**Step 2: Commit**

```bash
git commit -m "feat: pin workflow execution to content hash for reproducibility"
```

---

### Task 15: Git Sync Locking — Redis Distributed Lock ✅

**Status:** Committed in `ebbe4e10`.

**Why:** Prevent concurrent git sync operations from corrupting state.

**Files:**
- Create: `api/src/services/sync_lock.py`
- Create: `api/tests/unit/test_sync_lock.py`

**Step 1: Write the test**

```python
"""Tests for sync lock."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_lock_acquired():
    from src.services.sync_lock import acquire_sync_lock

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    result = await acquire_sync_lock(mock_redis)
    assert result is True


@pytest.mark.asyncio
async def test_lock_rejected_when_held():
    from src.services.sync_lock import acquire_sync_lock

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=False)  # NX returns False if key exists

    result = await acquire_sync_lock(mock_redis)
    assert result is False
```

**Step 2: Implement**

```python
"""Redis distributed lock for git sync operations."""

SYNC_LOCK_KEY = "bifrost:sync:lock"
SYNC_LOCK_TTL = 300  # 5 minutes


async def acquire_sync_lock(redis_client, ttl: int = SYNC_LOCK_TTL) -> bool:
    return await redis_client.set(SYNC_LOCK_KEY, "1", nx=True, ex=ttl)


async def release_sync_lock(redis_client) -> None:
    await redis_client.delete(SYNC_LOCK_KEY)
```

**Step 3: Commit**

```bash
git commit -m "feat: add Redis distributed lock for git sync operations"
```

</details>

---

## Unstaged Work (needs commit)

### Task 17a: Drop `workflows.code` and `code_hash` Columns ✅

**What was done:**
- `api/src/models/orm/workflows.py`: Removed `code` and `code_hash` mapped columns
- `api/alembic/versions/20260210_drop_workflow_code_columns.py`: Migration drops both columns
- `api/src/services/file_storage/indexers/workflow.py`: No longer writes `code`/`code_hash` in upsert
- All readers migrated to `file_index` (execution service, MCP tools, editor search, orphan service, workflow router)

**Note:** `github_sync.py` does NOT reference `workflow.code` — it reads workflow file content via `FileStorageService`, which already routes through `file_index`. No sync changes needed.

### Task 19: Remove Module Cache Prewarming ✅

**What was done:**
- `api/src/core/module_cache.py`: `warm_cache_from_db()` removed
- `api/src/jobs/consumers/workflow_execution.py`: `_sync_module_cache()` removed, `set_module` import removed
- `api/scripts/init_container.py`: Module cache warming step removed (init container now 2 steps: migrations + requirements cache)

---

## Remaining Work: Task 18 — Implement GitPython Sync

**Goal:** Make all 19 `test_git_sync_local.py` tests pass, then delete old E2E tests.

### What exists already
- `api/src/services/github_sync.py` — Pydantic models (`SyncPreview`, `SyncAction`, `ConflictInfo`, `PreflightIssue`, `PreflightResult`, `SyncResult`), old subprocess-based implementation
- `api/src/services/github_sync_virtual_files.py` — entity serialization (forms, agents, apps → file content)
- `api/src/services/github_config.py` — GitHub config
- `api/src/services/github_api.py` — GitHub REST API client (keep for repo listing)
- `api/tests/integration/platform/test_git_sync_local.py` — 19 TDD test stubs using local bare repos

### Implementation steps

**Step 1: Rewrite `github_sync.py` core**

Replace subprocess git calls + GitHub REST API push with GitPython:

| Current | New |
|---------|-----|
| `subprocess.run(["git", "clone", ...])` | `Repo.clone_from()` |
| `subprocess.run(["git", "rev-parse", "HEAD"])` | `repo.head.commit.hexsha` |
| Push via GitHub REST API blobs/trees/commits/refs | `repo.index.add()` → `commit()` → `push()` |
| SHA comparison via `WorkspaceFile.github_sha` + `git_status` | `git diff` (let git handle this) |
| `GitHubAPIClient` for push | Removed from sync (keep for repo listing) |

**Step 2: Implement sync flows**

**Push (platform → repo):**
1. Copy `_repo/` from S3 to temp dir (working tree with `.git/`)
2. Serialize current DB state → write files to working tree
3. Generate `.bifrost/metadata.yaml` manifest
4. `git add -A && git commit && git push`
5. Copy updated `_repo/` back to S3

**Pull (repo → platform):**
1. Copy `_repo/` from S3 to temp dir
2. `git pull origin main`
3. Read `.bifrost/metadata.yaml` → reconcile with DB
4. For each changed file: update DB entity + `file_index`
5. Copy updated `_repo/` back to S3

**Preview:**
1. Copy `_repo/` to temp, `git fetch origin`
2. Compare local vs remote via `git diff`
3. Detect conflicts, run preflight
4. Return `SyncPreview`

**Step 3: Implement preflight validation**

New method: `preflight_check(repo_path) → PreflightResult`

1. **Python syntax** — `compile()` on all `.py` files
2. **Ruff linting** — `subprocess.run(["ruff", "check", ...])` on `.py` files
3. **Ref resolution** — scan entity files for UUID references, verify in manifest
4. **Orphan detection** — entity refs point to missing workflows
5. **Manifest validity** — `.bifrost/metadata.yaml` parses, all listed paths exist

**Step 4: Config update**
- `github_config.py` — accept `file://`, `ssh://`, `https://` URLs

**Step 5: Delete old E2E tests**
- Delete `tests/e2e/api/test_github.py` (1 test — uses old REST API sync)
- Delete `tests/e2e/api/test_github_virtual_files.py` (5 tests — uses old SHA comparison)
- The 19 `test_git_sync_local.py` tests replace them

### Key files to modify

| File | Action |
|------|--------|
| `api/src/services/github_sync.py` | Rewrite: GitPython replaces subprocess + REST API |
| `api/src/services/github_config.py` | Modify: accept `file://`, `ssh://`, `https://` URLs |
| `api/src/services/github_api.py` | Keep for repo/branch listing; remove from sync path |
| `api/src/services/github_sync_virtual_files.py` | Keep: entity serialization reused |
| `api/tests/e2e/api/test_github.py` | Delete after implementation |
| `api/tests/e2e/api/test_github_virtual_files.py` | Delete after implementation |

### Verification

```bash
# All 19 git sync tests should pass
./test.sh tests/integration/platform/test_git_sync_local.py -v

# Full suite: 0 failures
./test.sh
```

---

## Follow-up: Entity YAML Migration

**Goal:** Migrate entity file formats from JSON to YAML for consistency with the architecture doc.

- `.form.json` → `.form.yaml` (portable form definitions)
- `.agent.json` → `.agent.yaml` (portable agent definitions)
- Update serializers in `github_sync_virtual_files.py`
- Update path patterns in `code_editor.py` (`_list_text_files`, `_search_text_files` exclusions)
- Update path patterns in `entity_detector.py`
- Update `folder_ops.py` entity routing
- Update tests

**Key principle:** YAML for everything — forms, agents, apps, manifest. Only `.py` files use Python format.

---

## Completed Tasks (reference only — Task 16, 17c)

### Task 16: Remove `workspace_files` Table References ✅

**Completed on this branch.** All `WorkspaceFile` references removed from production code. Migration `20260210_drop_workspace_files` drops the table. Key changes:
- `code_editor.py` rewritten: modules/text list/search/delete use `FileIndex` queries
- `reindex.py` rewritten: `FileIndex` upsert/hard-delete (no soft-delete)
- `folder_ops.py` `upload_from_directory` returns `int` count
- `files.py` router uses `FileEntry` dataclass
- `ref_translation.py` deleted (UUIDs used directly)
- `git_tracker.py` deleted (git manages its own state)
- `WorkspaceFile` removed from model exports
- 14 test files updated, 2 portable refs test files removed

### Task 17c: Remove `portable_ref` Column ✅

**Included in Task 16 migration.** `DROP COLUMN IF EXISTS portable_ref` in `20260210_drop_workspace_files` migration.

---

## Summary

| Scope | Tasks | Status |
|-------|-------|--------|
| Phase 1 (infrastructure) | 1-10 | ✅ Committed |
| Phase 2 (migrate reads + column drops) | 11-15, 17a, 19 | ✅ Committed |
| Drop workspace_files + portable_ref | 16, 17c | ✅ Unstaged, ready to commit |
| Storage integrity tests | — | ✅ Created |
| Git sync TDD tests | — | ✅ 19 stubs created |
| GitPython sync implementation | 18 | **TODO** — make TDD tests pass |
| Entity YAML migration | — | **TODO** — `.form.json` → `.form.yaml` |

**Test status: 2852 pass, 23 fail** (all 23 are git sync tests waiting for Task 18).
