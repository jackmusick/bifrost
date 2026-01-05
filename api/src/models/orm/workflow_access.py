"""
WorkflowAccess ORM model.

Precomputed table for fast execution authorization lookups.
Populated at mutation time (form create/update, app publish) - NOT execution time.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.organizations import Organization


class WorkflowAccess(Base):
    """
    Precomputed workflow access table for fast authorization lookups.

    This table is populated when forms/apps are created or updated,
    allowing O(1) execution authorization checks instead of JSONB traversal.

    Security boundary: Only API endpoints update this table.
    File sync/import NEVER sets permissions (even if files contain access_level).
    """

    __tablename__ = "workflow_access"

    # Composite primary key
    workflow_id: Mapped[UUID] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity_id: Mapped[UUID] = mapped_column(primary_key=True)

    # Access control
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    organization: Mapped["Organization | None"] = relationship()

    __table_args__ = (
        # Index for fast execution lookups
        Index("ix_workflow_access_lookup", "workflow_id", "organization_id"),
        # Index for entity cleanup (delete all access for a form/app)
        Index("ix_workflow_access_entity", "entity_type", "entity_id"),
    )
