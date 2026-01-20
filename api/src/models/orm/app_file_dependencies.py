"""
App File Dependencies ORM model.

Tracks dependencies between app files and other entities (workflows, forms, data providers).
Dependencies are extracted by parsing source code for patterns like useWorkflow('uuid').

These are NOT foreign key relationships - they're an index of what entities are referenced
in app code. This allows:
- Fast lookups for entity management ("what apps use this workflow?")
- Dangling references (referenced entity was deleted)
- Import/export without constraint violations
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.applications import AppFile


class AppFileDependency(Base):
    """
    Tracks a dependency from an app file to another entity.

    The dependency_id is NOT a foreign key - it's just a UUID that we
    extracted from the source code. The referenced entity may or may not exist.
    """

    __tablename__ = "app_file_dependencies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # FK to the app file - cascade delete when file is deleted
    app_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_files.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Type of dependency: "workflow", "form", "data_provider"
    dependency_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # The referenced entity's UUID (NOT a FK - may reference non-existent entity)
    dependency_id: Mapped[UUID] = mapped_column(nullable=False)

    # When this dependency was detected
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
    )

    # Relationship back to the file
    app_file: Mapped["AppFile"] = relationship(  # noqa: F821
        "AppFile",
        back_populates="dependencies",
    )

    __table_args__ = (
        # Fast lookup: "what dependencies does this file have?"
        Index("ix_app_file_dep_file_id", "app_file_id"),
        # Fast lookup: "what files reference this entity?"
        Index("ix_app_file_dep_target", "dependency_type", "dependency_id"),
        # Prevent duplicate entries for same file + type + id
        Index(
            "ix_app_file_dep_unique",
            "app_file_id",
            "dependency_type",
            "dependency_id",
            unique=True,
        ),
    )
