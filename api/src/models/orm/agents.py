"""
Agent, AgentTool, AgentDelegation, AgentRole, Conversation, and Message ORM models.

Represents AI agents, their tool/delegation relationships, and chat conversations.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import AgentAccessLevel, MessageRole
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.ai_usage import AIUsage
    from src.models.orm.organizations import Organization
    from src.models.orm.users import Role, User
    from src.models.orm.workflows import Workflow


class Agent(Base):
    """Agent database table."""

    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list] = mapped_column(JSONB, default=["chat"])
    access_level: Mapped[AgentAccessLevel] = mapped_column(
        SQLAlchemyEnum(
            AgentAccessLevel,
            name="agent_access_level",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AgentAccessLevel.ROLE_BASED,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_coding_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), default=None)
    # Knowledge namespaces this agent can search (RAG)
    knowledge_sources: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default='{}'
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    organization: Mapped["Organization | None"] = relationship(back_populates="agents")
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    # Tools via junction table
    tools: Mapped[list["Workflow"]] = relationship(
        secondary="agent_tools",
        back_populates="agents",
    )
    # Delegations (agents this agent can delegate to)
    delegated_agents: Mapped[list["Agent"]] = relationship(
        secondary="agent_delegations",
        primaryjoin="Agent.id == agent_delegations.c.parent_agent_id",
        secondaryjoin="Agent.id == agent_delegations.c.child_agent_id",
        backref="parent_agents",
    )
    # Roles via junction table
    roles: Mapped[list["Role"]] = relationship(
        secondary="agent_roles",
        back_populates="agents",
    )

    __table_args__ = (
        Index(
            "ix_agents_file_path_unique",
            "file_path",
            unique=True,
            postgresql_where=text("file_path IS NOT NULL"),
        ),
        Index("ix_agents_organization_id", "organization_id"),
        Index("ix_agents_is_active", "is_active"),
    )


class AgentTool(Base):
    """Agent-Tool (Workflow) association table."""

    __tablename__ = "agent_tools"

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True
    )


class AgentDelegation(Base):
    """Agent-to-Agent delegation association table."""

    __tablename__ = "agent_delegations"

    parent_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    child_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )


class AgentRole(Base):
    """Agent-Role association table."""

    __tablename__ = "agent_roles"

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[str] = mapped_column(String(255))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )


class Conversation(Base):
    """Conversation database table."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), default="chat")
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    extra_data: Mapped[dict] = mapped_column(JSONB, default={})  # Channel-specific metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    agent: Mapped["Agent | None"] = relationship(back_populates="conversations")
    user: Mapped["User"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sequence",
    )
    ai_usages: Mapped[list["AIUsage"]] = relationship(back_populates="conversation")

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_agent_id", "agent_id"),
        Index("ix_conversations_created_at", "created_at"),
    )


class Message(Base):
    """Message database table."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        SQLAlchemyEnum(
            MessageRole,
            name="message_role",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    content: Mapped[str | None] = mapped_column(Text, default=None)
    # For assistant messages requesting tool calls: [{id, name, arguments}]
    tool_calls: Mapped[list | None] = mapped_column(JSONB, default=None)
    # For tool result messages - which tool call this responds to
    tool_call_id: Mapped[str | None] = mapped_column(String(255), default=None)
    tool_name: Mapped[str | None] = mapped_column(String(255), default=None)
    # Execution ID for fetching logs from tool executions
    execution_id: Mapped[str | None] = mapped_column(String(36), default=None)
    # Token usage metrics
    token_count_input: Mapped[int | None] = mapped_column(Integer, default=None)
    token_count_output: Mapped[int | None] = mapped_column(Integer, default=None)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # Order within conversation
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_sequence", "conversation_id", "sequence"),
    )
