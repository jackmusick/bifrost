# Eliminate app.yaml — Consolidate into .bifrost/apps.yaml

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the per-app `app.yaml` file — move `name`, `description`, and `dependencies` into `.bifrost/apps.yaml` and the `Application` DB model. App source directories become pure TSX/TS/CSS code with no metadata files.

**Architecture:** `ManifestApp` gains `name`, `description`, `dependencies` fields. A new `dependencies` JSON column on `Application` stores npm deps in the DB. All code paths that read/write `app.yaml` from S3 switch to reading from the DB or manifest. The `path` field in ManifestApp changes from `apps/{slug}/app.yaml` to `apps/{slug}` (directory). Backward compat: during import, if an `app.yaml` exists, parse its deps into the DB column.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (async), Pydantic, PostgreSQL, Alembic, pytest

---

### Task 1: Add `dependencies` column to Application ORM + migration

**Files:**
- Modify: `api/src/models/orm/applications.py:62-64`
- Create: `api/alembic/versions/YYYYMMDD_add_app_dependencies.py`

**Step 1: Add the column to the ORM model**

In `api/src/models/orm/applications.py`, after the `description` field (line 63):

```python
    description: Mapped[str | None] = mapped_column(Text, default=None)
    dependencies: Mapped[dict | None] = mapped_column(JSON, default=None, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), default=None)
```

**Step 2: Create the alembic migration**

Run: `cd api && alembic revision -m "add dependencies column to applications"`

Edit the generated migration:

```python
def upgrade() -> None:
    op.add_column("applications", sa.Column("dependencies", sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column("applications", "dependencies")
```

**Step 3: Commit**

```bash
git add api/src/models/orm/applications.py api/alembic/versions/*add_app_dependencies*
git commit -m "feat: add dependencies JSON column to Application model"
```

---

### Task 2: Add `name`, `description`, `dependencies` to ManifestApp model

**Files:**
- Modify: `api/src/services/manifest.py:96-103`

**Step 1: Update the model**

```python
class ManifestApp(BaseModel):
    """App entry in manifest."""
    id: str
    path: str              # app source directory (e.g. "apps/my-app"), NOT app.yaml
    slug: str | None = None
    name: str | None = None
    description: str | None = None
    dependencies: dict[str, str] = Field(default_factory=dict)
    organization_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    access_level: str = "authenticated"
```

**Step 2: Update the unit test fixture**

In `api/tests/unit/test_manifest.py:566-573`, update the app fixture:

```python
"apps": {
    "my_app": {
        "id": app_id,
        "path": "apps/my-app",
        "name": "My App",
        "description": "Test app",
        "dependencies": {"recharts": "2.12"},
        "organization_id": org_id,
        "roles": [role_id],
    },
},
```

**Step 3: Run tests**

Run: `./test.sh tests/unit/test_manifest.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add api/src/services/manifest.py api/tests/unit/test_manifest.py
git commit -m "feat: add name, description, dependencies to ManifestApp model"
```

---

### Task 3: Update manifest generator — stop appending /app.yaml

**Files:**
- Modify: `api/src/services/manifest_generator.py:333-343`

**Step 1: Update the app serialization**

The DB `repo_path` is already the directory (`apps/{slug}`). The generator currently appends `/app.yaml` at line 336. Change to:

```python
apps={
    app.name: ManifestApp(
        id=str(app.id),
        path=(app.repo_path or f"apps/{app.slug}").rstrip("/"),
        slug=app.slug,
        name=app.name,
        description=app.description,
        dependencies=app.dependencies or {},
        organization_id=str(app.organization_id) if app.organization_id else None,
        roles=app_roles_by_app.get(str(app.id), []),
        access_level=app.access_level if app.access_level else "authenticated",
    )
    for app in apps_list
},
```

**Step 2: Commit**

```bash
git add api/src/services/manifest_generator.py
git commit -m "fix: manifest generator uses directory path for apps, serializes name/desc/deps"
```

---

### Task 4: Update `_resolve_app` — read from ManifestApp, not app.yaml

**Files:**
- Modify: `api/src/services/github_sync.py:2008-2088`

**Step 1: Rewrite `_resolve_app` to not require content**

