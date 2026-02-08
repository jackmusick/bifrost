import types
from typing import Annotated, Optional, Union

from pydantic import BaseModel

from src.models.contracts.refs import (
    WorkflowRef,
    _get_inner_model_from_annotation,
    _has_workflow_ref,
    _is_list_annotation,
    _is_union_type,
    get_workflow_ref_paths,
    transform_refs_for_export,
    transform_refs_for_import,
)


# ---------------------------------------------------------------------------
# Test models used across multiple test classes
# ---------------------------------------------------------------------------


class InnerModel(BaseModel):
    workflow_id: Annotated[str | None, WorkflowRef()] = None
    name: str = ""


class OuterModel(BaseModel):
    title: str = ""
    inner: InnerModel | None = None
    workflow_id: Annotated[str | None, WorkflowRef()] = None


class ListModel(BaseModel):
    title: str = ""
    items: list[InnerModel] | None = None
    workflow_id: Annotated[str | None, WorkflowRef()] = None


class ToolIdsModel(BaseModel):
    """Model with a list[str] field annotated with WorkflowRef."""

    tool_ids: Annotated[list[str] | None, WorkflowRef()] = None
    name: str = ""


class PlainModel(BaseModel):
    name: str = ""
    count: int = 0


# ---------------------------------------------------------------------------
# _is_union_type
# ---------------------------------------------------------------------------


class TestIsUnionType:

    def test_typing_union(self):
        assert _is_union_type(Union) is True

    def test_types_union_type(self):
        if hasattr(types, "UnionType"):
            assert _is_union_type(types.UnionType) is True

    def test_non_union_returns_false(self):
        assert _is_union_type(str) is False
        assert _is_union_type(list) is False
        assert _is_union_type(None) is False
        assert _is_union_type(int) is False


# ---------------------------------------------------------------------------
# _has_workflow_ref
# ---------------------------------------------------------------------------


class TestHasWorkflowRef:

    def test_field_with_workflow_ref(self):
        field_info = InnerModel.model_fields["workflow_id"]
        assert _has_workflow_ref(field_info) is True

    def test_field_without_workflow_ref(self):
        field_info = InnerModel.model_fields["name"]
        assert _has_workflow_ref(field_info) is False

    def test_plain_model_fields(self):
        for field_info in PlainModel.model_fields.values():
            assert _has_workflow_ref(field_info) is False


# ---------------------------------------------------------------------------
# _get_inner_model_from_annotation
# ---------------------------------------------------------------------------


class TestGetInnerModelFromAnnotation:

    def test_direct_base_model(self):
        assert _get_inner_model_from_annotation(InnerModel) is InnerModel

    def test_model_or_none(self):
        assert _get_inner_model_from_annotation(InnerModel | None) is InnerModel

    def test_optional_model(self):
        assert _get_inner_model_from_annotation(Optional[InnerModel]) is InnerModel

    def test_list_of_model(self):
        assert _get_inner_model_from_annotation(list[InnerModel]) is InnerModel

    def test_list_of_model_or_none(self):
        assert _get_inner_model_from_annotation(list[InnerModel] | None) is InnerModel

    def test_non_model_returns_none(self):
        assert _get_inner_model_from_annotation(str) is None
        assert _get_inner_model_from_annotation(int) is None
        assert _get_inner_model_from_annotation(list[str]) is None

    def test_none_returns_none(self):
        assert _get_inner_model_from_annotation(None) is None

    def test_union_of_non_models_returns_none(self):
        assert _get_inner_model_from_annotation(Union[str, int]) is None

    def test_optional_str_returns_none(self):
        assert _get_inner_model_from_annotation(Optional[str]) is None


# ---------------------------------------------------------------------------
# _is_list_annotation
# ---------------------------------------------------------------------------


