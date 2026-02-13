"""Test WorkflowIndexer enrich-only behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import Update, Insert
from sqlalchemy.sql import ClauseElement


SAMPLE_WORKFLOW = '''
from bifrost import workflow

@workflow(name="My Workflow")
def my_workflow(name: str, count: int = 5):
    """A sample workflow."""
    pass
'''


def _is_statement_type(stmt, *types) -> bool:
    """Check if a SQLAlchemy statement is one of the given types."""
    return isinstance(stmt, types)


@pytest.mark.asyncio
async def test_indexer_skips_unregistered_workflow():
    """WorkflowIndexer should NOT create DB records for unregistered functions."""
    from src.services.file_storage.indexers.workflow import WorkflowIndexer

    mock_db = AsyncMock()

    # No existing workflow in DB for this path+function
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    indexer = WorkflowIndexer(mock_db)
    await indexer.index_python_file("workflows/new.py", SAMPLE_WORKFLOW.encode())

    # Should have queried for existing workflow but NOT inserted/updated
    assert mock_db.execute.call_count >= 1
    # Verify no INSERT or UPDATE was issued (only SELECT)
    for call in mock_db.execute.call_args_list:
        stmt = call[0][0]
        assert not _is_statement_type(stmt, Insert), f"Unexpected INSERT statement"
        assert not _is_statement_type(stmt, Update), f"Unexpected UPDATE statement"


@pytest.mark.asyncio
async def test_indexer_enriches_registered_workflow():
    """WorkflowIndexer should UPDATE existing records with content-derived fields."""
    from src.services.file_storage.indexers.workflow import WorkflowIndexer

    mock_db = AsyncMock()
    existing_wf = MagicMock()
    existing_wf.id = uuid4()
    existing_wf.endpoint_enabled = False

    # Return existing workflow on lookup
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_wf
    mock_db.execute.return_value = mock_result

    indexer = WorkflowIndexer(mock_db)

    await indexer.index_python_file("workflows/existing.py", SAMPLE_WORKFLOW.encode())

    # Should have issued an UPDATE (not INSERT)
    calls = mock_db.execute.call_args_list
    update_issued = any(_is_statement_type(call[0][0], Update) for call in calls)
    assert update_issued, "Expected an UPDATE statement for existing workflow"

    # Verify NO INSERT was issued
    insert_issued = any(_is_statement_type(call[0][0], Insert) for call in calls)
    assert not insert_issued, "Should NOT have issued an INSERT"
