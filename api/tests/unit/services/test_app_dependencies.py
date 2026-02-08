"""
Unit tests for app dependency parsing and sync.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.services.app_dependencies import parse_dependencies, sync_file_dependencies


class TestParseDependencies:
    """Tests for parse_dependencies function."""

    def test_parses_single_use_workflow_with_uuid(self):
        """Single useWorkflow call with UUID is parsed."""
        source = "const w = useWorkflow('550e8400-e29b-41d4-a716-446655440000');"

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "550e8400-e29b-41d4-a716-446655440000"

    def test_parses_workflow_name(self):
        """useWorkflowQuery with a workflow name is parsed."""
        source = "const { data } = useWorkflowQuery('list_csp_tenants');"

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "list_csp_tenants"

    def test_parses_double_quoted_ref(self):
        """Double-quoted references are also parsed."""
        source = 'const w = useWorkflow("my_workflow");'

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "my_workflow"

    def test_parses_multiple_refs(self):
        """Multiple useWorkflow calls are all parsed."""
        source = """
const w1 = useWorkflowQuery('list_tenants');
const w2 = useWorkflowMutation('create_tenant');
"""
        refs = parse_dependencies(source)

        assert len(refs) == 2
        assert "list_tenants" in refs
        assert "create_tenant" in refs

    def test_deduplicates_same_ref(self):
        """Same ref used multiple times is deduplicated."""
        source = """
const w1 = useWorkflowQuery('list_tenants');
const w2 = useWorkflowQuery('list_tenants');
"""
        refs = parse_dependencies(source)

        assert len(refs) == 1

    def test_empty_source(self):
        """Empty source returns empty list."""
        refs = parse_dependencies("")

        assert len(refs) == 0

    def test_no_use_workflow_calls(self):
        """Source without useWorkflow returns empty list."""
        source = "const x = 1; const y = 2;"

        refs = parse_dependencies(source)

        assert len(refs) == 0

    def test_parses_use_workflow_query(self):
        """useWorkflowQuery call is parsed."""
        source = "const { data } = useWorkflowQuery('550e8400-e29b-41d4-a716-446655440000');"

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "550e8400-e29b-41d4-a716-446655440000"

    def test_parses_use_workflow_mutation(self):
        """useWorkflowMutation call is parsed."""
        source = "const { execute } = useWorkflowMutation('run_report');"

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "run_report"

    def test_parses_mixed_hook_calls(self):
        """All three hook variants are parsed and deduplicated."""
        source = """
const q = useWorkflowQuery('query_workflow');
const m = useWorkflowMutation('mutate_workflow');
const w = useWorkflow('legacy_workflow');
"""
        refs = parse_dependencies(source)

        assert len(refs) == 3

    def test_deduplicates_across_hook_variants(self):
        """Same ref used via different hooks is deduplicated."""
        source = """
const q = useWorkflowQuery('my_workflow');
const m = useWorkflowMutation('my_workflow');
"""
        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "my_workflow"

    def test_parses_ref_with_spaces_around_quotes(self):
        """Whitespace between parens and quotes is handled."""
        source = "const w = useWorkflowQuery( 'my_workflow' );"

        refs = parse_dependencies(source)

        assert len(refs) == 1
        assert refs[0] == "my_workflow"

    def test_mixed_uuid_and_name_refs(self):
        """Both UUID and name refs are extracted."""
        source = """
const q = useWorkflowQuery('550e8400-e29b-41d4-a716-446655440000');
const m = useWorkflowMutation('create_tenant');
"""
        refs = parse_dependencies(source)

        assert len(refs) == 2
        assert "550e8400-e29b-41d4-a716-446655440000" in refs
        assert "create_tenant" in refs


class TestSyncFileDependencies:
    """Tests for sync_file_dependencies function."""

    @pytest.mark.asyncio
    async def test_no_deps_for_empty_source(self):
        """Returns 0 when source has no workflow references."""
        db = AsyncMock()
        file_id = uuid4()
        source = "const x = 1;"

        count = await sync_file_dependencies(db, file_id, source)

        # Should have called execute (for delete) but not add
        assert db.execute.called
        assert not db.add.called
        assert count == 0

    @pytest.mark.asyncio
    async def test_resolves_name_based_ref(self):
        """Name-based refs are resolved against workflow DB query."""
        db = AsyncMock()
        file_id = uuid4()
        wf_id = uuid4()

        # Mock the workflow query to return a workflow matching by name
        mock_result = MagicMock()
        mock_result.all.return_value = [(wf_id, "list_tenants")]
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query
        ]

        source = "const { data } = useWorkflowQuery('list_tenants');"

        count = await sync_file_dependencies(db, file_id, source, uuid4())

        assert count == 1
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_resolves_uuid_based_ref(self):
        """UUID-based refs are resolved against workflow DB query."""
        db = AsyncMock()
        file_id = uuid4()
        wf_id = UUID("550e8400-e29b-41d4-a716-446655440000")

        # Mock the workflow query to return a workflow matching by UUID
        mock_result = MagicMock()
        mock_result.all.return_value = [(wf_id, "some_workflow")]
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query
        ]

        source = f"const w = useWorkflow('{wf_id}');"

        count = await sync_file_dependencies(db, file_id, source, uuid4())

        assert count == 1
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_unresolved_ref_not_inserted(self):
        """Refs that don't match any workflow are not inserted."""
        db = AsyncMock()
        file_id = uuid4()

        # Mock the workflow query to return no matching workflows
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query (empty)
        ]

        source = "const { data } = useWorkflowQuery('nonexistent_workflow');"

        count = await sync_file_dependencies(db, file_id, source, uuid4())

        assert count == 0
        assert not db.add.called

    @pytest.mark.asyncio
    async def test_deduplicates_before_insert(self):
        """Same workflow referenced multiple times only produces one dep row."""
        db = AsyncMock()
        file_id = uuid4()
        wf_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [(wf_id, "my_workflow")]
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query
        ]

        source = """
const q = useWorkflowQuery('my_workflow');
const m = useWorkflowMutation('my_workflow');
"""

        count = await sync_file_dependencies(db, file_id, source, uuid4())

        assert count == 1
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_different_workflows(self):
        """Multiple different workflow refs each produce a dep row."""
        db = AsyncMock()
        file_id = uuid4()
        wf_id_1 = uuid4()
        wf_id_2 = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            (wf_id_1, "workflow_a"),
            (wf_id_2, "workflow_b"),
        ]
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query
        ]

        source = """
const a = useWorkflowQuery('workflow_a');
const b = useWorkflowMutation('workflow_b');
"""

        count = await sync_file_dependencies(db, file_id, source, uuid4())

        assert count == 2
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_defaults_to_global_only_without_org_id(self):
        """Without org_id, only global workflows should be queried."""
        db = AsyncMock()
        file_id = uuid4()
        wf_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [(wf_id, "global_workflow")]
        db.execute.side_effect = [
            AsyncMock(),  # delete call
            mock_result,  # workflow query
        ]

        source = "const w = useWorkflow('global_workflow');"

        # No org_id passed - should still work (global only)
        count = await sync_file_dependencies(db, file_id, source)

        assert count == 1
