# Entity Management Improvements Plan

## Feature 1: Dependency Count on Entity List Items

### Goal
Add a `used_by_count` field to `WorkflowMetadata` (and similar models for forms/agents/apps) so the EntityManagement page can show how many things reference each entity — and filter to "unused" items.

### Backend Changes

#### 1a. Add `used_by_count` to `WorkflowMetadata` contract
- **File:** `api/src/models/contracts/workflows.py`
- Add field: `used_by_count: int = Field(default=0, description="Number of entities that reference this workflow")`

#### 1b. Compute counts in `list_workflows` endpoint
- **File:** `api/src/routers/workflows.py`
- After querying workflows, batch-compute the used_by counts in a single query
- Join across: `forms.workflow_id`, `forms.launch_workflow_id`, `form_fields.data_provider_id`, `agent_tools.workflow_id`, `app_file_dependencies.dependency_id`
- Use a `UNION ALL` subquery to count all references per workflow ID, then join to the workflow list
- Pass the count into `_convert_workflow_orm_to_schema()` or set it after conversion

#### 1c. Similarly for other entity types (if desired)
- Forms, agents, apps could also get `used_by_count` on their list models
- Forms: count of apps referencing them via `app_file_dependencies`
- Agents: probably 0 references (nothing references agents currently)
- Apps: probably 0 references
- **Recommendation:** Start with workflows only since they're the primary "leaf" entities that everything else references. Expand later if needed.

### Frontend Changes

#### 1d. Regenerate types
- Run `npm run generate:types` to pick up new `used_by_count` field

#### 1e. Show count on EntityManagement cards
- **File:** `client/src/pages/EntityManagement.tsx`
- Add a small badge/pill to each entity card showing the count (e.g., `3 refs` or a link icon + number)
- Zero-count items get a subtle "unused" indicator (e.g., muted text "No references")

#### 1f. Add "Unused" filter
- **File:** `client/src/pages/EntityManagement.tsx`
- Add a toggle or filter option in the FilterPopover: "Unused only" or "No dependencies"
- Filters to entities where `used_by_count === 0`

---

## Feature 2: Delete Workflow from Entity Management

### Goal
Allow users to delete a workflow from the EntityManagement page. This triggers the same deactivation/replacement dialog used in the code editor, then performs the actual file surgery (delete the file or remove the function block).

### Backend Changes

#### 2a. New endpoint: `DELETE /api/workflows/{workflow_id}`
- **File:** `api/src/routers/workflows.py`
- **Flow:**
  1. Look up the workflow by ID to get its `path` and `function_name`
  2. Read the workspace file content
  3. Parse with AST to count decorated functions in the file
  4. Run deactivation check via `DeactivationProtectionService.detect_pending_deactivations()` — this returns `PendingDeactivation` with `affected_entities` (the "used by" info)
  5. If there are pending deactivations and `force_deactivation` is not set, return `409` with `WorkflowDeactivationConflict` (same response shape as the code editor)
  6. If confirmed (force_deactivation=True or replacements provided):
     - **Single function file:** Call `file_ops.delete_file(path)` — existing cleanup handles DB
     - **Multi-function file:** Remove the function block from the source using line numbers from AST (`node.lineno` to `node.end_lineno`, including decorators), then call `file_ops.write_file(path, new_content)` with `force_deactivation=True` — the indexer re-runs on the remaining content
  7. If replacements provided, call `DeactivationProtectionService.apply_workflow_replacements()` before the file operation

#### 2b. AST-based function removal utility
- **File:** `api/src/services/file_storage/code_surgery.py` (new)
- Function: `remove_function_from_source(source: str, function_name: str) -> str | None`
  - Parse AST, find function by name
  - Get line range including decorators (walk decorator nodes for earliest `lineno`)
  - Remove those lines from source string
  - Return new source, or `None` if it was the only function (signals "delete the whole file")
  - Also strip any trailing blank lines left behind

#### 2c. Request/response models
- **File:** `api/src/models/contracts/workflows.py` (or editor.py since models exist there)
- `DeleteWorkflowRequest`:
  - `force_deactivation: bool = False`
  - `replacements: dict[str, str] | None = None` — same semantics as `FileContentRequest`
- Response: reuse `WorkflowDeactivationConflict` for 409, simple 200/204 for success

### Frontend Changes

#### 2d. Add delete action to EntityManagement
- **File:** `client/src/pages/EntityManagement.tsx`
- Add a delete button/menu item on workflow entity cards (only for workflows, since forms/agents/apps have different lifecycle)
- Could be a trash icon, a context menu, or a button in the card's action area

#### 2e. Wire up the deactivation dialog
- Reuse `WorkflowDeactivationDialog` component (already exists at `client/src/components/editor/WorkflowDeactivationDialog.tsx`)
- Flow:
  1. User clicks delete on a workflow
  2. Call `DELETE /api/workflows/{id}` (without force)
  3. If 409 response → open `WorkflowDeactivationDialog` with the `pending_deactivations` and `available_replacements` from the response
  4. User chooses: force deactivate, apply replacements, or cancel
  5. If confirmed → re-call `DELETE /api/workflows/{id}` with `force_deactivation=true` and/or `replacements`
  6. On success → refetch workflow list

#### 2f. Regenerate types
- Run `npm run generate:types` after API changes

---

## Implementation Order

1. **1a–1b**: Backend dependency count (workflow model + list endpoint)
2. **1d–1f**: Frontend dependency count display + filter
3. **2b**: AST function removal utility + tests
4. **2a, 2c**: Delete endpoint with deactivation protection
5. **2d–2e**: Frontend delete action + dialog wiring
6. **2f**: Final type regeneration

## Testing

- **Unit tests** for `remove_function_from_source()` — single function, multi-function, decorators with args, async functions
- **Unit tests** for dependency count query logic
- **Integration tests** for `DELETE /api/workflows/{id}` — 409 flow, force deactivation, replacement application, file deletion vs function removal
- All via `./test.sh`
