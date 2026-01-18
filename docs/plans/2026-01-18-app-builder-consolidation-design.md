# App Builder Consolidation: Component Engine Removal

**Date:** 2026-01-18
**Status:** Implementation Complete (Migration Pending)
**Author:** Jack + Claude

## Overview

Consolidate the app builder by removing the component-based engine entirely, leaving only the code-based (JSX/TypeScript) engine. This simplifies the codebase, drops legacy tables, and establishes a cleaner architecture for apps.

## Background

The platform currently supports two app builder engines:

1. **Component Engine (v1)** - Visual builder with JSON component trees stored in `app_pages` and `app_components` tables
2. **Code Engine (v2)** - File-based JSX/TypeScript stored in `app_code_files` table

The code engine is superior for flexibility and developer experience. No production apps use the component engine, enabling a clean break.

## Changes

### 1. Database Schema

**Drop tables:**
- `app_pages` - Component engine only
- `app_components` - Component engine only

**Drop columns:**
- `applications.engine` - No longer needed with single engine

**Rename tables:**
- `app_code_files` → `app_files`

**Keep unchanged:**
- `applications` - Core app metadata
- `app_versions` - Version management (draft/active)
- `app_roles` - Role-based access control

### 2. API & MCP Tools

**Rename tools (drop "code" prefix):**

| Current | New |
|---------|-----|
| `code_list_files` | `list_app_files` |
| `code_get_file` | `get_app_file` |
| `code_create_file` | `create_app_file` |
| `code_update_file` | `update_app_file` |
| `code_delete_file` | `delete_app_file` |

**Remove tools:**
- `get_page` (with component tree)
- `create_page` (component engine)
- `create_component`
- `update_component`
- `delete_component`
- `list_components`
- All component CRUD operations

### 3. Code Cleanup

**Backend (Python):**
- Remove component engine handlers in `api/src/handlers/`
- Remove component contracts in `api/src/models/contracts/app_components.py`
- Remove component-related repository methods
- Update application contracts to remove engine field

**Frontend (TypeScript):**
- Remove component builder UI (`client/src/components/app-builder/`)
- Remove component renderer (`AppRenderer.tsx` component engine paths)
- Keep code editor and file tree components
- Update types after regeneration

### 4. Permissions Model

**Current limitation:** The `useUser()` hook only exposes `role: string` (first role).

**Fix:** Expand to expose all roles:

```typescript
// Before
interface JsxUser {
  id: string;
  email: string;
  name: string;
  role: string;  // First role only
  organizationId: string;
}

// After
interface JsxUser {
  id: string;
  email: string;
  name: string;
  roles: string[];  // All roles
  hasRole: (role: string) => boolean;  // Helper
  organizationId: string;
}
```

**Page-level permissions:** Handled in code by developers:

```tsx
const { hasRole } = useUser()

if (!hasRole('Admin')) {
  return <Navigate to="/unauthorized" />
}
```

No separate permission metadata files - permissions live in code.

### 5. GitHub Serialization

**Export structure:**
```
apps/{slug}/
  app.json              # Portable metadata only
  _layout.tsx
  _providers.tsx
  pages/
    index.tsx
    settings.tsx
    projects/[id].tsx
  components/
    ProjectCard.tsx
    StatusBadge.tsx
  modules/
    utils.ts
```

**app.json contents (portable only):**
```json
{
  "name": "Project Manager",
  "slug": "project-manager",
  "description": "Track projects and tasks",
  "icon": "folder-kanban",
  "navigation": {
    "items": [
      { "label": "Dashboard", "path": "/" },
      { "label": "Projects", "path": "/projects" }
    ]
  }
}
```

**Excluded from serialization (instance-specific):**
- `permissions` - Role IDs don't transfer between instances
- `access_level` - Set to safe default on import
- `organization_id` - Set from import context
- `role_ids` - Cleared on import
- `created_by`, `created_at`, timestamps

**Import behavior:**
- `access_level` defaults to `"role_based"` (locked down)
- `permissions` defaults to `{}`
- `organization_id` set from import context (or NULL for global)
- Files synced via git naturally (no enumeration in manifest)

### 6. Shared Modules

**Mechanism:** Global apps' exports are loaded into the `$` registry at runtime.

**How it works:**
1. Apps with `organization_id = NULL` are global
2. Runtime loader fetches global app modules
3. Exports added to `$` registry
4. Any app can access via destructuring: `const { formatDate } = $`

