"""
Application contract models for Bifrost App Builder.

Provides Pydantic models for API request/response handling.
Applications use code-based files (TSX/TypeScript) stored in app_files table.

Type Alignment:
These models are designed to match the frontend TypeScript types exactly.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
import re


# ==================== NAVIGATION & PERMISSION TYPES ====================


PageTransition = Literal["fade", "slide", "blur", "none"]
PermissionLevel = Literal["none", "view", "edit", "admin"]


class NavItem(BaseModel):
    """Navigation item for sidebar/navbar."""

    id: str = Field(description="Item identifier (usually page ID)")
    label: str = Field(description="Display label")
    icon: str | None = Field(default=None, description="Icon name (lucide icon)")
    path: str | None = Field(default=None, description="Navigation path")
    visible: str | None = Field(default=None, description="Visibility expression")
    order: int | None = Field(default=None, description="Order in navigation")
    is_section: bool | None = Field(
        default=None, description="Whether this is a section header (group)"
    )
    children: list["NavItem"] | None = Field(
        default=None, description="Child items for section groups"
    )


class NavigationConfig(BaseModel):
    """Navigation configuration for the application."""

    sidebar: list[NavItem] | None = Field(
        default=None, description="Sidebar navigation items"
    )
    show_sidebar: bool | None = Field(
        default=None, description="Whether to show the sidebar"
    )
    show_header: bool | None = Field(
        default=None, description="Whether to show the header"
    )
    logo_url: str | None = Field(default=None, description="Custom logo URL")
    brand_color: str | None = Field(default=None, description="Brand color (hex)")
    page_transition: PageTransition | None = Field(
        default=None,
        description="Page transition animation. Defaults to 'fade'. Use 'none' to disable.",
    )


class PermissionRule(BaseModel):
    """Permission rule for app access control."""

    role: str = Field(
        description='Role that has this permission (e.g., "admin", "user", "*" for all)'
    )
    level: Literal["view", "edit", "admin"] = Field(
        description="Permission level: view, edit, admin"
    )


class PermissionConfig(BaseModel):
    """Permission configuration for an application."""

    public: bool | None = Field(
        default=None, description="Whether the app is public (no auth required)"
    )
    default_level: PermissionLevel | None = Field(
        default=None, description="Default permission level for authenticated users"
    )
    rules: list[PermissionRule] | None = Field(
        default=None, description="Role-based permission rules"
    )

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
    role_ids: list[UUID] = Field(default_factory=list)
    navigation: NavigationConfig | dict[str, Any] | None = Field(
        default=None,
        description="Navigation configuration (sidebar items, etc.)",
    )
    # Export fields - optional, only included when exporting full app
    permissions: PermissionConfig | None = Field(
        default=None,
        description="Permission configuration (included in export)",
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


# ==================== APP FILE MODELS ====================


class AppFileBase(BaseModel):
    """Shared code file fields."""

    path: str = Field(
        min_length=1,
        max_length=500,
        description="File path within the app (e.g., 'pages/clients/[id]', 'components/Button')",
    )


class AppFileCreate(AppFileBase):
    """Input for creating a code file."""

    source: str = Field(
        min_length=1,
        description="Original source code",
    )


class AppFileUpdate(BaseModel):
    """Input for updating a code file."""

    source: str | None = Field(
        default=None,
        description="Updated source code",
    )
    compiled: str | None = Field(
        default=None,
        description="Compiled output",
    )


class AppFileResponse(AppFileBase):
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


class AppFileListResponse(BaseModel):
    """Response for listing code files."""

    files: list[AppFileResponse]
    total: int


# ==================== IMPORT MODELS ====================
# Applications use file sync (like forms/agents), not a dedicated import endpoint
