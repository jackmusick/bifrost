"""
Application contract models for Bifrost App Builder.

Provides Pydantic models for API request/response handling.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
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


class ApplicationUpdate(BaseModel):
    """Input for updating application metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=50)


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
