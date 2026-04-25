"""Agent prompt change history."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class AgentPromptHistory(Base):
    __tablename__ = "agent_prompt_history"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_prompt: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    new_prompt: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    changed_by: Mapped[UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    tuning_session_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
