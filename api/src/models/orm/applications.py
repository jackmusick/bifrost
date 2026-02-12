"""
Application, AppVersion, and AppFile ORM models.

Represents applications with:
- applications: metadata, access control
- app_versions: version snapshots (active = live, draft = current work)
- app_files: source code files for apps
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import AppAccessLevel
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.app_file_dependencies import AppFileDependency
    from src.models.orm.app_roles import AppRole
    from src.models.orm.organizations import Organization
    from src.models.orm.tables import Table


class AppVersion(Base):
    """Version snapshot for an application.

    Each version represents a point-in-time snapshot of the application.
    - active_version: The currently published/live version
    - draft_version: The current work-in-progress version
    """

    __tablename__ = "app_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )

    # Relationships
    files: Mapped[list["AppFile"]] = relationship(
        "AppFile",
        back_populates="version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_app_versions_application_id", "application_id"),
    )


class Application(Base):
    """Application entity for App Builder.

    Applications hold app metadata with files in app_files table.
    - organization_id = NULL: Global application (platform-wide)
    - organization_id = UUID: Organization-scoped application
    """

    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )

    # Version pointers
    active_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_versions.id", ondelete="SET NULL", use_alter=True),
        default=None,
    )
    draft_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_versions.id", ondelete="SET NULL", use_alter=True),
        default=None,
    )

    # Publish history
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Published snapshot: {path: content_hash} mapping from file_index
    # NULL = never published, empty dict = published with no files
    published_snapshot: Mapped[dict | None] = mapped_column(
        JSON, default=None, nullable=True
    )

    # Access control (follows same pattern as forms)
    access_level: Mapped[str] = mapped_column(
        String(20), default=AppAccessLevel.AUTHENTICATED, server_default="'authenticated'"
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, default=None)
    icon: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[str | None] = mapped_column(String(255), default=None)

    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="applications"
    )
    tables: Mapped[list["Table"]] = relationship("Table", back_populates="application")
    roles: Mapped[list["AppRole"]] = relationship(
        "AppRole", cascade="all, delete-orphan", passive_deletes=True
    )
    versions: Mapped[list["AppVersion"]] = relationship(
        "AppVersion",
        cascade="all, delete-orphan",
        foreign_keys="AppVersion.application_id",
    )
    active_version: Mapped["AppVersion | None"] = relationship(
        "AppVersion",
        foreign_keys=[active_version_id],
        post_update=True,
    )
    draft_version_ref: Mapped["AppVersion | None"] = relationship(
        "AppVersion",
        foreign_keys=[draft_version_id],
        post_update=True,
    )

    __table_args__ = (
        Index("ix_applications_organization_id", "organization_id"),
        # Partial unique indexes handled in migration
    )

    @property
    def is_published(self) -> bool:
        """Check if the application has been published at least once."""
        return self.active_version_id is not None

    @property
    def has_unpublished_changes(self) -> bool:
        """Check if there are unpublished changes in the draft."""
        if self.draft_version_id is None:
            return False
        if self.active_version_id is None:
            return True  # Never published, so draft has changes
        return self.draft_version_id != self.active_version_id


class AppFile(Base):
    """Source code file for apps.

    Each file belongs to a version (via app_version_id).
    Path is the unique identifier within a version (e.g., "pages/clients/[id].tsx").
    """

    __tablename__ = "app_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    app_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_versions.id", ondelete="CASCADE"), nullable=False
    )

    # Identity (path is the key within a version)
    path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Content
    source: Mapped[str] = mapped_column(Text, nullable=False)  # Original source code
    compiled: Mapped[str | None] = mapped_column(Text, default=None)  # Compiled output

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    version: Mapped["AppVersion"] = relationship("AppVersion", back_populates="files")
    dependencies: Mapped[list["AppFileDependency"]] = relationship(
        "AppFileDependency",
        back_populates="app_file",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_app_files_version", "app_version_id"),
        Index("ix_app_files_path", "app_version_id", "path", unique=True),
    )
