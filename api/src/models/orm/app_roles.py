"""
AppRole ORM model.

Junction table for application role-based access control,
following the same pattern as FormRole.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class AppRole(Base):
    """Application-Role association table.

    Links applications to roles for role-based access control.
    Follows the same pattern as FormRole for consistency.
    """

    __tablename__ = "app_roles"

    app_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_app_roles_role_id", "role_id"),
    )
