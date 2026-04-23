"""Full-text search column exists and is indexed."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_agent_runs_has_search_tsv_column(db_session):
    result = await db_session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agent_runs' AND column_name = 'search_tsv'
    """))
    assert result.scalar_one_or_none() == "search_tsv"


@pytest.mark.asyncio
async def test_agent_runs_has_gin_index_on_search_tsv(db_session):
    result = await db_session.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'agent_runs' AND indexname = 'ix_agent_runs_search_tsv_gin'
    """))
    assert result.scalar_one_or_none() == "ix_agent_runs_search_tsv_gin"
