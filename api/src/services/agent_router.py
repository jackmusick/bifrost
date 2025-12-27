"""
Agent Router Service

Routes user messages to the appropriate agent based on:
1. @mention syntax (explicit routing)
2. AI-based intent analysis (automatic routing)
"""

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.orm import Agent
from src.services.llm import get_llm_client, LLMMessage

logger = logging.getLogger(__name__)


# Regex to match @[Agent Name] mentions (bracketed format)
MENTION_PATTERN = re.compile(r"@\[([^\]]+)\]")


class AgentRouter:
    """
    Routes chat messages to appropriate agents.

    Supports two routing modes:
    1. Explicit: User types @AgentName to switch to that agent
    2. Automatic: AI analyzes message intent and routes to best-fit agent
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def parse_mention(self, message: str) -> Agent | None:
        """
        Parse @mention from user message and find matching agent.

        Args:
            message: User's message text

        Returns:
            Agent if a valid @mention was found, None otherwise
        """
        match = MENTION_PATTERN.search(message)
        if not match:
            return None

        agent_name = match.group(1).strip()

        # Find agent by name (case-insensitive), with tools and delegations loaded
        result = await self.session.execute(
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
            )
            .where(Agent.name.ilike(agent_name))
            .where(Agent.is_active.is_(True))
        )
        agent = result.scalar_one_or_none()

        if agent:
            logger.info(f"@mention routing to agent: {agent.name}")

        return agent

    def _build_agent_description(self, agent: Agent) -> str:
        """Build agent description including tool and knowledge capabilities for routing."""
        description = agent.description or "General assistant"

        # Get tool names for this agent
        tool_names = []
        for tool in agent.tools:
            if tool.is_active and tool.is_tool:
                tool_names.append(tool.name)

        # Build capability strings
        capabilities = []
        if tool_names:
            capabilities.append(f"Tools: {', '.join(tool_names)}")
        if agent.knowledge_sources:
            capabilities.append(f"Knowledge: {', '.join(agent.knowledge_sources)}")

        if capabilities:
            return f"- {agent.name}: {description} ({'; '.join(capabilities)})"
        return f"- {agent.name}: {description}"

    async def route_message(
        self,
        message: str,
        available_agents: list[Agent] | None = None,
        is_platform_admin: bool = False,
    ) -> Agent | None:
        """
        Use AI to route a message to the most appropriate agent.

        Args:
            message: User's message text
            available_agents: Optional list of agents to consider (defaults to all active)
            is_platform_admin: Whether the user is a platform admin (enables coding agent)

        Returns:
            Agent if a good match was found, None to handle directly
        """
        # Get available agents if not provided (with tools and delegations eager-loaded)
        if available_agents is None:
            result = await self.session.execute(
                select(Agent)
                .options(
                    selectinload(Agent.tools),
                    selectinload(Agent.delegated_agents),
                )
                .where(Agent.is_active.is_(True))
            )
            available_agents = list(result.scalars().all())

        # For platform admins, include the coding agent (if not already in list)
        if is_platform_admin:
            from src.core.system_agents import get_coding_agent
            coding_agent = await get_coding_agent(self.session)
            if coding_agent and coding_agent not in available_agents:
                available_agents.append(coding_agent)

        # If no agents available, return None
        if not available_agents:
            return None

        # Build agent descriptions with tool and knowledge info for better routing
        agent_descriptions = "\n".join([
            self._build_agent_description(agent)
            for agent in available_agents
        ])

        router_prompt = f"""You are a routing assistant. Analyze the user's message and determine which agent (if any) is best suited to handle their request.

Available agents:
{agent_descriptions}

Rules:
1. If the user's request matches an agent's specialty, tools, or knowledge sources, respond with ONLY the agent name (exactly as shown above).
2. If the request is general or doesn't match any agent specialty, respond with "DIRECT".
3. When in doubt, prefer routing to a specialist if their tools or knowledge could help.
4. If a user asks about data that matches an agent's knowledge source (e.g., "tickets" matches "halopsa-tickets"), route to that agent.
5. For "Coding Assistant" specifically, route requests that involve:
   - Creating, building, or developing workflows, automations, or integrations
   - Writing or modifying code/scripts for the platform
   - SDK or API development questions
   - Questions about Bifrost SDK patterns or capabilities

User message: {message}

Your response (agent name or DIRECT):"""

        logger.debug(f"Router prompt:\n{router_prompt}")

        try:
            llm_client = await get_llm_client(self.session)

            # Use non-streaming for quick routing decision
            response = await llm_client.complete(
                messages=[
                    LLMMessage(role="system", content="You are a routing assistant. Respond only with the agent name or DIRECT."),
                    LLMMessage(role="user", content=router_prompt),
                ],
                max_tokens=50,
                temperature=0,  # Deterministic routing
            )

            if response.content:
                agent_name = response.content.strip()

                if agent_name.upper() == "DIRECT":
                    return None

                # Find matching agent
                for agent in available_agents:
                    if agent.name.lower() == agent_name.lower():
                        logger.info(f"AI routing to agent: {agent.name}")
                        return agent

            return None

        except Exception as e:
            logger.error(f"Agent routing failed: {e}")
            return None

    async def get_available_agents(self) -> list[Agent]:
        """Get all active agents for routing."""
        result = await self.session.execute(
            select(Agent).where(Agent.is_active.is_(True))
        )
        return list(result.scalars().all())

    def strip_mention(self, message: str) -> str:
        """
        Remove @mention from message for cleaner processing.

        Args:
            message: Original message with @mention

        Returns:
            Message with @mention removed
        """
        return MENTION_PATTERN.sub("", message).strip()
