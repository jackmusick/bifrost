# Code Editor Sync UI Improvements

**Date:** 2026-01-21
**Status:** Design Complete

## Overview

Three improvements to the Code Editor's source control panel to make the GitHub sync experience more intuitive:

1. **App conflict grouping** - Group app conflicts the same way incoming/outgoing are grouped, with per-file or all-at-once resolution
2. **Diff preview** - Click any sync item to see a readonly diff in the editor area
3. **Display names for conflicts** - Show entity names (e.g., "My Form") instead of filenames (e.g., `my-form.form.json`)

## Problem Analysis

### Issue 1: Apps not grouped in conflicts

The `groupSyncActions.ts` function handles app grouping for incoming/outgoing, but conflicts bypass this entirely. They render flat, making it hard to understand which files belong to which app and resolve them together.

### Issue 2: No preview capability

Users must choose "Keep Local" or "Accept Incoming" without seeing what's actually different. There's no way to preview the content before making a decision.

### Issue 3: Filenames shown instead of entity names

`SyncConflictInfo` has no `display_name` field. The frontend synthesizes it from the filename:
```typescript
display_name: conflict.path.split("/").pop() || conflict.path
```

So `forms/my-form.form.json` becomes `my-form.form.json` instead of "My Form".

## Solution Design

### Backend Changes

#### 1. Enrich `SyncConflictInfo` with metadata

**File:** `api/src/models/contracts/github.py`

Add the same metadata fields that `SyncAction` already has:

```python
class SyncConflictInfo(BaseModel):
    """Information about a conflict between local and remote."""
    path: str = Field(..., description="File path with conflict")
    local_content: str | None = Field(default=None, description="Local content")
    remote_content: str | None = Field(default=None, description="Remote content")
    local_sha: str = Field(..., description="SHA of local content")
    remote_sha: str = Field(..., description="SHA of remote content")
    # New fields
    display_name: str | None = Field(default=None, description="Human-readable name")
    entity_type: str | None = Field(default=None, description="Entity type")
    parent_slug: str | None = Field(default=None, description="Parent app slug for app files")
```

**File:** `api/src/routers/github.py`

When building the conflicts list, enrich with metadata using `extract_entity_metadata()`:

```python
from src.services.github_sync_entity_metadata import extract_entity_metadata

# In the sync preview endpoint
for c in preview.conflicts:
    metadata = extract_entity_metadata(c.path, c.remote_content.encode() if c.remote_content else None)
    conflicts.append(SyncConflictInfo(
        path=c.path,
        local_content=c.local_content,
        remote_content=c.remote_content,
        local_sha=c.local_sha,
        remote_sha=c.remote_sha,
        display_name=metadata.display_name,
        entity_type=metadata.entity_type,
        parent_slug=metadata.parent_slug,
    ))
```

#### 2. New endpoint for on-demand content fetching

**Endpoint:** `GET /api/github/sync/content`

Fetches the "other side" content when opening a diff preview. This keeps the sync preview response lightweight.

```python
class SyncContentRequest(BaseModel):
    path: str  # File path to fetch content for
    source: Literal["local", "remote"]  # Which side to fetch

class SyncContentResponse(BaseModel):
    path: str
    content: str | None  # null if file doesn't exist on that side
```

**Implementation:**
- `source: "local"` - Read from database based on entity type (forms, agents, apps, workflows)
- `source: "remote"` - Read from cloned repo on disk
- Return `null` if file doesn't exist on that side (new file being added)

### Frontend Changes

#### 1. Conflict grouping function

**File:** `client/src/components/editor/groupSyncActions.ts`

Add a new function that mirrors `groupSyncActions()` but for conflicts:

```typescript
export interface GroupedConflict {
    conflict: SyncConflictInfo;  // The app.json conflict (or standalone entity)
    childConflicts: SyncConflictInfo[];  // Child file conflicts for apps
}

export function groupConflicts(conflicts: SyncConflictInfo[]): GroupedConflict[] {
    const appGroups = new Map<string, GroupedConflict>();
    const standaloneConflicts: GroupedConflict[] = [];

    for (const conflict of conflicts) {
        if (conflict.entity_type === "app" && conflict.parent_slug) {
            // App metadata (app.json) - create or update group
            const existing = appGroups.get(conflict.parent_slug);
            if (existing) {
                existing.conflict = conflict;
            } else {
                appGroups.set(conflict.parent_slug, {
                    conflict,
                    childConflicts: [],
                });
            }
        } else if (conflict.entity_type === "app_file" && conflict.parent_slug) {
            // App file - add to parent group
            const existing = appGroups.get(conflict.parent_slug);
            if (existing) {
                existing.childConflicts.push(conflict);
            } else {
                appGroups.set(conflict.parent_slug, {
                    conflict: {
                        path: `apps/${conflict.parent_slug}/app.json`,
                        display_name: conflict.parent_slug,
                        entity_type: "app",
                        parent_slug: conflict.parent_slug,
                    } as SyncConflictInfo,
                    childConflicts: [conflict],
                });
            }
        } else {
            // Standalone entity (form, agent, workflow)
            standaloneConflicts.push({
                conflict,
                childConflicts: [],
            });
        }
    }

    // Sort and return
    const sortedApps = Array.from(appGroups.values()).sort((a, b) =>
        (a.conflict.display_name || "").localeCompare(b.conflict.display_name || "")
    );
    const sortedStandalone = standaloneConflicts.sort((a, b) =>
        (a.conflict.display_name || "").localeCompare(b.conflict.display_name || "")
    );

    return [...sortedApps, ...sortedStandalone];
}
```

