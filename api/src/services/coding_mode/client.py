"""
Coding Mode Client

Wraps Claude Agent SDK for Bifrost workflow development.
Handles session management, MCP tool registration, and streaming.
"""

import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.models.contracts.agents import ToolCall, ToolResult
from src.services.coding_mode.models import CodingModeChunk
from src.services.coding_mode.prompts import get_system_prompt
from src.services.coding_mode.session import SessionManager
from src.services.mcp import BifrostMCPServer, MCPContext

logger = logging.getLogger(__name__)

# Claude Agent SDK is optional - will be installed when using coding mode
try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient  # type: ignore
    from claude_agent_sdk.types import (  # type: ignore
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    # Stub classes for when SDK is not installed
    class ClaudeAgentOptions:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            raise ImportError(
                "claude-agent-sdk is required for coding mode. "
                "Install it with: pip install claude-agent-sdk"
            )

    class ClaudeSDKClient:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            raise ImportError(
                "claude-agent-sdk is required for coding mode. "
                "Install it with: pip install claude-agent-sdk"
            )

    # Type stubs
    AssistantMessage = Any  # type: ignore
    ResultMessage = Any  # type: ignore
    TextBlock = Any  # type: ignore
    ToolResultBlock = Any  # type: ignore
    ToolUseBlock = Any  # type: ignore
    UserMessage = Any  # type: ignore

# Workspace path for coding mode
WORKSPACE_PATH = Path("/tmp/bifrost/workspace")

# Allowed read paths for file access (SDK source for documentation)
ALLOWED_READ_PATHS = [
    "/tmp/bifrost/workspace",     # User's workspace (read/write)
    "/app/shared/bifrost_sdk",    # SDK source code (read-only docs)
    "/app/shared/workflows",      # Workflow patterns (read-only docs)
]

# Paths that can be written to
ALLOWED_WRITE_PATHS = [
    "/tmp/bifrost/workspace",     # Only the workspace is writable
]


class CodingModeClient:
    """
    Client for coding mode interactions.

    Wraps Claude Agent SDK with Bifrost-specific configuration:
    - MCP server with execute_workflow and list_integrations tools
    - Sandboxed to workspace directory
    - System prompt with Bifrost SDK documentation
    """

    def __init__(
        self,
        user_id: UUID | str,
        user_email: str,
        user_name: str,
        api_key: str,
        model: str,
        org_id: UUID | str | None = None,
        is_platform_admin: bool = True,
        session_id: str | None = None,
        system_tools: list[str] | None = None,
        knowledge_sources: list[str] | None = None,
    ):
        """
        Initialize coding mode client.

        Args:
            user_id: User ID for context
            user_email: User email for display
            user_name: User name for display
            api_key: Anthropic API key for Claude Agent SDK
            model: Model to use (e.g., "claude-sonnet-4-20250514")
            org_id: Organization ID (optional)
            is_platform_admin: Whether user is platform admin
            session_id: Optional session ID to resume
            system_tools: List of enabled system tool IDs (e.g., ["execute_workflow", "list_integrations"]).
                         If empty or None, no system MCP tools will be available.
            knowledge_sources: List of knowledge namespaces this agent can search.
        """
        self.user_id = str(user_id)
        self.user_email = user_email
        self.user_name = user_name
        self._api_key = api_key
        self._model = model
        self.org_id = str(org_id) if org_id else None
        self.is_platform_admin = is_platform_admin
        self.session_id = session_id or str(uuid4())
        self.session_manager = SessionManager()
        self._system_tools = system_tools or []
        self._knowledge_sources = knowledge_sources or []

        # Create MCP context with all fields
        self._mcp_context = MCPContext(
            user_id=self.user_id,
            org_id=self.org_id,
            is_platform_admin=self.is_platform_admin,
            user_email=self.user_email,
            user_name=self.user_name,
            enabled_system_tools=self._system_tools,
            accessible_namespaces=self._knowledge_sources,
        )

        # Create Bifrost MCP server
        self._mcp_server = BifrostMCPServer(self._mcp_context)

        # SDK client instance - created lazily and reused for conversation continuity
        self._sdk_client: Any = None  # ClaudeSDKClient when initialized

        logger.info(
            f"Initialized CodingModeClient for user {user_email}, session {self.session_id}"
        )

    def _get_options(self) -> ClaudeAgentOptions:
        """
        Build Claude Agent SDK options.

        Configures:
        - Model and system prompt
        - Working directory (workspace)
        - MCP servers (Bifrost tools)
        - Allowed tools (filtered based on agent.system_tools)
        - Path restrictions for file operations
        """
        system_prompt = get_system_prompt()
        logger.info(f"Using system prompt ({len(system_prompt)} chars) for model {self._model}")

        # Standard file tools are always available
        allowed_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]

        # Map system tool IDs to MCP tool names
        tool_id_to_mcp_name = {
            "execute_workflow": "mcp__bifrost__execute_workflow",
            "list_workflows": "mcp__bifrost__list_workflows",
            "list_integrations": "mcp__bifrost__list_integrations",
            "list_forms": "mcp__bifrost__list_forms",
            "get_form_schema": "mcp__bifrost__get_form_schema",
            "validate_form_schema": "mcp__bifrost__validate_form_schema",
            "search_knowledge": "mcp__bifrost__search_knowledge",
        }

        # Add only enabled system MCP tools
        for tool_id in self._system_tools:
            if tool_id in tool_id_to_mcp_name:
                allowed_tools.append(tool_id_to_mcp_name[tool_id])

        logger.info(f"Coding mode allowed_tools: {allowed_tools}")

        return ClaudeAgentOptions(
            model=self._model,
            system_prompt=system_prompt,
            cwd=str(WORKSPACE_PATH),
            mcp_servers={"bifrost": self._mcp_server.get_sdk_server()},
            allowed_tools=allowed_tools,
            permission_mode="acceptEdits",  # Auto-accept file edits in coding mode
            include_partial_messages=True,  # Stream events as they happen (tools, text)
        )

    async def _ensure_client(self) -> Any:
        """
        Get or create SDK client with proper lifecycle management.

        The client is cached to maintain conversation context across
        multiple chat() calls within the same session.
        """
        if self._sdk_client is None:
            # SDK reads API key from env var (doesn't accept api_key param directly)
            os.environ["ANTHROPIC_API_KEY"] = self._api_key

            options = self._get_options()
            self._sdk_client = ClaudeSDKClient(options=options)
            # Enter the async context to initialize the transport
            await self._sdk_client.__aenter__()
            logger.info(f"Created SDK client for session {self.session_id}, model={self._model}")
        return self._sdk_client

    async def close(self) -> None:
        """
        Clean up SDK client resources.

        Must be called when the session ends (e.g., WebSocket disconnect).
        """
        if self._sdk_client is not None:
            try:
                await self._sdk_client.__aexit__(None, None, None)
                logger.info(f"Closed SDK client for session {self.session_id}")
            except Exception as e:
                logger.warning(f"Error closing SDK client: {e}")
            finally:
                self._sdk_client = None

    async def chat(self, message: str) -> AsyncIterator[CodingModeChunk]:
        """
        Send a message and stream the response.

        Args:
            message: User message to process

        Yields:
            CodingModeChunk objects for streaming to frontend
        """
        start_time = time.time()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0

        # Track session activity
        await self.session_manager.update_activity(self.session_id, self.user_id)

        logger.info(f"Coding mode chat: {message[:100]}...")

        try:
            # Get or create SDK client
            client = await self._ensure_client()

            # Send message to Claude
            await client.query(message)

            # Track if we've already sent content (to add separators between messages)
            has_sent_content = False

            # Stream response from Claude Agent SDK
            # Use receive_response() which terminates after ResultMessage
            # (receive_messages() never terminates - it's for interactive multi-turn sessions)
            async for sdk_message in client.receive_response():
                # Convert SDK messages to our chunk format
                async for chunk in self._convert_sdk_message(sdk_message, has_sent_content):
                    if chunk.type == "delta" and chunk.content:
                        has_sent_content = True
                    yield chunk

                # Track token usage from result message
                # Per Claude Agent SDK docs: usage is a dict with 'input_tokens' and 'output_tokens'
                # Also available: total_cost_usd for direct cost
                if isinstance(sdk_message, ResultMessage):
                    logger.info(f"[SDK DEBUG] ResultMessage received: {sdk_message}")
                    if hasattr(sdk_message, "usage") and sdk_message.usage:
                        total_input_tokens = sdk_message.usage.get("input_tokens", 0) or 0
                        total_output_tokens = sdk_message.usage.get("output_tokens", 0) or 0
                        logger.info(f"[SDK DEBUG] Token usage: input={total_input_tokens}, output={total_output_tokens}")
                    else:
                        logger.warning("[SDK DEBUG] ResultMessage has no 'usage' attribute or it's empty")
                    if hasattr(sdk_message, "total_cost_usd"):
                        total_cost_usd = sdk_message.total_cost_usd or 0.0
                        logger.info(f"[SDK DEBUG] Total cost: ${total_cost_usd:.4f}")
                    else:
                        logger.warning("[SDK DEBUG] ResultMessage has no 'total_cost_usd' attribute")

            # Send done chunk with metrics
            duration_ms = int((time.time() - start_time) * 1000)
            yield CodingModeChunk(
                type="done",
                session_id=self.session_id,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=total_cost_usd if total_cost_usd > 0 else None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Error in coding mode chat: {e}")
            yield CodingModeChunk(
                type="error",
                error_message=str(e),
            )

    async def _convert_sdk_message(
        self, sdk_message: Any, has_prior_content: bool = False
    ) -> AsyncIterator[CodingModeChunk]:
        """
        Convert Claude Agent SDK message to our chunk format.

        Maps SDK types to ChatStreamChunk-compatible format for frontend reuse.

        Args:
            sdk_message: Message from Claude Agent SDK
            has_prior_content: Whether we've already sent content (for separators)
        """
        # Debug logging to understand SDK message structure
        logger.info(f"[SDK DEBUG] Message received: {type(sdk_message).__name__}")

        if isinstance(sdk_message, AssistantMessage):
            logger.info(f"[SDK DEBUG] AssistantMessage has {len(sdk_message.content)} content blocks")
            is_first_text_in_message = True
            for i, block in enumerate(sdk_message.content):
                block_type = type(block).__name__
                logger.info(f"[SDK DEBUG]   Block {i}: {block_type}")
                if isinstance(block, TextBlock):
                    content = block.text
                    # Debug: Log text content and check for XML tool calls
                    preview = content[:200] if len(content) > 200 else content
                    logger.info(f"[SDK DEBUG]     TextBlock preview: {preview!r}")
                    if "<function_calls>" in content or "<invoke" in content:
                        logger.warning("[SDK DEBUG]     ⚠️ XML tool call detected in TextBlock! SDK may not be executing tools properly.")
                    # Add separator if this is continuation of prior content
                    if (has_prior_content or not is_first_text_in_message) and content:
                        # Only add separator if content doesn't already start with newlines
                        if not content.startswith("\n"):
                            content = "\n\n" + content
                    is_first_text_in_message = False
                    # Text content
                    yield CodingModeChunk(
                        type="delta",
                        content=content,
                    )
                elif isinstance(block, ToolUseBlock):
                    # Debug: Log tool use details
                    logger.info(f"[SDK DEBUG]     ToolUseBlock: name={block.name}, id={block.id}")
                    logger.info(f"[SDK DEBUG]     ToolUseBlock input: {block.input}")
                    # Tool being called - use nested ToolCall object for frontend compatibility
                    yield CodingModeChunk(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        ),
                    )
                elif isinstance(block, ToolResultBlock):
                    # Tool result - SDK executed the tool and returned the result
                    tool_use_id = getattr(block, "tool_use_id", None)
                    logger.info(f"[SDK DEBUG]     ToolResultBlock: tool_use_id={tool_use_id}")
                    result_content = block.content
                    if isinstance(result_content, list):
                        # Extract text from content blocks
                        text_parts = []
                        for item in result_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        result_content = "\n".join(text_parts)

                    tool_call_id = getattr(block, "tool_use_id", None)
                    # Use nested ToolResult object for frontend compatibility
                    yield CodingModeChunk(
                        type="tool_result",
                        tool_result=ToolResult(
                            tool_call_id=tool_call_id or "",
                            tool_name="",  # SDK doesn't provide this in result block
                            result=result_content,
                        ),
                    )

        # Handle UserMessage which contains ToolResultBlock from SDK tool execution
        elif isinstance(sdk_message, UserMessage):
            logger.info(f"[SDK DEBUG] UserMessage has {len(sdk_message.content)} content blocks")
            for i, block in enumerate(sdk_message.content):
                block_type = type(block).__name__
                logger.info(f"[SDK DEBUG]   Block {i}: {block_type}")
                if isinstance(block, ToolResultBlock):
                    # Tool result from SDK execution
                    tool_use_id = getattr(block, "tool_use_id", None)
                    is_error = getattr(block, "is_error", False)
                    logger.info(f"[SDK DEBUG]     ToolResultBlock: tool_use_id={tool_use_id}, is_error={is_error}")

                    result_content = block.content
                    if isinstance(result_content, list):
                        # Extract text from content blocks
                        text_parts = []
                        for item in result_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        result_content = "\n".join(text_parts)

                    # Yield tool_result chunk for frontend to update status
                    yield CodingModeChunk(
                        type="tool_result",
                        tool_result=ToolResult(
                            tool_call_id=tool_use_id or "",
                            tool_name="",  # SDK doesn't provide this
                            result=result_content,
                            error=str(result_content) if is_error else None,
                        ),
                    )

    async def get_session_info(self) -> dict[str, Any]:
        """Get current session information."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "workspace": str(WORKSPACE_PATH),
        }
