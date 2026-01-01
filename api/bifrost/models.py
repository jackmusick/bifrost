"""
bifrost/models.py - Pydantic models (single source of truth)

All SDK types are defined here and used consistently across:
- API handlers (validation/serialization)
- SDK modules (return types)
- Client code (type hints)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Organization(BaseModel):
    """Organization entity."""

    id: str
    name: str
    domain: str | None = None
    is_active: bool = True
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Role(BaseModel):
    """Role entity."""

    id: str
    name: str
    description: str | None = None
    organization_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPublic(BaseModel):
    """User entity (public fields only)."""

    id: str
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    is_registered: bool
    user_type: str
    organization_id: str | None
    mfa_enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


class FormPublic(BaseModel):
    """Form entity (public fields)."""

    id: str
    name: str
    description: str | None
    workflow_id: str | None
    launch_workflow_id: str | None
    default_launch_params: dict | None
    allowed_query_params: list[str] | None
    form_schema: dict | None
    access_level: str
    organization_id: str | None
    is_active: bool
    file_path: str | None
    created_at: datetime | None
    updated_at: datetime | None


class WorkflowMetadata(BaseModel):
    """Workflow metadata."""

    id: str
    name: str
    description: str | None
    category: str | None
    tags: list[str]
    parameters: dict
    execution_mode: str
    timeout_seconds: int | None
    retry_policy: dict | None
    schedule: str | None
    endpoint_enabled: bool
    allowed_methods: list[str] | None
    disable_global_key: bool
    public_endpoint: bool
    is_tool: bool
    tool_description: str | None
    time_saved: int | None
    source_file_path: str | None
    relative_file_path: str | None


class WorkflowExecution(BaseModel):
    """Workflow execution record."""

    execution_id: str
    workflow_name: str
    org_id: str | None
    form_id: str | None
    executed_by: str | None
    executed_by_name: str | None
    status: str
    input_data: dict | None
    result: Any
    result_type: str | None
    error_message: str | None
    duration_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    logs: list[dict] | None
    variables: dict | None
    session_id: str | None
    peak_memory_bytes: int | None
    cpu_total_seconds: float | None


class IntegrationData(BaseModel):
    """Integration configuration data."""

    integration_id: str
    entity_id: str | None
    entity_name: str | None
    config: dict
    oauth: "OAuthCredentials | None" = None


class OAuthCredentials(BaseModel):
    """OAuth connection credentials."""

    connection_name: str
    client_id: str | None
    client_secret: str | None
    authorization_url: str | None
    token_url: str | None
    scopes: list[str]
    access_token: str | None
    refresh_token: str | None
    expires_at: str | None


class IntegrationMappingResponse(BaseModel):
    """Integration mapping record."""

    id: str
    integration_id: str
    organization_id: str
    entity_id: str
    entity_name: str | None
    oauth_token_id: str | None
    config: dict
    created_at: datetime
    updated_at: datetime


class ConfigData(BaseModel):
    """Configuration data with dict-like access.

    Supports both attribute and dict-style access:
    - cfg.my_key
    - cfg["my_key"]
    """

    data: dict[str, Any]

    def __getattr__(self, key: str) -> Any:
        """Allow attribute-style access (cfg.key)."""
        if key == "data":
            return super().__getattribute__(key)
        return self.data.get(key)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access (cfg["key"])."""
        return self.data[key]


class AIResponse(BaseModel):
    """AI completion response."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str


class AIStreamChunk(BaseModel):
    """AI streaming chunk."""

    content: str
    done: bool
    input_tokens: int | None = None
    output_tokens: int | None = None


class KnowledgeDocument(BaseModel):
    """Knowledge base document."""

    id: str
    namespace: str
    content: str
    metadata: dict | None
    score: float | None
    organization_id: str | None
    key: str | None
    created_at: datetime | None


class NamespaceInfo(BaseModel):
    """Knowledge namespace information."""

    namespace: str
    scopes: dict  # global/org/total counts


# ==================== TABLES SDK MODELS ====================


class TableInfo(BaseModel):
    """Table metadata."""

    id: str
    name: str
    description: str | None = None
    table_schema: dict | None = None
    organization_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentData(BaseModel):
    """Document with data and metadata."""

    id: str
    table_id: str
    data: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None
    created_by: str | None = None
    updated_by: str | None = None


class DocumentList(BaseModel):
    """Query result with documents and pagination."""

    documents: list[DocumentData]
    total: int
    limit: int
    offset: int
