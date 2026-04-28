"""
Workspace contract models for Bifrost.

Per chat-ux-design §2 / §11: workspaces are first-class containers for chat
conversations with personal/org/role scoping that mirrors agents/forms.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from src.models.enums import WorkspaceScope


class WorkspaceCreate(BaseModel):
    """Request model for creating a workspace."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    scope: WorkspaceScope = Field(...)
    organization_id: UUID | None = Field(
        default=None,
        description="Organization ID (required for scope=org/role; ignored otherwise)",
    )
    role_id: UUID | None = Field(
        default=None,
        description="Role ID (required for scope=role; ignored otherwise)",
    )
    default_agent_id: UUID | None = Field(default=None)
    enabled_tool_ids: list[str] | None = Field(
        default=None,
        description="If set, restricts the agent's effective tools to this intersection",
    )
    enabled_knowledge_source_ids: list[str] | None = Field(default=None)
    instructions: str | None = Field(default=None, max_length=50000)


class WorkspaceUpdate(BaseModel):
    """Request model for updating a workspace.

    Note: `scope`, `organization_id`, `role_id`, and `user_id` are immutable after
    creation (the chat-ux-design §16.3 General tab marks scope read-only).
    """
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    default_agent_id: UUID | None = Field(default=None)
    enabled_tool_ids: list[str] | None = Field(default=None)
    enabled_knowledge_source_ids: list[str] | None = Field(default=None)
    instructions: str | None = Field(default=None, max_length=50000)
    is_active: bool | None = None


class WorkspacePublic(BaseModel):
    """Workspace output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    scope: WorkspaceScope
    organization_id: UUID | None = None
    role_id: UUID | None = None
    user_id: UUID | None = None
    default_agent_id: UUID | None = None
    enabled_tool_ids: list[str] | None = None
    enabled_knowledge_source_ids: list[str] | None = None
    instructions: str | None = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("id")
    def serialize_id(self, v: UUID) -> str:
        return str(v)

    @field_serializer("organization_id", "role_id", "user_id", "default_agent_id")
    def serialize_nullable_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


class WorkspaceSummary(BaseModel):
    """Lightweight workspace summary for listings."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    scope: WorkspaceScope
    organization_id: UUID | None = None
    role_id: UUID | None = None
    user_id: UUID | None = None
    is_active: bool
    created_at: datetime
    conversation_count: int = Field(
        default=0, description="Active conversations in this workspace"
    )

    @field_serializer("id")
    def serialize_id(self, v: UUID) -> str:
        return str(v)

    @field_serializer("organization_id", "role_id", "user_id")
    def serialize_nullable_uuid(self, v: UUID | None) -> str | None:
        return str(v) if v else None

    @field_serializer("created_at")
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()
