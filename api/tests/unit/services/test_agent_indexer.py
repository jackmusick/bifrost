"""Unit tests for AgentIndexer."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent, AgentTool
from src.models.orm.workflows import Workflow
from src.services.file_storage.indexers.agent import AgentIndexer


@pytest_asyncio.fixture(autouse=True)
async def cleanup_agents(db_session: AsyncSession):
    """Clean up test agents after each test."""
    yield
    await db_session.execute(
        delete(Agent).where(Agent.created_by == "file_sync")
    )
    await db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentIndexer:
    async def test_index_agent_with_tools_alias(self, db_session: AsyncSession):
        """AgentIndexer should accept 'tools' as alias for 'tool_ids'."""
        wf_id = uuid4()
        db_session.add(Workflow(
            id=wf_id, name="test_wf_tools_alias", path="workflows/test_tools_alias.py",
            function_name="test_wf", is_active=True,
        ))
        await db_session.flush()

        agent_yaml = f"""name: Agent With Tools Alias
system_prompt: Test
tools:
- {wf_id}
"""
        indexer = AgentIndexer(db_session)
        await indexer.index_agent("agents/test.agent.yaml", agent_yaml.encode())
        await db_session.flush()

        agent = (await db_session.execute(
            select(Agent).where(Agent.name == "Agent With Tools Alias")
        )).scalar_one()
        tools = (await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent.id)
        )).scalars().all()
        assert len(tools) == 1
        assert tools[0].workflow_id == wf_id

    async def test_index_agent_with_tool_ids(self, db_session: AsyncSession):
        """AgentIndexer should still work with 'tool_ids' (canonical form)."""
        wf_id = uuid4()
        db_session.add(Workflow(
            id=wf_id, name="test_wf_tool_ids", path="workflows/test_tool_ids.py",
            function_name="test_wf", is_active=True,
        ))
        await db_session.flush()

        agent_yaml = f"""name: Agent With Tool IDs
system_prompt: Test
tool_ids:
- {wf_id}
"""
        indexer = AgentIndexer(db_session)
        await indexer.index_agent("agents/test2.agent.yaml", agent_yaml.encode())
        await db_session.flush()

        agent = (await db_session.execute(
            select(Agent).where(Agent.name == "Agent With Tool IDs")
        )).scalar_one()
        tools = (await db_session.execute(
            select(AgentTool).where(AgentTool.agent_id == agent.id)
        )).scalars().all()
        assert len(tools) == 1
        assert tools[0].workflow_id == wf_id