```python
async def _resolve_app(self, mapp) -> "list[SyncOp]":
    """Resolve an app from manifest into SyncOps (metadata only)."""
    from pathlib import PurePosixPath
    from uuid import UUID

    from src.models.orm.app_roles import AppRole
    from src.models.orm.applications import Application
    from src.services.sync_ops import SyncOp, SyncRoles, Upsert

    # repo_path is now the directory directly (no /app.yaml to strip)
    repo_path = mapp.path.rstrip("/") if mapp.path else None

    # Slug from manifest entry, or derive from repo_path leaf
    slug = mapp.slug or (PurePosixPath(repo_path).name if repo_path else None)
    if not slug:
        logger.warning(f"App {mapp.id} has no slug or path, skipping")
        return []

    if not repo_path:
        repo_path = f"apps/{slug}"

    app_id = UUID(mapp.id)
    org_id = UUID(mapp.organization_id) if mapp.organization_id else None
    access_level = getattr(mapp, "access_level", "role_based")

    # Two-step: check for existing app by natural key (org_id, slug)
    existing_query = select(Application.id).where(Application.slug == slug)
    if org_id:
        existing_query = existing_query.where(Application.organization_id == org_id)
    else:
        existing_query = existing_query.where(Application.organization_id.is_(None))

    existing = await self.db.execute(existing_query)
    existing_id = existing.scalar_one_or_none()

    app_values = {
        "name": mapp.name or "",
        "description": mapp.description,
        "slug": slug,
        "repo_path": repo_path,
        "organization_id": org_id,
        "access_level": access_level,
        "dependencies": mapp.dependencies or None,
    }

    ops: list[SyncOp] = []

    if existing_id is not None:
        ops.append(Upsert(
            model=Application,
            id=existing_id,
            values={"id": app_id, **app_values},
            match_on="id",
        ))
    else:
        ops.append(Upsert(
            model=Application,
            id=app_id,
            values=app_values,
            match_on="id",
        ))

    # Role sync op
    if hasattr(mapp, "roles") and mapp.roles:
        role_ids = {UUID(r) for r in mapp.roles}
        ops.append(SyncRoles(
            junction_model=AppRole,
            entity_fk="app_id",
            entity_id=app_id,
            role_ids=role_ids,
        ))

    return ops
```

**Step 2: Update callers in `_plan_import` (~line 964-972)**

Replace:
```python
# 4. Resolve apps (before tables — tables ref application_id)
for _app_name, mapp in manifest.apps.items():
    app_path = work_dir / mapp.path
    if app_path.exists():
        content = app_path.read_bytes()
        app_ops = await self._resolve_app(mapp, content)
        for op in app_ops:
            await op.execute(self.db)
        all_ops.extend(app_ops)
```

With:
```python
# 4. Resolve apps (before tables — tables ref application_id)
for _app_name, mapp in manifest.apps.items():
    app_ops = await self._resolve_app(mapp)
    for op in app_ops:
        await op.execute(self.db)
    all_ops.extend(app_ops)
```

**Step 3: Update `_import_all_entities` count (~line 1055)**

Replace:
```python
count += sum(1 for mapp in manifest.apps.values() if (work_dir / mapp.path).exists())
```
With:
```python
count += len(manifest.apps)
```

**Step 4: Update `_regenerate_manifest_to_dir` app filter (~line 544-547)**

Replace:
```python
manifest.apps = {
    k: v for k, v in manifest.apps.items()
    if (work_dir / v.path).exists()
}
```
With:
```python
manifest.apps = {
    k: v for k, v in manifest.apps.items()
    if (work_dir / v.path).is_dir()
}
```

**Step 5: Update `_sync_app_previews` (~line 1159-1160)**

Replace:
```python
# Derive source directory from app path (e.g. "apps/tickbox-grc/app.yaml" -> "apps/tickbox-grc")
app_source_dir = str(Path(mapp.path).parent)
```
With:
```python
# mapp.path is already the source directory (e.g. "apps/tickbox-grc")
app_source_dir = mapp.path
```

**Step 6: Update `_delete_stale_entities` app presence check (~line 1620-1623)**

Replace:
```python
present_app_ids: set[str] = set()
for mapp in manifest.apps.values():
    if (work_dir / mapp.path).exists():
        present_app_ids.add(mapp.id)
```
With:
```python
present_app_ids: set[str] = set()
for mapp in manifest.apps.values():
    if (work_dir / mapp.path).is_dir():
        present_app_ids.add(mapp.id)
```

**Step 7: Commit**

