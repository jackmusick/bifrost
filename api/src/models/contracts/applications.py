"""
Application contract models for Bifrost App Builder.

Provides Pydantic models for API request/response handling.
Supports the 3-table schema: applications -> app_pages -> app_components

Type Alignment:
These models are designed to match the frontend TypeScript types exactly.
Uses camelCase aliases for JSON serialization to match frontend conventions.
"""

from datetime import datetime
from typing import Any, ForwardRef, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from pydantic.alias_generators import to_camel
import re


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


class ApplicationUpdate(BaseModel):
    """Input for updating application metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=50)
    access_level: str | None = Field(
        default=None,
        description="Access level: 'authenticated' (any logged-in user) or 'role_based' (specific roles)",
    )
    role_ids: list[UUID] | None = Field(
        default=None,
        description="Role IDs for role_based access (replaces existing roles)",
    )

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v: str | None) -> str | None:
        """Validate access_level is one of the allowed values."""
        if v is not None and v not in ("authenticated", "role_based"):
            raise ValueError("access_level must be 'authenticated' or 'role_based'")
        return v


class ApplicationPublic(ApplicationBase):
    """Application output for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    organization_id: UUID | None
    live_version: int
    draft_version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    is_published: bool
    has_unpublished_changes: bool
    access_level: str = Field(default="authenticated")
    role_ids: list[UUID] = Field(default_factory=list)

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

    version: int = Field(
        ...,
        ge=1,
        description="Version number to rollback to (from version_history)",
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
    current_live_version: int
    current_draft_version: int


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
    permission: dict[str, Any] = Field(default_factory=dict, description="Page permission config (allowedRoles, etc.)")
    page_order: int = Field(default=0, ge=0, description="Order in navigation/page list")
    root_layout_type: str = Field(default="column", description="Root layout type (row, column, grid)")
    root_layout_config: dict[str, Any] = Field(default_factory=dict, description="Root layout config (gap, padding, etc.)")


class AppPageUpdate(BaseModel):
    """Input for updating a page."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    path: str | None = Field(default=None, min_length=1, max_length=255)
    data_sources: list[dict[str, Any]] | None = None
    variables: dict[str, Any] | None = None
    launch_workflow_id: UUID | None = None
    launch_workflow_params: dict[str, Any] | None = None
    permission: dict[str, Any] | None = None
    page_order: int | None = Field(default=None, ge=0)
    root_layout_type: str | None = None
    root_layout_config: dict[str, Any] | None = None


class AppPageSummary(BaseModel):
    """Page summary for listings (no component details)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_id: str
    title: str
    path: str
    is_draft: bool
    version: int
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
    root_layout_type: str
    root_layout_config: dict[str, Any]


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


class AppComponentUpdate(BaseModel):
    """Input for updating a component."""

    type: str | None = Field(default=None, min_length=1, max_length=50)
    props: dict[str, Any] | None = None
    component_order: int | None = Field(default=None, ge=0)
    visible: str | None = None
    width: str | None = Field(default=None, max_length=20)
    loading_workflows: list[str] | None = None


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
    is_draft: bool
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


# ==================== TYPED LAYOUT MODELS (matches frontend TypeScript types) ====================
#
# These models are the single source of truth for the layout system.
# They serialize to camelCase JSON that the frontend can use directly.
# TypeScript types are auto-generated from these via OpenAPI.


class CamelCaseModel(BaseModel):
    """Base model with camelCase serialization for frontend compatibility."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class DataSourceConfig(CamelCaseModel):
    """Data source configuration for dynamic data binding."""

    id: str
    type: Literal["api", "static", "computed", "data-provider", "workflow"]
    endpoint: str | None = None
    data: Any | None = None
    expression: str | None = None
    data_provider_id: str | None = None
    workflow_id: str | None = None
    input_params: dict[str, Any] | None = None
    auto_refresh: bool | None = None
    refresh_interval: int | None = None


class PagePermissionConfig(CamelCaseModel):
    """Page-level permission configuration."""

    allowed_roles: list[str] | None = None
    access_expression: str | None = None
    redirect_to: str | None = None


class AppComponentNode(CamelCaseModel):
    """
    Leaf component in the layout tree.

    Matches frontend TypeScript AppComponent interface.
    Examples: button, text, data-table, etc.
    """

    id: str
    type: str  # Component type: button, text, heading, data-table, etc.
    props: dict[str, Any] = Field(default_factory=dict)
    visible: str | None = None
    width: str | None = None
    loading_workflows: list[str] | None = None


# Forward reference for recursive type
LayoutContainerRef = ForwardRef("LayoutContainer")


class LayoutContainer(CamelCaseModel):
    """
    Layout container for organizing components.

    Matches frontend TypeScript LayoutContainer interface.
    Supports recursive nesting with children being either:
    - LayoutContainer (row, column, grid)
    - AppComponentNode (leaf components)
    """

    type: Literal["row", "column", "grid"]
    gap: int | None = None
    padding: int | None = None
    align: Literal["start", "center", "end", "stretch"] | None = None
    justify: Literal["start", "center", "end", "between", "around"] | None = None
    columns: int | None = None
    auto_size: bool | None = None
    visible: str | None = None
    class_name: str | None = None
    children: list[Union["LayoutContainer", AppComponentNode]] = Field(default_factory=list)


# Resolve forward reference
LayoutContainer.model_rebuild()


# Type alias for layout tree elements
LayoutElement = Union[LayoutContainer, AppComponentNode]


class PageDefinition(CamelCaseModel):
    """
    Full page definition with layout tree.

    Matches frontend TypeScript PageDefinition interface.
    This is the response format for GET /api/applications/{app_id}/pages/{page_id}.
    """

    id: str  # Page ID (e.g., "home", "settings")
    title: str
    path: str
    layout: LayoutContainer
    data_sources: list[DataSourceConfig] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    launch_workflow_id: str | None = None
    launch_workflow_params: dict[str, Any] | None = None
    permission: PagePermissionConfig | None = None


class PageListItem(CamelCaseModel):
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


class AppPageWithComponents(AppPageResponse):
    """
    Page response with full component tree.

    DEPRECATED: Use PageDefinition instead.
    Kept for backwards compatibility during migration.
    """

    components: list[ComponentTreeNode] = Field(
        default_factory=list,
        description="Component tree (root-level components with nested children)",
    )


# ==================== EXPORT/IMPORT MODELS ====================


class ApplicationExport(BaseModel):
    """Full application export for GitHub sync/portability."""

    # App metadata
    name: str
    slug: str
    description: str | None
    icon: str | None
    navigation: dict[str, Any]
    global_data_sources: list[dict[str, Any]]
    global_variables: dict[str, Any]
    permissions: dict[str, Any]

    # Pages with their component trees
    pages: list[dict[str, Any]] = Field(
        description="Array of page definitions with nested layout/components"
    )

    # Export metadata
    export_version: str = Field(default="1.0", description="Export format version")
    exported_at: datetime | None = None

    @field_serializer("exported_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


class ApplicationImport(BaseModel):
    """Input for importing an application from JSON."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[a-z][a-z0-9-]*$",
    )
    description: str | None = None
    icon: str | None = None
    navigation: dict[str, Any] = Field(default_factory=dict)
    global_data_sources: list[dict[str, Any]] = Field(default_factory=list)
    global_variables: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    pages: list[dict[str, Any]] = Field(description="Array of page definitions with nested layout/components")