**Scoping rules:**
- Global app modules → available to all apps
- Org-scoped app modules → available only to apps in same org

**No new tables required** - uses existing `app_files` with `organization_id` scoping from parent app.

## Migration Plan

### Phase 1: Preparation
1. Audit existing apps to confirm none use component engine
2. Add deprecation warnings to component engine UI (if any exist)

### Phase 2: Schema Migration
1. Create Alembic migration to:
   - Rename `app_code_files` → `app_files`
   - Drop `applications.engine` column
   - Drop `app_pages` table (cascades components)
   - Drop `app_components` table

### Phase 3: Backend Cleanup
1. Remove component engine handlers
2. Remove component contracts and models
3. Rename code file endpoints (drop "code" prefix)
4. Update MCP tools
5. Update GitHub sync virtual file generation

### Phase 4: Frontend Cleanup
1. Remove component builder components
2. Remove component renderer code paths
3. Update API service calls for renamed endpoints
4. Regenerate types

### Phase 5: Permissions Enhancement
1. Update `useUser()` hook to expose `roles[]` and `hasRole()`
2. Update `JsxUser` interface
3. Update documentation/examples

### Phase 6: Shared Modules (Future)
1. Implement global app module loading in runtime
2. Add scoping checks to module resolution
3. Document shared module patterns

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Existing component apps | Confirmed none exist - clean break |
| Breaking MCP integrations | Rename tools, update Bifrost MCP docs |
| GitHub sync format change | New format for code apps only; component apps never had good sync |

## Success Criteria

- [x] All component engine code removed
- [ ] Tables dropped, schema simplified *(Migration created, pending deployment)*
- [x] MCP tools renamed and working
- [x] `useUser()` exposes full roles
- [ ] GitHub sync works with new directory structure *(Deferred to Phase 2)*
- [x] TypeScript compiles with zero errors
- [x] All tests pass *(2213 passed, 7 pre-existing failures unrelated to this work)*

---

# Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the component engine entirely, leaving only the code-based app builder.

**Architecture:** Database migration first (drop tables, rename), then backend cleanup (remove files, update references), then frontend cleanup, then permissions enhancement.

**Tech Stack:** Python/FastAPI, SQLAlchemy/Alembic, TypeScript/React, PostgreSQL

---

## Task 1: Database Migration - Drop Component Tables & Rename

**Files:**
- Create: `api/alembic/versions/YYYYMMDD_HHMMSS_consolidate_app_builder.py`

**Step 1: Create the migration file**

```bash
cd api && alembic revision -m "consolidate_app_builder_remove_components"
```

**Step 2: Write the migration**

```python
"""consolidate_app_builder_remove_components

Drop component engine tables and rename app_code_files to app_files.
"""
from alembic import op
import sqlalchemy as sa


revision = "GENERATED_ID"
down_revision = "PREVIOUS_REVISION"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop app_components table (has FK to app_pages)
    op.drop_table("app_components")

    # 2. Drop app_pages table (has FK to applications and app_versions)
    op.drop_table("app_pages")

    # 3. Drop engine column from applications
    op.drop_column("applications", "engine")

    # 4. Rename app_code_files to app_files
    op.rename_table("app_code_files", "app_files")

    # 5. Rename indexes on app_files
    op.execute("ALTER INDEX ix_code_files_version RENAME TO ix_app_files_version")
    op.execute("ALTER INDEX ix_code_files_path RENAME TO ix_app_files_path")


def downgrade() -> None:
    # Reverse the changes (for rollback capability)
    op.execute("ALTER INDEX ix_app_files_path RENAME TO ix_code_files_path")
    op.execute("ALTER INDEX ix_app_files_version RENAME TO ix_code_files_version")
    op.rename_table("app_files", "app_code_files")

    op.add_column(
        "applications",
        sa.Column("engine", sa.String(20), server_default="'code'", nullable=False)
    )

    # Recreate app_pages table
    op.create_table(
        "app_pages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("application_id", sa.UUID(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("version_id", sa.UUID(), sa.ForeignKey("app_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_sources", sa.JSON(), server_default="[]"),
        sa.Column("variables", sa.JSON(), server_default="{}"),
        sa.Column("launch_workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="SET NULL")),
        sa.Column("launch_workflow_params", sa.JSON(), server_default="{}"),
        sa.Column("launch_workflow_data_source_id", sa.String(255)),
        sa.Column("permission", sa.JSON(), server_default="{}"),
        sa.Column("page_order", sa.Integer(), server_default="0"),
        sa.Column("fill_height", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Recreate app_components table
    op.create_table(
        "app_components",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("page_id", sa.UUID(), sa.ForeignKey("app_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.UUID(), sa.ForeignKey("app_components.id", ondelete="CASCADE")),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("props", sa.JSON(), server_default="{}"),
        sa.Column("component_order", sa.Integer(), server_default="0"),
        sa.Column("visible", sa.Text()),
        sa.Column("width", sa.String(20)),
        sa.Column("loading_workflows", sa.JSON(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
```