```bash
git add api/src/services/github_sync.py
git commit -m "fix: _resolve_app reads from ManifestApp fields, not app.yaml file

Removes app.yaml file reads from git sync import. App name, description,
and dependencies now come from .bifrost/apps.yaml manifest. Path field
points to source directory instead of app.yaml file."
```

---

### Task 5: Update dependency endpoints — read/write from DB

**Files:**
- Modify: `api/src/routers/app_code_files.py:82-138, 352-354, 537-544, 563, 610-689`
- Modify: `api/src/models/contracts/applications.py:309-312`

**Step 1: Remove `_parse_dependencies` and `_serialize_dependencies` helper functions**

Delete lines 82-148 (`_parse_dependencies` and `_serialize_dependencies`). These parsed YAML from S3 — no longer needed.

Keep the validation constants `_PKG_NAME_RE`, `_VERSION_RE`, `_MAX_DEPENDENCIES` (lines 76-79) — still needed for `put_dependencies` validation.

**Step 2: Update `render_app` endpoint (~line 537-544)**

Replace:
```python
# Read dependencies from app.yaml in S3
dependencies: dict[str, str] = {}
try:
    repo = RepoStorage()
    yaml_bytes = await repo.read(f"{_repo_prefix(app)}app.yaml")
    yaml_content = yaml_bytes.decode("utf-8", errors="replace")
    dependencies = _parse_dependencies(yaml_content)
except Exception:
    pass
```
With:
```python
# Read dependencies from DB
dependencies: dict[str, str] = app.dependencies or {}
```

**Step 3: Remove app.yaml skip in `render_app` (~line 563)**

Delete:
```python
if rel_path == "app.yaml":
    continue
```

**Step 4: Remove app.yaml skip in `list_files` (~line 352-354)**

Delete:
```python
# Skip app.yaml (manifest metadata, not a source file)
if rel_path == "app.yaml":
    continue
```

**Step 5: Rewrite `get_dependencies` endpoint (~line 619-631)**

```python
async def get_dependencies(
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> dict[str, str]:
    """Return the app's npm dependencies."""
    app = await get_application_or_404(ctx, app_id)
    return app.dependencies or {}
```

**Step 6: Rewrite `put_dependencies` endpoint (~line 639-689)**

```python
async def put_dependencies(
    deps: dict[str, str],
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> dict[str, str]:
    """Replace the app's npm dependencies.

    Validates every package name and version, enforces the max-dependency limit.
    """
    app = await get_application_or_404(ctx, app_id)

    # Validate
    if len(deps) > _MAX_DEPENDENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many dependencies (max {_MAX_DEPENDENCIES})",
        )
    for name, version in deps.items():
        if not _PKG_NAME_RE.match(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid package name: {name}",
            )
        if not _VERSION_RE.match(version):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid version for {name}: {version}",
            )

    # Update DB
    app.dependencies = deps if deps else None
    await ctx.db.commit()

    # Invalidate render cache
    app_storage = AppStorageService()
    await app_storage.invalidate_render_cache(str(app.id))

    return deps
```

**Step 7: Update section comment (~line 610)**

Change `# Dependencies endpoints — read/write app.yaml dependencies section` to `# Dependencies endpoints — read/write Application.dependencies`

**Step 8: Update contract docstring**

In `api/src/models/contracts/applications.py:309-312`:
```python
dependencies: dict[str, str] = Field(
    default_factory=dict,
    description="npm dependencies {name: version} for esm.sh loading",
)
```

**Step 9: Remove unused imports**

In `app_code_files.py`, remove imports that were only used by the deleted helpers: `yaml` (if unused elsewhere), `RepoStorage` (if unused elsewhere in this file). Check carefully — `yaml` and `RepoStorage` may still be needed by other functions in the file.

**Step 10: Commit**

```bash
git add api/src/routers/app_code_files.py api/src/models/contracts/applications.py
git commit -m "fix: dependency endpoints read/write from Application.dependencies DB column"
```

---

### Task 6: Update MCP app tools — deps from DB

**Files:**
- Modify: `api/src/services/mcp_server/tools/apps.py`

**Step 1: Update `get_app_dependencies` (~line 1033-1103)**

