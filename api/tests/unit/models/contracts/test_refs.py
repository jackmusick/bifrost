"""Tests for WorkflowRef marker and transform functions."""

from typing import Annotated

from pydantic import BaseModel, Field

from src.models.contracts.refs import (
    WorkflowRef,
    get_workflow_ref_paths,
    transform_refs_for_export,
    transform_refs_for_import,
)


# Test models
class InnerModel(BaseModel):
    data_provider_id: Annotated[str | None, WorkflowRef()] = None
    name: str = ""


class OuterModel(BaseModel):
    workflow_id: Annotated[str | None, WorkflowRef()] = None
    launch_workflow_id: Annotated[str | None, WorkflowRef()] = None
    nested: InnerModel | None = None
    items: list[InnerModel] = Field(default_factory=list)
    title: str = ""


class ModelWithList(BaseModel):
    tool_ids: Annotated[list[str], WorkflowRef()] = Field(default_factory=list)
    name: str = ""


class TestGetWorkflowRefPaths:
    def test_simple_fields(self):
        """Direct WorkflowRef fields are detected."""
        paths = get_workflow_ref_paths(OuterModel)
        assert "workflow_id" in paths
        assert "launch_workflow_id" in paths

    def test_nested_model(self):
        """Nested WorkflowRef fields use dot notation."""
        paths = get_workflow_ref_paths(OuterModel)
        assert "nested.data_provider_id" in paths

    def test_list_of_models(self):
        """List of models uses wildcard notation."""
        paths = get_workflow_ref_paths(OuterModel)
        assert "items.*.data_provider_id" in paths

    def test_non_ref_fields_excluded(self):
        """Non-WorkflowRef fields are not included."""
        paths = get_workflow_ref_paths(OuterModel)
        assert "title" not in paths
        assert "nested.name" not in paths

    def test_list_field_with_marker(self):
        """List field with WorkflowRef marker is detected."""
        paths = get_workflow_ref_paths(ModelWithList)
        assert "tool_ids" in paths


class TestTransformRefsForExport:
    def test_simple_field(self):
        """UUIDs are transformed to portable refs."""
        data = {"workflow_id": "uuid-123", "title": "Test"}
        uuid_to_ref = {"uuid-123": "workflows/test.py::my_workflow"}
        result = transform_refs_for_export(data, OuterModel, uuid_to_ref)
        assert result["workflow_id"] == "workflows/test.py::my_workflow"
        assert result["title"] == "Test"

    def test_nested_model(self):
        """Nested model fields are transformed."""
        data = {
            "workflow_id": None,
            "nested": {"data_provider_id": "uuid-456", "name": "Inner"},
            "title": "Test",
        }
        uuid_to_ref = {"uuid-456": "workflows/dp.py::provider"}
        result = transform_refs_for_export(data, OuterModel, uuid_to_ref)
        assert result["nested"]["data_provider_id"] == "workflows/dp.py::provider"

    def test_list_of_models(self):
        """List of models has all items transformed."""
        data = {
            "workflow_id": None,
            "items": [
                {"data_provider_id": "uuid-1", "name": "A"},
                {"data_provider_id": "uuid-2", "name": "B"},
            ],
            "title": "Test",
        }
        uuid_to_ref = {
            "uuid-1": "workflows/a.py::func_a",
            "uuid-2": "workflows/b.py::func_b",
        }
        result = transform_refs_for_export(data, OuterModel, uuid_to_ref)
        assert result["items"][0]["data_provider_id"] == "workflows/a.py::func_a"
        assert result["items"][1]["data_provider_id"] == "workflows/b.py::func_b"

    def test_unknown_uuid_unchanged(self):
        """UUIDs not in map are left unchanged."""
        data = {"workflow_id": "unknown-uuid", "title": "Test"}
        uuid_to_ref = {"other-uuid": "workflows/other.py::func"}
        result = transform_refs_for_export(data, OuterModel, uuid_to_ref)
        assert result["workflow_id"] == "unknown-uuid"

    def test_does_not_mutate_input(self):
        """Original data is not modified."""
        data = {"workflow_id": "uuid-123", "title": "Test"}
        uuid_to_ref = {"uuid-123": "workflows/test.py::my_workflow"}
        transform_refs_for_export(data, OuterModel, uuid_to_ref)
        assert data["workflow_id"] == "uuid-123"

    def test_list_of_strings_with_marker(self):
        """List of strings with WorkflowRef marker has all items transformed."""
        data = {"tool_ids": ["uuid-1", "uuid-2", "uuid-3"], "name": "Test"}
        uuid_to_ref = {
            "uuid-1": "workflows/a.py::func_a",
            "uuid-2": "workflows/b.py::func_b",
        }
        result = transform_refs_for_export(data, ModelWithList, uuid_to_ref)
        assert result["tool_ids"][0] == "workflows/a.py::func_a"
        assert result["tool_ids"][1] == "workflows/b.py::func_b"
        assert result["tool_ids"][2] == "uuid-3"  # Not in map, unchanged


