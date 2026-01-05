"""
Application, AppPage, and AppComponent ORM models.

Represents applications for the App Builder with:
- applications: metadata, navigation, permissions
- app_pages: one row per page (draft and live as separate rows)
- app_components: one row per component with parent_id for tree structure
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.enums import AppAccessLevel
from src.models.orm.base import Base

if TYPE_CHECKING:
    from src.models.orm.app_roles import AppRole
    from src.models.orm.organizations import Organization
    from src.models.orm.tables import Table
    from src.models.orm.workflows import Workflow


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

    # Versioning
    live_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    draft_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # App-level config (small JSONB)
    navigation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    global_data_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    global_variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Access control (follows same pattern as forms)
    access_level: Mapped[str] = mapped_column(
        String(20), default=AppAccessLevel.AUTHENTICATED, server_default="'authenticated'"
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


class AppPage(Base):
    """Page entity for App Builder.

    Each page has its own row for draft and live versions (is_draft flag).
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
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

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
    permission: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    page_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Root layout config
    root_layout_type: Mapped[str] = mapped_column(
        String(20), default="column", server_default="'column'"
    )
    root_layout_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
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
    application: Mapped["Application"] = relationship("Application", back_populates="pages")
    launch_workflow: Mapped["Workflow | None"] = relationship("Workflow")
    components: Mapped[list["AppComponent"]] = relationship(
        "AppComponent", back_populates="page", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_app_pages_application_id", "application_id"),
        Index("ix_app_pages_application_draft", "application_id", "is_draft"),
        Index("ix_app_pages_unique", "application_id", "page_id", "is_draft", unique=True),
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
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
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
        Index("ix_app_components_page_draft", "page_id", "is_draft"),
        Index("ix_app_components_parent_order", "parent_id", "component_order"),
        Index("ix_app_components_unique", "page_id", "component_id", "is_draft", unique=True),
    )

    @property
    def is_layout(self) -> bool:
        """Check if this component is a layout container."""
        return self.type in ("row", "column", "grid")
