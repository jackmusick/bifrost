# Organization-Scoped Editor Implementation Plan

**Date:** 2026-01-17
**Design Doc:** [2026-01-17-organization-scoped-editor-design.md](./2026-01-17-organization-scoped-editor-design.md)

## Overview

This plan implements the organization-scoped editor design. The work is broken into phases that can be completed incrementally, with each phase delivering value independently.

## Current State

**Existing infrastructure we can leverage:**

| Component | Location | Notes |
|-----------|----------|-------|
| Entity type icons | `FileTree.tsx:140-148` | Already has workflow/form/app/agent icons with colors |
| Extension icons | `FileTree.tsx:153-194` | Python, JSON, etc. icons for fallback |
| Org scope context | `OrgScopeContext.tsx` | Provides `useOrgScope()` hook, persists to localStorage |
| File tree component | `FileTree.tsx` | Drag-drop, expand/collapse, CRUD operations |
| Git sync UI | `SourceControlPanel.tsx` | Pull/push preview, conflict resolution, orphan warnings |
| Workflow update hook | `useWorkflows.ts:76-109` | **Has CSRF bug** - uses raw `fetch` |

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
    entityType: 'workflow' | 'form' | 'app' | 'agent';
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

1. After `fileService.writeFile()` returns, check if response indicates a new scoped entity was created
2. If new entity AND no org assigned, show `OrganizationScopeDialog`
3. On confirm, call API to update entity's organization

**Backend requirement:** The `writeFile` response already returns `entity_type` and `entity_id`. Need to also return `is_new_entity: boolean` to distinguish creates from updates.

### Task 3.2: Add is_new_entity to file write response

**File:** `api/src/handlers/files_handlers.py` (or wherever writeFile is handled)

Add `is_new_entity` field to response when indexer creates a new workflow/form/app/agent.

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

### Task 4.1: Update useFileTree to group by organization

**File:** `client/src/hooks/useFileTree.ts`

**Changes:**
1. Fetch entity org mappings along with file list
2. Build tree structure with org containers at root:
   - Global (null org_id)
   - Org A
   - Org B
   - etc.
3. Place files under their entity's org container
4. Non-entity files (plain Python modules) go under Global

**Data structure change:**
```typescript
// Current: flat list of files grouped into folder tree
// New: org containers at root, each containing folder tree

interface OrgContainer {
  type: 'org-container';
  orgId: string | null;  // null = Global
  orgName: string;
  children: FileTreeNode[];
}
```

### Task 4.2: Update FileTree component rendering

**File:** `client/src/components/editor/FileTree.tsx`

**Changes:**
1. Add org container rendering with distinct icon (📌 for Global, 📍 for orgs)
2. Org containers not deletable (no trash icon)
3. Org containers always collapsible
4. Visual distinction: different background/indent/styling

### Task 4.3: Update file tree drag-drop for re-scoping

**File:** `client/src/components/editor/FileTree.tsx`

**Changes:**
1. Allow dragging files between org containers
2. On drop to different org container:
   - Show `OrganizationScopeDialog` pre-filled with target org
   - On confirm, update entity's organization via API
   - Refresh file tree

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
- Show entity icon (⚡📋🤖⊞)
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
- [ ] Org containers have distinct icon, not deletable
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
- `client/src/components/editor/OrganizationScopeDialog.tsx`

### Modified Files (Frontend)
- `client/src/hooks/useWorkflows.ts` - Fix CSRF bug
- `client/src/hooks/useFileTree.ts` - Group by org
- `client/src/hooks/useGitHub.ts` - Pass org assignments
- `client/src/components/editor/FileTree.tsx` - Org containers, drag-drop
- `client/src/components/editor/CodeEditor.tsx` - Scope dialog on save
- `client/src/components/editor/SourceControlPanel.tsx` - Org assignment UI

### Modified Files (Backend)
- `api/src/handlers/files_handlers.py` - Return `is_new_entity`
- `api/src/handlers/github_handlers.py` - Accept org assignments
- `api/src/services/github_sync.py` - Apply org assignments on import

---

## Recommended Implementation Order

1. **Phase 1** - Quick fix, immediate value
2. **Phase 2** - Foundation for all other phases
3. **Phase 3** - Editor save flow (most common use case)
4. **Phase 4** - Visual organization (can parallelize with Phase 3)
5. **Phase 5 + 6** - Git sync (depends on Phase 2)

Phases 3 and 4 can be worked on in parallel once Phase 2 is complete.
