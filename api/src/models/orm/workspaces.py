"""
Workspace ORM model.

Workspaces are first-class scoping containers for chat conversations. Every
conversation belongs to exactly one workspace. A synthetic "Personal" workspace
is auto-created per user; org/role workspaces are admin-managed.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import WorkspaceScope
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.agents import Agent, Conversation
    from src.models.orm.organizations import Organization
    from src.models.orm.users import Role, User


class Workspace(Base):
    """Workspace database table."""

    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    scope: Mapped[WorkspaceScope] = mapped_column(
        SQLAlchemyEnum(
            WorkspaceScope,
            name="workspace_scope",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )
    role_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), default=None
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None
    )
    default_agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    enabled_tool_ids: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    enabled_knowledge_source_ids: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    instructions: Mapped[str | None] = mapped_column(Text, default=None)
    default_model: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organization: Mapped["Organization | None"] = relationship(foreign_keys=[organization_id])
    role: Mapped["Role | None"] = relationship(foreign_keys=[role_id])
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])
    default_agent: Mapped["Agent | None"] = relationship(foreign_keys=[default_agent_id])
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_workspaces_organization_id", "organization_id"),
        Index("ix_workspaces_role_id", "role_id"),
        Index("ix_workspaces_user_id", "user_id"),
        Index("ix_workspaces_is_active", "is_active"),
        Index("ix_workspaces_scope", "scope"),
    )
