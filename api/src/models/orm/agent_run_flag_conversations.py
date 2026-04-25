"""Per-flag tuning conversation log.

One row per flagged ``AgentRun`` (1:1, enforced by a unique constraint on
``run_id``). The ``messages`` column is an ordered list of polymorphic turn
dicts (user / assistant / proposal / dryrun); see
``src.models.contracts.agent_run_flag_conversations`` for the typed
contracts.
"""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class AgentRunFlagConversation(Base):
    __tablename__ = "agent_run_flag_conversations"

    id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    messages: Mapped[list[dict]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
