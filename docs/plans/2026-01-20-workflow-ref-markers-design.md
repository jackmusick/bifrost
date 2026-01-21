# Workflow Ref Markers Design

## Problem

The current portable ref system for GitHub sync is fragile:

1. **Scattered code** - `@field_serializer` and `@field_validator` decorators spread across `FormField`, `FormCreate`, `FormUpdate`, `FormPublic`, `AgentPublic`
2. **Context threading** - `workflow_map` must be passed through multiple layers via Pydantic context
3. **Manual lists** - `_export.workflow_refs` in JSON can drift from actual fields
4. **Multiple code paths** - Preview and push serialize differently, causing sync bugs

Adding a new workflow reference field requires changes in 4+ places.

## Solution

Use `Annotated` type markers to declare workflow ref fields in one place. Transform via pure functions at the sync boundary.

### Core Components

**Marker class** (`api/src/models/contracts/refs.py`):
```python
@dataclass(frozen=True)
class WorkflowRef:
    """Marks a field as a workflow reference (UUID ↔ path::function_name)."""
    pass
```

**Model usage**:
```python
class FormField(BaseModel):
    data_provider_id: Annotated[UUID | None, WorkflowRef()] = None

class FormPublic(BaseModel):
    workflow_id: Annotated[str | None, WorkflowRef()] = None
    launch_workflow_id: Annotated[str | None, WorkflowRef()] = None
    created_at: datetime | None = Field(default=None, exclude=True)
```

**Introspection**:
```python
def get_workflow_ref_paths(model: type[BaseModel]) -> list[str]:
    """Returns paths like ["workflow_id", "form_schema.fields.*.data_provider_id"]"""
```

**Transform functions**:
```python
def transform_refs_for_export(data: dict, model: type[BaseModel], uuid_to_ref: dict[str, str]) -> dict
def transform_refs_for_import(data: dict, model: type[BaseModel], ref_to_uuid: dict[str, str]) -> dict
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| No-export fields | Use Pydantic's `Field(exclude=True)` | Built-in, well-tested |
| Transform location | Outside model (pure functions on dicts) | No DB hit for normal API calls, easier to test |
| Nested model handling | Introspect model hierarchy | Adding field to `FormField` works everywhere automatically |
| `_export` metadata | Auto-generate, keep in JSON | Self-documenting files, model is source of truth |
| Marker design | Separate classes per ref type | Ready for `AgentRef`, `FormRef` later |
| Which models get markers | Only `FormField` and `FormPublic` (leaf models) | Fewer places to update, API models don't need sync knowledge |

### What Gets Removed

- All `@field_serializer` for workflow refs
- All `@field_validator` for workflow refs
- Context forwarding through `form_schema` validators
- Manual `exclude={...}` sets in serialization
- Manual `_export.workflow_refs` lists
- `resolve_workflow_ref()` helper
- `transform_path_refs_to_uuids()` helper

### Migration Phases

1. **Add new module** - Create `refs.py` with markers, introspection, transforms. Add tests.
2. **Update models** - Add `Annotated[..., WorkflowRef()]` and `Field(exclude=True)`. Keep old code.
3. **Update serialization** - Switch to `transform_refs_for_export()`. Remove context passing.
4. **Update import** - Switch to `transform_refs_for_import()`. Remove context passing.
5. **Cleanup** - Remove old decorators and unused functions.

### Files Changed

**New:**
- `api/src/models/contracts/refs.py`
- `api/tests/unit/models/contracts/test_refs.py`

**Modified:**
- `api/src/models/contracts/forms.py` - Add markers, remove decorators
- `api/src/models/contracts/agents.py` - Add markers, remove decorators
- `api/src/services/file_storage/indexers/form.py` - Use transform functions
- `api/src/services/file_storage/indexers/agent.py` - Use transform functions
- `api/src/services/file_storage/ref_translation.py` - Remove unused functions
