"""Shared helpers for agent execution (used by both chat and autonomous executors)."""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent
from src.services.llm import ToolDefinition
from src.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


AUTONOMOUS_MODE_SUFFIX = """

---
EXECUTION MODE: You are running autonomously — there is no human in this conversation.
- Your final response MUST be conclusive: a summary, report, action result, or structured output.
- Do NOT ask questions, request clarification, or use phrases like "let me know if you need anything else."
- If you lack information, state what you could not determine and why, then provide the best result possible with available data.
- If a tool call fails, attempt reasonable alternatives before reporting failure."""


def agent_delegation_slug(name: str) -> str:
    """Generate the tool name slug for a delegated agent."""
    return f"delegate_to_{name.lower().replace(' ', '_')}"


def find_delegated_agent(agent: Agent, tool_name: str) -> Agent | None:
    """Match a delegate_to_* tool name to the target agent."""
    for d in (agent.delegated_agents or []):
        if agent_delegation_slug(d.name) == tool_name and d.is_active:
            return d
    return None


def build_agent_system_prompt(
    agent: Agent,
    *,
    execution_context: dict | None = None,
) -> str:
    """Build the system prompt from agent configuration.

    When execution_context has mode="autonomous", appends instructions
    telling the LLM to produce conclusive output (no follow-up questions).
    """
    prompt = agent.system_prompt

    if execution_context and execution_context.get("mode") == "autonomous":
        prompt += AUTONOMOUS_MODE_SUFFIX

    return prompt


async def resolve_agent_tools(
    agent: Agent,
    session: AsyncSession,
) -> tuple[list[ToolDefinition], dict[str, UUID]]:
    """Resolve tool definitions for an agent.

    Returns (tool_definitions, tool_workflow_id_map).
    The id_map maps normalized tool names to workflow UUIDs.
    """
    tool_registry = ToolRegistry(session)
    tool_definitions: list[ToolDefinition] = []
    tool_workflow_id_map: dict[str, UUID] = {}
    seen_names: dict[str, str] = {}

    # 1. System tools first (they always win conflicts)
    system_tool_ids = list(agent.system_tools or [])

    # Auto-add search_knowledge when agent has knowledge sources
    if agent.knowledge_sources and "search_knowledge" not in system_tool_ids:
        system_tool_ids.append("search_knowledge")

    if system_tool_ids:
        from src.services.mcp_server.server import get_system_tools

        all_system_tools = get_system_tools()
        tool_map = {t["id"]: t for t in all_system_tools}

        for tool_id in system_tool_ids:
            if tool_id in tool_map:
                t = tool_map[tool_id]
                td = ToolDefinition(
                    name=t["id"],
                    description=t["description"],
                    parameters=t["parameters"],
                )
                seen_names[td.name] = f"system tool '{td.name}'"
                tool_definitions.append(td)

    # 2. Workflow tools (sorted by ID for determinism)
    tool_ids = [tool.id for tool in agent.tools]

    if tool_ids:
        workflow_tool_defs = await tool_registry.get_tool_definitions(tool_ids)
        workflow_tool_defs_sorted = sorted(workflow_tool_defs, key=lambda t: str(t.id))

        for td in workflow_tool_defs_sorted:
            if td.name not in seen_names:
                seen_names[td.name] = f"workflow '{td.workflow_name}'"
                tool_workflow_id_map[td.name] = td.id
                tool_definitions.append(
                    ToolDefinition(
                        name=td.name,
                        description=td.description,
                        parameters=td.parameters,
                    )
                )
            else:
                logger.warning(
                    f"Tool name conflict: workflow '{td.workflow_name}' ({td.name}) "
                    f"hidden by {seen_names[td.name]}"
                )

    # 3. Delegation tools (use already-loaded relationship, no extra query)
    if agent.delegated_agents:
        for delegated in agent.delegated_agents:
            if not delegated.is_active:
                continue
            tool_name = agent_delegation_slug(delegated.name)
            if tool_name not in seen_names:
                tool_definitions.append(
                    ToolDefinition(
                        name=tool_name,
                        description=f"Delegate a task to {delegated.name}. {delegated.description or ''}",
                        parameters={
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": "The task or question to delegate to this agent",
                                },
                            },
                            "required": ["task"],
                        },
                    )
                )

    return tool_definitions, tool_workflow_id_map