Replace the S3 read with DB read:
```python
async def get_app_dependencies(
    context: Any,
    app_id: str | None = None,
    app_slug: str | None = None,
) -> ToolResult:
    """
    Get npm dependencies declared for an app.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application

    if not app_id and not app_slug:
        return error_result("Either app_id or app_slug is required")

    try:
        async with get_db_context() as db:
            if app_id:
                try:
                    app_uuid = UUID(app_id)
                except ValueError:
                    return error_result(f"Invalid app_id format: {app_id}")
                query = select(Application).where(Application.id == app_uuid)
            else:
                query = select(Application).where(Application.slug == app_slug)

            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query)
            app = result.scalar_one_or_none()
            if not app:
                return error_result(f"Application not found: {app_id or app_slug}")

            deps = app.dependencies or {}

            if not deps:
                return success_result(
                    f"No dependencies declared for {app.name}",
                    {"dependencies": {}, "app_id": str(app.id), "app_name": app.name},
                )

            dep_list = ", ".join(f"{k}@{v}" for k, v in deps.items())
            return success_result(
                f"{app.name} dependencies: {dep_list}",
                {"dependencies": deps, "app_id": str(app.id), "app_name": app.name},
            )

    except Exception as e:
        logger.exception(f"Error getting app dependencies: {e}")
        return error_result(f"Error getting dependencies: {str(e)}")
```

**Step 2: Update `update_app_dependencies` (~line 1106-1205)**

Replace S3 read/write with DB update:
```python
async def update_app_dependencies(
    context: Any,
    app_id: str,
    dependencies: dict[str, str],
) -> ToolResult:
    """
    Update npm dependencies for an app.
    """
    import re
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.app_storage import AppStorageService

    MAX_DEPS = 20
    PKG_NAME_RE = re.compile(r"^(@[a-z0-9-]+/)?[a-z0-9][a-z0-9._-]*$")
    VERSION_RE = re.compile(r"^\^?~?\d+(\.\d+){0,2}$")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return error_result(f"Invalid app_id format: {app_id}")

    if len(dependencies) > MAX_DEPS:
        return error_result(f"Too many dependencies (max {MAX_DEPS})")

    for name, version in dependencies.items():
        if not PKG_NAME_RE.match(name):
            return error_result(f"Invalid package name: {name}")
        if not VERSION_RE.match(version):
            return error_result(f"Invalid version for {name}: {version}")

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query)
            app = result.scalar_one_or_none()
            if not app:
                return error_result(f"Application not found: {app_id}")

            app.dependencies = dependencies if dependencies else None
            await db.commit()

            # Invalidate render cache
            app_storage = AppStorageService()
            await app_storage.invalidate_render_cache(str(app.id))

            if dependencies:
                dep_list = ", ".join(f"{k}@{v}" for k, v in dependencies.items())
                display_text = f"Updated {app.name} dependencies: {dep_list}"
            else:
                display_text = f"Removed all dependencies from {app.name}"

            return success_result(display_text, {
                "dependencies": dependencies,
                "app_id": str(app.id),
                "app_name": app.name,
            })

    except Exception as e:
        logger.exception(f"Error updating app dependencies: {e}")
        return error_result(f"Error updating dependencies: {str(e)}")
```

**Step 3: Update `validate_app` (~line 777-842)**

Replace:
```python
# Parse declared dependencies from app.yaml
from src.routers.app_code_files import _parse_dependencies

yaml_content = files.get(f"{prefix}app.yaml", "")
declared_deps = _parse_dependencies(yaml_content) if yaml_content else {}
```
With:
```python
# Get declared dependencies from DB
declared_deps = app.dependencies or {}
```

Update error messages at lines 838-842:
- `"Missing dependency: '{dep}' is imported but not in app.yaml dependencies"` → `"Missing dependency: '{dep}' is imported but not declared in app dependencies"`
- `"Unused dependency: '{dep}' is declared but not imported by any file"` → keep as is (no app.yaml ref)
- Change `"file": "app.yaml"` to `"file": "dependencies"` in both error dicts

**Step 4: Update `get_app_schema` documentation (~line 589-641)**

Replace the `app.yaml` dependency documentation section with:

```python
"""
## External Dependencies (npm packages)

Apps can use npm packages loaded at runtime from esm.sh CDN.

### Managing dependencies:
- Use `get_app_dependencies` / `update_app_dependencies` tools
- Or use the REST API: `GET/PUT /api/applications/{app_id}/dependencies`
- Dependencies are stored in `.bifrost/apps.yaml` and synced via git

### Using in code:
```tsx
import { LineChart, Line, XAxis, YAxis } from "recharts";
import dayjs from "dayjs";
```

### Rules:
- Max 20 dependencies per app
- Version format: semver with optional `^` or `~` prefix (e.g., `"2.12"`, `"^1.5.3"`)
- Package names: lowercase, hyphens, optional `@scope/` prefix
"""
```

