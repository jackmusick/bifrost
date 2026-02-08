"""
KnowledgeSource and KnowledgeSourceRole ORM models.

Represents first-class knowledge source entities with role-based access control,
following the same pattern as WorkflowRole, AgentRole, FormRole.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.organizations import Organization
    from src.models.orm.users import Role


class KnowledgeSource(Base):
    """Knowledge source entity — a named, scoped knowledge namespace."""

    __tablename__ = "knowledge_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    access_level: Mapped[str] = mapped_column(
        ENUM("authenticated", "role_based", name="knowledge_source_access_level", create_type=False),
        default="role_based",
        server_default="role_based",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    document_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    organization: Mapped["Organization | None"] = relationship()
    roles: Mapped[list["Role"]] = relationship(
        secondary="knowledge_source_roles",
    )

    __table_args__ = (
        Index("ix_knowledge_sources_organization_id", "organization_id"),
        Index("ix_knowledge_sources_namespace_org", "namespace", "organization_id", unique=True),
    )

    @property
    def role_ids(self) -> list[str]:
        return [str(r.id) for r in self.roles]


class KnowledgeSourceRole(Base):
    """Knowledge source to role junction table."""

    __tablename__ = "knowledge_source_roles"

    knowledge_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_knowledge_source_roles_role_id", "role_id"),
    )
