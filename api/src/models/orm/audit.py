"""
AuditLog ORM model.

Represents audit logs for tracking user actions.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.orm.base import Base


class AuditLog(Base):
    """Audit log for tracking user actions."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(100), default=None)
    resource_id: Mapped[UUID | None] = mapped_column(default=None)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_audit_logs_org_time", "organization_id", "created_at"),
        Index("ix_audit_logs_user", "user_id"),
    )