class TestIsListAnnotation:

    def test_list_of_model(self):
        assert _is_list_annotation(list[InnerModel]) is True

    def test_list_of_str(self):
        assert _is_list_annotation(list[str]) is True

    def test_list_or_none(self):
        assert _is_list_annotation(list[InnerModel] | None) is True

    def test_optional_list(self):
        assert _is_list_annotation(Optional[list[str]]) is True

    def test_non_list(self):
        assert _is_list_annotation(str) is False
        assert _is_list_annotation(InnerModel) is False
        assert _is_list_annotation(int) is False

    def test_none_returns_false(self):
        assert _is_list_annotation(None) is False

    def test_optional_model_not_list(self):
        assert _is_list_annotation(InnerModel | None) is False


# ---------------------------------------------------------------------------
# get_workflow_ref_paths
# ---------------------------------------------------------------------------


class TestGetWorkflowRefPaths:

    def test_simple_model(self):
        paths = get_workflow_ref_paths(InnerModel)
        assert paths == ["workflow_id"]

    def test_plain_model_returns_empty(self):
        paths = get_workflow_ref_paths(PlainModel)
        assert paths == []

    def test_nested_model(self):
        paths = get_workflow_ref_paths(OuterModel)
        assert "workflow_id" in paths
        assert "inner.workflow_id" in paths
        assert len(paths) == 2

    def test_list_model_uses_wildcard(self):
        paths = get_workflow_ref_paths(ListModel)
        assert "workflow_id" in paths
        assert "items.*.workflow_id" in paths
        assert len(paths) == 2

    def test_prefix_argument(self):
        paths = get_workflow_ref_paths(InnerModel, prefix="root")
        assert paths == ["root.workflow_id"]

    def test_tool_ids_model(self):
        paths = get_workflow_ref_paths(ToolIdsModel)
        assert paths == ["tool_ids"]

    def test_deeply_nested_model(self):
        class Level2(BaseModel):
            ref_id: Annotated[str | None, WorkflowRef()] = None

        class Level1(BaseModel):
            children: list[Level2] | None = None

        class Root(BaseModel):
            section: Level1 | None = None

        paths = get_workflow_ref_paths(Root)
        assert paths == ["section.children.*.ref_id"]


# ---------------------------------------------------------------------------
# transform_refs_for_export
# ---------------------------------------------------------------------------


class TestTransformRefsForExport:

    def test_transforms_uuid_to_ref(self):
        data = {"workflow_id": "uuid-123", "name": "test"}
        mapping = {"uuid-123": "workflows/my_flow.py::run"}
        result = transform_refs_for_export(data, InnerModel, mapping)
        assert result["workflow_id"] == "workflows/my_flow.py::run"
        assert result["name"] == "test"

    def test_does_not_mutate_input(self):
        data = {"workflow_id": "uuid-123", "name": "test"}
        original = data.copy()
        mapping = {"uuid-123": "workflows/my_flow.py::run"}
        transform_refs_for_export(data, InnerModel, mapping)
        assert data == original

    def test_skips_none_values(self):
        data = {"workflow_id": None, "name": "test"}
        result = transform_refs_for_export(data, InnerModel, {})
        assert result["workflow_id"] is None

    def test_unknown_uuid_unchanged(self):
        data = {"workflow_id": "uuid-unknown", "name": "test"}
        result = transform_refs_for_export(data, InnerModel, {})
        assert result["workflow_id"] == "uuid-unknown"

    def test_nested_model(self):
        data = {
            "title": "top",
            "inner": {"workflow_id": "uuid-nested", "name": "nested"},
            "workflow_id": "uuid-top",
        }
        mapping = {
            "uuid-top": "top.py::run",
            "uuid-nested": "nested.py::run",
        }
        result = transform_refs_for_export(data, OuterModel, mapping)
        assert result["workflow_id"] == "top.py::run"
        assert result["inner"]["workflow_id"] == "nested.py::run"

    def test_list_of_models(self):
        data = {
            "title": "parent",
            "items": [
                {"workflow_id": "uuid-1", "name": "a"},
                {"workflow_id": "uuid-2", "name": "b"},
            ],
            "workflow_id": None,
        }
        mapping = {"uuid-1": "a.py::run", "uuid-2": "b.py::run"}
        result = transform_refs_for_export(data, ListModel, mapping)
        assert result["items"][0]["workflow_id"] == "a.py::run"
        assert result["items"][1]["workflow_id"] == "b.py::run"

    def test_list_str_with_workflow_ref(self):
        data = {"tool_ids": ["uuid-a", "uuid-b", "uuid-c"], "name": "test"}
        mapping = {"uuid-a": "a.py::run", "uuid-c": "c.py::run"}
        result = transform_refs_for_export(data, ToolIdsModel, mapping)
        assert result["tool_ids"] == ["a.py::run", "uuid-b", "c.py::run"]

    def test_missing_field_in_data_skipped(self):
        data = {"name": "test"}
        result = transform_refs_for_export(data, InnerModel, {})
        assert result == {"name": "test"}

    def test_nested_none_value_skipped(self):
        data = {"title": "top", "inner": None, "workflow_id": None}
        result = transform_refs_for_export(data, OuterModel, {})
        assert result["inner"] is None


