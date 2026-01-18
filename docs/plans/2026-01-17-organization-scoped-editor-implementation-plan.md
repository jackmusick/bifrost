# Organization-Scoped Editor Implementation Plan

**Date:** 2026-01-17
**Updated:** 2026-01-18 (reflects modular FileTree refactor)
**Design Doc:** [2026-01-17-organization-scoped-editor-design.md](./2026-01-17-organization-scoped-editor-design.md)

## Overview

This plan implements the organization-scoped editor design. The work is broken into phases that can be completed incrementally, with each phase delivering value independently.

## Current State (Post-Refactor)

The FileTree has been refactored into a modular, dependency-injected architecture:

| Component | Location | Notes |
|-----------|----------|-------|
| **FileTree component** | `components/file-tree/FileTree.tsx` | Modular, accepts `FileOperations` interface |
| **FileOperations interface** | `components/file-tree/types.ts` | Abstract interface for any backend |
| **Icon resolvers** | `components/file-tree/icons.ts` | Includes `orgScopedIconResolver` already |
| **useFileTree hook** | `components/file-tree/useFileTree.ts` | Manages tree state, accepts operations |
| **FileNode type** | `components/file-tree/types.ts` | Has `metadata` field for custom data |
| Org scope context | `OrgScopeContext.tsx` | Provides `useOrgScope()` hook |
| Git sync UI | `SourceControlPanel.tsx` | Pull/push preview, conflict resolution |
| Workflow update hook | `useWorkflows.ts:76-109` | **Has CSRF bug** - uses raw `fetch` |

**Key insight:** The `orgScopedIconResolver` already exists and uses `file.metadata?.isOrgContainer` to detect org containers. The `FileNode.metadata` field is designed for exactly this use case.

**Removed:** The old app indexer (`.app.json`) has been removed. Entity types are now: workflow, form, agent.

## Phase 1: Fix CSRF Bug (Quick Win)

**Goal:** Unblock workflow organization updates immediately.

### Task 1.1: Fix useUpdateWorkflow hook

**File:** `client/src/hooks/useWorkflows.ts`

**Change:** Replace raw `fetch` with `apiClient.patch`:

```typescript
// Before (line 97-105)
const response = await fetch(`/api/workflows/${workflowId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// After
const response = await apiClient.patch(`/api/workflows/${workflowId}`, body);
```

**Test:** Manually verify workflow org can be changed via WorkflowEditDialog.

---

## Phase 2: Organization Scope Dialog Component

**Goal:** Create reusable dialog for all scope assignment operations.

### Task 2.1: Create OrganizationScopeDialog component

**File:** `client/src/components/editor/OrganizationScopeDialog.tsx` (new)

**Props interface:**
```typescript
interface OrganizationScopeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;

  // Single or multi-entity mode
  entities: Array<{
    path: string;
    entityType: 'workflow' | 'form' | 'agent';
    currentOrgId?: string | null;  // Pre-fill for existing entities
  }>;

  // Callback with org assignments
  onConfirm: (assignments: Record<string, string | null>) => void;
  // assignments = { [path]: orgId | null (global) }
}
```

**UI Structure:**
- Single entity mode: Simple dropdown
- Multi-entity mode: "Apply to all" row + per-entity dropdowns
- Uses existing org list from `useOrganizations()` hook
- "Global" option at top of dropdown
- Confirm button disabled until all entities have selection

### Task 2.2: Create useOrganizations hook (if not exists)

**File:** `client/src/hooks/useOrganizations.ts`

Check if this exists. If not, create a hook that fetches the org list for the dropdown.

---

## Phase 3: Editor Save Flow Integration

**Goal:** Prompt for org when saving new scoped entities.

### Task 3.1: Detect new scoped entity on save

**File:** `client/src/components/editor/CodeEditor.tsx`

**Changes to `handleManualSave()`:**

1. After file write returns, check if response indicates a new scoped entity was created
2. If new entity AND no org assigned, show `OrganizationScopeDialog`
3. On confirm, call API to update entity's organization

**Backend requirement:** The write response already returns `entity_type` and `entity_id`. Need to also return `is_new_entity: boolean` to distinguish creates from updates.

### Task 3.2: Add is_new_entity to file write response

**File:** `api/src/handlers/files_handlers.py` (or wherever writeFile is handled)

Add `is_new_entity` field to response when indexer creates a new workflow/form/agent.

### Task 3.3: Wire up dialog in CodeEditor

**File:** `client/src/components/editor/CodeEditor.tsx`

Add state and dialog rendering:
```typescript
const [scopeDialogOpen, setScopeDialogOpen] = useState(false);
const [pendingScopeEntity, setPendingScopeEntity] = useState<{...} | null>(null);

