"""
Application ORM model.

Represents applications for the App Builder with draft/live versioning.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.organizations import Organization
    from src.models.orm.tables import Table


class Application(Base):
    """Application entity for App Builder.

    Applications hold app definitions with draft/live versioning.
    - organization_id = NULL: Global application (platform-wide)
    - organization_id = UUID: Organization-scoped application

    The definition contains the complete app structure (pages, components, etc.)
    stored as JSONB for flexibility.
    """

    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )

    # Versioning
    live_definition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    draft_definition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    live_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    draft_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    version_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)

    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="applications"
    )
    tables: Mapped[list["Table"]] = relationship(
        "Table", back_populates="application"
    )

    __table_args__ = (
        Index("ix_applications_organization_id", "organization_id"),
        # Partial unique indexes handled in migration
    )

    @property
    def is_published(self) -> bool:
        """Check if the application has been published at least once."""
        return self.live_version > 0

    @property
    def has_unpublished_changes(self) -> bool:
        """Check if there are unpublished changes in the draft."""
        return self.draft_version > self.live_version
