"""
Application, AppVersion, AppPage, AppComponent, and AppCodeFile ORM models.

Represents applications for the App Builder with:
- applications: metadata, navigation, permissions, engine type
- app_versions: version snapshots (active = live, draft = current work)
- app_pages: one row per page, linked to a version (components engine)
- app_components: one row per component with parent_id for tree structure (components engine)
- app_code_files: source code files for code engine apps
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import AppAccessLevel, AppEngine
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.app_roles import AppRole
    from src.models.orm.organizations import Organization
    from src.models.orm.tables import Table
    from src.models.orm.workflows import Workflow


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
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )

    # Relationships
    pages: Mapped[list["AppPage"]] = relationship(
        "AppPage",
        back_populates="version_ref",
        cascade="all, delete-orphan",
        foreign_keys="AppPage.version_id",
    )
    code_files: Mapped[list["AppCodeFile"]] = relationship(
        "AppCodeFile",
        back_populates="version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_app_versions_application_id", "application_id"),
    )


class Application(Base):
    """Application entity for App Builder.

    Applications hold app metadata with pages and components in separate tables.
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
    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # App-level config (small JSONB)
    navigation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Access control (follows same pattern as forms)
    access_level: Mapped[str] = mapped_column(
        String(20), default=AppAccessLevel.AUTHENTICATED, server_default="'authenticated'"
    )

    # Engine type: 'components' (v1 JSON tree) or 'jsx' (v2 file-based)
    engine: Mapped[str] = mapped_column(
        String(20), default=AppEngine.COMPONENTS, server_default="'components'"
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
    tables: Mapped[list["Table"]] = relationship("Table", back_populates="application")
    pages: Mapped[list["AppPage"]] = relationship(
        "AppPage", back_populates="application", cascade="all, delete-orphan"
    )
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


class AppPage(Base):
    """Page entity for App Builder.

    Each page belongs to a version (via version_id).
    Components are stored in the app_components table with parent_id references.
    """

    __tablename__ = "app_pages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "dashboard"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "/"

    # Version link: each page belongs to a specific version
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_versions.id", ondelete="CASCADE"), nullable=False
    )

    # Page-level config
    data_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    launch_workflow_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), default=None
    )
    launch_workflow_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    launch_workflow_data_source_id: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    permission: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    page_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Layout options
    fill_height: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Timestamps
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
    application: Mapped["Application"] = relationship("Application", back_populates="pages")
    launch_workflow: Mapped["Workflow | None"] = relationship("Workflow")
    components: Mapped[list["AppComponent"]] = relationship(
        "AppComponent", back_populates="page", cascade="all, delete-orphan"
    )
    version_ref: Mapped["AppVersion | None"] = relationship(
        "AppVersion", back_populates="pages", foreign_keys=[version_id]
    )

    __table_args__ = (
        Index("ix_app_pages_application_id", "application_id"),
        Index("ix_app_pages_version_id", "version_id"),
        Index("ix_app_pages_app_page_version", "application_id", "page_id", "version_id", unique=True),
    )


class AppComponent(Base):
    """Component entity for App Builder.

    Each component (including layout containers like row/column/grid) is a row.
    Tree structure is maintained via parent_id references.
    """

    __tablename__ = "app_components"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    page_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_pages.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "btn_submit"
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_components.id", ondelete="CASCADE"), default=None
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # "button", "row", etc.
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    component_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Common fields promoted to columns
    visible: Mapped[str | None] = mapped_column(Text, default=None)
    width: Mapped[str | None] = mapped_column(String(20), default=None)
    loading_workflows: Mapped[list[str] | None] = mapped_column(
        JSONB, default=None, server_default="[]"
    )

    # Timestamps
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
    page: Mapped["AppPage"] = relationship("AppPage", back_populates="components")
    parent: Mapped["AppComponent | None"] = relationship(
        "AppComponent", remote_side=[id], backref="children"
    )

    __table_args__ = (
        Index("ix_app_components_page_id", "page_id"),
        Index("ix_app_components_parent_order", "parent_id", "component_order"),
        Index("ix_app_components_page_component_unique", "page_id", "component_id", unique=True),
    )

    @property
    def is_layout(self) -> bool:
        """Check if this component is a layout container."""
        return self.type in ("row", "column", "grid")


class AppCodeFile(Base):
    """Source code file for code engine apps.

    Each file belongs to a version (via app_version_id).
    Path is the unique identifier within a version (e.g., "pages/clients/[id]").
    """

    __tablename__ = "app_code_files"

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
        DateTime, default=datetime.utcnow, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    version: Mapped["AppVersion"] = relationship("AppVersion", back_populates="code_files")

    __table_args__ = (
        Index("ix_code_files_version", "app_version_id"),
        Index("ix_code_files_path", "app_version_id", "path", unique=True),
    )
