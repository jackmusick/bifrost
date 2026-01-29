"""
Unit tests for AgentExecutor tool handling.

Tests cover:
- Tool conflict detection
- Automatic search_knowledge addition
- Notification creation for conflicts
- JSON serialization of tool results
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from src.services.agent_executor import AgentExecutor, _serialize_for_json
from src.services.llm import ToolDefinition


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def executor(mock_session):
    """Create an AgentExecutor instance with mocked session."""
    return AgentExecutor(mock_session)


@pytest.fixture
def mock_agent():
    """Create a mock agent with tools."""
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Test Agent"
    agent.tools = []
    agent.system_tools = []
    agent.knowledge_sources = []
    return agent


class TestAutoAddSearchKnowledge:
    """Test automatic addition of search_knowledge system tool."""

    @pytest.mark.asyncio
    async def test_search_knowledge_added_when_agent_has_knowledge_sources(
        self, executor, mock_agent
    ):
        """search_knowledge is auto-added when agent has knowledge_sources."""
        mock_agent.knowledge_sources = ["docs", "faq"]
        mock_agent.system_tools = ["list_organizations"]

        # Mock the tool registry to return empty (no workflow tools)
        executor.tool_registry.get_tool_definitions = AsyncMock(return_value=[])

        # Mock the _get_system_tool_definitions method
        def mock_system_tools(tool_ids):
            result = []
            if "list_organizations" in tool_ids:
                result.append(ToolDefinition(
                    name="list_organizations",
                    description="List all orgs",
                    parameters={"type": "object", "properties": {}},
                ))
            if "search_knowledge" in tool_ids:
                result.append(ToolDefinition(
                    name="search_knowledge",
                    description="Search the knowledge base",
                    parameters={"type": "object", "properties": {}},
                ))
            return result

        with patch.object(executor, "_get_system_tool_definitions", side_effect=mock_system_tools):
            tools = await executor._get_agent_tools(mock_agent)

        tool_names = [t.name for t in tools]
        assert "search_knowledge" in tool_names
        assert "list_organizations" in tool_names

    @pytest.mark.asyncio
    async def test_search_knowledge_not_duplicated_if_already_in_system_tools(
        self, executor, mock_agent
    ):
        """search_knowledge is not added twice if already in system_tools."""
        mock_agent.knowledge_sources = ["docs"]
        mock_agent.system_tools = ["search_knowledge"]

        executor.tool_registry.get_tool_definitions = AsyncMock(return_value=[])

        def mock_system_tools(tool_ids):
            result = []
            if "search_knowledge" in tool_ids:
                result.append(ToolDefinition(
                    name="search_knowledge",
                    description="Search the knowledge base",
                    parameters={"type": "object", "properties": {}},
                ))
            return result

        with patch.object(executor, "_get_system_tool_definitions", side_effect=mock_system_tools):
            tools = await executor._get_agent_tools(mock_agent)

        # Should only have one search_knowledge
        tool_names = [t.name for t in tools]
        assert tool_names.count("search_knowledge") == 1

    @pytest.mark.asyncio
    async def test_no_search_knowledge_when_no_knowledge_sources(
        self, executor, mock_agent
    ):
        """search_knowledge is not added when agent has no knowledge_sources."""
        mock_agent.knowledge_sources = []
        mock_agent.system_tools = ["list_organizations"]

        executor.tool_registry.get_tool_definitions = AsyncMock(return_value=[])

        def mock_system_tools(tool_ids):
            result = []
            if "list_organizations" in tool_ids:
                result.append(ToolDefinition(
                    name="list_organizations",
                    description="List all orgs",
                    parameters={"type": "object", "properties": {}},
                ))
            # search_knowledge not included since it shouldn't be in tool_ids
            if "search_knowledge" in tool_ids:
                result.append(ToolDefinition(
                    name="search_knowledge",
                    description="Search the knowledge base",
                    parameters={"type": "object", "properties": {}},
                ))
            return result

        with patch.object(executor, "_get_system_tool_definitions", side_effect=mock_system_tools):
            tools = await executor._get_agent_tools(mock_agent)

        tool_names = [t.name for t in tools]
        assert "search_knowledge" not in tool_names


class TestToolConflictDetection:
    """Test detection and handling of tool name conflicts."""

    @pytest.mark.asyncio
    async def test_system_tools_win_over_workflow_tools(self, executor, mock_agent):
        """System tools take priority over workflow tools with same name."""
        from src.services.tool_registry import ToolDefinition as RegistryToolDefinition

        # Set up agent with a system tool
        mock_agent.system_tools = ["execute_workflow"]

        # Create a workflow tool that would normalize to 'wf_execute_workflow'
        # This shouldn't conflict, but let's test a direct conflict scenario
        mock_workflow_tool = MagicMock()
        mock_workflow_tool.id = uuid4()
        mock_agent.tools = [mock_workflow_tool]

        # Mock workflow tool definition that conflicts with system tool
        conflicting_tool = RegistryToolDefinition(
            id=mock_workflow_tool.id,
            name="execute_workflow",  # Same name as system tool
            description="Conflicting workflow",
            parameters={"type": "object", "properties": {}},
            workflow_name="Execute Workflow",
            category=None,
        )
        executor.tool_registry.get_tool_definitions = AsyncMock(
            return_value=[conflicting_tool]
        )

        def mock_system_tools(tool_ids):
            result = []
            if "execute_workflow" in tool_ids:
                result.append(ToolDefinition(
                    name="execute_workflow",
                    description="Execute a workflow",
                    parameters={"type": "object", "properties": {}},
                ))
            return result

        with patch.object(executor, "_get_system_tool_definitions", side_effect=mock_system_tools):
            with patch.object(executor, "_notify_tool_conflicts", new_callable=AsyncMock) as mock_notify:
                tools = await executor._get_agent_tools(mock_agent)

        # Should only have the system tool (workflow tool shadowed)
        tool_names = [t.name for t in tools]
        assert tool_names.count("execute_workflow") == 1

        # Should have called notification
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        conflicts = call_args[0][1]
        assert len(conflicts) == 1
        assert conflicts[0][0] == "execute_workflow"  # Tool name
        assert "Execute Workflow" in conflicts[0][1]  # Loser (workflow)
        assert "execute_workflow" in conflicts[0][2]  # Winner (system tool)

    @pytest.mark.asyncio
    async def test_no_conflict_with_prefixed_workflow_tools(self, executor, mock_agent):
        """Workflow tools with category prefix don't conflict with system tools."""
        from src.services.tool_registry import ToolDefinition as RegistryToolDefinition

        mock_agent.system_tools = ["execute_workflow"]

        mock_workflow_tool = MagicMock()
        mock_workflow_tool.id = uuid4()
        mock_agent.tools = [mock_workflow_tool]

        # This workflow has a category, so it gets prefixed - no conflict
        non_conflicting_tool = RegistryToolDefinition(
            id=mock_workflow_tool.id,
            name="halopsa_execute_workflow",  # Prefixed - no conflict
            description="HaloPSA workflow",
            parameters={"type": "object", "properties": {}},
            workflow_name="Execute Workflow",
            category="HaloPSA",
        )
        executor.tool_registry.get_tool_definitions = AsyncMock(
            return_value=[non_conflicting_tool]
        )

        def mock_system_tools(tool_ids):
            result = []
            if "execute_workflow" in tool_ids:
                result.append(ToolDefinition(
                    name="execute_workflow",
                    description="Execute a workflow",
                    parameters={"type": "object", "properties": {}},
                ))
            return result

        with patch.object(executor, "_get_system_tool_definitions", side_effect=mock_system_tools):
            with patch.object(executor, "_notify_tool_conflicts", new_callable=AsyncMock) as mock_notify:
                tools = await executor._get_agent_tools(mock_agent)

        # Should have both tools
        tool_names = [t.name for t in tools]
        assert "execute_workflow" in tool_names
        assert "halopsa_execute_workflow" in tool_names

        # Should NOT have called notification (no conflicts)
        mock_notify.assert_not_called()


