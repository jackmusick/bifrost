"""
Unit tests for AgentExecutor context window management.

Tests token estimation, context pruning, and warning generation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.agent_executor import (
    CONTEXT_KEEP_RECENT,
    CONTEXT_MAX_TOKENS,
    CONTEXT_WARNING_TOKENS,
    TOOL_OUTPUT_PROTECT_TOKENS,
    AgentExecutor,
)
from src.services.llm import LLMMessage, ToolCallRequest


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


class TestTokenEstimation:
    """Test token estimation functionality."""

    def test_estimate_tokens_empty_messages(self, executor):
        """Test token estimation with empty message list."""
        result = executor._estimate_tokens([])
        assert result == 0

    def test_estimate_tokens_text_only(self, executor):
        """Test token estimation with text content only."""
        messages = [
            LLMMessage(role="system", content="Hello world"),  # 11 chars = ~2 tokens
            LLMMessage(role="user", content="How are you?"),  # 12 chars = ~3 tokens
        ]
        result = executor._estimate_tokens(messages)
        # (11 + 12) // 4 = 5 tokens
        assert result == 5

    def test_estimate_tokens_with_tool_calls(self, executor):
        """Test token estimation includes tool call JSON."""
        messages = [
            LLMMessage(
                role="assistant",
                content="Let me help",
                tool_calls=[
                    ToolCallRequest(
                        id="call_123",
                        name="search",
                        arguments={"query": "test"},
                    )
                ],
            ),
        ]
        result = executor._estimate_tokens(messages)
        # Should include both content and tool call JSON
        assert result > 0
        # Should be more than just the text content
        text_only = len("Let me help") // 4
        assert result > text_only

    def test_estimate_tokens_none_content(self, executor):
        """Test token estimation handles None content."""
        messages = [
            LLMMessage(role="assistant", content=None, tool_calls=None),
        ]
        result = executor._estimate_tokens(messages)
        assert result == 0

    def test_estimate_tokens_large_content(self, executor):
        """Test token estimation with large content."""
        # Create ~100K characters (should be ~25K tokens)
        large_content = "x" * 100_000
        messages = [LLMMessage(role="user", content=large_content)]
        result = executor._estimate_tokens(messages)
        assert result == 25_000  # 100000 // 4


class TestContextThresholds:
    """Test that context thresholds are properly configured."""

    def test_warning_threshold_less_than_max(self):
        """Verify warning threshold is less than max threshold."""
        assert CONTEXT_WARNING_TOKENS < CONTEXT_MAX_TOKENS

    def test_keep_recent_is_reasonable(self):
        """Verify keep_recent is a reasonable number."""
        assert CONTEXT_KEEP_RECENT >= 10
        assert CONTEXT_KEEP_RECENT <= 50

    def test_max_tokens_reasonable_for_claude(self):
        """Verify max tokens leaves headroom for Claude's 200K context."""
        assert CONTEXT_MAX_TOKENS <= 150_000  # Leave at least 50K for response


