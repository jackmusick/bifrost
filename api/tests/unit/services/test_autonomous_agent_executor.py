"""Unit tests for AutonomousAgentExecutor."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.execution.agent_helpers import find_delegated_agent
from src.services.execution.autonomous_agent_executor import AutonomousAgentExecutor
from src.services.llm.base import LLMResponse, ToolCallRequest


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Test Agent"
    agent.system_prompt = "You are a test agent."
    agent.tools = []
    agent.system_tools = []
    agent.knowledge_sources = []
    agent.delegated_agents = []
    agent.max_iterations = 10
    agent.max_token_budget = 50000
    agent.llm_model = None
    agent.llm_max_tokens = None
    agent.organization_id = uuid4()
    return agent


class TestAutonomousAgentExecutor:
    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_returns_structured_result(self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent):
        """Run returns output, iterations_used, tokens_used, status."""
        mock_resolve_tools.return_value = ([], {})

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content="Hello world",
            tool_calls=None,
            finish_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
        ))
        mock_get_llm.return_value = mock_llm

        executor = AutonomousAgentExecutor(mock_session)
        result = await executor.run(
            agent=mock_agent,
            input_data={"message": "hello"},
            run_id=str(uuid4()),
        )

        assert result["status"] == "completed"
        assert result["output"] == "Hello world"
        assert result["iterations_used"] == 1
        assert result["tokens_used"] == 150

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_records_steps(self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent):
        """Run records AgentRunStep entries via session.add."""
        mock_resolve_tools.return_value = ([], {})

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content="Response",
            tool_calls=None,
            finish_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
        ))
        mock_get_llm.return_value = mock_llm

        executor = AutonomousAgentExecutor(mock_session)
        await executor.run(
            agent=mock_agent,
            input_data={"task": "analyze"},
            run_id=str(uuid4()),
        )

        # Verify steps were recorded (session.add called for AgentRunStep objects)
        add_calls = mock_session.add.call_args_list
        step_adds = [c for c in add_calls if hasattr(c[0][0], "step_number")]
        # At least the initial llm_request step and the llm_response step
        assert len(step_adds) >= 2

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_with_tool_calls(self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent):
        """Run executes tools and continues the loop until no more tool calls."""
        workflow_id = uuid4()
        mock_resolve_tools.return_value = (
            [MagicMock(name="my_tool")],
            {"my_tool": workflow_id},
        )

        # First call returns a tool call, second call returns final content
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="tc1", name="my_tool", arguments={"x": 1})],
                finish_reason="tool_use",
                input_tokens=100,
                output_tokens=50,
            ),
            LLMResponse(
                content="Final answer",
                tool_calls=None,
                finish_reason="end_turn",
                input_tokens=200,
                output_tokens=100,
            ),
        ])
        mock_get_llm.return_value = mock_llm

        # Mock the workflow tool execution (imported inside _execute_tool)
        with patch("src.services.execution.service.execute_tool") as mock_exec_tool:
            mock_exec_tool.return_value = MagicMock(result="tool output", status=MagicMock(value="completed"))

            executor = AutonomousAgentExecutor(mock_session)
            result = await executor.run(
                agent=mock_agent,
                input_data={"task": "do something"},
                run_id=str(uuid4()),
            )

        assert result["status"] == "completed"
        assert result["output"] == "Final answer"
        assert result["iterations_used"] == 2
        assert result["tokens_used"] == 450  # 150 + 300

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_respects_iteration_budget(self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent):
        """Run stops when max_iterations is exceeded."""
        mock_agent.max_iterations = 2
        mock_resolve_tools.return_value = (
            [MagicMock(name="my_tool")],
            {"my_tool": uuid4()},
        )

        # Always return tool calls so the loop never ends naturally
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content=None,
            tool_calls=[ToolCallRequest(id="tc1", name="my_tool", arguments={})],
            finish_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ))
        mock_get_llm.return_value = mock_llm

        with patch("src.services.execution.service.execute_tool") as mock_exec_tool:
            mock_exec_tool.return_value = MagicMock(result="ok", status=MagicMock(value="completed"))

            executor = AutonomousAgentExecutor(mock_session)
            result = await executor.run(
                agent=mock_agent,
                run_id=str(uuid4()),
            )

        assert result["status"] == "budget_exceeded"
        assert result["iterations_used"] == 2

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_handles_llm_error(self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent):
        """Run returns failed status when LLM call raises."""
        mock_resolve_tools.return_value = ([], {})

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("API timeout"))
        mock_get_llm.return_value = mock_llm

        executor = AutonomousAgentExecutor(mock_session)
        result = await executor.run(
            agent=mock_agent,
            run_id=str(uuid4()),
        )

        assert result["status"] == "failed"
        assert "API timeout" in result["error"]
        assert result["output"] is None

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_parses_json_output_when_schema_given(
        self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent
    ):
        """When output_schema is provided, run attempts to parse JSON from LLM output."""
        mock_resolve_tools.return_value = ([], {})

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=LLMResponse(
            content='{"result": 42}',
            tool_calls=None,
            finish_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
        ))
        mock_get_llm.return_value = mock_llm

        executor = AutonomousAgentExecutor(mock_session)
        result = await executor.run(
            agent=mock_agent,
            output_schema={"type": "object", "properties": {"result": {"type": "integer"}}},
            run_id=str(uuid4()),
        )

        assert result["status"] == "completed"
        assert result["output"] == {"result": 42}

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_run_handles_tool_execution_error(
        self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent
    ):
        """Tool execution errors are caught and fed back to the LLM."""
        workflow_id = uuid4()
        mock_resolve_tools.return_value = (
            [MagicMock(name="broken_tool")],
            {"broken_tool": workflow_id},
        )

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="tc1", name="broken_tool", arguments={})],
                finish_reason="tool_use",
                input_tokens=50,
                output_tokens=25,
            ),
            LLMResponse(
                content="Recovered from error",
                tool_calls=None,
                finish_reason="end_turn",
                input_tokens=100,
                output_tokens=50,
            ),
        ])
        mock_get_llm.return_value = mock_llm

        with patch("src.services.execution.service.execute_tool") as mock_exec_tool:
            mock_exec_tool.side_effect = RuntimeError("Tool crashed")

            executor = AutonomousAgentExecutor(mock_session)
            result = await executor.run(
                agent=mock_agent,
                run_id=str(uuid4()),
            )

        assert result["status"] == "completed"
        assert result["output"] == "Recovered from error"

    @pytest.mark.asyncio
    @patch("src.services.execution.autonomous_agent_executor.get_llm_client")
    @patch("src.services.execution.autonomous_agent_executor.resolve_agent_tools")
    async def test_delegation_uses_find_delegated_agent(
        self, mock_resolve_tools, mock_get_llm, mock_session, mock_agent
    ):
        """Delegation tool calls use find_delegated_agent to resolve target."""
        # Create a delegated agent
        delegated = MagicMock()
        delegated.id = uuid4()
        delegated.name = "Sub Agent"
        delegated.is_active = True
        delegated.system_prompt = "You are a sub agent."
        delegated.tools = []
        delegated.system_tools = []
        delegated.knowledge_sources = []
        delegated.delegated_agents = []
        delegated.max_iterations = 5
        delegated.max_token_budget = 10000
        delegated.llm_model = None
        delegated.llm_max_tokens = None
        delegated.organization_id = mock_agent.organization_id

        mock_agent.delegated_agents = [delegated]

        # Verify find_delegated_agent resolves correctly
        found = find_delegated_agent(mock_agent, "delegate_to_sub_agent")
        assert found is delegated
        assert find_delegated_agent(mock_agent, "delegate_to_nonexistent") is None

        # Set up the main agent to make a delegation call
        mock_resolve_tools.return_value = (
            [MagicMock(name="delegate_to_sub_agent")],
            {},
        )

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=[
            # Main agent delegates
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(
                    id="tc1",
                    name="delegate_to_sub_agent",
                    arguments={"task": "Summarize data"},
                )],
                finish_reason="tool_use",
                input_tokens=100,
                output_tokens=50,
            ),
            # Sub agent responds (called by recursive run)
            LLMResponse(
                content="Sub agent summary",
                tool_calls=None,
                finish_reason="end_turn",
                input_tokens=80,
                output_tokens=40,
            ),
            # Main agent uses sub result
            LLMResponse(
                content="Final: Sub agent summary",
                tool_calls=None,
                finish_reason="end_turn",
                input_tokens=200,
                output_tokens=100,
            ),
        ])
        mock_get_llm.return_value = mock_llm

        executor = AutonomousAgentExecutor(mock_session)
        result = await executor.run(
            agent=mock_agent,
            input_data={"task": "Delegate work"},
            run_id=str(uuid4()),
        )

        assert result["status"] == "completed"
        assert "Sub agent summary" in result["output"]