class TestNotifyToolConflicts:
    """Test tool conflict notification creation."""

    @pytest.mark.asyncio
    async def test_notification_created_for_conflicts(self, executor, mock_agent):
        """Notification is created when tools conflict."""
        conflicts = [
            ("search_knowledge", "workflow 'Search Knowledge'", "system tool 'search_knowledge'"),
        ]

        with patch(
            "src.services.notification_service.get_notification_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_notification = AsyncMock()
            mock_get_service.return_value = mock_service

            await executor._notify_tool_conflicts(mock_agent, conflicts)

            mock_service.create_notification.assert_called_once()
            call_args = mock_service.create_notification.call_args

            # Verify notification properties
            assert call_args.kwargs["user_id"] == "system"
            assert call_args.kwargs["for_admins"] is True

            request = call_args.kwargs["request"]
            assert mock_agent.name in request.title
            assert "search_knowledge" in request.description
            assert request.metadata["agent_id"] == str(mock_agent.id)

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_raise(self, executor, mock_agent):
        """Notification failure doesn't break agent tool loading."""
        conflicts = [
            ("test_tool", "workflow 'Test'", "system tool 'test_tool'"),
        ]

        with patch(
            "src.services.notification_service.get_notification_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_notification = AsyncMock(
                side_effect=Exception("Redis connection failed")
            )
            mock_get_service.return_value = mock_service

            # Should not raise
            await executor._notify_tool_conflicts(mock_agent, conflicts)

    @pytest.mark.asyncio
    async def test_notification_description_truncated_if_too_long(
        self, executor, mock_agent
    ):
        """Long conflict descriptions are truncated."""
        # Create many conflicts to exceed 500 char limit
        conflicts = [
            (f"tool_{i}", f"workflow 'Very Long Workflow Name {i}'", f"system tool 'tool_{i}'")
            for i in range(20)
        ]

        with patch(
            "src.services.notification_service.get_notification_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.create_notification = AsyncMock()
            mock_get_service.return_value = mock_service

            await executor._notify_tool_conflicts(mock_agent, conflicts)

            call_args = mock_service.create_notification.call_args
            request = call_args.kwargs["request"]

            # Description should be truncated to ~500 chars
            assert len(request.description) <= 500
            assert request.description.endswith("...")


class TestSerializeForJson:
    """Test the _serialize_for_json helper function."""

    def test_none_returns_empty_string(self):
        """None values return empty string."""
        assert _serialize_for_json(None) == ""

    def test_string_returns_as_is(self):
        """String values are returned unchanged."""
        assert _serialize_for_json("hello world") == "hello world"
        assert _serialize_for_json('{"key": "value"}') == '{"key": "value"}'

    def test_dict_serializes_to_json(self):
        """Dictionaries are serialized to JSON."""
        result = _serialize_for_json({"key": "value", "number": 42})
        assert '"key":"value"' in result or '"key": "value"' in result
        assert "42" in result

    def test_list_serializes_to_json(self):
        """Lists are serialized to JSON."""
        result = _serialize_for_json([1, 2, 3])
        assert result == "[1,2,3]"

    def test_pydantic_model_serializes(self):
        """Pydantic models are properly serialized."""

        class SampleModel(BaseModel):
            text: str
            count: int

        model = SampleModel(text="hello", count=5)
        result = _serialize_for_json(model)

        assert "hello" in result
        assert "5" in result

    def test_nested_pydantic_models_serialize(self):
        """Nested Pydantic models are properly serialized."""

        class Inner(BaseModel):
            value: str

        class Outer(BaseModel):
            inner: Inner
            name: str

        model = Outer(inner=Inner(value="nested"), name="outer")
        result = _serialize_for_json(model)

        assert "nested" in result
        assert "outer" in result

    def test_list_of_pydantic_models_serializes(self):
        """Lists of Pydantic models are properly serialized."""

        class TextContent(BaseModel):
            type: str
            text: str

        content = [
            TextContent(type="text", text="Hello"),
            TextContent(type="text", text="World"),
        ]
        result = _serialize_for_json(content)

        assert "Hello" in result
        assert "World" in result
        assert "text" in result

    def test_mixed_content_serializes(self):
        """Mixed content with Pydantic and primitives serializes."""

        class Item(BaseModel):
            name: str

        data = {
            "items": [Item(name="first"), Item(name="second")],
            "count": 2,
            "active": True,
        }
        result = _serialize_for_json(data)

        assert "first" in result
        assert "second" in result
        assert "2" in result