class TestContextPruning:
    """Test context pruning functionality."""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for summarization."""
        client = AsyncMock()
        client.complete = AsyncMock(
            return_value=MagicMock(content="Summary of previous conversation.")
        )
        return client

    @pytest.mark.asyncio
    async def test_prune_context_below_threshold(self, executor, mock_llm_client):
        """Test that pruning is skipped when below threshold."""
        # Create messages well under the limit
        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there!"),
        ]

        result, original_tokens = await executor._prune_context(
            messages, mock_llm_client
        )

        # Should return original messages unchanged
        assert result == messages
        assert original_tokens < CONTEXT_MAX_TOKENS
        # LLM should not be called for summarization
        mock_llm_client.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_prune_context_above_threshold(self, executor, mock_llm_client):
        """Test that pruning occurs when above threshold."""
        # Create a large system message to exceed threshold
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)  # Exceed threshold

        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="First question"),
            LLMMessage(role="assistant", content=large_content),
            LLMMessage(role="user", content="Follow up 1"),
            LLMMessage(role="assistant", content="Response 1"),
            LLMMessage(role="user", content="Follow up 2"),
            LLMMessage(role="assistant", content="Response 2"),
        ]

        result, original_tokens = await executor._prune_context(
            messages, mock_llm_client, keep_recent=2
        )

        # Should have pruned messages
        assert len(result) < len(messages)
        # Should have called LLM for summarization
        mock_llm_client.complete.assert_called_once()
        # First message should still be system prompt
        assert result[0].role == "system"
        # Should include first user message
        assert any(m.content == "First question" for m in result)
        # Should include summary message
        assert any("[Previous conversation summary]" in (m.content or "") for m in result)

    @pytest.mark.asyncio
    async def test_prune_context_preserves_system_prompt(
        self, executor, mock_llm_client
    ):
        """Test that system prompt is always preserved."""
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)
        system_prompt = "You are a specialized assistant"

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content="Question 1"),
            LLMMessage(role="assistant", content=large_content),
            LLMMessage(role="user", content="Question 2"),
            LLMMessage(role="assistant", content="Answer 2"),
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=2
        )

        # System prompt must be first message
        assert result[0].role == "system"
        assert result[0].content == system_prompt

    @pytest.mark.asyncio
    async def test_prune_context_preserves_first_user_message(
        self, executor, mock_llm_client
    ):
        """Test that first user message is preserved for context."""
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)
        first_user_msg = "My original question that provides important context"

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content=first_user_msg),
            LLMMessage(role="assistant", content=large_content),
            LLMMessage(role="user", content="Follow up"),
            LLMMessage(role="assistant", content="Response"),
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=2
        )

        # First user message should be preserved
        assert any(m.content == first_user_msg for m in result)

    @pytest.mark.asyncio
    async def test_prune_context_preserves_recent_messages(
        self, executor, mock_llm_client
    ):
        """Test that recent messages are preserved."""
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Old question"),
            LLMMessage(role="assistant", content=large_content),
            LLMMessage(role="user", content="Recent question 1"),
            LLMMessage(role="assistant", content="Recent answer 1"),
            LLMMessage(role="user", content="Recent question 2"),
            LLMMessage(role="assistant", content="Recent answer 2"),
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=4
        )

        # Last 4 messages should be preserved
        assert any(m.content == "Recent question 1" for m in result)
        assert any(m.content == "Recent answer 1" for m in result)
        assert any(m.content == "Recent question 2" for m in result)
        assert any(m.content == "Recent answer 2" for m in result)

    @pytest.mark.asyncio
    async def test_prune_context_not_enough_to_summarize(
        self, executor, mock_llm_client
    ):
        """Test that pruning is skipped when not enough messages to summarize."""
        # Even if tokens are high, if there aren't enough messages between
        # first user and recent, we shouldn't summarize
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content=large_content),  # First user is large
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=5
        )

        # Should return original messages (nothing to summarize)
        assert result == messages
        mock_llm_client.complete.assert_not_called()


class TestSummarizeMessages:
    """Test message summarization functionality."""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for summarization."""
        client = AsyncMock()
        client.complete = AsyncMock(
            return_value=MagicMock(content="Summary of the conversation.")
        )
        return client

    @pytest.mark.asyncio
    async def test_summarize_messages_basic(self, executor, mock_llm_client):
        """Test basic message summarization."""
        messages = [
            LLMMessage(role="user", content="What is Python?"),
            LLMMessage(role="assistant", content="Python is a programming language."),
        ]

        result = await executor._summarize_messages(messages, mock_llm_client)

        assert result == "Summary of the conversation."
        mock_llm_client.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_messages_includes_tool_calls(
        self, executor, mock_llm_client
    ):
        """Test that tool calls are included in summarization input."""
        messages = [
            LLMMessage(
                role="assistant",
                content="I'll search for that.",
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="search",
                        arguments={"query": "test"},
                    )
                ],
            ),
        ]

        await executor._summarize_messages(messages, mock_llm_client)

        # Check that the LLM was called with content mentioning the tool
        call_args = mock_llm_client.complete.call_args
        user_message = call_args.kwargs["messages"][1]
        assert "TOOL_CALL" in user_message.content
        assert "search" in user_message.content

    @pytest.mark.asyncio
    async def test_summarize_messages_includes_tool_results(
        self, executor, mock_llm_client
    ):
        """Test that tool results are included in summarization input."""
        messages = [
            LLMMessage(
                role="tool",
                content='{"result": "Found 5 items"}',
                tool_name="search",
            ),
        ]

        await executor._summarize_messages(messages, mock_llm_client)

        # Check that the LLM was called with content mentioning the tool result
        call_args = mock_llm_client.complete.call_args
        user_message = call_args.kwargs["messages"][1]
        assert "TOOL_RESULT" in user_message.content
        assert "search" in user_message.content

    @pytest.mark.asyncio
    async def test_summarize_messages_handles_empty_content(
        self, executor, mock_llm_client
    ):
        """Test handling of messages with None content."""
        mock_llm_client.complete.return_value = MagicMock(content=None)

        messages = [
            LLMMessage(role="user", content="Test"),
        ]

        result = await executor._summarize_messages(messages, mock_llm_client)

        # Should return empty string for None response
        assert result == ""


