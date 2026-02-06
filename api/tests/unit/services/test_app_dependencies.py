"""
Unit tests for app dependency parsing and sync.
"""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.services.app_dependencies import parse_dependencies, sync_file_dependencies


class TestParseDependencies:
    """Tests for parse_dependencies function."""

    def test_parses_single_use_workflow(self):
        """Single useWorkflow call is parsed."""
        source = "const w = useWorkflow('550e8400-e29b-41d4-a716-446655440000');"

        deps = parse_dependencies(source)

        assert len(deps) == 1
        assert deps[0][0] == "workflow"
        assert deps[0][1] == UUID("550e8400-e29b-41d4-a716-446655440000")

    def test_parses_double_quoted_uuid(self):
        """Double-quoted UUIDs are also parsed."""
        source = 'const w = useWorkflow("550e8400-e29b-41d4-a716-446655440000");'

        deps = parse_dependencies(source)

        assert len(deps) == 1

    def test_parses_multiple_workflows(self):
        """Multiple useWorkflow calls are all parsed."""
        source = """
const w1 = useWorkflow('11111111-1111-1111-1111-111111111111');
const w2 = useWorkflow('22222222-2222-2222-2222-222222222222');
"""
        deps = parse_dependencies(source)

        assert len(deps) == 2

    def test_deduplicates_same_uuid(self):
        """Same UUID used multiple times is deduplicated."""
        source = """
const w1 = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
const w2 = useWorkflow('550e8400-e29b-41d4-a716-446655440000');
"""
        deps = parse_dependencies(source)

        assert len(deps) == 1

    def test_ignores_non_uuid_strings(self):
        """Non-UUID strings in useWorkflow are ignored."""
        source = "const w = useWorkflow('not-a-valid-uuid');"

        deps = parse_dependencies(source)

        assert len(deps) == 0

    def test_ignores_portable_refs(self):
        """Portable refs (not UUIDs) are ignored by dependency parser."""
        source = "const w = useWorkflow('workflows/test.py::my_func');"

        deps = parse_dependencies(source)

        assert len(deps) == 0

    def test_empty_source(self):
        """Empty source returns empty list."""
        deps = parse_dependencies("")

        assert len(deps) == 0

    def test_no_use_workflow_calls(self):
        """Source without useWorkflow returns empty list."""
        source = "const x = 1; const y = 2;"

        deps = parse_dependencies(source)

        assert len(deps) == 0


class TestSyncFileDependencies:
    """Tests for sync_file_dependencies function."""

    @pytest.mark.asyncio
    async def test_deletes_existing_and_inserts_new(self):
        """Existing dependencies are deleted before inserting new ones."""
        db = AsyncMock()
        file_id = uuid4()
        workflow_uuid = "550e8400-e29b-41d4-a716-446655440000"
        source = f"const w = useWorkflow('{workflow_uuid}');"

        count = await sync_file_dependencies(db, file_id, source)

        # Should have called execute (for delete) then add (for insert)
        assert db.execute.called
        assert db.add.called
        assert count == 1

    @pytest.mark.asyncio
    async def test_returns_zero_for_no_dependencies(self):
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
    async def test_inserts_multiple_dependencies(self):
        """Multiple distinct workflow references each get inserted."""
        db = AsyncMock()
        file_id = uuid4()
        source = """
const w1 = useWorkflow('11111111-1111-1111-1111-111111111111');
const w2 = useWorkflow('22222222-2222-2222-2222-222222222222');
"""

        count = await sync_file_dependencies(db, file_id, source)

        assert count == 2
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_deduplicates_before_insert(self):
        """Duplicate UUIDs in source only produce one dependency row."""
        db = AsyncMock()
        file_id = uuid4()
        source = """
const w1 = useWorkflow('11111111-1111-1111-1111-111111111111');
const w2 = useWorkflow('11111111-1111-1111-1111-111111111111');
"""

        count = await sync_file_dependencies(db, file_id, source)

        assert count == 1
        assert db.add.call_count == 1
