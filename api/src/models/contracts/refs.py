"""
Portable reference markers for Pydantic models.

Use with Annotated to mark fields that should be transformed
during GitHub sync (UUID <-> path::function_name).

Example:
    class FormPublic(BaseModel):
        workflow_id: Annotated[str | None, WorkflowRef()] = None
"""

import types
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel


def _is_union_type(origin: Any) -> bool:
    """Check if origin is a Union type (handles both typing.Union and types.UnionType)."""
    if origin is Union:
        return True
    # Python 3.10+ has types.UnionType for X | Y syntax
    if hasattr(types, "UnionType") and origin is types.UnionType:
        return True
    return False


@dataclass(frozen=True)
class WorkflowRef:
    """Marks a field as a workflow reference (UUID <-> path::function_name)."""

    pass


def _has_workflow_ref(field_info: Any) -> bool:
    """Check if a field has WorkflowRef marker in its metadata."""
    return any(isinstance(m, WorkflowRef) for m in field_info.metadata)


def _get_inner_model_from_annotation(annotation: Any) -> type[BaseModel] | None:
    """
    Extract nested BaseModel from an annotation.

    Handles: Model, Model | None, list[Model], list[Model] | None
    Returns the Model class or None if not a BaseModel.
    """
    if annotation is None:
        return None

    # Direct BaseModel
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Handle Union types (Model | None, Optional[Model])
    if _is_union_type(origin):
        for arg in args:
            if arg is type(None):
                continue
            # Recursively check each union member
            result = _get_inner_model_from_annotation(arg)
            if result:
                return result
        return None

    # Handle list[Model]
    if origin is list and args:
        inner = args[0]
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            return inner
        # Could be list[Model | None]
        return _get_inner_model_from_annotation(inner)

    return None


def _is_list_annotation(annotation: Any) -> bool:
    """Check if annotation is a list type (list[X] or list[X] | None)."""
    if annotation is None:
        return False

    origin = get_origin(annotation)

    # Direct list
    if origin is list:
        return True

    # Union with list (list[X] | None)
    if _is_union_type(origin):
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            if get_origin(arg) is list:
                return True

    return False


def get_workflow_ref_paths(model: type[BaseModel], prefix: str = "") -> list[str]:
    """
    Get all field paths marked with WorkflowRef in a model.

    Handles nested models recursively, returning dot-notation paths.
    For lists of models, uses '*' wildcard notation.

    Args:
        model: The Pydantic model class to introspect
        prefix: Current path prefix for recursive calls

    Returns:
        List of field paths like ["workflow_id", "form_schema.fields.*.data_provider_id"]
    """
    paths: list[str] = []

    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        current_path = f"{prefix}.{field_name}" if prefix else field_name

        if annotation is None:
            continue

        # Check if this field has WorkflowRef marker (from Annotated metadata)
        if _has_workflow_ref(field_info):
            paths.append(current_path)
            continue

        # Check for nested models
        inner_model = _get_inner_model_from_annotation(annotation)
        if inner_model:
            if _is_list_annotation(annotation):
                nested = get_workflow_ref_paths(inner_model, f"{current_path}.*")
            else:
                nested = get_workflow_ref_paths(inner_model, current_path)
            paths.extend(nested)

    return paths


def transform_refs_for_export(
    data: dict[str, Any],
    model: type[BaseModel],
    uuid_to_ref: dict[str, str],
) -> dict[str, Any]:
    """
    Transform all WorkflowRef fields from UUID to portable ref.

    Args:
        data: Dict from model_dump()
        model: The Pydantic model class
        uuid_to_ref: UUID -> "path::function_name" mapping

    Returns:
        Transformed dict with portable refs (new dict, does not mutate input)
    """
    result = data.copy()

    for field_name, field_info in model.model_fields.items():
        if field_name not in result:
            continue

        annotation = field_info.annotation
        value = result[field_name]

        if value is None:
            continue

        # Check if this field has WorkflowRef marker
        if _has_workflow_ref(field_info):
            if isinstance(value, str) and value in uuid_to_ref:
                result[field_name] = uuid_to_ref[value]
            elif isinstance(value, list):
                # Handle list[str] with WorkflowRef marker (e.g., tool_ids)
                result[field_name] = [
                    uuid_to_ref.get(item, item) if isinstance(item, str) else item
                    for item in value
                ]
            continue

        # Check for nested models
        inner_model = _get_inner_model_from_annotation(annotation)
        if inner_model:
            if _is_list_annotation(annotation) and isinstance(value, list):
                result[field_name] = [
                    transform_refs_for_export(item, inner_model, uuid_to_ref)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[field_name] = transform_refs_for_export(value, inner_model, uuid_to_ref)

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
        Transformed dict with UUIDs (new dict, does not mutate input)
    """
    result = data.copy()

    for field_name, field_info in model.model_fields.items():
        if field_name not in result:
            continue

        annotation = field_info.annotation
        value = result[field_name]

        if value is None:
            continue

        # Check if this field has WorkflowRef marker
        if _has_workflow_ref(field_info):
            if isinstance(value, str) and "::" in value:
                result[field_name] = ref_to_uuid.get(value, value)
            elif isinstance(value, list):
                # Handle list[str] with WorkflowRef marker (e.g., tool_ids)
                result[field_name] = [
                    ref_to_uuid.get(item, item) if isinstance(item, str) and "::" in item else item
                    for item in value
                ]
            continue

        # Check for nested models
        inner_model = _get_inner_model_from_annotation(annotation)
        if inner_model:
            if _is_list_annotation(annotation) and isinstance(value, list):
                result[field_name] = [
                    transform_refs_for_import(item, inner_model, ref_to_uuid)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            elif isinstance(value, dict):
                result[field_name] = transform_refs_for_import(value, inner_model, ref_to_uuid)

    return result