class TestTurnBoundaries:
    """Test turn boundary detection for tool_use/tool_result grouping."""

    def test_simple_messages(self, executor):
        """Each simple message is its own turn."""
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
        ]
        boundaries = executor._find_turn_boundaries(messages)
        assert boundaries == [0, 1, 2]

    def test_tool_call_group(self, executor):
        """Assistant with tool_calls + tool results form one turn."""
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Search for X"),
            LLMMessage(
                role="assistant",
                content="Searching...",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={"q": "X"})],
            ),
            LLMMessage(role="tool", content="Result for X", tool_call_id="c1", tool_name="search"),
            LLMMessage(role="assistant", content="I found X"),
        ]
        boundaries = executor._find_turn_boundaries(messages)
        # Index 2 (assistant+tool_calls) and 3 (tool) are grouped together
        assert boundaries == [0, 1, 2, 4]

    def test_multiple_tool_results(self, executor):
        """Multiple tool results following one assistant are grouped."""
        messages = [
            LLMMessage(role="user", content="Do two things"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCallRequest(id="c1", name="tool_a", arguments={}),
                    ToolCallRequest(id="c2", name="tool_b", arguments={}),
                ],
            ),
            LLMMessage(role="tool", content="Result A", tool_call_id="c1", tool_name="tool_a"),
            LLMMessage(role="tool", content="Result B", tool_call_id="c2", tool_name="tool_b"),
            LLMMessage(role="assistant", content="Done"),
        ]
        boundaries = executor._find_turn_boundaries(messages)
        # user(0), assistant+2tools(1), assistant(4)
        assert boundaries == [0, 1, 4]

    def test_assistant_without_tool_calls(self, executor):
        """Assistant message without tool_calls is a standalone turn."""
        messages = [
            LLMMessage(role="assistant", content="Just text"),
            LLMMessage(role="user", content="OK"),
        ]
        boundaries = executor._find_turn_boundaries(messages)
        assert boundaries == [0, 1]


