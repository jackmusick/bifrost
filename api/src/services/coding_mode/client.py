"""
Coding Mode Client

Wraps Claude Agent SDK for Bifrost workflow development.
Handles session management, MCP tool registration, and streaming.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from src.core.paths import CODING_AGENT_PATH
from src.models.contracts.agents import (
    AskUserQuestion,
    AskUserQuestionOption,
    ChatStreamChunk,
    TodoItem,
    ToolCall,
    ToolResult,
)
from src.models.enums import CodingModePermission
from src.services.coding_mode.prompts import get_system_prompt
from src.services.coding_mode.session import SessionManager
from src.services.mcp_server import BifrostMCPServer, MCPContext

logger = logging.getLogger(__name__)

# Claude Agent SDK is optional - will be installed when using coding mode
try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient  # type: ignore
    from claude_agent_sdk.types import (  # type: ignore
        AssistantMessage,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        StreamEvent,
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
    PermissionResultAllow = Any  # type: ignore
    PermissionResultDeny = Any  # type: ignore
    ResultMessage = Any  # type: ignore
    StreamEvent = Any  # type: ignore
    TextBlock = Any  # type: ignore
    ToolResultBlock = Any  # type: ignore
    ToolUseBlock = Any  # type: ignore
    UserMessage = Any  # type: ignore

# Coding agent scratch space - for Claude SDK's bash/file tools
# This is NOT the workspace for modules/workflows (those come from DB via MCP tools)
# This is just a local sandbox for the LLM to do file operations
WORKSPACE_PATH = CODING_AGENT_PATH

# Allowed read paths for file access (SDK source for documentation)
ALLOWED_READ_PATHS = [
    str(CODING_AGENT_PATH),       # Agent's scratch space (read/write)
    "/app/shared/bifrost_sdk",    # SDK source code (read-only docs)
    "/app/shared/workflows",      # Workflow patterns (read-only docs)
]

# Paths that can be written to
ALLOWED_WRITE_PATHS = [
    str(CODING_AGENT_PATH),       # Only the scratch space is writable
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
        permission_mode: CodingModePermission = CodingModePermission.EXECUTE,
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
            permission_mode: Permission mode for the SDK (plan or execute).
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
        self._permission_mode = permission_mode

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

        # For AskUserQuestion support
        self._pending_question: asyncio.Future[dict[str, str]] | None = None
        self._pending_request_id: str | None = None
        self._chunk_callback: Callable[[ChatStreamChunk], Awaitable[None]] | None = None

        # For streaming delta tracking (SDK sends cumulative content, we compute deltas)
        self._last_text_content: str = ""

        logger.info(
            f"Initialized CodingModeClient for user {user_email}, session {self.session_id}, mode={permission_mode.value}"
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

        # Standard file tools are always available, plus WebSearch and TodoWrite
        allowed_tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "TodoWrite"]

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
            permission_mode=self._permission_mode.value,  # Plan mode restricts writes, Execute mode auto-accepts
            env={"ANTHROPIC_API_KEY": self._api_key},  # Pass API key to SDK subprocess
            include_partial_messages=True,  # Stream events as they happen (tools, text)
            can_use_tool=self._can_use_tool,  # Handle AskUserQuestion and other permissions
        )

    def set_chunk_callback(
        self, callback: Callable[[ChatStreamChunk], Awaitable[None]]
    ) -> None:
        """
        Set callback for emitting chunks during can_use_tool.

        Used to send ask_user_question chunks to the frontend while
        the SDK is waiting for user input.
        """
        self._chunk_callback = callback

    async def _can_use_tool(
        self, tool_name: str, input_data: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        """
        Handle SDK permission requests, including AskUserQuestion.

        This callback is invoked by the SDK when it wants to use a tool
        that requires permission. For AskUserQuestion, we emit a chunk
        to the frontend and block until the user provides an answer.

        Args:
            tool_name: Name of the tool being requested
            input_data: Input parameters for the tool
            context: SDK context with abort signal (reserved for future use)

        Returns:
            PermissionResultAllow or PermissionResultDeny
        """
        # Note: context contains { signal: AbortSignal | None } for abort handling
        # Currently unused but required by SDK callback signature
        if tool_name == "AskUserQuestion":
            request_id = str(uuid4())
            self._pending_request_id = request_id
            self._pending_question = asyncio.get_event_loop().create_future()

            logger.info(f"AskUserQuestion received, request_id={request_id}")

            # Emit question chunk to frontend via callback
            if self._chunk_callback:
                questions = [
                    AskUserQuestion(
                        question=q["question"],
                        header=q["header"],
                        options=[
                            AskUserQuestionOption(
                                label=o["label"],
                                description=o.get("description", ""),
                            )
                            for o in q.get("options", [])
                        ],
                        multi_select=q.get("multiSelect", False),
                    )
                    for q in input_data.get("questions", [])
                ]
                await self._chunk_callback(
                    ChatStreamChunk(
                        type="ask_user_question",
                        request_id=request_id,
                        questions=questions,
                    )
                )
            else:
                logger.warning(
                    "AskUserQuestion received but no chunk callback set - denying"
                )
                return PermissionResultDeny(message="No UI available for questions")

            # Block here until provide_answer() is called
            try:
                answers = await self._pending_question
                logger.info(f"AskUserQuestion answered, request_id={request_id}")
            except asyncio.CancelledError:
                logger.info(f"AskUserQuestion cancelled, request_id={request_id}")
                return PermissionResultDeny(message="User cancelled")

            return PermissionResultAllow(
                updated_input={
                    "questions": input_data.get("questions"),
                    "answers": answers,
                }
            )

        # Handle TodoWrite - emit todo_update to frontend
        if tool_name == "TodoWrite":
            todos_data = input_data.get("todos", [])
            logger.info(f"TodoWrite received with {len(todos_data)} items")

            if self._chunk_callback and todos_data:
                todos = [
                    TodoItem(
                        content=t.get("content", ""),
                        status=t.get("status", "pending"),
                        active_form=t.get("activeForm", t.get("active_form", "")),
                    )
                    for t in todos_data
                ]
                await self._chunk_callback(
                    ChatStreamChunk(
                        type="todo_update",
                        todos=todos,
                    )
                )

            # Allow the tool to proceed
            return PermissionResultAllow(updated_input=input_data)

        # All other tools: allow by default
        return PermissionResultAllow(updated_input=input_data)

    async def provide_answer(
        self, request_id: str, answers: dict[str, str]
    ) -> None:
        """
        Provide user's answer to a pending AskUserQuestion.

        Unblocks the waiting can_use_tool callback with the user's answers.

        Args:
            request_id: The request_id from the ask_user_question chunk
            answers: Map of question text to selected answer label(s)
        """
        if self._pending_question and self._pending_request_id == request_id:
            if not self._pending_question.done():
                self._pending_question.set_result(answers)
                logger.info(f"Answer provided for request_id={request_id}")
            self._pending_question = None
            self._pending_request_id = None
        else:
            logger.warning(
                f"Answer received for unknown request_id={request_id} "
                f"(pending={self._pending_request_id})"
            )

    async def interrupt(self) -> None:
        """
        Interrupt the current SDK operation.

        Cancels any pending AskUserQuestion and interrupts the SDK client.
        """
        logger.info(f"Interrupting session {self.session_id}")

        # Cancel pending question first (so can_use_tool unblocks)
        if self._pending_question and not self._pending_question.done():
            self._pending_question.cancel()
        self._pending_question = None
        self._pending_request_id = None

        # Interrupt SDK client
        if self._sdk_client:
            try:
                await self._sdk_client.interrupt()
                logger.info(f"SDK client interrupted for session {self.session_id}")
            except Exception as e:
                logger.warning(f"Error interrupting SDK client: {e}")

    async def _ensure_client(self) -> Any:
        """
        Get or create SDK client with proper lifecycle management.

        The client is cached to maintain conversation context across
        multiple chat() calls within the same session.
        """
        if self._sdk_client is None:
            # Ensure the scratch space directory exists
            # This is the coding agent's local sandbox for bash/file operations
            WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured coding agent scratch space exists: {WORKSPACE_PATH}")

            # API key is passed via ClaudeAgentOptions.env to the SDK subprocess
            logger.debug(f"Using ANTHROPIC_API_KEY (key prefix: {self._api_key[:7]}...)")

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

    async def set_permission_mode(self, mode: CodingModePermission) -> None:
        """
        Change the permission mode for this session.

        This will close the existing SDK client and create a new one
        with the updated permission mode on the next chat() call.

        Args:
            mode: New permission mode (PLAN or EXECUTE)
        """
        if self._permission_mode == mode:
            logger.info(f"Permission mode already {mode.value}, no change needed")
            return

        old_mode = self._permission_mode
        self._permission_mode = mode

        # Close existing client - it will be recreated with new options on next chat()
        if self._sdk_client is not None:
            await self.close()
            logger.info("Closed SDK client to apply permission mode change")

        # Update session state
        await self.session_manager.set_permission_mode(self.session_id, mode)

        logger.info(f"Permission mode changed from {old_mode.value} to {mode.value} for session {self.session_id}")

    @property
    def permission_mode(self) -> CodingModePermission:
        """Get the current permission mode."""
        return self._permission_mode

    async def chat(self, message: str) -> AsyncIterator[ChatStreamChunk]:
        """
        Send a message and stream the response.

        Args:
            message: User message to process

        Yields:
            ChatStreamChunk objects for streaming to frontend
        """
        start_time = time.time()
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost_usd = 0.0

        # Reset delta tracking for this chat turn
        self._last_text_content = ""

        # Track session activity
        await self.session_manager.update_activity(self.session_id, self.user_id)

        logger.info(f"Coding mode chat: {message[:100]}...")

        try:
            # Get or create SDK client
            client = await self._ensure_client()

            # Send message to Claude
            await client.query(message)

            # Stream response from Claude Agent SDK
            # Use receive_response() which terminates after ResultMessage
            # (receive_messages() never terminates - it's for interactive multi-turn sessions)
            async for sdk_message in client.receive_response():
                # Convert SDK messages to our chunk format
                async for chunk in self._convert_sdk_message(sdk_message):
                    yield chunk

                # Track token usage from result message
                # Per Claude Agent SDK docs: usage is a dict with 'input_tokens' and 'output_tokens'
                # Also available: total_cost_usd for direct cost
                if isinstance(sdk_message, ResultMessage):
                    if hasattr(sdk_message, "usage") and sdk_message.usage:
                        total_input_tokens = sdk_message.usage.get("input_tokens", 0) or 0
                        total_output_tokens = sdk_message.usage.get("output_tokens", 0) or 0
                    if hasattr(sdk_message, "total_cost_usd"):
                        total_cost_usd = sdk_message.total_cost_usd or 0.0

            # Send done chunk with metrics
            duration_ms = int((time.time() - start_time) * 1000)
            yield ChatStreamChunk(
                type="done",
                session_id=self.session_id,
                token_count_input=total_input_tokens,
                token_count_output=total_output_tokens,
                cost_usd=total_cost_usd if total_cost_usd > 0 else None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception(f"Error in coding mode chat: {e}")
            yield ChatStreamChunk(
                type="error",
                error=str(e),
            )

    async def _convert_sdk_message(
        self, sdk_message: Any
    ) -> AsyncIterator[ChatStreamChunk]:
        """
        Convert Claude Agent SDK message to our chunk format.

        Handles StreamEvent for real-time streaming data. The SDK yields:
        - StreamEvent (many): Real-time text deltas, tool calls, tool results
        - AssistantMessage: Final text response only (skip, already streamed)
        - ResultMessage: Cost/usage metrics (handled in chat() method)

        Args:
            sdk_message: Message from Claude Agent SDK
        """
        # Handle StreamEvent for ALL real-time streaming data
        if HAS_CLAUDE_SDK and isinstance(sdk_message, StreamEvent):
            event = sdk_message.event
            event_type = event.get("type")

            if event_type == "message_start":
                yield ChatStreamChunk(type="assistant_message_start")

            elif event_type == "content_block_start":
                content_block = event.get("content_block", {})
                block_type = content_block.get("type")

                if block_type == "tool_use":
                    # Tool is being called
                    yield ChatStreamChunk(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=content_block.get("id", ""),
                            name=content_block.get("name", ""),
                            arguments={},  # Input comes in deltas
                        ),
                    )
                elif block_type == "tool_result":
                    # Tool has completed - emit tool_result
                    tool_use_id = content_block.get("tool_use_id", "")
                    is_error = content_block.get("is_error", False)
                    content = content_block.get("content", "")

                    # Handle content that's a list of text blocks
                    if isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        content = "\n".join(text_parts)

                    yield ChatStreamChunk(
                        type="tool_result",
                        tool_result=ToolResult(
                            tool_call_id=tool_use_id,
                            tool_name="",
                            result=content,
                            error=str(content) if is_error else None,
                        ),
                    )

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type")

                if delta_type == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield ChatStreamChunk(type="delta", content=text)
                # Note: input_json_delta for tool arguments could be handled here too

            elif event_type == "message_delta":
                # Contains stop_reason - no action needed, just consume the event
                pass

            elif event_type == "message_stop":
                yield ChatStreamChunk(
                    type="assistant_message_end",
                    stop_reason="end_turn",
                )

            return  # StreamEvent handled

        # AssistantMessage contains final content
        # Extract text from TextBlock and tool results from ToolResultBlock
        if isinstance(sdk_message, AssistantMessage):
            # Check for SDK-level errors (authentication, billing, rate limits)
            if hasattr(sdk_message, "error") and sdk_message.error:
                logger.error(f"SDK AssistantMessage error: {sdk_message.error}")
                yield ChatStreamChunk(
                    type="error",
                    error=f"Claude SDK error: {sdk_message.error}",
                )
                return

            for block in sdk_message.content:

                # Handle TextBlock - extract text content
                if isinstance(block, TextBlock):
                    if block.text:
                        yield ChatStreamChunk(type="delta", content=block.text)
                    continue

                # Handle ToolUseBlock - tool is being called
                elif isinstance(block, ToolUseBlock):
                    yield ChatStreamChunk(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        ),
                    )
                    continue

                # Handle ToolResultBlock - tool execution completed
                elif isinstance(block, ToolResultBlock):
                    tool_use_id = getattr(block, "tool_use_id", None)
                    is_error = getattr(block, "is_error", False)

                    result_content = block.content
                    if isinstance(result_content, list):
                        text_parts = []
                        for item in result_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        result_content = "\n".join(text_parts)

                    yield ChatStreamChunk(
                        type="tool_result",
                        tool_result=ToolResult(
                            tool_call_id=tool_use_id or "",
                            tool_name="",
                            result=result_content,
                            error=str(result_content) if is_error else None,
                        ),
                    )
            return

        # Handle UserMessage which contains ToolResultBlock from SDK tool execution
        elif isinstance(sdk_message, UserMessage):
            for block in sdk_message.content:
                if isinstance(block, ToolResultBlock):
                    # Tool result from SDK execution
                    tool_use_id = getattr(block, "tool_use_id", None)
                    is_error = getattr(block, "is_error", False)

                    result_content = block.content
                    if isinstance(result_content, list):
                        # Extract text from content blocks
                        text_parts = []
                        for item in result_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                        result_content = "\n".join(text_parts)

                    # Yield tool_result chunk for frontend to update status
                    yield ChatStreamChunk(
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
