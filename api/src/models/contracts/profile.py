"""
Profile contract models for user profile management.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class ProfileUpdate(BaseModel):
    """Request model for updating user profile."""

    name: str | None = Field(default=None, min_length=1, max_length=255, description="Display name")


class PasswordChange(BaseModel):
    """Request model for changing or setting password."""

    current_password: str | None = Field(default=None, min_length=1, description="Current password (required if user has a password set)")
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")


class ProfileResponse(BaseModel):
    """Response model for user profile."""

    id: UUID
    email: str
    name: str | None
    has_avatar: bool
    has_password: bool
    organization_id: UUID | None
    is_superuser: bool