class TestCompactToolOutputs:
    """Test tool output compaction (Phase 1 of pruning)."""

    def test_preserves_recent_tool_outputs(self, executor):
        """Recent tool outputs within protection budget are kept intact."""
        messages = [
            LLMMessage(role="user", content="Do something"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(role="tool", content="Short result", tool_call_id="c1", tool_name="search"),
        ]
        result = executor._compact_tool_outputs(messages)
        assert result[2].content == "Short result"

    def test_compacts_old_large_tool_outputs(self, executor):
        """Old large tool outputs get replaced with placeholder."""
        # Create messages where old tool output is large and recent one is small
        old_tool_content = "x" * (TOOL_OUTPUT_PROTECT_TOKENS * 4 + 1000)  # Exceeds budget
        messages = [
            LLMMessage(role="user", content="First"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(
                role="tool",
                content=old_tool_content,
                tool_call_id="c1",
                tool_name="search",
            ),
            LLMMessage(role="user", content="Second"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c2", name="search", arguments={})],
            ),
            LLMMessage(
                role="tool",
                content="Recent small result",
                tool_call_id="c2",
                tool_name="search",
            ),
        ]
        result = executor._compact_tool_outputs(messages)

        # Old large output compacted
        assert result[2].content == "[Tool output cleared for context management]"
        assert result[2].tool_call_id == "c1"
        assert result[2].tool_name == "search"

        # Recent output preserved
        assert result[5].content == "Recent small result"

    def test_preserves_structure(self, executor):
        """Compaction preserves tool_call_id and tool_name on compacted messages."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="my_tool", arguments={})],
            ),
            LLMMessage(
                role="tool",
                content="x" * 50000,  # Large
                tool_call_id="c1",
                tool_name="my_tool",
            ),
        ]
        result = executor._compact_tool_outputs(messages)
        assert result[1].role == "tool"
        assert result[1].tool_call_id == "c1"
        assert result[1].tool_name == "my_tool"

    def test_skips_small_outputs(self, executor):
        """Tool outputs <= 200 chars are never compacted."""
        small_content = "x" * 200
        # Make a message that would exceed the protect budget but is small
        messages = [
            LLMMessage(role="tool", content=small_content, tool_call_id="c1", tool_name="t"),
        ]
        result = executor._compact_tool_outputs(messages)
        assert result[0].content == small_content


class TestFixInterleavedMessages:
    """Test reordering of user messages wedged between tool_use and tool_result."""

    def test_no_interleaving_unchanged(self, executor):
        """Normal sequence passes through unchanged."""
        messages = [
            LLMMessage(role="user", content="Search for X"),
            LLMMessage(
                role="assistant",
                content="Searching...",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(role="tool", content="Result", tool_call_id="c1", tool_name="search"),
            LLMMessage(role="assistant", content="Found it"),
        ]
        result = executor._fix_interleaved_messages(messages)
        assert result == messages

    def test_user_between_tool_use_and_result(self, executor):
        """User message wedged between tool_use and tool_result gets moved after."""
        messages = [
            LLMMessage(role="user", content="Search for X"),
            LLMMessage(
                role="assistant",
                content="Searching...",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(role="user", content="Actually nevermind"),  # interleaved
            LLMMessage(role="tool", content="Result", tool_call_id="c1", tool_name="search"),
            LLMMessage(role="assistant", content="Found it"),
        ]
        result = executor._fix_interleaved_messages(messages)
        assert len(result) == 5
        # tool_result should immediately follow tool_use
        assert result[1].role == "assistant"
        assert result[1].tool_calls is not None
        assert result[2].role == "tool"
        assert result[2].tool_call_id == "c1"
        # user message moved after tool result
        assert result[3].role == "user"
        assert result[3].content == "Actually nevermind"
        assert result[4].role == "assistant"

    def test_multiple_tool_results_with_interleaved_user(self, executor):
        """User message between multi-tool assistant and results."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCallRequest(id="c1", name="tool_a", arguments={}),
                    ToolCallRequest(id="c2", name="tool_b", arguments={}),
                ],
            ),
            LLMMessage(role="user", content="Oops"),  # interleaved
            LLMMessage(role="tool", content="Result A", tool_call_id="c1", tool_name="tool_a"),
            LLMMessage(role="tool", content="Result B", tool_call_id="c2", tool_name="tool_b"),
            LLMMessage(role="assistant", content="Done"),
        ]
        result = executor._fix_interleaved_messages(messages)
        # assistant, tool_a, tool_b, user, assistant
        assert result[0].role == "assistant"
        assert result[1].role == "tool" and result[1].tool_call_id == "c1"
        assert result[2].role == "tool" and result[2].tool_call_id == "c2"
        assert result[3].role == "user" and result[3].content == "Oops"
        assert result[4].role == "assistant"

    def test_no_tool_calls_unchanged(self, executor):
        """Plain conversation without tools passes through unchanged."""
        messages = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
            LLMMessage(role="user", content="Bye"),
        ]
        result = executor._fix_interleaved_messages(messages)
        assert result == messages


