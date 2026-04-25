"""Verdict change audit trail.

One immutable row per verdict change on an ``AgentRun``. Append-only:
writers insert; nobody updates or deletes (except via ON DELETE CASCADE
when the parent run is removed).
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class AgentRunVerdictHistory(Base):
    __tablename__ = "agent_run_verdict_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    changed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    __table_args__ = (Index("ix_verdict_history_run_id", "run_id"),)
