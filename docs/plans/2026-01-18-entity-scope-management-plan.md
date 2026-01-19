# Entity Scope Management Plan

**Date:** 2026-01-18
**Supersedes:** 2026-01-17-organization-scoped-editor-implementation-plan.md

## Overview

This plan implements a dedicated maintenance page for managing organization and role assignments for platform entities (workflows, forms, agents). The editor will have simpler org-grouping with drag-drop reassignment.

## Key Design Decisions

1. **No inline prompts on save** - Entities are created with default state, managed via maintenance page
2. **No "limbo" state** - `org_id = NULL` + `access_level = 'role_based'` with no roles is valid, just means platform admins only
3. **Two surfaces:**
   - **Maintenance page** - Bulk management with filters, multi-select, drag-to-assign
   - **Editor** - Org-grouped file tree with drag-drop between orgs

## Phase 1: Fix CSRF Bug (Quick Win)

**Goal:** Unblock workflow organization updates immediately.

### Task 1.1: Fix useUpdateWorkflow hook

**File:** `client/src/hooks/useWorkflows.ts`

**Status:** ✅ Complete - Changed to use `authFetch` instead of raw `fetch`.

---

## Phase 2: Entity Scope Management Page

**Goal:** Create dedicated page for managing org and role assignments.

### Task 2.1: Create page route and layout

**File:** `client/src/pages/maintenance/EntityScopeManagement.tsx` (new)

**Layout:**
```
┌─────────────────────────────────┬──────────────────────────────────────┐
│  ENTITIES (narrower, ~40%)      │  TARGETS (wider, ~60%)               │
│                                 │                                      │
│  [Filters]                      │  ┌─ ORGANIZATIONS ─────────────────┐ │
│  Type: [All ▼]                  │  │ 🌐 Global │ Acme │ Beta │ ...   │ │
│  Org:  [All ▼]                  │  └──────────────────────────────────┘ │
│  Access: [All ▼]                │                                      │
│  Search: [________]             │  ┌─ ROLES ─────────────────────────┐ │
│                                 │  │ 🔐 Auth │ Admin │ Viewer │ ...  │ │
│  ┌──────────────────────┐       │  └──────────────────────────────────┘ │
│  │ □ process_invoices   │       │                                      │
│  │   workflow · Acme    │       │                                      │
│  │   role: Admin        │       │                                      │
│  └──────────────────────┘       │                                      │
│  ┌──────────────────────┐       │                                      │
│  │ □ user_form          │       │                                      │
│  │   form · (Global)    │       │                                      │
│  │   access: global     │       │                                      │
│  └──────────────────────┘       │                                      │
│  ...                            │                                      │
└─────────────────────────────────┴──────────────────────────────────────┘
```

### Task 2.2: Create useEntitiesWithScope hook

**File:** `client/src/hooks/useEntitiesWithScope.ts` (new)

Fetches all platform entities with their org and access level info:

```typescript
interface EntityWithScope {
  id: string;
  name: string;
  path: string;
  entityType: 'workflow' | 'form' | 'agent';
  organizationId: string | null;
  organizationName: string | null;
  accessLevel: 'global' | 'authenticated' | 'role_based' | null;
  roles: string[];  // Role names if role_based
  createdAt: string;
}

export function useEntitiesWithScope(filters?: {
  entityType?: string;
  organizationId?: string | null;
  accessLevel?: string;
  search?: string;
}) {
  // Returns { data: EntityWithScope[], isLoading, error, refetch }
}
```

**Backend requirement:** Need endpoint that returns entities with scope info. May need to aggregate from workflows, forms, agents tables.

### Task 2.3: Create EntityCard component

**File:** `client/src/pages/maintenance/components/EntityCard.tsx` (new)

Card component for entity list:

```typescript
interface EntityCardProps {
  entity: EntityWithScope;
  selected: boolean;
  onSelect: (selected: boolean) => void;
  draggable?: boolean;
}
```

**Features:**
- Checkbox for selection
- Entity type icon (workflow/form/agent)
- Name and path
- Current org (or "Global")
- Current access level and roles
- Draggable for drag-drop

### Task 2.4: Create OrgDropTarget component

**File:** `client/src/pages/maintenance/components/OrgDropTarget.tsx` (new)

Drop target for organizations row:

```typescript
interface OrgDropTargetProps {
  organization: { id: string | null; name: string };  // null = Global
  isPinned?: boolean;  // Global is pinned
  onDrop: (entityIds: string[], orgId: string | null) => void;
}
```

### Task 2.5: Create RoleDropTarget component

**File:** `client/src/pages/maintenance/components/RoleDropTarget.tsx` (new)

Drop target for roles row:

```typescript
interface RoleDropTargetProps {
  role: { id: string; name: string } | 'authenticated';  // 'authenticated' is pinned
  isPinned?: boolean;
  onDrop: (entityIds: string[], roleId: string | 'authenticated') => void;
}
```

**Behavior:**
- Drop sets `access_level = 'role_based'` and assigns the role
- For 'authenticated', sets `access_level = 'authenticated'`

### Task 2.6: Wire up drag-drop and API calls

**File:** `client/src/pages/maintenance/EntityScopeManagement.tsx`

**State:**
```typescript
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
```

**Handlers:**
```typescript
const handleOrgDrop = async (entityIds: string[], orgId: string | null) => {
  await updateEntitiesOrganization(entityIds, orgId);
  refetch();
};

const handleRoleDrop = async (entityIds: string[], roleId: string | 'authenticated') => {
  if (roleId === 'authenticated') {
    await updateEntitiesAccessLevel(entityIds, 'authenticated');
  } else {
    await updateEntitiesRole(entityIds, roleId);
  }
  refetch();
};
```

