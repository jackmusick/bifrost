"""
Coding Agent Handler

Orchestrates Claude Agent SDK and publishes response chunks to RabbitMQ.
Manages SDK client lifecycle per session.
"""

import logging
from typing import Any
from uuid import UUID

from src.core.database import get_db_context
from src.jobs.rabbitmq import publish_to_exchange
from src.services.coding_mode.client import CodingModeClient
from src.services.llm.factory import get_coding_mode_config

logger = logging.getLogger(__name__)


def get_response_exchange(session_id: str) -> str:
    """Get the exchange name for a session's response stream."""
    return f"coding.responses.{session_id}"


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
        exchange_name = get_response_exchange(session_id)

        try:
            # Get or create SDK client for this session
            client = await self._get_or_create_client(session_id, context)

            # Stream response from SDK
            async for chunk in client.chat(message):
                # Convert chunk to dict and add session info
                chunk_data = chunk.model_dump(exclude_none=True)
                chunk_data["session_id"] = session_id
                chunk_data["conversation_id"] = conversation_id

                # Publish to exchange for API to consume
                await publish_to_exchange(exchange_name, chunk_data)

                logger.debug(f"Published chunk type={chunk.type} to {exchange_name}")

        except Exception as e:
            logger.error(f"Error in chat processing: {e}", exc_info=True)

            # Publish error chunk so API knows something went wrong
            error_chunk = {
                "type": "error",
                "session_id": session_id,
                "conversation_id": conversation_id,
                "error_message": str(e),
            }
            await publish_to_exchange(exchange_name, error_chunk)

            # Re-raise to trigger DLQ if this was a systemic failure
            raise

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
        # Use model from context (API sends it), fall back to config
        model = context.get("model") or coding_config.model

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
        )

        self._clients[session_id] = client
        logger.info(f"Created new SDK client for session {session_id}")

        return client

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

    async def cleanup_all(self) -> None:
        """Clean up all SDK clients (called on shutdown)."""
        for session_id in list(self._clients.keys()):
            await self.cleanup_session(session_id)
