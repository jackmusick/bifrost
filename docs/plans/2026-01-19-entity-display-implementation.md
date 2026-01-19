# Entity Display and Editor Simplification - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance git sync UI with entity display names and icons, then remove forms/agents from the code editor entirely.

**Architecture:** Backend enriches SyncAction with display_name/entity_type parsed from JSON. Frontend groups and renders entities with icons. Phase 2 removes S3 writes and workspace_files entries for forms/agents.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React (frontend), PostgreSQL (migrations), Alembic (schema changes)

---

## Status

| Task | Description | Status |
|------|-------------|--------|
| 1 | Extend SyncAction Model with Entity Metadata | ✅ Done |
| 2 | Add Entity Metadata Extraction Utilities | ✅ Done |
| 3 | Enrich SyncActions with Entity Metadata in get_sync_preview | ✅ Done |
| 4 | Regenerate TypeScript Types | ✅ Done |
| 5 | Create EntitySyncItem Component | ✅ Done |
| 6 | Create Entity Grouping Utility | ✅ Done |
| 7 | Update SourceControlPanel to Use Entity Display | ✅ Done |
| 8 | Manual Testing | ⏳ Pending (requires human UI verification) |
| 9 | Create Migration to Delete workspace_files Entries | ✅ Done |
| 10 | Remove S3 Write Functions from Forms Router | ✅ Done |
| 11 | Remove S3 Write Functions from Agents Router | ✅ Done |
| 12 | Remove S3 Writes from MCP Tools | ✅ Done (completed in Tasks 10-11) |
| 13 | Create Migration to Remove file_path Columns | ✅ Done |
| 14 | Run Full Test Suite | ✅ Done (39/39 form+agent tests pass) |

**Notes:**
- Task 4 required updating both the service model AND the contract model (`api/src/models/contracts/github.py`), plus updating the router mapping to pass through the new fields
- Fixed pre-existing TypeScript errors related to `clear_roles` and null `id` handling
- Task 13 also removed `file_path` references from contract models, routers, MCP tools, indexers, and file operations
- 13 pre-existing test failures in full suite are unrelated to this work (workflow validation `created_at` issues, infrastructure timeouts)

---

## Phase 1: Git Sync UI Enhancement

### Task 1: Extend SyncAction Model with Entity Metadata

**Files:**
- Modify: `api/src/services/github_sync.py:63-69`

**Step 1: Add new fields to SyncAction model**

```python
class SyncAction(BaseModel):
    """A single sync action (pull or push)."""
    path: str = Field(..., description="File path relative to workspace root")
    action: SyncActionType = Field(..., description="Type of action")
    sha: str | None = Field(default=None, description="Git blob SHA (for pull actions)")

    # Entity metadata for UI display
    display_name: str | None = Field(default=None, description="Human-readable entity name")
    entity_type: str | None = Field(default=None, description="Entity type: form, agent, app, app_file, workflow")
    parent_slug: str | None = Field(default=None, description="For app_file: parent app slug")

    model_config = ConfigDict(from_attributes=True)
```

**Step 2: Run type check**

Run: `cd api && pyright src/services/github_sync.py`
Expected: PASS (no errors)

**Step 3: Commit**

```bash
git add api/src/services/github_sync.py
git commit -m "feat(sync): add display_name and entity_type to SyncAction model"
```

---

### Task 2: Add Entity Metadata Extraction Utilities

**Files:**
- Create: `api/src/services/github_sync_entity_metadata.py`
- Test: `api/tests/unit/services/test_github_sync_entity_metadata.py`

**Step 1: Write the failing test**

