# App Builder Implementation Plan

## Overview

This plan covers the remaining implementation work before the comprehensive review:
1. Entity type unification cleanup
2. WorkflowSelectorDialog integration across all workflow selection points

For the comprehensive review checklist, see: `2026-01-14-app-builder-review-checklist.md`

---

## Phase 1: Entity Type Unification Cleanup

### Status: 95% Complete

The model changes are done. Only cleanup and verification remain.

### Task 1.1: Delete Unused Types File

**Status:** Ready to delete (0 active imports confirmed)

```bash
rm client/src/lib/app-builder-types.ts
```

### Task 1.2: Final Verification

```bash
# Backend
cd api && pyright && ruff check .

# Frontend (requires dev stack running)
cd client && npm run generate:types && npm run tsc && npm run lint

# Tests
./test.sh
```

---

## Phase 2: WorkflowSelectorDialog Integration

### Status: Component exists, needs integration

The `WorkflowSelectorDialog` component exists at `client/src/components/workflows/WorkflowSelectorDialog.tsx` with full role context support. It needs integration into all workflow selection points.

### Why This Matters

The selector dialog shows:
- Parent entity's roles (left panel)
- Workflow role status with mismatch warnings
- Option to auto-assign missing roles on select

Without this integration, users don't see role context when selecting workflows, leading to access issues at runtime.

### Integration Points

#### High Priority (Core editing flows)

| Location | File | Field(s) | Current | Action |
|----------|------|----------|---------|--------|
| Page Launch Workflow | `PropertyEditor.tsx:374-390` | `launch_workflow_id` | WorkflowSelector | Upgrade to dialog |
| Button Workflow Action | `PropertyEditor.tsx:1169-1205` | `props.workflow_id` | WorkflowSelector | Upgrade to dialog |
| Form Submit Action | `PropertyEditor.tsx:1207-1246` | `props.workflow_id` | WorkflowSelector | Upgrade to dialog |
| Table Row Actions | `TableActionBuilder.tsx:289-332` | `action.on_click.workflow_id` | WorkflowSelector | Upgrade to dialog |
| Action Builder | `ActionBuilder.tsx:174-200` | `value.workflowId` | WorkflowSelector | Upgrade to dialog |

#### Medium Priority (Other editors)

| Location | File | Field(s) | Current | Action |
|----------|------|----------|---------|--------|
| Form Editor | `FormEditor.tsx` (if exists) | `workflow_id`, `launch_workflow_id` | TBD | Add dialog |
| Agent Tools | `AgentEditor.tsx` | `tool_ids` | Multi-select | Add dialog (multi mode) |
| Event Subscriptions | `CreateSubscriptionDialog.tsx:117` | `workflowId` | Native Select | Upgrade to dialog |

### Implementation Pattern

Each integration follows this pattern:

```typescript
// 1. Add state for dialog
const [workflowSelectorOpen, setWorkflowSelectorOpen] = useState(false);

// 2. Get entity roles from context
const { roles: entityRoles } = useAppContext(); // or form/agent context

// 3. Replace WorkflowSelector with trigger + dialog
<Button onClick={() => setWorkflowSelectorOpen(true)}>
  {currentWorkflow?.name || "Select Workflow"}
</Button>

<WorkflowSelectorDialog
  open={workflowSelectorOpen}
  onOpenChange={setWorkflowSelectorOpen}
  entityRoles={entityRoles}
  workflowType="workflow"
  mode="single"
  selectedWorkflowIds={value ? [value] : []}
  onSelect={(ids, assignRoles) => {
    onChange(ids[0] || null);
    // assignRoles flag handled by save mutation (auto-syncs roles)
  }}
/>
```

### Backend Auto-Assignment (Already Implemented)

When forms/agents/apps are saved, the backend automatically syncs roles:
- `sync_form_roles_to_workflows()` in `forms.py`
- `sync_agent_roles_to_workflows()` in `agents.py`
- `sync_app_roles_to_workflows()` in `applications.py`

The `assignRoles` flag from the dialog is informational - role sync happens on save regardless.

---

## Phase 3: Redis Caching (Deferred)

### Status: Not started, not blocking

Performance optimization for workflow role lookups. Defer until performance profiling shows this is a bottleneck.

---

## Implementation Checklist

### Phase 1: Cleanup (30 min)
- [ ] Delete `client/src/lib/app-builder-types.ts`
- [ ] Run `npm run generate:types` (requires dev stack)
- [ ] Run `npm run tsc` - verify no type errors
- [ ] Run `npm run lint` - verify no lint errors
- [ ] Run `pyright` in api/ - verify no type errors
- [ ] Run `./test.sh` - all tests pass

### Phase 2: PropertyEditor Integration (2 hours)
- [ ] Add `WorkflowSelectorDialog` import to `PropertyEditor.tsx`
- [ ] Replace page launch workflow selector
- [ ] Replace button workflow action selector
- [ ] Replace form submit action selector
- [ ] Test each integration in dev environment

### Phase 3: Action Builder Integration (1 hour)
- [ ] Update `ActionBuilder.tsx` to use dialog
- [ ] Update `TableActionBuilder.tsx` to use dialog
- [ ] Test table row action workflow selection

### Phase 4: Other Editors (2 hours)
- [ ] Form Editor - add workflow selector dialog
- [ ] Agent Editor - add multi-select dialog for tools
- [ ] Event Subscriptions - upgrade to dialog

### Phase 5: Comprehensive Review
- [ ] Execute review checklist (see `2026-01-14-app-builder-review-checklist.md`)
- [ ] Fix critical issues immediately
- [ ] Catalog high/low priority issues
- [ ] Generate findings report

### Phase 6: Final Verification
- [ ] Run full test suite
- [ ] All type checks pass
- [ ] Ready for manual E2E testing

---

## Success Criteria

### Entity Unification
- [ ] `app-builder-types.ts` deleted
- [ ] All type checks pass
- [ ] All tests pass

### Workflow Selector Integration
- [ ] All workflow selection points use `WorkflowSelectorDialog`
- [ ] Role context displayed when selecting workflows
- [ ] Mismatch warnings appear for workflows missing entity roles
- [ ] Role auto-assignment works on save

### Comprehensive Review
- [ ] All critical issues fixed
- [ ] High priority issues fixed before testing
- [ ] Low priority issues cataloged

---

## Files Reference

### New Component
- `client/src/components/workflows/WorkflowSelectorDialog.tsx`

### Files to Modify
- `client/src/components/app-builder/editor/PropertyEditor.tsx`
- `client/src/components/app-builder/editor/property-editors/ActionBuilder.tsx`
- `client/src/components/app-builder/editor/property-editors/TableActionBuilder.tsx`
- `client/src/components/events/CreateSubscriptionDialog.tsx`

### Files to Delete
- `client/src/lib/app-builder-types.ts`

---

## Related Documents

- `2026-01-14-app-builder-review-checklist.md` - Comprehensive review checklist
- `.plans/archive/scopes.md` - Completed scope resolution work
- `.plans/archive/workflow-role-access.md` - Completed workflow role access work