# ---------------------------------------------------------------------------
# transform_refs_for_import
# ---------------------------------------------------------------------------


class TestTransformRefsForImport:

    def test_transforms_ref_to_uuid(self):
        data = {"workflow_id": "workflows/my_flow.py::run", "name": "test"}
        mapping = {"workflows/my_flow.py::run": "uuid-123"}
        result = transform_refs_for_import(data, InnerModel, mapping)
        assert result["workflow_id"] == "uuid-123"
        assert result["name"] == "test"

    def test_does_not_mutate_input(self):
        data = {"workflow_id": "workflows/flow.py::run", "name": "test"}
        original = data.copy()
        mapping = {"workflows/flow.py::run": "uuid-123"}
        transform_refs_for_import(data, InnerModel, mapping)
        assert data == original

    def test_skips_none_values(self):
        data = {"workflow_id": None, "name": "test"}
        result = transform_refs_for_import(data, InnerModel, {})
        assert result["workflow_id"] is None

    def test_value_without_double_colon_unchanged(self):
        data = {"workflow_id": "plain-uuid-no-colons", "name": "test"}
        result = transform_refs_for_import(data, InnerModel, {})
        assert result["workflow_id"] == "plain-uuid-no-colons"

    def test_unknown_ref_unchanged(self):
        data = {"workflow_id": "unknown/path.py::unknown_func", "name": "test"}
        result = transform_refs_for_import(data, InnerModel, {})
        assert result["workflow_id"] == "unknown/path.py::unknown_func"

    def test_nested_model(self):
        data = {
            "title": "top",
            "inner": {"workflow_id": "nested.py::run", "name": "nested"},
            "workflow_id": "top.py::run",
        }
        mapping = {"top.py::run": "uuid-top", "nested.py::run": "uuid-nested"}
        result = transform_refs_for_import(data, OuterModel, mapping)
        assert result["workflow_id"] == "uuid-top"
        assert result["inner"]["workflow_id"] == "uuid-nested"

    def test_list_of_models(self):
        data = {
            "title": "parent",
            "items": [
                {"workflow_id": "a.py::run", "name": "a"},
                {"workflow_id": "b.py::run", "name": "b"},
            ],
            "workflow_id": None,
        }
        mapping = {"a.py::run": "uuid-1", "b.py::run": "uuid-2"}
        result = transform_refs_for_import(data, ListModel, mapping)
        assert result["items"][0]["workflow_id"] == "uuid-1"
        assert result["items"][1]["workflow_id"] == "uuid-2"

    def test_list_str_with_workflow_ref(self):
        data = {"tool_ids": ["a.py::run", "plain-id", "c.py::run"], "name": "test"}
        mapping = {"a.py::run": "uuid-a", "c.py::run": "uuid-c"}
        result = transform_refs_for_import(data, ToolIdsModel, mapping)
        assert result["tool_ids"] == ["uuid-a", "plain-id", "uuid-c"]

    def test_missing_field_in_data_skipped(self):
        data = {"name": "test"}
        result = transform_refs_for_import(data, InnerModel, {})
        assert result == {"name": "test"}

    def test_nested_none_value_skipped(self):
        data = {"title": "top", "inner": None, "workflow_id": None}
        result = transform_refs_for_import(data, OuterModel, {})
        assert result["inner"] is None
