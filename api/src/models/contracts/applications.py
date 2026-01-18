"""
Application contract models for Bifrost App Builder.

Provides Pydantic models for API request/response handling.
Supports the 3-table schema: applications -> app_pages -> app_components

Type Alignment:
These models are designed to match the frontend TypeScript types exactly.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
import re

from src.models.contracts.app_components import NavigationConfig, PageDefinition, PermissionConfig

# ==================== APPLICATION MODELS ====================


class ApplicationBase(BaseModel):
    """Shared application fields."""

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Application display name",
    )
    description: str | None = Field(default=None, description="Optional application description")
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Icon identifier (e.g., 'home', 'settings', 'chart')",
    )


class ApplicationCreate(ApplicationBase):
    """Input for creating an application."""

    slug: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="URL-friendly slug (lowercase letters, numbers, hyphens)",
    )
    access_level: str = Field(
        default="authenticated",
        description="Access level: 'authenticated' (any logged-in user) or 'role_based' (specific roles)",
    )
    role_ids: list[UUID] = Field(
        default_factory=list,
        description="Role IDs for role_based access (ignored if access_level is 'authenticated')",
    )
    engine: str = Field(
        default="components",
        description="Rendering engine: 'components' (JSON tree) or 'code' (code files)",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format."""
        if not re.match(r"^[a-z][a-z0-9-]*$", v):
            raise ValueError(
                "Slug must start with a letter and contain only lowercase letters, "
                "numbers, and hyphens"
            )
        return v

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v: str) -> str:
        """Validate access_level is one of the allowed values."""
        if v not in ("authenticated", "role_based"):
            raise ValueError("access_level must be 'authenticated' or 'role_based'")
        return v

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        """Validate engine is one of the allowed values."""
        if v not in ("components", "code"):
            raise ValueError("engine must be 'components' or 'code'")
        return v


