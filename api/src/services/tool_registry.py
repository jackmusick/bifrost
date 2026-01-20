"""
Tool Registry Service

Provides AI agent tools from workflows with type='tool'.
Converts workflow metadata to LLM-friendly tool definitions.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Workflow

logger = logging.getLogger(__name__)


def _normalize_tool_name(name: str) -> str:
    """
    Convert workflow name to valid API tool name.

    Anthropic API requires tool names to match ^[a-zA-Z0-9_-]{1,128}$
    This converts names like "Add Comment (Demo)" to "add_comment_demo".
    """
    name = name.lower().strip()
    # Replace spaces and hyphens with underscores
    name = re.sub(r"[\s\-]+", "_", name)
    # Remove invalid characters (keep only alphanumeric and underscore)
    name = re.sub(r"[^a-z0-9_]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Strip leading/trailing underscores
    name = name.strip("_")
    return name


@dataclass
class ToolDefinition:
    """Tool definition in LLM-friendly format."""

    id: UUID
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema format
    workflow_name: str  # Original workflow name for execution


@dataclass
class RegisteredTool:
    """Registered tool with full workflow metadata."""

    id: UUID
    name: str
    description: str
    category: str
    parameters_schema: list[dict[str, Any]]
    file_path: str
    function_name: str


class ToolRegistry:
    """
    Registry for AI agent tools.

    Provides tools from workflows with type='tool'.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_tools(self) -> Sequence[RegisteredTool]:
        """
        Get all registered tools.

        Returns:
            List of RegisteredTool objects
        """
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.type == "tool")
            .order_by(Workflow.name)
        )
        workflows = result.scalars().all()

        return [
            RegisteredTool(
                id=w.id,
                name=w.name,
                description=w.tool_description or w.description or "",
                category=w.category,
                parameters_schema=w.parameters_schema,
                file_path=w.path,
                function_name=w.function_name,
            )
            for w in workflows
        ]

    async def get_tools_by_ids(self, tool_ids: list[UUID]) -> Sequence[RegisteredTool]:
        """
        Get specific tools by their IDs.

        Args:
            tool_ids: List of workflow UUIDs to retrieve

        Returns:
            List of RegisteredTool objects
        """
        if not tool_ids:
            return []

        # First, check what workflows exist with these IDs (for debugging)
        all_workflows_result = await self.session.execute(
            select(Workflow.id, Workflow.name, Workflow.is_active, Workflow.type)
            .where(Workflow.id.in_(tool_ids))
        )
        all_workflows = all_workflows_result.fetchall()
        for w in all_workflows:
            logger.debug(
                f"Workflow '{w.name}' (id={w.id}): is_active={w.is_active}, type={w.type}"
            )
            if w.type != "tool":
                logger.warning(
                    f"Workflow '{w.name}' is assigned to agent but type='{w.type}' - "
                    "it won't be available as a tool!"
                )
            if not w.is_active:
                logger.warning(
                    f"Workflow '{w.name}' is assigned to agent but is_active=False - "
                    "it won't be available as a tool!"
                )

        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.id.in_(tool_ids))
            .where(Workflow.is_active.is_(True))
            .where(Workflow.type == "tool")
            .order_by(Workflow.name)
        )
        workflows = result.scalars().all()
        logger.info(f"Filtered to {len(workflows)} active tools from {len(tool_ids)} requested IDs")

        return [
            RegisteredTool(
                id=w.id,
                name=w.name,
                description=w.tool_description or w.description or "",
                category=w.category,
                parameters_schema=w.parameters_schema,
                file_path=w.path,
                function_name=w.function_name,
            )
            for w in workflows
        ]

    async def get_tool_definitions(
        self, tool_ids: list[UUID] | None = None
    ) -> list[ToolDefinition]:
        """
        Get tool definitions in LLM-friendly format.

        Args:
            tool_ids: Optional list of tool IDs to filter by.
                     If None, returns all tools.

        Returns:
            List of ToolDefinition objects ready for LLM function calling
        """
        if tool_ids is not None:
            tools = await self.get_tools_by_ids(tool_ids)
        else:
            tools = await self.get_all_tools()

        return [self._to_tool_definition(t) for t in tools]

    def _to_tool_definition(self, tool: RegisteredTool) -> ToolDefinition:
        """
        Convert a RegisteredTool to LLM-friendly ToolDefinition.

        Converts workflow parameter schema to JSON Schema format
        compatible with OpenAI/Anthropic function calling.
        """
        # Build JSON Schema from parameters
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in tool.parameters_schema:
            param_name = param.get("name", "")
            param_type = param.get("type", "string")
            param_label = param.get("label") or param_name

            # Map workflow types to JSON Schema types
            json_type = self._map_type_to_json_schema(param_type)

            properties[param_name] = {
                "type": json_type,
                "description": param_label,
            }

            # Add default value if present
            if "default_value" in param and param["default_value"] is not None:
                properties[param_name]["default"] = param["default_value"]

            # Track required parameters
            if param.get("required", False):
                required.append(param_name)

        parameters_schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }

        if required:
            parameters_schema["required"] = required

        return ToolDefinition(
            id=tool.id,
            name=_normalize_tool_name(tool.name),
            description=tool.description,
            parameters=parameters_schema,
            workflow_name=tool.name,  # Keep original for execution lookup
        )

    def _map_type_to_json_schema(self, param_type: str) -> str:
        """Map workflow parameter type to JSON Schema type."""
        type_map = {
            "string": "string",
            "str": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "json": "object",
            "dict": "object",
            "object": "object",
            "list": "array",
            "array": "array",
        }
        return type_map.get(param_type.lower(), "string")

    async def get_tool_by_name(self, name: str) -> RegisteredTool | None:
        """
        Get a specific tool by name.

        Args:
            name: Tool (workflow) name

        Returns:
            RegisteredTool or None if not found
        """
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.name == name)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.type == "tool")
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return None

        return RegisteredTool(
            id=workflow.id,
            name=workflow.name,
            description=workflow.tool_description or workflow.description or "",
            category=workflow.category,
            parameters_schema=workflow.parameters_schema,
            file_path=workflow.path,
            function_name=workflow.function_name,
        )

    async def get_tool_by_id(self, tool_id: UUID) -> RegisteredTool | None:
        """
        Get a specific tool by ID.

        Args:
            tool_id: Tool (workflow) UUID

        Returns:
            RegisteredTool or None if not found
        """
        result = await self.session.execute(
            select(Workflow)
            .where(Workflow.id == tool_id)
            .where(Workflow.is_active.is_(True))
            .where(Workflow.type == "tool")
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return None

        return RegisteredTool(
            id=workflow.id,
            name=workflow.name,
            description=workflow.tool_description or workflow.description or "",
            category=workflow.category,
            parameters_schema=workflow.parameters_schema,
            file_path=workflow.path,
            function_name=workflow.function_name,
        )


def format_tools_for_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """
    Format tools for OpenAI function calling API.

    Args:
        tools: List of ToolDefinition objects

    Returns:
        List of OpenAI tool definitions
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def format_tools_for_anthropic(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """
    Format tools for Anthropic Claude tool use API.

    Args:
        tools: List of ToolDefinition objects

    Returns:
        List of Anthropic tool definitions
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        for tool in tools
    ]