Also update the `validate_app` docstring (line 721-722) to remove "app.yaml" references.

And update the tool metadata descriptions at line 1219-1220:
- `"Get npm dependencies declared in an app's app.yaml."` → `"Get npm dependencies declared for an app."`
- `"Update npm dependencies in an app's app.yaml. Pass a dict of {package: version}."` → `"Update npm dependencies for an app. Pass a dict of {package: version}."`

**Step 5: Remove unused imports**

Remove `_parse_dependencies`, `_serialize_dependencies` imports from `app_code_files`, `RepoStorage`, `get_file_storage_service` if no longer used in this file.

**Step 6: Commit**

```bash
git add api/src/services/mcp_server/tools/apps.py
git commit -m "fix: MCP app tools read/write dependencies from DB instead of app.yaml"
```

---

### Task 7: Remove app.yaml skip logic and entity detection

**Files:**
- Modify: `api/src/services/app_storage.py:100-102, 168-169`
- Modify: `api/src/services/file_storage/entity_detector.py:49-54`
- Modify: `api/src/services/github_sync_entity_metadata.py:20, 56-61, 68-69`

**Step 1: Remove app.yaml skips in app_storage.py**

In `sync_preview` (~line 100-102), delete:
```python
# Skip app.yaml (manifest metadata, not a source file)
if rel_path == "app.yaml":
    continue
```

In `sync_preview_compiled` (~line 168-169), delete:
```python
if rel_path == "app.yaml":
    continue
```

**Step 2: Update entity_detector.py**

In `detect_platform_entity_type` (~line 49-54), replace:
```python
# App files: apps/{slug}/...
if path.startswith("apps/"):
    parts = path.split("/")
    if len(parts) >= 3 and parts[2] == "app.yaml":
        return "app"
    return "app_file"
```
With:
```python
# App files: apps/{slug}/...
if path.startswith("apps/"):
    return "app_file"
```

**Step 3: Update github_sync_entity_metadata.py**

Remove `APP_YAML_PATTERN` at line 20.

Replace the app.yaml metadata extraction block (~line 56-61):
```python
# App metadata: apps/{slug}/app.yaml
match = APP_YAML_PATTERN.match(path)
if match:
    slug = match.group(1)
    display_name = _extract_yaml_name(content, slug)
    return EntityMetadata(entity_type="app", display_name=display_name, parent_slug=slug)
```
Delete it entirely.

Remove the `app.yaml` skip at line 68-69:
```python
# Skip app.yaml (handled above)
if relative_path != "app.yaml":
```
Change to just not checking — the `APP_FILE_PATTERN` match block should always execute for app files now (remove the inner `if` condition, keeping the body).

**Step 4: Commit**

```bash
git add api/src/services/app_storage.py api/src/services/file_storage/entity_detector.py api/src/services/github_sync_entity_metadata.py
git commit -m "fix: remove app.yaml skip logic and entity detection — no longer exists"
```

---

### Task 8: Update tests

**Files:**
- Modify: `api/tests/unit/test_manifest.py`
- Modify: `api/tests/unit/services/test_dependencies_api.py`
- Modify: `api/tests/unit/services/test_entity_detector.py`
- Modify: `api/tests/unit/services/test_github_sync_entity_metadata.py`
- Modify: `api/tests/unit/routers/test_github_sync_preview.py`
- Modify: `api/tests/e2e/platform/test_git_sync_local.py`

**Step 1: Update test_entity_detector.py**

Remove the `test_detect_app_yaml` test (~line 102-106). The "app" entity type for `app.yaml` detection no longer exists.

**Step 2: Update test_github_sync_entity_metadata.py**

Remove the `test_app_yaml_extracts_name` test (~line 32-41).

**Step 3: Update test_github_sync_preview.py**

Remove the `test_extract_entity_metadata_for_app` test (~line 25-32) that tests `apps/dashboard/app.yaml` extraction.

**Step 4: Rewrite test_dependencies_api.py**

The old tests tested `_parse_dependencies` and `_serialize_dependencies` (YAML parsing). Replace with tests for the new DB-based flow. Since `_parse_dependencies` and `_serialize_dependencies` are deleted, these tests need to test the validation logic that remains in the endpoints. Write basic validation tests:

