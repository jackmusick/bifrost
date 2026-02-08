"""
KnowledgeNamespaceRole ORM model.

Lightweight junction table for role-based access to knowledge namespaces.
Namespaces are derived from the knowledge_store table, not a separate entity.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.users import Role


class KnowledgeNamespaceRole(Base):
    """Maps a knowledge namespace to a role for access control."""

    __tablename__ = "knowledge_namespace_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    role: Mapped["Role"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "namespace", "organization_id", "role_id",
            name="uq_knowledge_ns_role_org",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_knowledge_namespace_roles_role_id", "role_id"),
        Index("ix_knowledge_namespace_roles_namespace", "namespace"),
    )
