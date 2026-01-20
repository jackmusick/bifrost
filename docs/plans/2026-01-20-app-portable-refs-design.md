# Design: Portable Workflow References in App Builder Files

## Overview

Extend the existing portable reference translation system to handle `useWorkflow()` calls in App Builder TSX files. On export to Git, UUIDs are replaced with portable refs (`workflows/path.py::function`). On import from Git, portable refs are resolved back to UUIDs.

## Scope

**In scope:**

- Transform `useWorkflow('{uuid}')` to/from `useWorkflow('workflows/path.py::function')` in TSX files
- Create persistent per-entity notifications for unresolved references
- Clean up unused `useForm` and `useDataProvider` patterns from `app_dependencies.py`

**Out of scope:**

- Other hooks (only `useWorkflow` is used in App Builder)
- Changes to the `useWorkflow` hook implementation itself

## Technical Approach

### 1. New Functions in `ref_translation.py`

```python
def transform_app_source_uuids_to_refs(
    source: str,
    workflow_map: dict[str, str]
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{uuid}') to useWorkflow('{ref}') in TSX source.
    Returns (transformed_source, list_of_transformed_uuids).
    """

def transform_app_source_refs_to_uuids(
    source: str,
    ref_to_uuid: dict[str, str]
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{ref}') to useWorkflow('{uuid}') in TSX source.
    Returns (transformed_source, list_of_unresolved_refs).
    """
```

Both use regex replacement on the source string - similar to how JSON string replacement works for forms/agents, but operating on TSX source code.

### 2. Regex Pattern

```python
# Matches useWorkflow('...') or useWorkflow("...")
USE_WORKFLOW_PATTERN = re.compile(r"useWorkflow\(['\"]([^'\"]+)['\"]\)")
```

This pattern captures the argument regardless of whether it's a UUID or portable ref, then the transformation logic decides what to do with it.

## Indexer Changes (`app.py`)

### On Export (serialize to git)

In `_serialize_app_files()` or equivalent, after getting the source content:

```python
workflow_map = await build_workflow_ref_map(db)

for app_file in app_files:
    source = app_file.source
    transformed_source, _ = transform_app_source_uuids_to_refs(source, workflow_map)
    # Use transformed_source for git blob
```

### On Import (deserialize from git)

In the file processing loop, before saving to database:

```python
ref_to_uuid = await build_ref_to_uuid_map(db)

for file_path, source in git_files:
    transformed_source, unresolved = transform_app_source_refs_to_uuids(source, ref_to_uuid)

    if unresolved:
        # Create persistent notification for this app file
        await create_unresolved_ref_notification(
            entity_type="app_file",
            entity_id=app_file.id,
            entity_name=file_path,
            unresolved_refs=unresolved
        )

    # Save transformed_source to database
    app_file.source = transformed_source
```

**Dependency scanning:** The existing `parse_dependencies()` runs *after* transformation, so it sees UUIDs and works unchanged.

## Notification System

### Per-Entity Persistent Notifications

When an app file (or form/agent) has unresolved refs during import, create a system notification that:

- Links to the specific entity
- Lists the unresolved portable refs
- Persists until the refs are resolved on a subsequent sync

### Notification Lifecycle

1. **On any app file save** (import from git OR user edit via API):
   - Run transformation to resolve refs
   - Clear existing "unresolved ref" notification for this file
   - If unresolved refs remain, create new notification

2. **Same pattern for forms/agents** - on save, re-evaluate and update notification state

This matches the workflow config/integration validation pattern where the notification reflects the *current* state of the entity, not the state at last import.

### Clearing Notifications

On each save, before processing:

1. Clear any existing "unresolved ref" notifications for the entity being processed
2. After transformation, create new notifications only if unresolved refs remain

This way, once a missing workflow is synced (or the file is fixed), the notification auto-clears.

### Extend to Forms/Agents

The same notification pattern should apply to forms and agents that have unresolved refs today (they currently just log warnings). This is a small addition to the form and agent indexers using the same notification helper.

## Cleanup: Remove Unused Patterns

### In `app_dependencies.py`

Remove `useForm` and `useDataProvider` from `DEPENDENCY_PATTERNS`:

```python
# Before
DEPENDENCY_PATTERNS: dict[str, re.Pattern[str]] = {
    "workflow": re.compile(r'useWorkflow\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
    "form": re.compile(r'useForm\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
    "data_provider": re.compile(r'useDataProvider\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
}

# After
DEPENDENCY_PATTERNS: dict[str, re.Pattern[str]] = {
    "workflow": re.compile(r'useWorkflow\([\'"]([a-f0-9-]{36})[\'"]\)', re.IGNORECASE),
}
```

### Database Cleanup (optional)

Existing `AppFileDependency` records with `dependency_type` of `"form"` or `"data_provider"` are orphaned. Could add a migration to delete these, or just let them be (they're harmless).

## Implementation Order

1. **Add translation functions to `ref_translation.py`**
   - `transform_app_source_uuids_to_refs()`
   - `transform_app_source_refs_to_uuids()`
   - Unit tests for both

2. **Create notification helper** (or identify existing one)
   - `create_unresolved_ref_notification()`
   - `clear_unresolved_ref_notification()`
   - Ensure idempotent behavior

3. **Update app indexer (`app.py`)**
   - Export: transform UUIDs to refs before writing to git
   - Import/Save: transform refs to UUIDs, manage notifications

4. **Extend notifications to forms/agents**
   - Update form indexer to use notification helper on unresolved refs
   - Update agent indexer to use notification helper on unresolved refs

5. **Cleanup `app_dependencies.py`**
   - Remove `useForm` and `useDataProvider` patterns

6. **Integration tests**
   - Round-trip: export app with workflow ref, import, verify UUID restored
   - Unresolved ref: import app with missing workflow, verify notification created
   - Resolution: sync missing workflow, re-save app, verify notification cleared
