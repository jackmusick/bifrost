"""
Coding Agent RabbitMQ Consumer

Consumes chat requests from RabbitMQ queue, processes with Claude SDK,
and streams response chunks back via RabbitMQ exchange.
"""

import logging
from typing import Any

from src.jobs.rabbitmq import BaseConsumer
from src.coding_agent.handler import CodingAgentHandler

logger = logging.getLogger(__name__)

# Queue name for coding agent requests
CODING_AGENT_QUEUE = "coding-agent-requests"


class CodingAgentConsumer(BaseConsumer):
    """
    RabbitMQ consumer for coding agent chat requests.

    Receives chat messages from API, processes with Claude SDK,
    streams responses back via exchange.

    Uses prefetch_count=1 because SDK processing is blocking and
    can take significant time (20-30s init + response generation).
    """

    def __init__(self):
        super().__init__(
            queue_name=CODING_AGENT_QUEUE,
            prefetch_count=1,  # One message at a time - SDK is blocking
        )
        self._handler = CodingAgentHandler()

    async def process_message(self, body: dict[str, Any]) -> None:
        """
        Process a coding agent request.

        Expected message format:
        {
            "type": "chat",
            "session_id": "uuid",
            "conversation_id": "uuid",
            "message": "User message text",
            "context": {
                "user_id": "uuid",
                "user_email": "user@example.com",
                "user_name": "John Doe",
                "org_id": "uuid",
                "is_platform_admin": true,
                "system_tools": ["execute_workflow", "list_integrations"],
                "knowledge_sources": ["docs"],
                "model": "claude-sonnet-4-20250514",
            }
        }
        """
        message_type = body.get("type")

        if message_type == "chat":
            await self._handle_chat(body)
        elif message_type == "disconnect":
            await self._handle_disconnect(body)
        else:
            logger.warning(f"Unknown message type: {message_type}")

    async def _handle_chat(self, body: dict[str, Any]) -> None:
        """Handle a chat message request."""
        session_id = body.get("session_id")
        conversation_id = body.get("conversation_id")
        message = body.get("message")
        context = body.get("context", {})

        if not all([session_id, conversation_id, message]):
            logger.error("Invalid chat message: missing required fields")
            return

        logger.info(
            f"Processing chat request for session {session_id}, "
            f"conversation {conversation_id}"
        )

        try:
            # Process with SDK and stream responses
            await self._handler.process_chat(
                session_id=session_id,
                conversation_id=conversation_id,
                message=message,
                context=context,
            )
        except Exception as e:
            logger.error(f"Error processing chat: {e}", exc_info=True)
            # Handler will have already published error chunk if possible
            raise

    async def _handle_disconnect(self, body: dict[str, Any]) -> None:
        """Handle a disconnect request (cleanup SDK client)."""
        session_id = body.get("session_id")

        if not session_id:
            logger.warning("Disconnect message missing session_id")
            return

        logger.info(f"Handling disconnect for session {session_id}")
        await self._handler.cleanup_session(session_id)