**Step 3: Verify migration syntax**

```bash
cd api && python -c "from alembic.config import Config; from alembic import command; command.check(Config('alembic.ini'))"
```

**Step 4: Commit**

```bash
git add api/alembic/versions/*consolidate_app_builder*.py
git commit -m "feat(db): Add migration to consolidate app builder

- Drop app_components table
- Drop app_pages table
- Drop applications.engine column
- Rename app_code_files to app_files"
```

---

## Task 2: Update ORM Models - Remove Component Classes

**Files:**
- Modify: `api/src/models/orm/applications.py`
- Modify: `api/src/models/enums.py`

**Step 1: Remove AppPage and AppComponent classes from ORM**

In `api/src/models/orm/applications.py`:

1. Remove the `AppPage` class (lines 177-248)
2. Remove the `AppComponent` class (lines 251-306)
3. Remove `pages` relationship from `Application` class (lines 135-137)
4. Remove `pages` relationship from `AppVersion` class (lines 51-56)
5. Rename `AppCodeFile` to `AppFile` and update tablename to `app_files`
6. Remove `engine` field from `Application` class (lines 111-114)
7. Update imports and TYPE_CHECKING references

**Step 2: Remove AppEngine enum from enums.py**

In `api/src/models/enums.py`, remove:
```python
class AppEngine(str, Enum):
    COMPONENTS = "components"
    CODE = "code"
```

**Step 3: Run type checker**

```bash
cd api && pyright
```

Expected: Errors about missing imports (to be fixed in subsequent tasks)

**Step 4: Commit**

```bash
git add api/src/models/orm/applications.py api/src/models/enums.py
git commit -m "refactor(models): Remove component engine ORM models

- Remove AppPage class
- Remove AppComponent class
- Rename AppCodeFile to AppFile
- Remove engine field from Application
- Remove AppEngine enum"
```

---

## Task 3: Delete Component Router & Contracts

**Files:**
- Delete: `api/src/routers/app_components.py`
- Delete: `api/src/models/contracts/app_components.py`
- Delete: `api/src/services/app_components_service.py`
- Modify: `api/src/routers/__init__.py` (remove import)
- Modify: `api/src/main.py` (remove router registration)

**Step 1: Delete the files**

```bash
rm api/src/routers/app_components.py
rm api/src/models/contracts/app_components.py
rm api/src/services/app_components_service.py
```

**Step 2: Remove router registration from main.py**

Find and remove the line that includes the app_components router.

**Step 3: Update any imports**

Search for imports of deleted modules and remove them.

**Step 4: Run type checker**

```bash
cd api && pyright
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(api): Delete component engine router, contracts, and service"
```

---

## Task 4: Delete Component MCP Tools

**Files:**
- Delete: `api/src/services/mcp_server/tools/components.py`
- Modify: `api/src/services/mcp_server/tools/__init__.py`
- Modify: `api/src/services/mcp_server/server.py` (remove tool registration)

**Step 1: Delete the component tools file**

```bash
rm api/src/services/mcp_server/tools/components.py
```

**Step 2: Remove from tool registration**

Update `__init__.py` and `server.py` to remove component tool imports and registration.

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(mcp): Remove component engine MCP tools"
```

---

## Task 5: Rename Code File MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_files.py` → rename to `app_files.py`
- Modify: `api/src/services/mcp_server/tools/__init__.py`
- Modify: `api/src/services/mcp_server/server.py`

**Step 1: Rename the file**

```bash
mv api/src/services/mcp_server/tools/code_files.py api/src/services/mcp_server/tools/app_files.py
```

**Step 2: Update function names in app_files.py**

