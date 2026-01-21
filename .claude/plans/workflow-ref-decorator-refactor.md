# Workflow Ref Decorator Refactor

## Problem

The current portable ref system is fragile and scattered:
1. Multiple serialization paths (`_serialize_form_to_json` vs `serialize_form_to_json`)
2. Context passing (`workflow_map`) easy to forget through multiple layers
3. Field-by-field `@field_serializer` and `@field_validator` decorators
4. Manual `_export.workflow_refs` list in JSON that can drift from actual fields
5. Preview vs Push use different code paths, causing sync bugs

Adding a new workflow reference field requires changes in 4+ places.

## Solution

Use `Annotated` types with marker classes to declare field behavior once:

```python
from typing import Annotated

class FormPublic(BaseModel):
    workflow_id: Annotated[str | None, WorkflowRef()]
    launch_workflow_id: Annotated[str | None, WorkflowRef()]
    created_at: Annotated[datetime, NoExport()]

class FormField(BaseModel):
    data_provider_id: Annotated[str | None, WorkflowRef()]
```

Benefits:
- Self-documenting: metadata lives with the field
- Single place to update when adding fields
- Auto-generates `_export.workflow_refs` from model introspection
- Symmetric serialization/deserialization
- Extensible for future ref types (`AgentRef`, `FormRef`, etc.)

## Files to Create

### 1. `api/src/models/contracts/refs.py`

Marker classes and serialization helpers:

```python
"""
Portable reference markers for Pydantic models.

Use with Annotated to mark fields that should be transformed
during GitHub sync (UUID <-> path::function_name).

Example:
    class FormPublic(BaseModel):
        workflow_id: Annotated[str | None, WorkflowRef()]
"""

from dataclasses import dataclass
from typing import Annotated, Any, get_args, get_origin
from pydantic import BaseModel


@dataclass(frozen=True)
class WorkflowRef:
    """Marks a field as a workflow reference (UUID <-> path::function_name)."""
    pass


@dataclass(frozen=True)
class NoExport:
    """Marks a field to exclude from GitHub export."""
    pass


def get_workflow_ref_fields(model: type[BaseModel]) -> list[str]:
    """
    Get all field names marked with WorkflowRef in a model.

    Handles nested models recursively, returning dot-notation paths.
    """
    paths = []
    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation

        # Check if Annotated with WorkflowRef
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            if any(isinstance(arg, WorkflowRef) for arg in args):
                paths.append(field_name)

            # Check for nested model
            base_type = args[0]
            if isinstance(base_type, type) and issubclass(base_type, BaseModel):
                nested_paths = get_workflow_ref_fields(base_type)
                paths.extend(f"{field_name}.{p}" for p in nested_paths)

        # Check for list of models (e.g., list[FormField])
        elif get_origin(annotation) is list:
            inner = get_args(annotation)[0]
            if get_origin(inner) is Annotated:
                inner = get_args(inner)[0]
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                nested_paths = get_workflow_ref_fields(inner)
                paths.extend(f"{field_name}.*.{p}" for p in nested_paths)

    return paths


def get_no_export_fields(model: type[BaseModel]) -> set[str]:
    """Get all field names marked with NoExport."""
    fields = set()
    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            if any(isinstance(arg, NoExport) for arg in args):
                fields.add(field_name)
    return fields


def transform_refs_for_export(
    data: dict[str, Any],
    model: type[BaseModel],
    workflow_map: dict[str, str],
) -> dict[str, Any]:
    """
    Transform all WorkflowRef fields from UUID to portable ref.

    Args:
        data: Dict from model_dump()
        model: The Pydantic model class
        workflow_map: UUID -> "path::function_name" mapping

    Returns:
        Transformed dict with portable refs
    """
    result = data.copy()

    for field_name, field_info in model.model_fields.items():
        if field_name not in result:
            continue

        annotation = field_info.annotation
        value = result[field_name]

        if value is None:
            continue

        # Direct WorkflowRef field
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            if any(isinstance(arg, WorkflowRef) for arg in args):
                if isinstance(value, str) and value in workflow_map:
                    result[field_name] = workflow_map[value]
                continue

            # Nested model
            base_type = args[0]
            if isinstance(base_type, type) and issubclass(base_type, BaseModel):
                result[field_name] = transform_refs_for_export(value, base_type, workflow_map)
                continue

        # List of models
        if get_origin(annotation) is list and isinstance(value, list):
            inner = get_args(annotation)[0]
            if get_origin(inner) is Annotated:
                inner_args = get_args(inner)
                # List items are WorkflowRef
                if any(isinstance(arg, WorkflowRef) for arg in inner_args):
                    result[field_name] = [
                        workflow_map.get(v, v) if isinstance(v, str) else v
                        for v in value
                    ]
                    continue
                inner = inner_args[0]

            if isinstance(inner, type) and issubclass(inner, BaseModel):
                result[field_name] = [
                    transform_refs_for_export(item, inner, workflow_map)
                    for item in value
                ]

    return result


def transform_refs_for_import(
    data: dict[str, Any],
    model: type[BaseModel],
    ref_to_uuid: dict[str, str],
) -> dict[str, Any]:
    """
    Transform all WorkflowRef fields from portable ref to UUID.

    Args:
        data: Dict to be passed to model_validate()
        model: The Pydantic model class
        ref_to_uuid: "path::function_name" -> UUID mapping

    Returns:
        Transformed dict with UUIDs
    """
    result = data.copy()

    for field_name, field_info in model.model_fields.items():
        if field_name not in result:
            continue

        annotation = field_info.annotation
        value = result[field_name]

        if value is None:
            continue

        # Direct WorkflowRef field
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            if any(isinstance(arg, WorkflowRef) for arg in args):
                if isinstance(value, str) and "::" in value:
                    result[field_name] = ref_to_uuid.get(value, value)
                continue

            # Nested model
            base_type = args[0]
            if isinstance(base_type, type) and issubclass(base_type, BaseModel):
                result[field_name] = transform_refs_for_import(value, base_type, ref_to_uuid)
                continue

        # List of models
        if get_origin(annotation) is list and isinstance(value, list):
            inner = get_args(annotation)[0]
            if get_origin(inner) is Annotated:
                inner_args = get_args(inner)
                # List items are WorkflowRef
                if any(isinstance(arg, WorkflowRef) for arg in inner_args):
                    result[field_name] = [
                        ref_to_uuid.get(v, v) if isinstance(v, str) and "::" in v else v
                        for v in value
                    ]
                    continue
                inner = inner_args[0]

            if isinstance(inner, type) and issubclass(inner, BaseModel):
                result[field_name] = [
                    transform_refs_for_import(item, inner, ref_to_uuid)
                    for item in value
                ]

    return result
```