class TestFixDanglingToolCalls:
    """Test dangling tool_call prevention."""

    def test_no_dangling(self, executor):
        """Messages with matching pairs are unchanged."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(role="tool", content="Result", tool_call_id="c1", tool_name="search"),
        ]
        result = executor._fix_dangling_tool_calls(messages)
        assert len(result) == 2
        assert result[1].content == "Result"

    def test_injects_missing_tool_result(self, executor):
        """Missing tool result gets a placeholder injected."""
        messages = [
            LLMMessage(
                role="assistant",
                content="Let me search",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={"q": "test"})],
            ),
            # No tool result follows!
            LLMMessage(role="user", content="What happened?"),
        ]
        result = executor._fix_dangling_tool_calls(messages)
        assert len(result) == 3
        assert result[1].role == "tool"
        assert result[1].tool_call_id == "c1"
        assert result[1].tool_name == "search"
        assert "[Tool execution was interrupted]" in result[1].content
        assert result[2].role == "user"

    def test_partial_results(self, executor):
        """Only missing tool results get placeholders, existing ones are kept."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCallRequest(id="c1", name="tool_a", arguments={}),
                    ToolCallRequest(id="c2", name="tool_b", arguments={}),
                ],
            ),
            LLMMessage(role="tool", content="Result A", tool_call_id="c1", tool_name="tool_a"),
            # c2 is missing
        ]
        result = executor._fix_dangling_tool_calls(messages)
        assert len(result) == 3
        # c1 result intact
        assert result[1].tool_call_id == "c1"
        assert result[1].content == "Result A"
        # c2 gets placeholder
        assert result[2].tool_call_id == "c2"
        assert result[2].tool_name == "tool_b"
        assert "[Tool execution was interrupted]" in result[2].content

    def test_no_tool_calls(self, executor):
        """Messages without tool_calls are unchanged."""
        messages = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
        ]
        result = executor._fix_dangling_tool_calls(messages)
        assert result == messages


class TestPruningPreservesToolPairs:
    """Test that context pruning never splits tool_use/tool_result pairs."""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for summarization."""
        client = AsyncMock()
        client.complete = AsyncMock(
            return_value=MagicMock(content="Summary of previous conversation.")
        )
        return client

    @pytest.mark.asyncio
    async def test_pruning_keeps_tool_pairs_intact(self, executor, mock_llm_client):
        """When pruning cuts messages, tool_use/tool_result pairs stay together."""
        large_content = "x" * (CONTEXT_MAX_TOKENS * 4 + 1000)

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Start"),
            LLMMessage(role="assistant", content=large_content),
            LLMMessage(role="user", content="Use a tool"),
            LLMMessage(
                role="assistant",
                content="OK",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={"q": "test"})],
            ),
            LLMMessage(role="tool", content="Found it", tool_call_id="c1", tool_name="search"),
            LLMMessage(role="assistant", content="Here are the results"),
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=4
        )

        # Verify that every assistant with tool_calls has matching tool results
        for i, msg in enumerate(result):
            if msg.role == "assistant" and msg.tool_calls:
                expected_ids = {tc.id for tc in msg.tool_calls}
                j = i + 1
                found_ids = set()
                while j < len(result) and result[j].role == "tool":
                    if result[j].tool_call_id:
                        found_ids.add(result[j].tool_call_id)
                    j += 1
                assert expected_ids == found_ids, (
                    f"Tool pair broken: expected {expected_ids}, found {found_ids}"
                )

    @pytest.mark.asyncio
    async def test_compaction_before_summarization(self, executor, mock_llm_client):
        """Phase 1 compaction can avoid summarization entirely."""
        # Create messages where tool outputs are large but compactable
        # System + user + assistant+tool(huge) + user + assistant+tool(small) + assistant
        huge_tool = "x" * (CONTEXT_MAX_TOKENS * 4)  # This makes it exceed threshold

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="First"),
            LLMMessage(
                role="assistant",
                content="Searching",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={})],
            ),
            LLMMessage(
                role="tool",
                content=huge_tool,
                tool_call_id="c1",
                tool_name="search",
            ),
            LLMMessage(role="user", content="Second"),
            LLMMessage(
                role="assistant",
                content="Searching again",
                tool_calls=[ToolCallRequest(id="c2", name="search", arguments={})],
            ),
            LLMMessage(
                role="tool",
                content="Small result",
                tool_call_id="c2",
                tool_name="search",
            ),
            LLMMessage(role="assistant", content="Done"),
        ]

        result, _ = await executor._prune_context(
            messages, mock_llm_client, keep_recent=20
        )

        # Compaction should have been sufficient — no summarization needed
        mock_llm_client.complete.assert_not_called()

        # The huge tool output should be compacted
        tool_msgs = [m for m in result if m.role == "tool"]
        assert any("[Tool output cleared" in (m.content or "") for m in tool_msgs)

        # But the small recent one should be preserved
        assert any(m.content == "Small result" for m in tool_msgs)
