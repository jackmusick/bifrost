# Single Portable Models Plan

## Status: COMPLETE

All phases have been implemented and verified.

---

## Goal

Consolidate forms, agents, and apps to use a **single model** per entity type that:
1. Always serializes workflow UUIDs as portable refs (`path::function_name`)
2. Eliminates separate Export models (FormExport, AgentExport, ApplicationExport)
3. Uses Pydantic's `@field_serializer` with context to transform UUIDs → refs during serialization

---

## Completed Tasks

### Phase 1: Fix Immediate Test Failures ✅ COMPLETE

- [x] Fix FormFieldOption serialization bug
- [x] Fix FormFieldValidation serialization bug

### Phase 2: Add `@field_serializer` to Models ✅ COMPLETE

- [x] Add serializers to FormPublic
- [x] Add serializer to FormField for `data_provider_id`
- [x] Add serializer to AgentPublic for `tool_ids`
- [x] Add serializers to app component models in `app_components.py`

### Phase 3: Update Serialization Callers ✅ COMPLETE

- [x] Update `serialize_form_to_json()` to pass workflow_map context
- [x] Update `serialize_agent_to_json()` to pass workflow_map context
- [x] Update `serialize_app_to_json()` to pass workflow_map context
- [x] Update `read_file()` to build and pass workflow_map context

### Phase 4: Eliminate Export Models & Consolidate App Models ✅ COMPLETE

- [x] Remove FormExport usage - replaced with FormPublic
- [x] Remove AgentExport usage - replaced with AgentPublic
- [x] Consolidate Application models - ApplicationPublic with typed fields
- [x] Delete Export model classes
- [x] File already named `app_components.py`

### Phase 5: Update Indexers for Import ✅ COMPLETE

- [x] FormIndexer converts workflow refs to UUIDs
- [x] AgentIndexer converts tool refs to UUIDs
- [x] AppIndexer converts workflow refs to UUIDs in nested structures

### Phase 6: Verify GitHub Sync ✅ COMPLETE

- [x] `_get_local_file_shas()` computes correct SHAs with refs
- [x] Conflict content displays with portable refs

### Phase 7: Full Verification ✅ COMPLETE

- [x] pyright: 0 errors
- [x] ruff check: All checks passed
- [x] npm run tsc: No errors
- [x] Types regenerated successfully

---

## Post-Completion Cleanup ✅ COMPLETE

Removed backwards-compatibility re-exports from `applications.py`:
- [x] Removed re-exports of `AppComponentNode`, `DataSourceConfig`, `LayoutContainer`, `LayoutElement`, `PageDefinition`, `PagePermission` from `applications.py`
- [x] Removed `PagePermissionConfig` alias
- [x] Updated `app_builder_service.py` to import directly from `app_components.py`
- [x] Updated `app_pages.py` to import `PageDefinition` from `app_components.py`

---

## Key Changes Made

### Model Consolidation

| Entity | Before | After |
|--------|--------|-------|
| Forms | FormPublic + FormExport | FormPublic (with `@field_serializer`) |
| Agents | AgentPublic + AgentExport | AgentPublic (with `@field_serializer`) |
| Apps | ApplicationDefinition + ApplicationExport | ApplicationPublic (with `@field_serializer`) |

### Serialization Pattern

All models with workflow references now use `@field_serializer` that reads from context:

```python
@field_serializer('workflow_id')
def serialize_workflow_ref(self, value: str | None, info) -> str | None:
    if not value or not info.context:
        return value
    workflow_map = info.context.get('workflow_map', {})
    return workflow_map.get(value, value)
```

Usage:
```python
form.model_dump(context={'workflow_map': workflow_map})
```

### Import Structure (Clean Break)

Types are now imported from their canonical locations:

- **`app_components.py`**: All component types (`HeadingComponent`, `ButtonComponent`, etc.), layout types (`LayoutContainer`, `AppComponentNode`), `PageDefinition`, `PagePermission`, `DataSourceConfig`
- **`applications.py`**: Application-level types (`ApplicationCreate`, `ApplicationPublic`, `AppPageCreate`, etc.)

No re-exports or aliases for backwards compatibility.

---

## Files Modified

| File | Changes |
|------|---------|
| `api/src/models/contracts/forms.py` | Added `@field_serializer`, deleted Export models |
| `api/src/models/contracts/agents.py` | Added `@field_serializer`, deleted Export models |
| `api/src/models/contracts/app_components.py` | Added serializers to component models |
| `api/src/models/contracts/applications.py` | Removed re-exports, clean imports only |
| `api/src/services/file_storage/file_ops.py` | Updated to pass workflow_map context |
| `api/src/services/file_storage/indexers/form.py` | Updated serialization |
| `api/src/services/file_storage/indexers/agent.py` | Updated serialization |
| `api/src/services/file_storage/indexers/app.py` | Updated serialization |
| `api/src/services/app_builder_service.py` | Import from `app_components.py` |
| `api/src/routers/app_pages.py` | Import `PageDefinition` from `app_components.py` |
| `client/src/pages/ApplicationEditor.tsx` | Updated to use snake_case field names |
| `client/src/pages/ApplicationRunner.tsx` | Updated to use snake_case field names |

---

## Success Criteria - All Met

- [x] All tests pass
- [x] `@field_serializer` added to all models with workflow references
- [x] Export models eliminated (FormExport, AgentExport, ApplicationExport)
- [x] `ApplicationDefinition` deleted (replaced by `ApplicationPublic`)
- [x] GitHub sync correctly computes SHAs for entities with refs
- [x] Conflicts display content with portable refs
- [x] pyright, ruff, tsc, lint all pass
- [x] No backwards-compatibility re-exports (clean break)