## Files to Modify

### 2. `api/src/models/contracts/forms.py`

Replace field-by-field serializers with Annotated markers:

```python
from typing import Annotated
from src.models.contracts.refs import WorkflowRef, NoExport

class FormField(BaseModel):
    name: str
    type: FormFieldType
    # ... other fields ...
    data_provider_id: Annotated[str | None, WorkflowRef()] = None

    # REMOVE: @field_validator("data_provider_id")
    # REMOVE: @field_serializer("data_provider_id")

class FormPublic(BaseModel):
    id: UUID
    name: str
    workflow_id: Annotated[str | None, WorkflowRef()] = None
    launch_workflow_id: Annotated[str | None, WorkflowRef()] = None

    # Mark no-export fields
    created_at: Annotated[datetime | None, NoExport()] = None
    updated_at: Annotated[datetime | None, NoExport()] = None
    organization_id: Annotated[str | None, NoExport()] = None
    access_level: Annotated[FormAccessLevel | None, NoExport()] = None

    # REMOVE: @field_serializer("workflow_id", "launch_workflow_id")
    # REMOVE: @field_validator("workflow_id", "launch_workflow_id")
```

### 3. `api/src/models/contracts/agents.py`

Same pattern:

```python
from typing import Annotated
from src.models.contracts.refs import WorkflowRef, NoExport

class AgentPublic(BaseModel):
    id: UUID
    name: str
    tool_ids: Annotated[list[str], WorkflowRef()] = []  # List of workflow refs

    # REMOVE: @field_serializer("tool_ids")
    # REMOVE: @field_validator("tool_ids")
```

### 4. `api/src/services/file_storage/indexers/form.py`

Simplify `_serialize_form_to_json`:

```python
from src.models.contracts.refs import (
    get_workflow_ref_fields,
    get_no_export_fields,
    transform_refs_for_export,
)

def _serialize_form_to_json(form: Form, workflow_map: dict[str, str] | None = None) -> bytes:
    form_public = FormPublic.model_validate(form)

    # Get fields to exclude
    exclude_fields = get_no_export_fields(FormPublic)

    # Dump without context (no more @field_serializer magic)
    form_data = form_public.model_dump(
        mode="json",
        exclude_none=True,
        exclude=exclude_fields,
    )

    # Transform refs if we have a workflow map
    if workflow_map:
        form_data = transform_refs_for_export(form_data, FormPublic, workflow_map)
        form_data["_export"] = {
            "workflow_refs": get_workflow_ref_fields(FormPublic),
            "version": "1.0",
        }

    return json.dumps(form_data, indent=2).encode("utf-8")
```

### 5. `api/src/services/file_storage/indexers/form.py` (import path)

Simplify the import/indexing:

```python
from src.models.contracts.refs import transform_refs_for_import

async def index_form_file(self, path: str, content: bytes, ...):
    form_data = json.loads(content)

    # Transform portable refs to UUIDs
    if "_export" in form_data:
        ref_to_uuid = await build_ref_to_uuid_map(self.db)
        form_data = transform_refs_for_import(form_data, FormPublic, ref_to_uuid)
        del form_data["_export"]

    # Now validate - all refs are already UUIDs
    # No more @field_validator needed for ref resolution
```

### 6. `api/src/services/file_storage/indexers/agent.py`

Same pattern for agents.

### 7. Remove from `api/src/services/file_storage/ref_translation.py`

Remove these functions (replaced by refs.py):
- `transform_uuids_to_refs()`
- `transform_path_refs_to_uuids()`
- `resolve_workflow_ref()`

Keep:
- `build_workflow_ref_map()` - still needed
- `build_ref_to_uuid_map()` - still needed

## Testing

### New test file: `api/tests/unit/contracts/test_refs.py`

```python
def test_get_workflow_ref_fields_simple():
    """Direct WorkflowRef fields are detected."""
    fields = get_workflow_ref_fields(FormPublic)
    assert "workflow_id" in fields
    assert "launch_workflow_id" in fields

def test_get_workflow_ref_fields_nested():
    """Nested WorkflowRef fields use dot notation."""
    fields = get_workflow_ref_fields(FormPublic)
    assert "form_schema.fields.*.data_provider_id" in fields

def test_transform_refs_for_export():
    """UUIDs are transformed to portable refs."""
    data = {"workflow_id": "uuid-123", "name": "Test"}
    workflow_map = {"uuid-123": "workflows/test.py::my_workflow"}
    result = transform_refs_for_export(data, FormPublic, workflow_map)
    assert result["workflow_id"] == "workflows/test.py::my_workflow"

def test_transform_refs_for_import():
    """Portable refs are transformed to UUIDs."""
    data = {"workflow_id": "workflows/test.py::my_workflow", "name": "Test"}
    ref_to_uuid = {"workflows/test.py::my_workflow": "uuid-123"}
    result = transform_refs_for_import(data, FormPublic, ref_to_uuid)
    assert result["workflow_id"] == "uuid-123"

def test_round_trip():
    """Export then import returns original UUIDs."""
    original = {"workflow_id": "uuid-123", "name": "Test"}
    workflow_map = {"uuid-123": "workflows/test.py::my_workflow"}
    ref_to_uuid = {"workflows/test.py::my_workflow": "uuid-123"}

    exported = transform_refs_for_export(original, FormPublic, workflow_map)
    imported = transform_refs_for_import(exported, FormPublic, ref_to_uuid)

    assert imported["workflow_id"] == original["workflow_id"]
```

## Migration Steps

1. Create `refs.py` with marker classes and transform functions
2. Add unit tests for the new module
3. Update `FormField` model with `Annotated[..., WorkflowRef()]`
4. Update `FormPublic` model with annotations
5. Update form indexer to use new transform functions
6. Remove old `@field_serializer`/`@field_validator` decorators from forms
7. Run form tests to verify
8. Repeat for `AgentPublic` model
9. Update agent indexer
10. Remove old decorators from agents
11. Run full test suite
12. Clean up unused functions in ref_translation.py

## Verification

```bash
# Unit tests for new refs module
./test.sh tests/unit/contracts/test_refs.py -v

# Form contract tests
./test.sh tests/unit/models/test_forms.py -v

# Integration tests
./test.sh tests/integration/platform/test_portable_ref_resolution.py -v

# E2E sync tests
./test.sh --e2e tests/e2e/api/test_portable_refs_sync.py -v

# Full regression
./test.sh
pyright
ruff check
```
