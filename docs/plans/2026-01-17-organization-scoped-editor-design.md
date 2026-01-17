# Organization-Scoped Editor Design

**Date:** 2026-01-17
**Status:** Draft

## Problem Statement

Bifrost is a multi-tenant platform where entities (workflows, forms, apps, agents) can be scoped to organizations or made globally available. Currently:

1. When importing from git, everything defaults to global scope
2. Re-scoping entities is tedious and partially broken (workflow org save returns 403 CSRF)
3. No clear visibility into what entities belong to which organization
4. The code editor doesn't reflect organizational boundaries

This creates friction when developing locally and deploying to environments with different organization structures.

## Design Principles

1. **Explicit scope on write** - Every new scoped entity requires an organization selection before it can be saved. No implicit defaults to global.
2. **Scope is a receiving-side concern** - Files in git are org-neutral. The destination environment decides where things land.
3. **One dialog for all scope operations** - The same UI component handles editor saves, git imports, and drag-drop operations.
4. **Visual clarity** - Distinct icons for entity types, clear org containers in the file tree.

## Design

### 1. Editor File Tree Structure

The file tree is reorganized with organization containers at the top level:

```
📌 Global
   📁 workflows/
      ⚡ email_notifications.py
      ⚡ google_calendar.py
   📁 forms/
      📋 support_ticket.form.json
   🐍 utils.py

📍 Customer A
   📁 workflows/
      ⚡ project_crud.py
   📁 apps/
      ⊞ project_dashboard.app.json
   📁 agents/
      🤖 pm_assistant.agent.json

📍 Customer B
   📁 workflows/
      ⚡ inventory.py
```

**Hierarchy:**
- **Global** appears first (pinned at top)
- **Organizations** appear below, alphabetically sorted
- Each org container is visually distinct from folders (different icon, not deletable)
- Inside each container, the familiar folder structure remains

**Entity icons:**

| Entity | Icon | Description |
|--------|------|-------------|
| Workflow | ⚡ | Executable automation |
| Module | 🐍 | Plain Python (unscoped, lives in Global) |
| Form | 📋 | User input collection |
| Agent | 🤖 | AI-powered assistant |
| App | ⊞ | Dashboard/application (grid icon) |

### 2. Scope Assignment Dialog

A single, reusable dialog component for all scope assignment operations.

**Single entity mode (editor save):**

```
┌─────────────────────────────────────┐
│  Select Organization                │
├─────────────────────────────────────┤
│  ⚡ project_crud.py                 │
│                                     │
│  Organization:  [Select... ▼]       │
│                                     │
│    • Global                         │
│    • Customer A                     │
│    • Customer B                     │
│                                     │
│  [Cancel]                [Save]     │
└─────────────────────────────────────┘
```

**Multi-entity mode (git import, bulk operations):**

```
┌─────────────────────────────────────┐
│  Select Organizations               │
├─────────────────────────────────────┤
│  Apply to all:  [Select ▼] [Apply]  │
│  ───────────────────────────────────│
│  ⚡ project_crud.py   [Customer A ▼]│
│  ⚡ inventory.py      [Customer B ▼]│
│  📋 intake.form.json  [Global ▼]    │
│  🤖 helper.agent.json [Select... ▼] │
│                                     │
│  [Cancel]              [Confirm]    │
└─────────────────────────────────────┘
```

**Behavior:**
- "Apply to all" bulk-assigns the same org to all items
- Individual dropdowns allow per-entity override
- Confirm/Save button disabled until all entities have a selection

**Used by:**
- Editor save (new scoped entity)
- Git pull (multiple incoming entities)
- Drag-drop between org containers (pre-filled with target org)
- Right-click "Change Organization..." action

### 3. Git Pull Integration

The git pull UI shows org assignments as subtext below each incoming file:

```
┌─────────────────────────────────┐
│  Pull from GitHub               │
├─────────────────────────────────┤
│  [Assign Organizations...]      │
│                                 │
│  Incoming Changes:              │
│                                 │
│  ⚡ project_crud.py             │
│     Customer A                  │
│                                 │
│  ⚡ inventory.py                │
│     Customer B                  │
│                                 │
│  📋 intake.form.json            │
│     Global                      │
│                                 │
│  🤖 helper.agent.json           │
│     ⚠️ Pending...               │
│                                 │
│  [Cancel]            [Pull]     │
└─────────────────────────────────┘
```

**Behavior:**
- "Assign Organizations..." button opens the multi-entity scope dialog
- Clicking an individual file opens the dialog for just that item
- Pull button disabled while any entity shows "Pending..."
- Once all assigned, pull proceeds and entities land in their designated orgs

**Push behavior unchanged** - files serialize without org info (scope is receiving-side concern)

### 4. Editor Save Behavior

**New scoped entity:**
1. User creates file with workflow/form/agent/app
2. On save, scope dialog appears (single entity mode)
3. User selects org → file saves → appears under that org's container

**Existing file:**
- Save proceeds without prompting (keeps current org)
- To change scope: drag-drop to different org, or right-click → "Change Organization..."

**Non-scoped files (modules, plain Python):**
- Save proceeds without prompting
- Appears under Global automatically

**File with multiple workflows:**
- All workflows in the file get the same org assignment from a single prompt
- To scope them differently, split into separate files

### 5. Bug Fix: Workflow Organization Save

**Issue:** Saving a workflow's organization returns 403 CSRF error.

**Cause:** Frontend uses raw `fetch` instead of `apiClient` which handles CSRF tokens.

**Fix:** Update the frontend call to use `apiClient`.

## Out of Scope

- **Projects/workspaces abstraction** - Adds unnecessary restriction without clear benefit
- **Dedicated entity management page** - The file tree and scope dialog handle this
- **Scope stored in files** - Scope is DB-only, determined at import time
- **Migration tooling** - Not needed; all entities already have `organization_id` (UUID or null)

## Implementation Notes

### Components to Create/Modify

**Frontend:**
- `OrganizationScopeDialog` - New shared component for scope selection
- File tree component - Add org container hierarchy and entity icons
- Git sync UI - Add org subtext and "Assign Organizations" button
- Editor save flow - Integrate scope dialog for new scoped entities

**Backend:**
- Fix CSRF issue on workflow org update endpoint
- No schema changes needed (org scoping already exists)

### Entity Detection

The system already detects entity types from files:
- `.py` with `@workflow` decorator → Workflow
- `.py` without decorator → Module
- `.form.json` → Form
- `.app.json` → App
- `.agent.json` → Agent

This detection drives which icon to show and whether scope dialog is needed.