#### 2. Update conflict rendering in SourceControlPanel

**File:** `client/src/components/editor/SourceControlPanel.tsx`

Replace flat conflict rendering with grouped rendering:

```typescript
// Before: conflicts.map((conflict) => ...)
// After: groupConflicts(conflicts).map((group) => ...)
```

**App-level resolution:**

When clicking "Keep Local" or "Accept Incoming" on an app header:
- Set resolution for the app.json path
- Set resolution for ALL child conflict paths

Individual child files can still be resolved independently, overriding the app-level choice.

#### 3. Add click handler for diff preview

**File:** `client/src/components/editor/SourceControlPanel.tsx`

Add `onClick` to all sync item rows (incoming, outgoing, conflicts) that triggers diff mode in the editor.

#### 4. Add diff mode to editor

**File:** Editor area component (likely `AppCodeEditorLayout.tsx` or parent)

Add editor state for diff mode:

```typescript
interface EditorState {
    mode: "edit" | "diff";
    // Diff mode state
    diffPath?: string;
    diffDisplayName?: string;
    diffEntityType?: string;
    diffLocalContent?: string | null;
    diffRemoteContent?: string | null;
    diffIsConflict?: boolean;
    diffResolution?: "keep_local" | "keep_remote";
    onDiffResolve?: (resolution: "keep_local" | "keep_remote") => void;
}
```

**Diff view UI:**

```
┌─────────────────────────────────────────────────────────────┐
│ Header: [Icon] Display Name (entity type badge)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Monaco DiffEditor (readonly)                              │
│   Left: "Local (Database)"  |  Right: "Incoming (GitHub)"   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Footer (conflicts only): [Keep Local] [Accept Incoming]     │
└─────────────────────────────────────────────────────────────┘
```

**Data flow when entering diff mode:**

1. Click sync item row
2. Set editor to diff mode with available content
3. If missing content (incoming needs local, outgoing needs remote):
   - Show loading state
   - Call `GET /api/github/sync/content` to fetch missing side
   - Update diff view with fetched content
4. For conflicts: Both sides already available in `SyncConflictInfo`

**Exiting diff mode:**

- Click on file tree to edit a file
- Click a different sync item (switches to that diff)
- Close the source control panel

#### 5. Regenerate TypeScript types

After API changes:
```bash
cd client && npm run generate:types
```

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────────┐
│ Source Control Panel              │  Editor Area                    │
│                                   │                                 │
│ ▼ Incoming (3)                    │  ┌─────────────────────────────┐│
│   📝 Contact Form                 │  │ 📝 Contact Form             ││
│   🤖 Support Agent    ◄── click ──┼──│─────────────────────────────││
│   📱 Dashboard App (2 files)      │  │ Local         │ Incoming    ││
│                                   │  │ (Database)    │ (GitHub)    ││
│ ▼ Outgoing (1)                    │  │               │             ││
│   ⚡ Export Workflow              │  │ {             │ {           ││
│                                   │  │   "name":     │   "name":   ││
│ ▼ Conflicts (2)                   │  │   "Support",  │   "Support",││
│   📱 Settings App (1 file)        │  │   "model":    │   "model":  ││
│     └─ 📄 config.json ⚠️          │  │   "gpt-4"     │   "gpt-4o"  ││
│   📝 User Form ⚠️                 │  │ }             │ }           ││
│     [Keep Local] [Accept Incoming]│  │               │             ││
│                                   │  └─────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation Order

1. **Backend: Enrich SyncConflictInfo** - Add metadata fields, populate in router
2. **Backend: Content fetch endpoint** - New endpoint for on-demand content
3. **Frontend: Regenerate types** - Get new TypeScript definitions
4. **Frontend: groupConflicts function** - Add conflict grouping logic
5. **Frontend: Update SourceControlPanel** - Use grouped conflicts, add click handlers
6. **Frontend: Add diff mode to editor** - Monaco DiffEditor, loading states, resolution buttons
7. **Testing** - Unit tests for grouping, integration tests for new endpoint

## Success Criteria

- [ ] Apps in conflicts are grouped with expandable child files
- [ ] "Resolve all" on app header sets resolution for all child conflicts
- [ ] Individual conflict files can still be resolved independently
- [ ] Clicking any sync item opens diff view in editor area
- [ ] Diff view shows local vs remote content correctly
- [ ] Diff view is readonly
- [ ] Conflicts show resolution buttons in diff view
- [ ] Forms and agents show display names, not filenames
- [ ] Loading state shown while fetching content for diff
