"""Per-flag tuning conversation service.

Owns the assistant-side of the multi-turn tuning chat that hangs off a
flagged AgentRun: appends the user's turn, calls the configured tuning
model with the run + history context, and persists the assistant reply.

This module exposes:
- ``append_user_message_and_reply(run_id, content, db)``: implemented in
  **Task 15**.
- ``enqueue_tune_chat(run_id, content)``: thin RabbitMQ publish helper used
  by the API router that accepts a new user message; the worker consumes
  the message and invokes ``append_user_message_and_reply``.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.jobs.rabbitmq import publish_message

TUNE_CHAT_QUEUE = "agent-tuning-chat"


async def append_user_message_and_reply(
    run_id: UUID, content: str, db: AsyncSession
) -> None:
    """Append a user turn + generate and persist the assistant reply.

    Implementation lands in Task 15.
    """
    raise NotImplementedError("append_user_message_and_reply implemented in Task 15")


async def enqueue_tune_chat(run_id: UUID, content: str) -> None:
    """Publish a tune-chat message for the agent-tuning-chat worker."""
    await publish_message(
        TUNE_CHAT_QUEUE, {"run_id": str(run_id), "content": content}
    )
