"""
Coding Agent Handler

Orchestrates Claude Agent SDK and publishes response chunks to RabbitMQ.
Manages SDK client lifecycle per session.
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from src.core.database import get_db_context
from src.jobs.rabbitmq import consume_from_exchange, publish_to_exchange
from src.models.contracts.agents import ChatStreamChunk
from src.models.enums import CodingModePermission
from src.services.coding_mode.client import CodingModeClient
from src.services.llm.factory import get_coding_mode_config

logger = logging.getLogger(__name__)


def get_response_exchange(session_id: str) -> str:
    """Get the exchange name for a session's response stream."""
    return f"coding.responses.{session_id}"


def get_answer_exchange(session_id: str) -> str:
    """Get the exchange name for receiving answers from the API."""
    return f"coding.answers.{session_id}"


class CodingAgentHandler:
    """
    Handles coding agent chat requests.

    Manages SDK client instances per session and streams responses
    to RabbitMQ exchanges for the API to consume.
    """

    def __init__(self):
        # Cache of SDK clients by session_id for conversation continuity
        self._clients: dict[str, CodingModeClient] = {}

    async def process_chat(
        self,
        session_id: str,
        conversation_id: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        """
        Process a chat message and stream responses to RabbitMQ.

        Supports bidirectional messaging for AskUserQuestion:
        - Publishes chunks (including ask_user_question) to response exchange
        - Listens for answers/stop commands on answer exchange

        Args:
            session_id: Unique session identifier
            conversation_id: Conversation ID for message persistence
            message: User message text
            context: User context including:
                - user_id, user_email, user_name
                - org_id, is_platform_admin
                - system_tools, knowledge_sources
                - model
        """
        response_exchange = get_response_exchange(session_id)
        answer_exchange = get_answer_exchange(session_id)

        # Get or create SDK client for this session
        client = await self._get_or_create_client(session_id, context)

        # Helper to publish chunks to RabbitMQ
        async def publish_chunk(chunk: ChatStreamChunk) -> None:
            chunk_data = chunk.model_dump(exclude_none=True)
            chunk_data["session_id"] = session_id
            chunk_data["conversation_id"] = conversation_id
            logger.info(f"[HANDLER] Publishing chunk type={chunk.type} to {response_exchange}")
            await publish_to_exchange(response_exchange, chunk_data)
            # Use INFO for tool_result to trace the flow
            if chunk.type == "tool_result":
                tool_call_id = chunk.tool_result.tool_call_id if chunk.tool_result else "none"
                logger.info(f"[HANDLER] Published tool_result chunk: tool_call_id={tool_call_id}")

        # Set up chunk callback for AskUserQuestion
        client.set_chunk_callback(publish_chunk)

        # Background task to listen for answers/stop commands
        answer_task: asyncio.Task[None] | None = None
        stop_event = asyncio.Event()

        async def answer_listener() -> None:
            """Listen for answers and stop commands from the API."""
            try:
                async for msg in consume_from_exchange(answer_exchange, timeout=600.0):
                    msg_type = msg.get("type")
                    logger.debug(f"Received answer exchange message: {msg_type}")

                    if msg_type == "answer":
                        # Forward answer to client
                        request_id = msg.get("request_id", "")
                        answers = msg.get("answers", {})
                        await client.provide_answer(request_id, answers)

                    elif msg_type == "stop":
                        # Interrupt the SDK
                        logger.info(f"Stop command received for session {session_id}")
                        await client.interrupt()
                        stop_event.set()
                        break

            except asyncio.CancelledError:
                logger.debug(f"Answer listener cancelled for session {session_id}")
            except Exception as e:
                logger.warning(f"Answer listener error: {e}")

        try:
            # Start answer listener in background
            answer_task = asyncio.create_task(answer_listener())

            # Stream response from SDK
            async for chunk in client.chat(message):
                # Check if we've been stopped
                if stop_event.is_set():
                    logger.info(f"Chat interrupted for session {session_id}")
                    break

                # Publish regular chunks
                await publish_chunk(chunk)

        except asyncio.CancelledError:
            logger.info(f"Chat cancelled for session {session_id}")
            # Publish error chunk so frontend knows
            error_chunk = ChatStreamChunk(
                type="error",
                error="Chat was cancelled",
            )
            await publish_chunk(error_chunk)

        except Exception as e:
            logger.error(f"Error in chat processing: {e}", exc_info=True)

            # Publish error chunk so API knows something went wrong
            error_chunk = ChatStreamChunk(
                type="error",
                error=str(e),
            )
            await publish_chunk(error_chunk)

            # Re-raise to trigger DLQ if this was a systemic failure
            raise

        finally:
            # Clean up answer listener
            if answer_task and not answer_task.done():
                answer_task.cancel()
                try:
                    await answer_task
                except asyncio.CancelledError:
                    pass

    async def _get_or_create_client(
        self,
        session_id: str,
        context: dict[str, Any],
    ) -> CodingModeClient:
        """
        Get existing SDK client or create new one for session.

        Clients are cached to maintain conversation context across
        multiple messages in the same session.
        """
        if session_id in self._clients:
            logger.debug(f"Reusing existing SDK client for session {session_id}")
            return self._clients[session_id]

        # Get API key and model from database (same as API does)
        async with get_db_context() as db:
            coding_config = await get_coding_mode_config(db)

        if not coding_config:
            raise ValueError(
                "Coding mode not configured. Please configure Anthropic API key "
                "in System Settings > AI Configuration."
            )

        api_key = coding_config.api_key
        logger.info(f"Coding config: model={coding_config.model}, api_key_prefix={api_key[:10] if api_key else 'None'}...")
        # Use model from context (API sends it), fall back to config
        model = context.get("model") or coding_config.model

        # Get permission mode from context (default to EXECUTE)
        permission_mode_str = context.get("permission_mode", CodingModePermission.EXECUTE.value)
        try:
            permission_mode = CodingModePermission(permission_mode_str)
        except ValueError:
            logger.warning(f"Invalid permission_mode '{permission_mode_str}', defaulting to EXECUTE")
            permission_mode = CodingModePermission.EXECUTE

        client = CodingModeClient(
            user_id=UUID(context["user_id"]) if context.get("user_id") else None,
            user_email=context.get("user_email", "unknown@example.com"),
            user_name=context.get("user_name", "Unknown User"),
            api_key=api_key,
            model=model,
            org_id=UUID(context["org_id"]) if context.get("org_id") else None,
            is_platform_admin=context.get("is_platform_admin", False),
            session_id=session_id,
            system_tools=context.get("system_tools", []),
            knowledge_sources=context.get("knowledge_sources", []),
            permission_mode=permission_mode,
        )

        self._clients[session_id] = client
        logger.info(f"Created new SDK client for session {session_id}, mode={permission_mode.value}")

        return client

    async def interrupt_session(self, session_id: str) -> bool:
        """
        Interrupt the current SDK operation for a session.

        Args:
            session_id: Session to interrupt

        Returns:
            True if session was found and interrupted, False otherwise
        """
        if session_id in self._clients:
            client = self._clients[session_id]
            try:
                await client.interrupt()
                logger.info(f"Interrupted SDK client for session {session_id}")
                return True
            except Exception as e:
                logger.warning(f"Error interrupting SDK client: {e}")
                return False
        else:
            logger.warning(f"No client found for session {session_id} to interrupt")
            return False

    async def cleanup_session(self, session_id: str) -> None:
        """
        Clean up SDK client for a session.

        Called when user disconnects or session expires.
        """
        if session_id in self._clients:
            client = self._clients.pop(session_id)
            try:
                await client.close()
                logger.info(f"Cleaned up SDK client for session {session_id}")
            except Exception as e:
                logger.warning(f"Error cleaning up SDK client: {e}")

    async def set_permission_mode(
        self, session_id: str, permission_mode: CodingModePermission
    ) -> bool:
        """
        Change the permission mode for a session.

        This will update the SDK client's permission mode, which will
        recreate the client with the new mode on the next chat() call.

        Args:
            session_id: Session to update
            permission_mode: New permission mode (PLAN or EXECUTE)

        Returns:
            True if session was found and mode was changed, False otherwise
        """
        if session_id in self._clients:
            client = self._clients[session_id]
            await client.set_permission_mode(permission_mode)
            logger.info(f"Changed permission mode to {permission_mode.value} for session {session_id}")
            return True
        else:
            logger.warning(f"No client found for session {session_id} to change permission mode")
            return False

    def get_permission_mode(self, session_id: str) -> CodingModePermission | None:
        """
        Get the current permission mode for a session.

        Args:
            session_id: Session to query

        Returns:
            Current permission mode or None if session not found
        """
        if session_id in self._clients:
            return self._clients[session_id].permission_mode
        return None

    async def cleanup_all(self) -> None:
        """Clean up all SDK clients (called on shutdown)."""
        for session_id in list(self._clients.keys()):
            await self.cleanup_session(session_id)