class TestTransformRefsForImport:
    def test_simple_field(self):
        """Portable refs are transformed to UUIDs."""
        data = {"workflow_id": "workflows/test.py::my_workflow", "title": "Test"}
        ref_to_uuid = {"workflows/test.py::my_workflow": "uuid-123"}
        result = transform_refs_for_import(data, OuterModel, ref_to_uuid)
        assert result["workflow_id"] == "uuid-123"

    def test_nested_model(self):
        """Nested model refs are transformed."""
        data = {
            "workflow_id": None,
            "nested": {"data_provider_id": "workflows/dp.py::provider", "name": "Inner"},
            "title": "Test",
        }
        ref_to_uuid = {"workflows/dp.py::provider": "uuid-456"}
        result = transform_refs_for_import(data, OuterModel, ref_to_uuid)
        assert result["nested"]["data_provider_id"] == "uuid-456"

    def test_list_of_models(self):
        """List of models has all items transformed."""
        data = {
            "workflow_id": None,
            "items": [
                {"data_provider_id": "workflows/a.py::func_a", "name": "A"},
                {"data_provider_id": "workflows/b.py::func_b", "name": "B"},
            ],
            "title": "Test",
        }
        ref_to_uuid = {
            "workflows/a.py::func_a": "uuid-1",
            "workflows/b.py::func_b": "uuid-2",
        }
        result = transform_refs_for_import(data, OuterModel, ref_to_uuid)
        assert result["items"][0]["data_provider_id"] == "uuid-1"
        assert result["items"][1]["data_provider_id"] == "uuid-2"

    def test_unresolved_ref_unchanged(self):
        """Refs not in map are left unchanged."""
        data = {"workflow_id": "workflows/unknown.py::func", "title": "Test"}
        ref_to_uuid = {"workflows/other.py::func": "uuid-123"}
        result = transform_refs_for_import(data, OuterModel, ref_to_uuid)
        assert result["workflow_id"] == "workflows/unknown.py::func"

    def test_uuid_unchanged(self):
        """Already-UUID values are left unchanged."""
        data = {"workflow_id": "uuid-123", "title": "Test"}
        ref_to_uuid = {"workflows/test.py::func": "uuid-456"}
        result = transform_refs_for_import(data, OuterModel, ref_to_uuid)
        assert result["workflow_id"] == "uuid-123"

    def test_list_of_strings_with_marker(self):
        """List of strings with WorkflowRef marker has all items transformed."""
        data = {
            "tool_ids": [
                "workflows/a.py::func_a",
                "workflows/b.py::func_b",
                "uuid-already",  # Already a UUID
            ],
            "name": "Test",
        }
        ref_to_uuid = {
            "workflows/a.py::func_a": "uuid-1",
            "workflows/b.py::func_b": "uuid-2",
        }
        result = transform_refs_for_import(data, ModelWithList, ref_to_uuid)
        assert result["tool_ids"][0] == "uuid-1"
        assert result["tool_ids"][1] == "uuid-2"
        assert result["tool_ids"][2] == "uuid-already"  # Not a ref, unchanged


class TestRoundTrip:
    def test_export_then_import_restores_uuids(self):
        """Export then import returns original UUIDs."""
        original = {
            "workflow_id": "uuid-123",
            "launch_workflow_id": "uuid-456",
            "nested": {"data_provider_id": "uuid-789", "name": "Nested"},
            "items": [
                {"data_provider_id": "uuid-aaa", "name": "A"},
            ],
            "title": "Test",
        }
        uuid_to_ref = {
            "uuid-123": "workflows/main.py::main",
            "uuid-456": "workflows/launch.py::launch",
            "uuid-789": "workflows/dp.py::provider",
            "uuid-aaa": "workflows/a.py::func_a",
        }
        ref_to_uuid = {v: k for k, v in uuid_to_ref.items()}

        exported = transform_refs_for_export(original, OuterModel, uuid_to_ref)
        imported = transform_refs_for_import(exported, OuterModel, ref_to_uuid)

        assert imported["workflow_id"] == "uuid-123"
        assert imported["launch_workflow_id"] == "uuid-456"
        assert imported["nested"]["data_provider_id"] == "uuid-789"
        assert imported["items"][0]["data_provider_id"] == "uuid-aaa"