```python
"""Tests for entity metadata extraction from sync files."""
import pytest
from src.services.github_sync_entity_metadata import (
    extract_entity_metadata,
    EntityMetadata,
)


class TestExtractEntityMetadata:
    """Tests for extract_entity_metadata function."""

    def test_form_extracts_name(self):
        """Form JSON extracts name as display_name."""
        path = "forms/abc123.form.json"
        content = b'{"name": "Customer Intake", "id": "abc123"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "form"
        assert result.display_name == "Customer Intake"
        assert result.parent_slug is None

    def test_agent_extracts_name(self):
        """Agent JSON extracts name as display_name."""
        path = "agents/xyz789.agent.json"
        content = b'{"name": "Support Bot", "id": "xyz789"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "agent"
        assert result.display_name == "Support Bot"
        assert result.parent_slug is None

    def test_app_json_extracts_name(self):
        """App app.json extracts name as display_name."""
        path = "apps/dashboard/app.json"
        content = b'{"name": "Dashboard", "slug": "dashboard"}'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "app"
        assert result.display_name == "Dashboard"
        assert result.parent_slug == "dashboard"

    def test_app_file_extracts_parent_slug(self):
        """App code file extracts parent slug."""
        path = "apps/dashboard/pages/index.tsx"
        content = b'export default function Home() { return <div>Home</div> }'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "app_file"
        assert result.display_name == "pages/index.tsx"
        assert result.parent_slug == "dashboard"

    def test_workflow_uses_filename(self):
        """Workflow uses filename as display_name."""
        path = "workflows/process_payment.py"
        content = b'@workflow\ndef process_payment(): pass'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "workflow"
        assert result.display_name == "process_payment.py"
        assert result.parent_slug is None

    def test_unknown_file_returns_filename(self):
        """Unknown file type returns filename as display_name."""
        path = "random/file.txt"
        content = b'some content'

        result = extract_entity_metadata(path, content)

        assert result.entity_type is None
        assert result.display_name == "file.txt"
        assert result.parent_slug is None

    def test_invalid_json_uses_filename(self):
        """Invalid JSON falls back to filename."""
        path = "forms/broken.form.json"
        content = b'not valid json'

        result = extract_entity_metadata(path, content)

        assert result.entity_type == "form"
        assert result.display_name == "broken.form.json"
```

**Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/unit/services/test_github_sync_entity_metadata.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
"""
Entity metadata extraction for GitHub sync UI.

Extracts display names and entity types from file paths and content
to provide human-readable labels in the sync preview UI.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Path patterns for entity detection
FORM_PATTERN = re.compile(r"^forms/.*\.form\.json$")
AGENT_PATTERN = re.compile(r"^agents/.*\.agent\.json$")
APP_JSON_PATTERN = re.compile(r"^apps/([^/]+)/app\.json$")
APP_FILE_PATTERN = re.compile(r"^apps/([^/]+)/(.+)$")
WORKFLOW_PATTERN = re.compile(r"^(workflows|data_providers)/.*\.py$")


@dataclass
class EntityMetadata:
    """Metadata extracted from a sync file for UI display."""
    entity_type: str | None
    display_name: str
    parent_slug: str | None = None


def extract_entity_metadata(path: str, content: bytes | None = None) -> EntityMetadata:
    """
    Extract entity metadata from a file path and optional content.

    Args:
        path: File path relative to workspace root
        content: Optional file content for JSON parsing

    Returns:
        EntityMetadata with type, display name, and parent slug
    """
    filename = Path(path).name

    # Form: forms/*.form.json
    if FORM_PATTERN.match(path):
        display_name = _extract_json_name(content, filename)
        return EntityMetadata(entity_type="form", display_name=display_name)

    # Agent: agents/*.agent.json
    if AGENT_PATTERN.match(path):
        display_name = _extract_json_name(content, filename)
        return EntityMetadata(entity_type="agent", display_name=display_name)

    # App metadata: apps/{slug}/app.json
    match = APP_JSON_PATTERN.match(path)
    if match:
        slug = match.group(1)
        display_name = _extract_json_name(content, slug)
        return EntityMetadata(entity_type="app", display_name=display_name, parent_slug=slug)

    # App file: apps/{slug}/**/*
    match = APP_FILE_PATTERN.match(path)
    if match:
        slug = match.group(1)
        relative_path = match.group(2)
        # Skip app.json (handled above)
        if relative_path != "app.json":
            return EntityMetadata(
                entity_type="app_file",
                display_name=relative_path,
                parent_slug=slug
            )

    # Workflow: workflows/*.py or data_providers/*.py
    if WORKFLOW_PATTERN.match(path):
        return EntityMetadata(entity_type="workflow", display_name=filename)

    # Unknown file type
    return EntityMetadata(entity_type=None, display_name=filename)


def _extract_json_name(content: bytes | None, fallback: str) -> str:
    """Extract 'name' field from JSON content, with fallback."""
    if content is None:
        return fallback

    try:
        data = json.loads(content.decode("utf-8"))
        return data.get("name", fallback)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.debug(f"Failed to parse JSON for name extraction, using fallback: {fallback}")
        return fallback
```

**Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/unit/services/test_github_sync_entity_metadata.py -v`
Expected: PASS

**Step 5: Run type check**

Run: `cd api && pyright src/services/github_sync_entity_metadata.py`
Expected: PASS

**Step 6: Commit**

```bash
git add api/src/services/github_sync_entity_metadata.py api/tests/unit/services/test_github_sync_entity_metadata.py
git commit -m "feat(sync): add entity metadata extraction for sync UI"
```

---

### Task 3: Enrich SyncActions with Entity Metadata in get_sync_preview

**Files:**
- Modify: `api/src/services/github_sync.py`

**Step 1: Add import at top of file**

Find the imports section (around line 31-35) and add:

```python
from src.services.github_sync_entity_metadata import extract_entity_metadata
```

**Step 2: Create helper function to enrich SyncAction**

Add after the SyncAction class definition (around line 70):

```python
def _enrich_sync_action(
    path: str,
    action: SyncActionType,
    sha: str | None,
    content: bytes | None = None,
) -> SyncAction:
    """Create a SyncAction enriched with entity metadata."""
    metadata = extract_entity_metadata(path, content)
    return SyncAction(
        path=path,
        action=action,
        sha=sha,
        display_name=metadata.display_name,
        entity_type=metadata.entity_type,
        parent_slug=metadata.parent_slug,
    )
```

**Step 3: Update get_sync_preview to use enriched actions**

This requires finding where SyncAction objects are created in `get_sync_preview()` and replacing them with `_enrich_sync_action()` calls. The content is available from either:
- Local files: read from temp clone or S3
- Remote files: read from temp clone

Search for `SyncAction(` in the file and update each occurrence to use the helper.

**Step 4: Run existing tests**

Run: `cd api && python -m pytest tests/unit/services/test_github_sync.py tests/unit/services/test_github_sync_virtual_files.py -v`
Expected: PASS (existing tests should still pass)

**Step 5: Run type check**

Run: `cd api && pyright src/services/github_sync.py`
Expected: PASS

**Step 6: Commit**

```bash
git add api/src/services/github_sync.py
git commit -m "feat(sync): enrich SyncActions with entity metadata in preview"
```

---

### Task 4: Regenerate TypeScript Types

**Files:**
- Modify: `client/src/lib/v1.d.ts` (auto-generated)

**Step 1: Ensure dev stack is running**

Run: `docker ps --filter "name=bifrost" | grep -q "bifrost-dev-api" || echo "Start dev stack with ./debug.sh"`

**Step 2: Regenerate types**

Run: `cd client && npm run generate:types`
Expected: Types regenerated successfully

**Step 3: Verify SyncAction has new fields**

Run: `grep -A 10 "SyncAction" client/src/lib/v1.d.ts | head -20`
Expected: Should show `display_name`, `entity_type`, `parent_slug` fields

**Step 4: Commit**

```bash
git add client/src/lib/v1.d.ts
git commit -m "chore: regenerate types with SyncAction entity metadata"
```

---

### Task 5: Create EntitySyncItem Component

**Files:**
- Create: `client/src/components/editor/EntitySyncItem.tsx`

**Step 1: Create the component**

```tsx
/**
 * EntitySyncItem - Renders a single entity in the sync preview.
 *
 * Shows entity with appropriate icon and display name.
 * For apps, shows expandable file list.
 */

import { useState } from "react";
import {
	ChevronDown,
	ChevronRight,
	Plus,
	Minus,
	Edit3,
	AppWindow,
	Bot,
	FileText,
	Workflow,
	FileCode,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { SyncAction } from "@/hooks/useGitHub";

/** Icon mapping for entity types */
const ENTITY_ICONS = {
	form: { icon: FileText, className: "text-green-500" },
	agent: { icon: Bot, className: "text-orange-500" },
	app: { icon: AppWindow, className: "text-purple-500" },
	workflow: { icon: Workflow, className: "text-blue-500" },
	app_file: { icon: FileCode, className: "text-gray-500" },
} as const;

/** Get icon for action type (add/modify/delete) */
function getActionIcon(action: "add" | "modify" | "delete") {
	switch (action) {
		case "add":
			return <Plus className="h-3 w-3 text-green-500" />;
		case "modify":
			return <Edit3 className="h-3 w-3 text-blue-500" />;
		case "delete":
			return <Minus className="h-3 w-3 text-red-500" />;
	}
}

interface EntitySyncItemProps {
	/** The primary sync action (for single entities) or app metadata (for apps) */
	action: SyncAction;
	/** Child files for app entities */
	childFiles?: SyncAction[];
	/** Whether this is a conflict item */
	isConflict?: boolean;
	/** Resolution state for conflicts */
	resolution?: "keep_local" | "keep_remote";
	/** Callback for conflict resolution */
	onResolve?: (resolution: "keep_local" | "keep_remote") => void;
}

export function EntitySyncItem({
	action,
	childFiles = [],
	isConflict = false,
	resolution,
	onResolve,
}: EntitySyncItemProps) {
	const [expanded, setExpanded] = useState(false);
	const entityType = action.entity_type as keyof typeof ENTITY_ICONS | null;
	const iconConfig = entityType ? ENTITY_ICONS[entityType] : null;
	const IconComponent = iconConfig?.icon ?? FileCode;
	const iconClassName = iconConfig?.className ?? "text-gray-500";

	const isApp = action.entity_type === "app";
	const hasChildren = isApp && childFiles.length > 0;

	return (
		<div className="py-1">
			{/* Main entity row */}
			<div
				className={cn(
					"flex items-center gap-2 text-xs py-1.5 px-2 rounded",
					isConflict && !resolution && "bg-orange-500/10",
					isConflict && resolution && "bg-green-500/10",
					!isConflict && "hover:bg-muted/30"
				)}
			>
				{/* Expand/collapse for apps */}
				{hasChildren ? (
					<button
						onClick={() => setExpanded(!expanded)}
						className="p-0.5 hover:bg-muted rounded"
					>
						{expanded ? (
							<ChevronDown className="h-3 w-3" />
						) : (
							<ChevronRight className="h-3 w-3" />
						)}
					</button>
				) : (
					<span className="w-4" /> // Spacer for alignment
				)}

				{/* Action icon */}
				{getActionIcon(action.action)}

				{/* Entity icon */}
				<IconComponent className={cn("h-4 w-4 flex-shrink-0", iconClassName)} />

				{/* Display name */}
				<span className="flex-1 truncate" title={action.path}>
					{action.display_name || action.path}
				</span>

				{/* File count for apps */}
				{hasChildren && (
					<span className="text-xs text-muted-foreground">
						{childFiles.length} file{childFiles.length !== 1 ? "s" : ""}
					</span>
				)}
			</div>

			{/* Conflict resolution buttons */}
			{isConflict && onResolve && (
				<div className="flex gap-1 ml-8 mt-1">
					<button
						onClick={() => onResolve("keep_local")}
						className={cn(
							"px-2 py-0.5 text-xs rounded",
							resolution === "keep_local"
								? "bg-blue-500 text-white"
								: "bg-muted hover:bg-muted/80"
						)}
					>
						Keep Local
					</button>
					<button
						onClick={() => onResolve("keep_remote")}
						className={cn(
							"px-2 py-0.5 text-xs rounded",
							resolution === "keep_remote"
								? "bg-blue-500 text-white"
								: "bg-muted hover:bg-muted/80"
						)}
					>
						Keep Remote
					</button>
				</div>
			)}

			{/* Expanded app files */}
			{hasChildren && expanded && (
				<div className="ml-6 mt-1 border-l-2 border-muted pl-2 space-y-0.5">
					{childFiles.map((file) => (
						<div
							key={file.path}
							className="flex items-center gap-2 text-xs py-0.5 px-1 text-muted-foreground"
						>
							{getActionIcon(file.action)}
							<FileCode className="h-3 w-3" />
							<span className="truncate">{file.display_name || file.path}</span>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
```

**Step 2: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 3: Commit**

```bash
git add client/src/components/editor/EntitySyncItem.tsx
git commit -m "feat(sync-ui): add EntitySyncItem component for entity display"
```

---

### Task 6: Create Entity Grouping Utility

**Files:**
- Create: `client/src/components/editor/groupSyncActions.ts`

**Step 1: Create the utility**

```typescript
/**
 * Groups sync actions by entity for UI display.
 *
 * - Forms, agents, workflows: individual items
 * - Apps: grouped with their files as children
 */

import type { SyncAction } from "@/hooks/useGitHub";

export interface GroupedEntity {
	/** The main entity action (or app metadata action) */
	action: SyncAction;
	/** Child files for app entities */
	childFiles: SyncAction[];
}

/**
 * Group sync actions by entity for display.
 *
 * Apps are grouped together with their files as children.
 * Other entities (forms, agents, workflows) remain individual.
 */
export function groupSyncActions(actions: SyncAction[]): GroupedEntity[] {
	const appGroups = new Map<string, GroupedEntity>();
	const standaloneEntities: GroupedEntity[] = [];

	for (const action of actions) {
		if (action.entity_type === "app" && action.parent_slug) {
			// App metadata (app.json) - create or update group
			const existing = appGroups.get(action.parent_slug);
			if (existing) {
				// Replace placeholder with actual app metadata
				existing.action = action;
			} else {
				appGroups.set(action.parent_slug, {
					action,
					childFiles: [],
				});
			}
		} else if (action.entity_type === "app_file" && action.parent_slug) {
			// App file - add to group
			const existing = appGroups.get(action.parent_slug);
			if (existing) {
				existing.childFiles.push(action);
			} else {
				// Create placeholder group (app.json may come later)
				appGroups.set(action.parent_slug, {
					action: {
						...action,
						entity_type: "app",
						display_name: action.parent_slug,
					},
					childFiles: [action],
				});
			}
		} else {
			// Standalone entity (form, agent, workflow, unknown)
			standaloneEntities.push({
				action,
				childFiles: [],
			});
		}
	}

	// Combine: apps first, then standalone entities
	// Sort apps by display name, standalone by display name
	const sortedApps = Array.from(appGroups.values()).sort((a, b) =>
		(a.action.display_name || "").localeCompare(b.action.display_name || "")
	);
	const sortedStandalone = standaloneEntities.sort((a, b) =>
		(a.action.display_name || "").localeCompare(b.action.display_name || "")
	);

	return [...sortedApps, ...sortedStandalone];
}
```

**Step 2: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 3: Commit**

```bash
git add client/src/components/editor/groupSyncActions.ts
git commit -m "feat(sync-ui): add utility to group sync actions by entity"
```

---

### Task 7: Update SourceControlPanel to Use Entity Display

**Files:**
- Modify: `client/src/components/editor/SourceControlPanel.tsx`

**Step 1: Add imports**

At top of file, add:

```typescript
import { EntitySyncItem } from "./EntitySyncItem";
import { groupSyncActions } from "./groupSyncActions";
```

**Step 2: Update SyncActionList component**

Replace the existing `SyncActionList` component (around lines 695-740) with:

```typescript
/**
 * List of sync actions (files to pull or push) - Entity-centric display
 */
function SyncActionList({
	title,
	icon,
	actions,
}: {
	title: string;
	icon: React.ReactNode;
	actions: SyncAction[];
}) {
	const [expanded, setExpanded] = useState(true);
	const groupedEntities = groupSyncActions(actions);

	return (
		<div className={cn("border-t flex flex-col min-h-0", expanded && "flex-1")}>
			<button
				onClick={() => setExpanded(!expanded)}
				className="w-full px-4 py-2 flex items-center gap-2 hover:bg-muted/30 transition-colors text-left flex-shrink-0"
			>
				{expanded ? (
					<ChevronDown className="h-4 w-4 flex-shrink-0" />
				) : (
					<ChevronRight className="h-4 w-4 flex-shrink-0" />
				)}
				{icon}
				<span className="text-sm font-medium flex-1 truncate">{title}</span>
				<span className="text-xs text-muted-foreground bg-muted w-10 text-center py-0.5 rounded-full flex-shrink-0">
					{groupedEntities.length > 999 ? "999+" : groupedEntities.length}
				</span>
			</button>
			{expanded && (
				<div className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
					{groupedEntities.map((entity) => (
						<EntitySyncItem
							key={entity.action.path}
							action={entity.action}
							childFiles={entity.childFiles}
						/>
					))}
				</div>
			)}
		</div>
	);
}
```

**Step 3: Update ConflictList to use entity display**

The conflict list also needs updating to show entity names. Update the conflict rendering (around lines 783-830) to use `EntitySyncItem`:

```typescript
{conflicts.map((conflict) => {
	const resolution = resolutions[conflict.path];
	// Extract entity metadata from path
	const metadata = {
		path: conflict.path,
		action: "modify" as const,
		display_name: conflict.path.split("/").pop() || conflict.path,
		entity_type: conflict.path.endsWith(".form.json")
			? "form"
			: conflict.path.endsWith(".agent.json")
			? "agent"
			: conflict.path.startsWith("apps/")
			? "app"
			: "workflow",
	};

	return (
		<EntitySyncItem
			key={conflict.path}
			action={metadata}
			isConflict
			resolution={resolution}
			onResolve={(res) => onResolve(conflict.path, res)}
		/>
	);
})}
```

**Step 4: Run type check**

Run: `cd client && npm run tsc`
Expected: PASS

**Step 5: Run lint**

Run: `cd client && npm run lint`
Expected: PASS (fix any issues)

**Step 6: Commit**

```bash
git add client/src/components/editor/SourceControlPanel.tsx
git commit -m "feat(sync-ui): update SourceControlPanel with entity-centric display"
```

---

### Task 8: Manual Testing

**Step 1: Start dev stack**

Run: `./debug.sh`

**Step 2: Create test entities**

1. Create a form via the UI
2. Create an agent via the UI
3. Create an app with a few files via the UI
4. Create a workflow

**Step 3: Trigger sync preview**

1. Go to Source Control panel
2. Click refresh/sync
3. Verify entities show with display names and icons
4. Verify apps are grouped with expandable file lists

**Step 4: Test conflict resolution**

1. Make local changes to an entity
2. Simulate remote changes (or use a real GitHub repo)
3. Verify conflict shows with entity name, not path
4. Verify resolution buttons work at entity level

---

## Phase 2: Remove Forms/Agents from Editor

### Task 9: Create Migration to Delete workspace_files Entries

**Files:**
- Create: `api/alembic/versions/YYYYMMDD_remove_form_agent_workspace_files.py`

**Step 1: Generate migration**

Run: `cd api && alembic revision -m "remove_form_agent_workspace_files"`

**Step 2: Edit the migration**

```python
"""Remove form and agent entries from workspace_files.