class ApplicationUpdate(BaseModel):
    """Input for updating application metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=50)
    scope: str | None = Field(
        default=None,
        description="Organization scope: 'global' for platform-wide, or org UUID string. Platform admin only.",
    )
    access_level: str | None = Field(
        default=None,
        description="Access level: 'authenticated' (any logged-in user) or 'role_based' (specific roles)",
    )
    role_ids: list[UUID] | None = Field(
        default=None,
        description="Role IDs for role_based access (replaces existing roles)",
    )
    navigation: NavigationConfig | None = Field(
        default=None,
        description="Navigation configuration (sidebar items, header settings)",
    )

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v: str | None) -> str | None:
        """Validate access_level is one of the allowed values."""
        if v is not None and v not in ("authenticated", "role_based"):
            raise ValueError("access_level must be 'authenticated' or 'role_based'")
        return v


class ApplicationPublic(ApplicationBase):
    """Application output for API responses.

    This is the unified model for both list/get operations AND export/import.
    Fields like `pages` are optional - omitted for list views, included for export.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    organization_id: UUID | None
    active_version_id: UUID | None = Field(
        default=None,
        description="ID of the currently live version (null if never published)",
    )
    draft_version_id: UUID | None = Field(
        default=None,
        description="ID of the current draft version",
    )
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    is_published: bool
    has_unpublished_changes: bool
    access_level: str = Field(default="authenticated")
    engine: str = Field(
        default="components",
        description="Rendering engine: 'components' (JSON tree) or 'code' (code files)",
    )
    role_ids: list[UUID] = Field(default_factory=list)
    navigation: NavigationConfig | None = Field(
        default=None,
        description="Navigation configuration (sidebar items, etc.)",
    )
    # Export fields - optional, only included when exporting full app
    permissions: PermissionConfig | None = Field(
        default=None,
        description="Permission configuration (included in export)",
    )
    pages: list[PageDefinition] | None = Field(
        default=None,
        description="Page definitions with nested layout/components (included in export)",
    )

    @field_serializer("created_at", "updated_at", "published_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


class ApplicationListResponse(BaseModel):
    """Response for listing applications."""

    applications: list[ApplicationPublic]
    total: int


# ==================== DEFINITION MODELS ====================


class ApplicationDefinition(BaseModel):
    """Application definition (the complete app structure)."""

    model_config = ConfigDict(from_attributes=True)

    definition: dict[str, Any] | None = Field(
        default=None,
        description="Complete application definition (pages, components, etc.)",
    )
    version: int = Field(description="Version number of this definition")
    is_live: bool = Field(description="Whether this is the live or draft version")


class ApplicationDraftSave(BaseModel):
    """Input for saving a draft definition."""

    definition: dict[str, Any] = Field(
        ...,
        description="Complete application definition to save as draft",
    )


class ApplicationPublishRequest(BaseModel):
    """Request to publish draft to live."""

    message: str | None = Field(
        default=None,
        max_length=500,
        description="Optional publish message for version history",
    )


class ApplicationRollbackRequest(BaseModel):
    """Request to rollback to a previous version."""

    version_id: UUID = Field(
        ...,
        description="UUID of the version to rollback to",
    )


# ==================== VERSION HISTORY MODELS ====================


class VersionHistoryEntry(BaseModel):
    """A single entry in the version history."""

    version: int
    definition: dict[str, Any]
    published_at: datetime
    published_by: str | None
    message: str | None

    @field_serializer("published_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class VersionHistoryResponse(BaseModel):
    """Response for version history endpoint."""

    history: list[VersionHistoryEntry]
    active_version_id: UUID | None = Field(
        default=None,
        description="ID of the currently live version",
    )
    draft_version_id: UUID | None = Field(
        default=None,
        description="ID of the current draft version",
    )


# ==================== PAGE MODELS ====================


class AppPageBase(BaseModel):
    """Shared page fields."""

    page_id: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Page identifier (lowercase letters, numbers, underscores, hyphens)",
    )
    title: str = Field(min_length=1, max_length=255, description="Page display title")
    path: str = Field(min_length=1, max_length=255, description="Page URL path (e.g., '/' or '/settings')")


class AppPageCreate(AppPageBase):
    """Input for creating a page."""

    data_sources: list[dict[str, Any]] = Field(default_factory=list, description="Page-level data sources")
    variables: dict[str, Any] = Field(default_factory=dict, description="Page-level variables")
    launch_workflow_id: UUID | None = Field(default=None, description="Workflow to execute on page mount")
    launch_workflow_params: dict[str, Any] | None = Field(default=None, description="Parameters for launch workflow")
    launch_workflow_data_source_id: str | None = Field(default=None, description="Data source ID for workflow results (defaults to workflow function name)")
    permission: dict[str, Any] = Field(default_factory=dict, description="Page permission config (allowedRoles, etc.)")
    page_order: int = Field(default=0, ge=0, description="Order in navigation/page list")


class AppPageUpdate(BaseModel):
    """Input for updating a page."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    path: str | None = Field(default=None, min_length=1, max_length=255)
    data_sources: list[dict[str, Any]] | None = None
    variables: dict[str, Any] | None = None
    launch_workflow_id: UUID | None = None
    launch_workflow_params: dict[str, Any] | None = None
    launch_workflow_data_source_id: str | None = None
    permission: dict[str, Any] | None = None
    page_order: int | None = Field(default=None, ge=0)


class AppPageSummary(BaseModel):
    """Page summary for listings (no component details)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_id: str
    title: str
    path: str
    version_id: UUID = Field(description="ID of the version this page belongs to")
    page_order: int
    permission: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class AppPageResponse(AppPageSummary):
    """Full page response with all fields (but not component tree)."""

    application_id: UUID
    data_sources: list[dict[str, Any]]
    variables: dict[str, Any]
    launch_workflow_id: UUID | None
    launch_workflow_params: dict[str, Any] | None
    launch_workflow_data_source_id: str | None


class AppPageListResponse(BaseModel):
    """Response for listing pages."""

    pages: list[AppPageSummary]
    total: int


# ==================== COMPONENT MODELS ====================


class AppComponentBase(BaseModel):
    """Shared component fields."""

    component_id: str = Field(
        min_length=1,
        max_length=255,
        description="Component identifier (e.g., 'btn_submit', 'table_customers')",
    )
    type: str = Field(
        min_length=1,
        max_length=50,
        description="Component type (button, text, data-table, row, column, grid, etc.)",
    )


class AppComponentCreate(AppComponentBase):
    """Input for creating a component."""

    parent_id: UUID | None = Field(default=None, description="Parent component ID (null for root level)")
    props: dict[str, Any] = Field(default_factory=dict, description="Component-specific properties")
    component_order: int = Field(default=0, ge=0, description="Order among siblings")
    visible: str | None = Field(default=None, description="Visibility expression (e.g., \"{{ user.role == 'admin' }}\")")
    width: str | None = Field(default=None, max_length=20, description="Component width (auto, full, 1/2, etc.)")
    loading_workflows: list[str] | None = Field(default=None, description="Workflow IDs that show loading skeleton")

    @model_validator(mode="after")
    def validate_layout_props(self) -> "AppComponentCreate":
        """Validate layout container props match expected types."""
        if self.type in ("row", "column", "grid"):
            # Validate layout-specific props
            props = self.props or {}
            if "padding" in props and not isinstance(props["padding"], int | type(None)):
                raise ValueError(f"padding must be an integer, got {type(props['padding']).__name__}")
            if "gap" in props and not isinstance(props["gap"], int | type(None)):
                raise ValueError(f"gap must be an integer, got {type(props['gap']).__name__}")
            if "columns" in props and not isinstance(props["columns"], int | type(None)):
                raise ValueError(f"columns must be an integer, got {type(props['columns']).__name__}")
            if "maxHeight" in props and not isinstance(props["maxHeight"], int | type(None)):
                raise ValueError(f"maxHeight must be an integer, got {type(props['maxHeight']).__name__}")
            if "stickyOffset" in props and not isinstance(props["stickyOffset"], int | type(None)):
                raise ValueError(f"stickyOffset must be an integer, got {type(props['stickyOffset']).__name__}")
            if "distribute" in props and props["distribute"] not in (None, "natural", "equal", "fit"):
                raise ValueError(f"distribute must be one of: natural, equal, fit, got {props['distribute']}")
            if "overflow" in props and props["overflow"] not in (None, "auto", "scroll", "hidden", "visible"):
                raise ValueError(f"overflow must be one of: auto, scroll, hidden, visible, got {props['overflow']}")
            if "sticky" in props and props["sticky"] not in (None, "top", "bottom"):
                raise ValueError(f"sticky must be one of: top, bottom, got {props['sticky']}")
            if "align" in props and props["align"] not in (None, "start", "center", "end", "stretch"):
                raise ValueError(f"align must be one of: start, center, end, stretch, got {props['align']}")
            if "justify" in props and props["justify"] not in (None, "start", "center", "end", "between", "around"):
                raise ValueError(f"justify must be one of: start, center, end, between, around, got {props['justify']}")
        return self


class AppComponentUpdate(BaseModel):
    """Input for updating a component."""

    type: str | None = Field(default=None, min_length=1, max_length=50)
    props: dict[str, Any] | None = None
    component_order: int | None = Field(default=None, ge=0)
    visible: str | None = None
    width: str | None = Field(default=None, max_length=20)
    loading_workflows: list[str] | None = None

    @model_validator(mode="after")
    def validate_layout_props(self) -> "AppComponentUpdate":
        """Validate layout container props match expected types."""
        # Only validate if type is a layout container
        # (type can be None in updates, so check if props look like layout props)
        if self.type in ("row", "column", "grid") and self.props:
            props = self.props
            if "padding" in props and not isinstance(props["padding"], int | type(None)):
                raise ValueError(f"padding must be an integer, got {type(props['padding']).__name__}")
            if "gap" in props and not isinstance(props["gap"], int | type(None)):
                raise ValueError(f"gap must be an integer, got {type(props['gap']).__name__}")
            if "columns" in props and not isinstance(props["columns"], int | type(None)):
                raise ValueError(f"columns must be an integer, got {type(props['columns']).__name__}")
            if "maxHeight" in props and not isinstance(props["maxHeight"], int | type(None)):
                raise ValueError(f"maxHeight must be an integer, got {type(props['maxHeight']).__name__}")
            if "stickyOffset" in props and not isinstance(props["stickyOffset"], int | type(None)):
                raise ValueError(f"stickyOffset must be an integer, got {type(props['stickyOffset']).__name__}")
            if "distribute" in props and props["distribute"] not in (None, "natural", "equal", "fit"):
                raise ValueError(f"distribute must be one of: natural, equal, fit, got {props['distribute']}")
            if "overflow" in props and props["overflow"] not in (None, "auto", "scroll", "hidden", "visible"):
                raise ValueError(f"overflow must be one of: auto, scroll, hidden, visible, got {props['overflow']}")
            if "sticky" in props and props["sticky"] not in (None, "top", "bottom"):
                raise ValueError(f"sticky must be one of: top, bottom, got {props['sticky']}")
            if "align" in props and props["align"] not in (None, "start", "center", "end", "stretch"):
                raise ValueError(f"align must be one of: start, center, end, stretch, got {props['align']}")
            if "justify" in props and props["justify"] not in (None, "start", "center", "end", "between", "around"):
                raise ValueError(f"justify must be one of: start, center, end, between, around, got {props['justify']}")
        return self


class AppComponentMove(BaseModel):
    """Input for moving a component to a new parent/position."""

    new_parent_id: UUID | None = Field(description="New parent component ID (null for root level)")
    new_order: int = Field(ge=0, description="New order among siblings")


class AppComponentSummary(BaseModel):
    """Component summary for listings (type + position info)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    component_id: str
    parent_id: UUID | None
    type: str
    component_order: int


class AppComponentResponse(AppComponentSummary):
    """Full component response with all fields."""

    page_id: UUID
    props: dict[str, Any]
    visible: str | None
    width: str | None
    loading_workflows: list[str] | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class AppComponentListResponse(BaseModel):
    """Response for listing components."""

    components: list[AppComponentSummary]
    total: int


class PageListItem(BaseModel):
    """Summary of a page for list endpoints (without full layout)."""

    id: str
    title: str
    path: str
    page_order: int


# ==================== LEGACY TREE MODELS (for internal use, to be deprecated) ====================


class ComponentTreeNode(BaseModel):
    """
    A component with its children for tree representation.

    DEPRECATED: Use LayoutContainer and AppComponentNode instead.
    Kept for backwards compatibility during migration.
    """

    id: UUID
    component_id: str
    type: str
    props: dict[str, Any]
    visible: str | None = None
    width: str | None = None
    loading_workflows: list[str] | None = None
    component_order: int
    children: list["ComponentTreeNode"] = Field(default_factory=list)


# ==================== CODE FILE MODELS ====================


class AppCodeFileBase(BaseModel):
    """Shared code file fields."""

    path: str = Field(
        min_length=1,
        max_length=500,
        description="File path within the app (e.g., 'pages/clients/[id]', 'components/Button')",
    )


class AppCodeFileCreate(AppCodeFileBase):
    """Input for creating a code file."""

    source: str = Field(
        min_length=1,
        description="Original source code",
    )


class AppCodeFileUpdate(BaseModel):
    """Input for updating a code file."""

    source: str | None = Field(
        default=None,
        description="Updated source code",
    )
    compiled: str | None = Field(
        default=None,
        description="Compiled output",
    )


class AppCodeFileResponse(AppCodeFileBase):
    """Full code file response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    app_version_id: UUID = Field(description="ID of the version this file belongs to")
    source: str = Field(description="Original source code")
    compiled: str | None = Field(default=None, description="Compiled output")
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class AppCodeFileListResponse(BaseModel):
    """Response for listing code files."""

    files: list[AppCodeFileResponse]
    total: int


# ==================== IMPORT MODELS ====================
# Applications use file sync (like forms/agents), not a dedicated import endpoint