### Task 2.7: Add filters UI

**File:** `client/src/pages/maintenance/EntityScopeManagement.tsx`

Filter controls:
- Entity type dropdown (All, Workflow, Form, Agent)
- Organization dropdown (All, Global, + each org)
- Access level dropdown (All, Global, Authenticated, Role-based)
- Search input (filters by name/path)

---

## Phase 3: Backend API for Scope Management

**Goal:** Provide endpoints for fetching and updating entity scopes.

### Task 3.1: Create entities scope list endpoint

**File:** `api/src/routers/maintenance.py` (or new file)

```
GET /api/maintenance/entities
Query params: entity_type, organization_id, access_level, search, limit, offset
Response: { entities: EntityWithScope[], total: number }
```

Aggregates from workflows, forms, agents tables with their scope info.

### Task 3.2: Create bulk org update endpoint

**File:** `api/src/routers/maintenance.py`

```
PATCH /api/maintenance/entities/organization
Body: { entity_ids: string[], organization_id: string | null }
```

Updates `organization_id` for all specified entities (across tables).

### Task 3.3: Create bulk access level update endpoint

**File:** `api/src/routers/maintenance.py`

```
PATCH /api/maintenance/entities/access-level
Body: { entity_ids: string[], access_level: 'global' | 'authenticated' | 'role_based', role_id?: string }
```

Updates `access_level` and optionally assigns a role.

### Task 3.4: Add Pydantic models

**File:** `api/shared/models.py`

```python
class EntityWithScope(BaseModel):
    id: str
    name: str
    path: str
    entity_type: Literal['workflow', 'form', 'agent']
    organization_id: str | None
    organization_name: str | None
    access_level: Literal['global', 'authenticated', 'role_based'] | None
    roles: list[str]
    created_at: datetime

class BulkOrgUpdateRequest(BaseModel):
    entity_ids: list[str]
    organization_id: str | None

class BulkAccessLevelUpdateRequest(BaseModel):
    entity_ids: list[str]
    access_level: Literal['global', 'authenticated', 'role_based']
    role_id: str | None = None
```

---

## Phase 4: Editor Org-Grouped File Tree (Follow-up)

**Goal:** Visual organization in editor with drag-drop reassignment.

### Task 4.1: Create OrgScopedFileOperations adapter

**File:** `client/src/services/orgScopedFileOperations.ts` (new)

Wraps `fileService` to present org-grouped view:
- Root lists org containers (Global first, then orgs alphabetically)
- Each container shows files belonging to that org
- Drag-drop between containers calls API to update org

### Task 4.2: Wire up in Editor

**File:** `client/src/pages/Editor.tsx` (or equivalent)

Use org-scoped operations with existing `orgScopedIconResolver`.

### Task 4.3: Handle drag-drop org reassignment

When dropping file on different org container:
1. Call API to update entity's `organization_id`
2. Refresh file tree

---

## Phase 5: Git Sync Integration (Future)

**Goal:** Handle org assignment for entities from git sync.

**Approach:** Since we now have a maintenance page, git sync can:
1. Import entities with default state (`org_id = NULL`, `access_level = 'role_based'`, no roles)
2. Platform admins use maintenance page to assign orgs/roles
3. Optionally: Show notification "X new entities need scope assignment"

This removes the blocking flow from source control panel.

---

## Testing Checklist

### Phase 1
- [x] Can change workflow organization via WorkflowEditDialog without CSRF error

### Phase 2
- [ ] Page renders with two-column layout
- [ ] Entities load with filters working
- [ ] Click to select/deselect entities
- [ ] Multi-select works (click multiple cards)
- [ ] Drag entity to org updates organization
- [ ] Drag entity to role updates access level and assigns role
- [ ] Drag to "Global" sets org_id = NULL
- [ ] Drag to "Authenticated" sets access_level = 'authenticated'
- [ ] Filters work: type, org, access level, search
- [ ] Bulk drag (multiple selected) works

### Phase 3
- [ ] GET /api/maintenance/entities returns aggregated data
- [ ] PATCH organization endpoint updates across tables
- [ ] PATCH access-level endpoint updates correctly
- [ ] Endpoints respect existing permissions

### Phase 4
- [ ] Editor shows org-grouped file tree
- [ ] Drag-drop between orgs works
- [ ] Global container at top

---

## File Summary

### New Files
- `client/src/pages/maintenance/EntityScopeManagement.tsx` - Main page
- `client/src/pages/maintenance/components/EntityCard.tsx` - Entity card
- `client/src/pages/maintenance/components/OrgDropTarget.tsx` - Org drop target
- `client/src/pages/maintenance/components/RoleDropTarget.tsx` - Role drop target
- `client/src/hooks/useEntitiesWithScope.ts` - Data fetching hook
- `client/src/services/orgScopedFileOperations.ts` - FileOperations adapter (Phase 4)
- `api/src/routers/maintenance.py` - Backend endpoints

### Modified Files
- `client/src/hooks/useWorkflows.ts` - ✅ CSRF fix done
- `client/src/App.tsx` or router config - Add route for maintenance page
- `api/shared/models.py` - Add Pydantic models

---

## Implementation Order

1. **Phase 1** - ✅ Complete
2. **Phase 2 + 3** - Maintenance page (frontend + backend together)
3. **Phase 4** - Editor org-grouping (can be deferred)
4. **Phase 5** - Git sync integration (future)

Phase 2 and 3 should be worked together since the frontend needs the backend endpoints.