These entities are now fully virtual - they exist only in their
entity tables and are serialized on-the-fly for git sync.

Revision ID: <auto-generated>
Revises: <previous>
Create Date: <auto-generated>
"""
from alembic import op


# revision identifiers
revision = "<auto-generated>"
down_revision = "<previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Delete form and agent entries from workspace_files."""
    op.execute("""
        DELETE FROM workspace_files
        WHERE entity_type IN ('form', 'agent')
    """)


def downgrade() -> None:
    """No downgrade - entries were virtual anyway."""
    pass
```

**Step 3: Commit**

```bash
git add api/alembic/versions/*remove_form_agent_workspace_files*.py
git commit -m "migration: remove form/agent entries from workspace_files"
```

---

### Task 10: Remove S3 Write Functions from Forms Router

**Files:**
- Modify: `api/src/routers/forms.py`

**Step 1: Remove `_write_form_to_file` function**

Delete the entire function (lines ~259-315).

**Step 2: Remove `_update_form_file` function**

Delete the entire function (lines ~318-348).

**Step 3: Remove `_deactivate_form_file` function**

Delete this function if it exists.

**Step 4: Remove calls to these functions**

Search for `_write_form_to_file` and `file_path = await _write_form_to_file` and remove those lines. Also remove the `form.file_path = file_path` assignments.

**Step 5: Remove FileStorageService import if no longer used**

Check if `FileStorageService` is still used elsewhere in the file. If not, remove the import.

**Step 6: Run type check**

Run: `cd api && pyright src/routers/forms.py`
Expected: PASS

**Step 7: Run tests**

Run: `./test.sh tests/integration/api/test_forms.py -v`
Expected: PASS (tests should still pass without S3 writes)

**Step 8: Commit**

```bash
git add api/src/routers/forms.py
git commit -m "refactor(forms): remove S3 write functions - forms are now virtual"
```

---

### Task 11: Remove S3 Write Functions from Agents Router

**Files:**
- Modify: `api/src/routers/agents.py`

**Step 1: Remove `_write_agent_to_file` function**

Delete the entire function.

**Step 2: Remove calls to the function**

Search for `_write_agent_to_file` calls and remove them along with `file_path` assignments.

**Step 3: Run type check**

Run: `cd api && pyright src/routers/agents.py`
Expected: PASS

**Step 4: Run tests**

Run: `./test.sh tests/integration/api/test_agents.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/src/routers/agents.py
git commit -m "refactor(agents): remove S3 write functions - agents are now virtual"
```

---

### Task 12: Remove S3 Writes from MCP Tools

**Files:**
- Modify: `api/src/services/mcp_server/tools/forms.py`
- Modify: `api/src/services/mcp_server/tools/agents.py`

**Step 1: Remove form S3 write calls in MCP tools**

Search for `_write_form_to_file` in `tools/forms.py` and remove those calls.

**Step 2: Remove agent S3 write calls in MCP tools**

Search for `_write_agent_to_file` in `tools/agents.py` and remove those calls.

**Step 3: Run type check**

Run: `cd api && pyright src/services/mcp_server/tools/forms.py src/services/mcp_server/tools/agents.py`
Expected: PASS

**Step 4: Commit**

```bash
git add api/src/services/mcp_server/tools/forms.py api/src/services/mcp_server/tools/agents.py
git commit -m "refactor(mcp): remove S3 writes from form/agent MCP tools"
```

---

### Task 13: Create Migration to Remove file_path Columns

**Files:**
- Create: `api/alembic/versions/YYYYMMDD_remove_file_path_columns.py`

**Step 1: Generate migration**

Run: `cd api && alembic revision -m "remove_file_path_columns"`

**Step 2: Edit the migration**

```python
"""Remove file_path columns from forms and agents tables.

These fields are no longer used now that forms/agents are fully virtual.

Revision ID: <auto-generated>
Revises: <previous>
Create Date: <auto-generated>
"""
from alembic import op
import sqlalchemy as sa


revision = "<auto-generated>"
down_revision = "<previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove file_path columns."""
    op.drop_column("forms", "file_path")
    op.drop_column("agents", "file_path")


def downgrade() -> None:
    """Re-add file_path columns."""
    op.add_column("forms", sa.Column("file_path", sa.String(1000), nullable=True))
    op.add_column("agents", sa.Column("file_path", sa.String(1000), nullable=True))
```

**Step 3: Update ORM models**

Remove `file_path` from `api/src/models/orm/forms.py` and `api/src/models/orm/agents.py`.

**Step 4: Run type check**

Run: `cd api && pyright`
Expected: PASS (may need to fix references to file_path elsewhere)

**Step 5: Commit**

```bash
git add api/alembic/versions/*remove_file_path*.py api/src/models/orm/forms.py api/src/models/orm/agents.py
git commit -m "migration: remove file_path columns from forms and agents"
```

---

### Task 14: Run Full Test Suite

**Step 1: Run all backend tests**

Run: `./test.sh`
Expected: All tests PASS

**Step 2: Run type checks**

Run: `cd api && pyright`
Expected: PASS

Run: `cd client && npm run tsc`
Expected: PASS

**Step 3: Run linting**

Run: `cd api && ruff check .`
Expected: PASS

Run: `cd client && npm run lint`
Expected: PASS

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address test and lint issues from virtual entity changes"
```

---

## Summary

**Phase 1 (Tasks 1-8):** Enhances git sync UI with entity display names and icons. Non-breaking, can be deployed independently.

**Phase 2 (Tasks 9-14):** Removes forms/agents from editor entirely. Requires coordinated deploy with migrations.

**Key files modified:**
- `api/src/services/github_sync.py` - SyncAction model + enrichment
- `api/src/services/github_sync_entity_metadata.py` - New metadata extraction
- `client/src/components/editor/SourceControlPanel.tsx` - Entity-centric UI
- `client/src/components/editor/EntitySyncItem.tsx` - New component
- `client/src/components/editor/groupSyncActions.ts` - Grouping utility
- `api/src/routers/forms.py` - Remove S3 writes
- `api/src/routers/agents.py` - Remove S3 writes
- `api/src/models/orm/forms.py` - Remove file_path
- `api/src/models/orm/agents.py` - Remove file_path