// In save handler, after detecting new entity:
if (response.is_new_entity && response.entity_type) {
  setPendingScopeEntity({
    path: filePath,
    entityType: response.entity_type,
    entityId: response.entity_id,
  });
  setScopeDialogOpen(true);
}

// Dialog callback
const handleScopeConfirm = async (assignments) => {
  const orgId = assignments[pendingScopeEntity.path];
  await updateEntityOrganization(pendingScopeEntity.entityType, pendingScopeEntity.entityId, orgId);
  setScopeDialogOpen(false);
};
```

---

## Phase 4: Organization-Scoped File Tree

**Goal:** Reorganize file tree with org containers at top level.

### Task 4.1: Create OrgScopedFileOperations adapter

**File:** `client/src/services/orgScopedFileOperations.ts` (new)

This adapter wraps the existing `fileService` and transforms the flat file list into org-grouped structure:

```typescript
import type { FileOperations, FileNode } from "@/components/file-tree/types";
import { fileService } from "./fileService";

export function createOrgScopedFileOperations(
  entityOrgMap: Map<string, string | null>  // path -> orgId
): FileOperations {
  return {
    async list(path: string): Promise<FileNode[]> {
      // If listing root, return org containers
      if (path === "") {
        return buildOrgContainers(entityOrgMap);
      }

      // If path starts with org container prefix, strip it and delegate
      const [orgPrefix, ...rest] = path.split("/");
      const realPath = rest.join("/");
      const files = await fileService.listFiles(realPath);

      // Filter to only files belonging to this org
      return files.filter(f => matchesOrg(f, orgPrefix, entityOrgMap));
    },
    // ... other methods delegate to fileService with path transformation
  };
}

function buildOrgContainers(entityOrgMap: Map<string, string | null>): FileNode[] {
  // Build: Global (null), then each org alphabetically
  // Each container has metadata.isOrgContainer = true
}
```

### Task 4.2: Fetch entity-to-org mapping

**File:** `client/src/hooks/useEntityOrgMap.ts` (new)

Hook that fetches the mapping of file paths to organization IDs:

```typescript
export function useEntityOrgMap() {
  // Fetch all entities (workflows, forms, agents) with their org_id
  // Build Map<path, orgId | null>
  // Return { data: Map, isLoading, error }
}
```

This requires a backend endpoint or extending existing endpoints to return org_id with file listings.

### Task 4.3: Wire up org-scoped operations in workspace editor

**File:** Where the workspace editor creates its FileTree (likely `client/src/pages/Editor.tsx` or similar)

```typescript
const { data: entityOrgMap } = useEntityOrgMap();
const operations = useMemo(
  () => createOrgScopedFileOperations(entityOrgMap ?? new Map()),
  [entityOrgMap]
);

<FileTree
  operations={operations}
  iconResolver={orgScopedIconResolver}  // Already exists in icons.ts
  editor={editorCallbacks}
  config={{ enableUpload: true, enableDragMove: true }}
