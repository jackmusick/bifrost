"""
System Agents - Built-in agents that are auto-created.

Provides system agents like the Coding Assistant that are created on startup
and cannot be deleted by users.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import AgentAccessLevel
from src.models.orm import Agent

logger = logging.getLogger(__name__)

# System coding agent definition
CODING_AGENT_NAME = "Coding Assistant"
CODING_AGENT_DESCRIPTION = (
    "AI-powered workflow development assistant. Helps create workflows, "
    "tools, and integrations using the Bifrost SDK. Uses Claude's coding "
    "capabilities with access to platform documentation and examples."
)

# System prompt will be in prompts.py - this is just the database record
CODING_AGENT_SYSTEM_PROMPT = """You are Bifrost's Coding Assistant.

Your role is to help platform administrators create and modify Bifrost workflows, tools, and integrations.

IMPORTANT: Before writing code, read the SDK documentation and examples by using the Read tool on the paths provided in your instructions.

When a user asks you to create something, always:
1. Understand what they want to build
2. Clarify how they want to run it (webhook, form, schedule, or manual trigger)
3. Read relevant SDK code to understand patterns
4. Create the workflow in the workspace directory

Be helpful, clear, and write production-quality code."""


async def ensure_system_agents(db: AsyncSession) -> None:
    """
    Ensure all system agents exist in the database.

    Called on application startup to create built-in agents if they don't exist.
    """
    await ensure_coding_agent(db)


async def ensure_coding_agent(db: AsyncSession) -> Agent:
    """
    Ensure the Coding Assistant system agent exists.

    Creates it if it doesn't exist, updates it if the system prompt has changed.

    Returns:
        The Coding Assistant agent
    """
    # Look for existing coding agent by is_coding_mode flag
    result = await db.execute(
        select(Agent).where(Agent.is_coding_mode == True)  # noqa: E712
    )
    agent = result.scalars().first()

    if agent:
        logger.info(f"Coding Assistant agent already exists: {agent.id}")
        # Update system prompt if changed
        if agent.system_prompt != CODING_AGENT_SYSTEM_PROMPT:
            agent.system_prompt = CODING_AGENT_SYSTEM_PROMPT
            await db.commit()
            logger.info("Updated Coding Assistant system prompt")
        return agent

    # Create new coding agent
    agent = Agent(
        name=CODING_AGENT_NAME,
        description=CODING_AGENT_DESCRIPTION,
        system_prompt=CODING_AGENT_SYSTEM_PROMPT,
        channels=["chat"],
        access_level=AgentAccessLevel.ROLE_BASED,  # Role-based with no roles = platform admins only
        organization_id=None,  # Global agent (no org restriction)
        is_active=True,
        is_coding_mode=True,
        is_system=True,  # Can't be deleted
        created_by="system",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info(f"Created Coding Assistant system agent: {agent.id}")
    return agent


async def get_coding_agent(db: AsyncSession) -> Agent | None:
    """
    Get the Coding Assistant agent.

    Returns:
        The Coding Assistant agent, or None if not found
    """
    result = await db.execute(
        select(Agent).where(Agent.is_coding_mode == True)  # noqa: E712
    )
    return result.scalars().first()


async def get_coding_agent_id(db: AsyncSession) -> UUID | None:
    """
    Get the Coding Assistant agent ID.

    Returns:
        The agent ID, or None if not found
    """
    agent = await get_coding_agent(db)
    return agent.id if agent else None