```python
"""Tests for dependency validation logic."""
import re

_PKG_NAME_RE = re.compile(r"^(@[a-z0-9-]+/)?[a-z0-9][a-z0-9._-]*$")
_VERSION_RE = re.compile(r"^\^?~?\d+(\.\d+){0,2}$")


def test_valid_package_names():
    """Standard and scoped package names pass validation."""
    assert _PKG_NAME_RE.match("recharts")
    assert _PKG_NAME_RE.match("dayjs")
    assert _PKG_NAME_RE.match("@tanstack/react-table")
    assert _PKG_NAME_RE.match("react-icons")


def test_invalid_package_names():
    """Invalid package names are rejected."""
    assert not _PKG_NAME_RE.match("")
    assert not _PKG_NAME_RE.match("UPPERCASE")
    assert not _PKG_NAME_RE.match("../path-traversal")


def test_valid_versions():
    """Semver versions with optional prefix pass."""
    assert _VERSION_RE.match("2.12")
    assert _VERSION_RE.match("^1.5.3")
    assert _VERSION_RE.match("~1.11")


def test_invalid_versions():
    """Invalid versions are rejected."""
    assert not _VERSION_RE.match("latest")
    assert not _VERSION_RE.match("*")
```

**Step 5: Update E2E git sync app tests**

In `api/tests/e2e/platform/test_git_sync_local.py`, all app tests need updating. The pattern change is:

1. **Remove** all `(app_dir / "app.yaml").write_text(...)` lines
2. **Change** manifest `"path"` from `"apps/{slug}/app.yaml"` to `"apps/{slug}"`
3. **Add** `"name"` and `"description"` to the manifest dict
4. **Add** `"dependencies"` to the manifest dict where needed
5. **Remove** `"apps/{slug}/app.yaml"` from expected file lists in `working_clone.index.add()`

Example for `test_app_natural_key_import` (~line 2829-2855):

Before:
```python
(app_dir / "app.yaml").write_text(yaml.dump({
    "name": "Natural Key App Updated",
    "description": "Updated from remote",
}, default_flow_style=False))
...
"path": "apps/natural-key-app/app.yaml",
...
working_clone.index.add([
    "apps/natural-key-app/app.yaml",
    ".bifrost/metadata.yaml",
])
```

After:
```python
# No app.yaml to write — name/description in manifest
...
"path": "apps/natural-key-app",
"name": "Natural Key App Updated",
"description": "Updated from remote",
...
working_clone.index.add([
    ".bifrost/metadata.yaml",
])
```

Note: some tests still need at least one source file in the app dir (e.g., `_layout.tsx`) for the directory to exist. Check each test — if the test was relying on `app.yaml` as the only file in the directory, add a minimal `_layout.tsx` instead.

Apply this pattern to all ~6 app test blocks (search for `app.yaml` in the file).

**Step 6: Run all tests**

Run: `./test.sh tests/unit/ -v`
Expected: PASS

Run: `./test.sh tests/e2e/platform/test_git_sync_local.py -v -k "app"`
Expected: PASS

**Step 7: Commit**

```bash
git add api/tests/
git commit -m "test: update all tests for app.yaml elimination"
```

---

### Task 9: Update client-side docstring and run full verification

**Files:**
- Modify: `client/src/lib/esm-loader.ts:25` (docstring only)

**Step 1: Update esm-loader docstring**

Change `@param deps - Map of {packageName: version} from app.yaml` to `@param deps - Map of {packageName: version} from app dependencies`

**Step 2: Regenerate client types**

Run: `cd client && npm run generate:types`

This will auto-update `v1.d.ts` with the new docstring from `AppRenderResponse.dependencies`.

**Step 3: Run full verification**

Run: `cd api && pyright`
Expected: 0 errors

Run: `cd api && ruff check .`
Expected: Clean

Run: `cd client && npm run tsc`
Expected: Clean

Run: `./test.sh`
Expected: All PASS

**Step 4: Commit**

```bash
git add client/src/lib/esm-loader.ts client/src/lib/v1.d.ts
git commit -m "chore: update client docstrings for app.yaml elimination"
```

---

### Task 10: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the Manifest Serialization section**

In the "Integration sync: what gets serialized" table or adjacent section, update any references to app.yaml. Add a note that `ManifestApp` in `.bifrost/apps.yaml` carries all app metadata (name, description, dependencies, access_level, roles) and that app source directories contain only source code.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for app.yaml elimination"
```
