"""
Unit tests for workflow_access_service.

Tests the extraction and sync functions for precomputed workflow access.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.services.workflow_access_service import (
    extract_form_workflows,
    extract_app_workflows,
    _extract_workflows_from_props,
    sync_workflow_access,
    sync_form_workflow_access,
    sync_app_workflow_access,
)


# =============================================================================
# Test: extract_form_workflows
# =============================================================================


class TestExtractFormWorkflows:
    """Tests for extract_form_workflows function."""

    def test_extracts_workflow_id(self):
        """Should extract workflow_id from form."""
        workflow_id = uuid4()
        form = MagicMock()
        form.workflow_id = str(workflow_id)
        form.launch_workflow_id = None
        form.fields = []

        result = extract_form_workflows(form)

        assert workflow_id in result

    def test_extracts_launch_workflow_id(self):
        """Should extract launch_workflow_id from form."""
        launch_workflow_id = uuid4()
        form = MagicMock()
        form.workflow_id = None
        form.launch_workflow_id = str(launch_workflow_id)
        form.fields = []

        result = extract_form_workflows(form)

        assert launch_workflow_id in result

    def test_extracts_data_provider_id_from_fields(self):
        """Should extract data_provider_id from form fields."""
        dp_id = uuid4()
        field = MagicMock()
        field.data_provider_id = dp_id

        form = MagicMock()
        form.workflow_id = None
        form.launch_workflow_id = None
        form.fields = [field]

        result = extract_form_workflows(form)

        assert dp_id in result

    def test_extracts_all_workflow_types(self):
        """Should extract all workflow types from form."""
        workflow_id = uuid4()
        launch_workflow_id = uuid4()
        dp_id = uuid4()

        field = MagicMock()
        field.data_provider_id = dp_id

        form = MagicMock()
        form.workflow_id = str(workflow_id)
        form.launch_workflow_id = str(launch_workflow_id)
        form.fields = [field]

        result = extract_form_workflows(form)

        assert workflow_id in result
        assert launch_workflow_id in result
        assert dp_id in result
        assert len(result) == 3

    def test_handles_none_fields(self):
        """Should handle None workflow IDs gracefully."""
        form = MagicMock()
        form.workflow_id = None
        form.launch_workflow_id = None
        form.fields = []

        result = extract_form_workflows(form)

        assert len(result) == 0

    def test_handles_invalid_uuid_format(self):
        """Should skip invalid UUID strings."""
        form = MagicMock()
        form.workflow_id = "not-a-valid-uuid"
        form.launch_workflow_id = None
        form.fields = []

        result = extract_form_workflows(form)

        assert len(result) == 0

    def test_uses_provided_fields_list(self):
        """Should use provided fields list instead of form.fields."""
        dp_id_1 = uuid4()
        dp_id_2 = uuid4()

        field_in_form = MagicMock()
        field_in_form.data_provider_id = dp_id_1

        field_provided = MagicMock()
        field_provided.data_provider_id = dp_id_2

        form = MagicMock()
        form.workflow_id = None
        form.launch_workflow_id = None
        form.fields = [field_in_form]

        result = extract_form_workflows(form, fields=[field_provided])

        assert dp_id_2 in result
        assert dp_id_1 not in result


# =============================================================================
# Test: _extract_workflows_from_props
# =============================================================================


class TestExtractWorkflowsFromProps:
    """Tests for _extract_workflows_from_props recursive extraction."""

    def test_extracts_top_level_workflow_id(self):
        """Should extract workflowId at top level of props."""
        workflow_id = uuid4()
        props = {"workflowId": str(workflow_id)}

        result = _extract_workflows_from_props(props)

        assert workflow_id in result

    def test_extracts_nested_workflow_id(self):
        """Should extract workflowId nested in onClick."""
        workflow_id = uuid4()
        props = {
            "onClick": {
                "workflowId": str(workflow_id),
            }
        }

        result = _extract_workflows_from_props(props)

        assert workflow_id in result

    def test_extracts_workflow_from_row_actions(self):
        """Should extract workflowId from rowActions array."""
        workflow_id = uuid4()
        props = {
            "rowActions": [
                {
                    "onClick": {
                        "workflowId": str(workflow_id),
                    }
                }
            ]
        }

        result = _extract_workflows_from_props(props)

        assert workflow_id in result

    def test_extracts_workflow_from_header_actions(self):
        """Should extract workflowId from headerActions array."""
        workflow_id = uuid4()
        props = {
            "headerActions": [
                {
                    "onClick": {
                        "workflowId": str(workflow_id),
                    }
                }
            ]
        }

        result = _extract_workflows_from_props(props)

        assert workflow_id in result

    def test_extracts_workflow_from_footer_actions(self):
        """Should extract workflowId from footerActions."""
        workflow_id = uuid4()
        props = {
            "footerActions": [
                {
                    "workflowId": str(workflow_id),
                }
            ]
        }

        result = _extract_workflows_from_props(props)

        assert workflow_id in result

    def test_extracts_data_provider_id(self):
        """Should extract dataProviderId."""
        dp_id = uuid4()
        props = {"dataProviderId": str(dp_id)}

        result = _extract_workflows_from_props(props)

        assert dp_id in result

    def test_extracts_multiple_workflows_deeply_nested(self):
        """Should extract all workflows from complex nested structure."""
        wf1 = uuid4()
        wf2 = uuid4()
        wf3 = uuid4()
        dp1 = uuid4()

        props = {
            "workflowId": str(wf1),
            "rowActions": [
                {
                    "onClick": {
                        "workflowId": str(wf2),
                    }
                }
            ],
            "columns": [
                {
                    "cell": {
                        "onClick": {
                            "workflowId": str(wf3),
                        }
                    }
                }
            ],
            "dataProviderId": str(dp1),
        }

        result = _extract_workflows_from_props(props)

        assert wf1 in result
        assert wf2 in result
        assert wf3 in result
        assert dp1 in result

    def test_handles_empty_dict(self):
        """Should handle empty dict."""
        result = _extract_workflows_from_props({})
        assert len(result) == 0

    def test_handles_empty_list(self):
        """Should handle empty list."""
        result = _extract_workflows_from_props([])
        assert len(result) == 0

    def test_handles_invalid_uuid(self):
        """Should skip invalid UUID values."""
        props = {"workflowId": "not-a-uuid"}
        result = _extract_workflows_from_props(props)
        assert len(result) == 0

    def test_handles_non_string_workflow_id(self):
        """Should skip non-string workflowId values."""
        props = {"workflowId": 12345}
        result = _extract_workflows_from_props(props)
        assert len(result) == 0


# =============================================================================
# Test: extract_app_workflows
# =============================================================================


class TestExtractAppWorkflows:
    """Tests for extract_app_workflows function."""

    def test_extracts_page_launch_workflow_id(self):
        """Should extract launch_workflow_id from pages."""
        launch_wf_id = uuid4()
        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = launch_wf_id
        page.data_sources = []

        result = extract_app_workflows([page], [])

        assert launch_wf_id in result

    def test_extracts_workflow_from_data_sources(self):
        """Should extract workflowId from page data_sources."""
        wf_id = uuid4()
        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = None
        page.data_sources = [{"workflowId": str(wf_id)}]

        result = extract_app_workflows([page], [])

        assert wf_id in result

    def test_extracts_data_provider_from_data_sources(self):
        """Should extract dataProviderId from page data_sources."""
        dp_id = uuid4()
        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = None
        page.data_sources = [{"dataProviderId": str(dp_id)}]

        result = extract_app_workflows([page], [])

        assert dp_id in result

    def test_extracts_loading_workflows_from_component(self):
        """Should extract loading_workflows from components."""
        wf_id = uuid4()
        comp = MagicMock()
        comp.is_draft = False
        comp.loading_workflows = [str(wf_id)]
        comp.props = {}

        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = None
        page.data_sources = []

        result = extract_app_workflows([page], [comp])

        assert wf_id in result

    def test_extracts_workflow_from_component_props(self):
        """Should extract workflowId from component props."""
        wf_id = uuid4()
        comp = MagicMock()
        comp.is_draft = False
        comp.loading_workflows = []
        comp.props = {"onClick": {"workflowId": str(wf_id)}}

        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = None
        page.data_sources = []

        result = extract_app_workflows([page], [comp])

        assert wf_id in result

    def test_works_with_dict_pages(self):
        """Should work with dict page objects (for flexibility)."""
        wf_id = uuid4()
        page = {
            "is_draft": False,
            "launch_workflow_id": str(wf_id),
            "data_sources": [],
        }

        result = extract_app_workflows([page], [])

        assert wf_id in result

    def test_works_with_dict_components(self):
        """Should work with dict component objects (for flexibility)."""
        wf_id = uuid4()
        page = {"is_draft": False, "launch_workflow_id": None, "data_sources": []}
        comp = {
            "is_draft": False,
            "loading_workflows": [str(wf_id)],
            "props": {},
        }

        result = extract_app_workflows([page], [comp])

        assert wf_id in result


# =============================================================================
# Test: sync_workflow_access
# =============================================================================


class TestSyncWorkflowAccess:
    """Tests for sync_workflow_access function."""

    @pytest.mark.asyncio
    async def test_deletes_existing_entries(self):
        """Should delete existing entries for the entity."""
        db = AsyncMock()
        entity_id = uuid4()
        wf_id = uuid4()

        await sync_workflow_access(
            db=db,
            entity_type="form",
            entity_id=entity_id,
            workflow_ids={wf_id},
            access_level="authenticated",
            organization_id=None,
        )

        # Verify delete was called
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_inserts_new_entries(self):
        """Should insert new entries for each workflow."""
        db = AsyncMock()
        entity_id = uuid4()
        wf_id_1 = uuid4()
        wf_id_2 = uuid4()

        await sync_workflow_access(
            db=db,
            entity_type="form",
            entity_id=entity_id,
            workflow_ids={wf_id_1, wf_id_2},
            access_level="authenticated",
            organization_id=None,
        )

        # Verify add was called twice (once per workflow)
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_empty_workflow_set(self):
        """Should handle empty workflow set (just deletes)."""
        db = AsyncMock()
        entity_id = uuid4()

        await sync_workflow_access(
            db=db,
            entity_type="form",
            entity_id=entity_id,
            workflow_ids=set(),
            access_level="authenticated",
            organization_id=None,
        )

        # Verify delete was called but no adds
        db.execute.assert_called_once()
        db.add.assert_not_called()


# =============================================================================
# Test: sync_form_workflow_access
# =============================================================================


class TestSyncFormWorkflowAccess:
    """Tests for sync_form_workflow_access convenience function."""

    @pytest.mark.asyncio
    async def test_extracts_and_syncs(self):
        """Should extract workflows from form and sync."""
        db = AsyncMock()
        wf_id = uuid4()

        form = MagicMock()
        form.id = uuid4()
        form.workflow_id = str(wf_id)
        form.launch_workflow_id = None
        form.fields = []
        form.access_level = MagicMock()
        form.access_level.value = "authenticated"
        form.organization_id = None

        await sync_form_workflow_access(db, form)

        # Should have called execute (delete) and add (insert)
        db.execute.assert_called_once()
        db.add.assert_called_once()


# =============================================================================
# Test: sync_app_workflow_access
# =============================================================================


class TestSyncAppWorkflowAccess:
    """Tests for sync_app_workflow_access convenience function."""

    @pytest.mark.asyncio
    async def test_extracts_and_syncs_live_only(self):
        """Should extract workflows from live pages/components and sync."""
        db = AsyncMock()
        wf_id = uuid4()

        page = MagicMock()
        page.is_draft = False
        page.launch_workflow_id = wf_id
        page.data_sources = []

        comp = MagicMock()
        comp.is_draft = False
        comp.loading_workflows = []
        comp.props = {}

        app_id = uuid4()

        await sync_app_workflow_access(
            db=db,
            app_id=app_id,
            access_level="authenticated",
            organization_id=None,
            pages=[page],
            components=[comp],
        )

        # Should have called execute (delete) and add (insert)
        db.execute.assert_called_once()
        db.add.assert_called_once()