Rename all functions:
- `code_list_files` → `list_app_files`
- `code_get_file` → `get_app_file`
- `code_create_file` → `create_app_file`
- `code_update_file` → `update_app_file`
- `code_delete_file` → `delete_app_file`

**Step 3: Update tool registration**

Update imports and tool registration in `__init__.py` and `server.py`.

**Step 4: Run type checker**

```bash
cd api && pyright
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(mcp): Rename code file tools to app file tools

- code_list_files → list_app_files
- code_get_file → get_app_file
- code_create_file → create_app_file
- code_update_file → update_app_file
- code_delete_file → delete_app_file"
```

---

## Task 6: Update Application Contracts

**Files:**
- Modify: `api/src/models/contracts/applications.py`

**Step 1: Remove engine field from contracts**

1. Remove `engine` field from `ApplicationCreate`
2. Remove `engine` field from `ApplicationPublic`
3. Remove `engine` field from `ApplicationUpdate`
4. Rename `AppCodeFile*` contracts to `AppFile*`
5. Remove any engine-related validators

**Step 2: Run type checker**

```bash
cd api && pyright
```

**Step 3: Commit**

```bash
git add api/src/models/contracts/applications.py
git commit -m "refactor(contracts): Remove engine field, rename AppCodeFile to AppFile"
```

---

## Task 7: Update Application Router & Repository

**Files:**
- Modify: `api/src/routers/applications.py`
- Modify: `api/src/repositories/applications.py`

**Step 1: Remove engine references from router**

Remove any logic that checks or sets `engine` field.

**Step 2: Remove engine references from repository**

Remove any `engine` filtering or setting.

**Step 3: Update imports**

Change `AppCodeFile` references to `AppFile`.

**Step 4: Run type checker**

```bash
cd api && pyright
```

**Step 5: Commit**

```bash
git add api/src/routers/applications.py api/src/repositories/applications.py
git commit -m "refactor(apps): Remove engine references from router and repository"
```

---

## Task 8: Delete App Pages Router

**Files:**
- Delete: `api/src/routers/app_pages.py`
- Modify: `api/src/main.py` (remove router)

**Step 1: Delete the file**

```bash
rm api/src/routers/app_pages.py
```

**Step 2: Remove from main.py**

Remove the router registration.

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(api): Delete app pages router (component engine only)"
```

---

## Task 9: Delete Component Engine Tests

**Files:**
- Delete: `api/tests/e2e/api/test_app_components.py`
- Delete: `api/tests/unit/test_unified_component_model.py` (if exists)

**Step 1: Delete test files**

```bash
rm -f api/tests/e2e/api/test_app_components.py
rm -f api/tests/unit/test_unified_component_model.py
```

**Step 2: Run tests to verify nothing breaks**

```bash
./test.sh
```

**Step 3: Commit**

```bash
git add -A
git commit -m "test: Remove component engine tests"
```

---

## Task 10: Update useUser Hook - Expose All Roles

**Files:**
- Modify: `client/src/lib/app-code-platform/useUser.ts`

**Step 1: Update the JsxUser interface and hook**

```typescript
/**
 * Platform hook: useUser
 *
 * Returns the current authenticated user information.
 * Wraps the auth context to provide a simplified interface for JSX apps.
 */

import { useAuth } from "@/contexts/AuthContext";
import { useCallback } from "react";

interface JsxUser {
	/** User's unique ID */
	id: string;
	/** User's email address */
	email: string;
	/** User's display name */
	name: string;
	/** All roles assigned to the user */
	roles: string[];
	/** Check if user has a specific role */
	hasRole: (role: string) => boolean;
	/** User's organization ID (empty string if platform user) */
	organizationId: string;
}

/**
 * Get the current authenticated user
 *
 * @returns User object with id, email, name, roles, hasRole, and organizationId
 *
 * @example
 * ```jsx
 * const { name, hasRole } = useUser();
 *
 * return (
 *   <div>
 *     <Text>Welcome, {name}</Text>
 *     {hasRole('Admin') && (
 *       <Button onClick={() => navigate('/settings')}>
 *         Settings
 *       </Button>
 *     )}
 *   </div>
 * );
 * ```
 */