/>
```

### Task 4.4: Handle drag-drop between org containers

**File:** `client/src/components/file-tree/FileTree.tsx`

The modular FileTree already supports drag-drop. Need to detect when drop target is a different org container:

1. In drop handler, check if source and target have different `metadata.orgId`
2. If different org, show `OrganizationScopeDialog` pre-filled with target org
3. On confirm, update entity's organization via API, then refresh tree

---

## Phase 5: Git Sync Integration

**Goal:** Require org assignment before pull completes.

### Task 5.1: Add org assignment state to SourceControlPanel

**File:** `client/src/components/editor/SourceControlPanel.tsx`

**New state:**
```typescript
const [pendingOrgAssignments, setPendingOrgAssignments] = useState<Record<string, string | null>>({});
// { [filePath]: orgId | null | undefined }
// undefined = not yet assigned (pending)
```

### Task 5.2: Update SyncActionList to show org subtext

**File:** `client/src/components/editor/SourceControlPanel.tsx`

For each incoming file that would create a scoped entity:
- Show entity icon (use `defaultIconResolver` from `file-tree/icons.ts`)
- Show file name
- Show org assignment as subtext below:
  - "Global" / "Customer A" / etc. if assigned
  - "⚠️ Pending..." if not assigned

### Task 5.3: Add "Assign Organizations" button

**File:** `client/src/components/editor/SourceControlPanel.tsx`

Above the incoming changes list:
- Button: "Assign Organizations..."
- Opens `OrganizationScopeDialog` in multi-entity mode
- Pre-fills any existing assignments
- On confirm, updates `pendingOrgAssignments` state

### Task 5.4: Block pull until all assigned

**File:** `client/src/components/editor/SourceControlPanel.tsx`

**Changes:**
1. Compute `allAssigned = !incomingEntities.some(e => pendingOrgAssignments[e.path] === undefined)`
2. Disable Pull button if `!allAssigned`
3. Show count: "X of Y entities need organization assignment"

### Task 5.5: Pass org assignments to sync execute

**File:** `client/src/hooks/useGitHub.ts` (and backend)

**Changes:**
1. Update `useSyncExecute` to accept `orgAssignments` parameter
2. Backend: Apply org assignments when creating entities during pull

**Backend file:** `api/src/services/github_sync.py` or related

Add parameter to import flow that sets `organization_id` based on provided mapping.

---

## Phase 6: Backend Support for Org Assignment on Import

**Goal:** Backend accepts org assignments during git sync.

### Task 6.1: Update sync execute endpoint

**File:** `api/src/handlers/github_handlers.py` (or similar)

**Changes:**
1. Accept `org_assignments: dict[str, str | None]` in request body
2. Pass to sync service

### Task 6.2: Update sync service to apply org assignments

**File:** `api/src/services/github_sync.py`

**Changes:**
1. When creating new entities from imported files, look up path in `org_assignments`
2. Set `organization_id` accordingly
3. If path not in assignments, raise error (don't default to global)

---

## Testing Checklist

### Phase 1
- [ ] Can change workflow organization via WorkflowEditDialog without CSRF error

### Phase 2
- [ ] Dialog renders in single-entity mode
- [ ] Dialog renders in multi-entity mode with "Apply to all"
- [ ] Confirm button disabled until all selections made
- [ ] Global option appears in dropdown

### Phase 3
- [ ] Saving new workflow prompts for org selection
- [ ] Saving new form prompts for org selection
- [ ] Saving existing file does NOT prompt
- [ ] Saving plain Python module does NOT prompt

### Phase 4
- [ ] File tree shows Global container at top
- [ ] File tree shows org containers below Global
- [ ] Files appear under correct org based on entity's organization_id
- [ ] Org containers have distinct icon (Building2), not deletable
- [ ] Drag-drop between orgs triggers scope dialog

### Phase 5
- [ ] Git pull shows org assignment subtext per file
- [ ] "Assign Organizations" button opens dialog
- [ ] Pull button disabled while entities pending
- [ ] Pull succeeds with all assignments made
- [ ] Entities land in correct orgs after pull

---

## File Summary

### New Files
- `client/src/components/editor/OrganizationScopeDialog.tsx` - Reusable scope selection dialog
- `client/src/services/orgScopedFileOperations.ts` - FileOperations adapter for org grouping
- `client/src/hooks/useEntityOrgMap.ts` - Fetch entity-to-org mapping

### Modified Files (Frontend)
- `client/src/hooks/useWorkflows.ts` - Fix CSRF bug
- `client/src/hooks/useGitHub.ts` - Pass org assignments
- `client/src/components/editor/CodeEditor.tsx` - Scope dialog on save
- `client/src/components/editor/SourceControlPanel.tsx` - Org assignment UI
- `client/src/pages/Editor.tsx` (or equivalent) - Wire up org-scoped operations

### Modified Files (Backend)
- `api/src/handlers/files_handlers.py` - Return `is_new_entity`
- `api/src/handlers/github_handlers.py` - Accept org assignments
- `api/src/services/github_sync.py` - Apply org assignments on import

### Already Exists (No Changes Needed)
- `client/src/components/file-tree/icons.ts` - `orgScopedIconResolver` already handles `metadata.isOrgContainer`
- `client/src/components/file-tree/types.ts` - `FileNode.metadata` field ready for use
- `client/src/components/file-tree/FileTree.tsx` - Modular, no changes needed

---

## Recommended Implementation Order

1. **Phase 1** - Quick fix, immediate value
2. **Phase 2** - Foundation for all other phases
3. **Phase 3** - Editor save flow (most common use case)
4. **Phase 4** - Visual organization (can parallelize with Phase 3)
5. **Phase 5 + 6** - Git sync (depends on Phase 2)

Phases 3 and 4 can be worked on in parallel once Phase 2 is complete.

---

## Architecture Notes

The modular FileTree refactor means we don't touch the core component at all. Instead:

1. **Create adapter** (`orgScopedFileOperations`) that transforms paths and injects org containers
2. **Use existing icon resolver** (`orgScopedIconResolver`) that's already in `icons.ts`
3. **Pass to FileTree** via dependency injection - no coupling to org logic in the component

This keeps the FileTree reusable for other contexts (App Builder JSX files, etc.) while adding org-scoping as a layer on top.
