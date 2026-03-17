"""
Unit tests for AnthropicClient._convert_messages.

Verifies correct conversion of LLMMessage sequences to Anthropic API format,
especially tool_use/tool_result pairing.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.llm import LLMMessage, ToolCallRequest


@pytest.fixture
def client():
    """Create an AnthropicClient with mocked dependencies."""
    with patch("src.services.llm.anthropic_client.AsyncAnthropic"):
        from src.services.llm.anthropic_client import AnthropicClient

        config = MagicMock()
        config.api_key = "test-key"
        config.model = "claude-sonnet-4-20250514"
        config.max_tokens = 1024
        return AnthropicClient(config)


class TestConvertMessages:
    """Test _convert_messages formatting for Anthropic API."""

    def test_basic_conversation(self, client):
        """Simple user/assistant messages convert correctly."""
        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there"),
        ]
        system, result = client._convert_messages(messages)
        assert system == "You are helpful"
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_single_tool_call_and_result(self, client):
        """Single tool_use + tool_result pair converts correctly."""
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Search for X"),
            LLMMessage(
                role="assistant",
                content="Searching...",
                tool_calls=[ToolCallRequest(id="c1", name="search", arguments={"q": "X"})],
            ),
            LLMMessage(role="tool", content="Found X", tool_call_id="c1", tool_name="search"),
        ]
        system, result = client._convert_messages(messages)
        assert len(result) == 3
        # assistant has tool_use
        assert result[1]["role"] == "assistant"
        # tool result is a user message
        assert result[2]["role"] == "user"
        content = result[2]["content"]
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "c1"

    def test_multiple_tool_results_merged(self, client):
        """Multiple consecutive tool results merge into a single user message."""
        messages = [
            LLMMessage(role="system", content="System"),
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
        ]
        system, result = client._convert_messages(messages)

        # Should be: user, assistant, user (with both tool_results)
        assert len(result) == 3
        assert result[2]["role"] == "user"
        content = result[2]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "c1"
        assert content[1]["type"] == "tool_result"
        assert content[1]["tool_use_id"] == "c2"

    def test_tool_results_not_merged_across_user_message(self, client):
        """Tool results separated by a user message are NOT merged."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="t", arguments={})],
            ),
            LLMMessage(role="tool", content="Result 1", tool_call_id="c1", tool_name="t"),
            LLMMessage(role="user", content="Now do another thing"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[ToolCallRequest(id="c2", name="t", arguments={})],
            ),
            LLMMessage(role="tool", content="Result 2", tool_call_id="c2", tool_name="t"),
        ]
        system, result = client._convert_messages(messages)

        # assistant, user(tool_result c1), user(text), assistant, user(tool_result c2)
        assert len(result) == 5
        # First tool result
        assert isinstance(result[1]["content"], list)
        assert len(result[1]["content"]) == 1
        # User text message
        assert result[2]["content"] == "Now do another thing"
        # Second tool result
        assert isinstance(result[4]["content"], list)
        assert len(result[4]["content"]) == 1

    def test_three_tool_results_merged(self, client):
        """Three consecutive tool results all merge into one user message."""
        messages = [
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCallRequest(id="c1", name="a", arguments={}),
                    ToolCallRequest(id="c2", name="b", arguments={}),
                    ToolCallRequest(id="c3", name="c", arguments={}),
                ],
            ),
            LLMMessage(role="tool", content="R1", tool_call_id="c1", tool_name="a"),
            LLMMessage(role="tool", content="R2", tool_call_id="c2", tool_name="b"),
            LLMMessage(role="tool", content="R3", tool_call_id="c3", tool_name="c"),
        ]
        system, result = client._convert_messages(messages)
        assert len(result) == 2  # assistant + single user with 3 tool_results
        content = result[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 3
        assert [b["tool_use_id"] for b in content] == ["c1", "c2", "c3"]