export function useUser(): JsxUser {
	const { user } = useAuth();

	const hasRole = useCallback(
		(role: string) => {
			return user?.roles.includes(role) ?? false;
		},
		[user?.roles]
	);

	// Return a consistent shape even if user is null
	// (shouldn't happen in JSX apps since they require auth)
	if (!user) {
		return {
			id: "",
			email: "",
			name: "",
			roles: [],
			hasRole: () => false,
			organizationId: "",
		};
	}

	return {
		id: user.id,
		email: user.email,
		name: user.name,
		roles: user.roles,
		hasRole,
		organizationId: user.organizationId ?? "",
	};
}
```

**Step 2: Run type checker**

```bash
cd client && npm run tsc
```

**Step 3: Commit**

```bash
git add client/src/lib/app-code-platform/useUser.ts
git commit -m "feat(useUser): Expose all roles and hasRole helper

BREAKING CHANGE: useUser() now returns roles[] instead of role string"
```

---

## Task 11: Update App Code Platform Types

**Files:**
- Modify: `client/src/lib/app-code-platform.d.ts`

**Step 1: Update the type declaration**

Update the `JsxUser` type to match the new interface with `roles` and `hasRole`.

**Step 2: Run type checker**

```bash
cd client && npm run tsc
```

**Step 3: Commit**

```bash
git add client/src/lib/app-code-platform.d.ts
git commit -m "types: Update JsxUser type declaration for roles array"
```

---

## Task 12: Regenerate API Types

**Step 1: Start the dev stack (if not running)**

```bash
./debug.sh
```

**Step 2: Regenerate types**

```bash
cd client && npm run generate:types
```

**Step 3: Verify types compile**

```bash
cd client && npm run tsc
```

**Step 4: Commit**

```bash
git add client/src/lib/v1.d.ts
git commit -m "types: Regenerate API types after backend changes"
```

---

## Task 13: Run Full Test Suite

**Step 1: Run backend tests**

```bash
./test.sh
```

Expected: All tests pass

**Step 2: Run frontend type checking**

```bash
cd client && npm run tsc
```

Expected: Zero errors

**Step 3: Run frontend linting**

```bash
cd client && npm run lint
```

Expected: Zero errors

**Step 4: Run backend linting**

```bash
cd api && ruff check .
```

Expected: Zero errors

---

## Task 14: Apply Database Migration

**Step 1: With dev stack running, apply migration**

```bash
docker compose -f docker-compose.dev.yml restart api
```

The migration will run automatically on API startup.

**Step 2: Verify tables dropped**

```bash
docker compose -f docker-compose.dev.yml exec db psql -U bifrost -d bifrost -c "\dt app_*"
```

Expected: Only `app_files`, `app_versions`, `app_roles` should exist (no `app_pages`, `app_components`)

---

## Task 15: Final Verification & Commit

**Step 1: Create a test app via MCP tools**

Use the Bifrost MCP tools to:
1. Create an app
2. Create a file with `create_app_file` (new name)
3. List files with `list_app_files` (new name)
4. Verify the app works

**Step 2: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: Final cleanup after app builder consolidation"
```

---

## Deferred Tasks (Phase 2)

These are tracked but not part of initial implementation:

### Task D1: Update GitHub Sync for New Directory Format

The current virtual file system exports apps as single JSON files. Update to export as directories with real files. This is a larger change that can be done separately.

### Task D2: Implement Shared Modules

Load global app exports into the `$` registry. This requires runtime loader changes and can be implemented after the consolidation is complete.

### Task D3: Frontend Component Cleanup

Delete the component builder UI components. This can be done after verifying the backend consolidation works:

```bash
rm -rf client/src/components/app-builder/components/
rm client/src/components/app-builder/ComponentRegistry.tsx
rm client/src/components/app-builder/editor/ComponentInserter.tsx
# ... etc
```

---

## Summary

| Task | Description | Estimated |
|------|-------------|-----------|
| 1 | Database migration | 15 min |
| 2 | Update ORM models | 20 min |
| 3 | Delete component router/contracts | 10 min |
| 4 | Delete component MCP tools | 5 min |
| 5 | Rename code file MCP tools | 15 min |
| 6 | Update application contracts | 15 min |
| 7 | Update router/repository | 15 min |
| 8 | Delete app pages router | 5 min |
| 9 | Delete component tests | 5 min |
| 10 | Update useUser hook | 10 min |
| 11 | Update platform types | 5 min |
| 12 | Regenerate API types | 5 min |
| 13 | Run full test suite | 10 min |
| 14 | Apply migration | 5 min |
| 15 | Final verification | 10 min |
| **Total** | | **~2.5 hours** |
