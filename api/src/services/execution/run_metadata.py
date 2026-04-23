"""Helpers for agent-emitted metadata on runs.

Provides a thin async helper that lets a tool author (or future SDK surface)
attach a small dict of string-valued metadata to an ``AgentRun`` row. The
caps protect the row from a misbehaving agent dumping arbitrary blobs into
the JSONB column: at most ``MAX_KEYS`` entries, with each key truncated to
``MAX_KEY_LEN`` characters and each value to ``MAX_VALUE_LEN``.

The DB column is named ``metadata`` but the Python attribute is
``run_metadata`` (``DeclarativeBase.metadata`` is reserved by SQLAlchemy);
see :class:`src.models.orm.agent_runs.AgentRun`.
"""
from typing import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.orm.agent_runs import AgentRun


class TooManyMetadataKeys(ValueError):
    """Raised when an agent attempts to set more than ``MAX_KEYS`` metadata entries."""


MAX_KEYS = 16
MAX_KEY_LEN = 64
MAX_VALUE_LEN = 256


async def set_run_metadata(
    run_id: UUID,
    metadata: Mapping[str, str],
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Replace a run's metadata dict.

    Validates the key-count cap and truncates over-long keys/values. Commits
    the change in its own session so the helper can be called from a tool
    context that does not own the request session.
    """
    if len(metadata) > MAX_KEYS:
        raise TooManyMetadataKeys(
            f"Maximum {MAX_KEYS} metadata keys (got {len(metadata)})"
        )
    cleaned = {
        str(k)[:MAX_KEY_LEN]: str(v)[:MAX_VALUE_LEN]
        for k, v in metadata.items()
    }
    async with session_factory() as db:
        run = (
            await db.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one()
        # Python attribute; DB column is ``metadata``.
        run.run_metadata = cleaned
        await db.commit()
