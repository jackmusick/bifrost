"""Post-run summarization — populates asked/did/confidence/metadata on an AgentRun.

This module owns:
- ``summarize_run(run_id, session_factory)``: load the completed run, render the
  conversation, ask the configured summarization model, and persist the parsed
  result onto ``AgentRun`` (asked/did/confidence/run_metadata/summary_status).
  Implemented in **Task 12**.
- ``enqueue_summarize(run_id)``: thin RabbitMQ publish helper used by the
  agent-runs consumer once a run finishes. Lives here (not in the worker
  module) so callers don't have to import worker code.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.jobs.rabbitmq import publish_message

SUMMARIZE_QUEUE = "agent-summarization"


async def summarize_run(
    run_id: UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Generate and persist a summary for a completed AgentRun.

    Implementation lands in Task 12.
    """
    raise NotImplementedError("summarize_run implemented in Task 12")


async def enqueue_summarize(run_id: UUID) -> None:
    """Publish a summarize message for the agent-summarization worker."""
    await publish_message(SUMMARIZE_QUEUE, {"run_id": str(run_id)})
