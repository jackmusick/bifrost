"""
Workflow metadata and validation contract models for Bifrost.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import FormAccessLevel
from src.models.contracts.base import RetryPolicy

if TYPE_CHECKING:
    pass


# ==================== WORKFLOW PARAMETER & METADATA ====================


class WorkflowParameter(BaseModel):
    """Workflow parameter metadata"""
    name: str
    type: str  # string, int, bool, etc.
    required: bool
    label: str | None = None
    data_provider: str | None = None
    default_value: Any | None = None
    help_text: str | None = None
    validation: dict[str, Any] | None = None
    description: str | None = None


class WorkflowMetadata(BaseModel):
    """Workflow metadata for discovery API"""
    # Unique identifier
    id: str = Field(..., description="Workflow UUID")

    # Required fields
    name: str = Field(..., min_length=1, pattern=r"^[a-z0-9_]+$", description="Workflow name (snake_case)")
    description: str | None = Field(None, description="Human-readable description")

    # Optional fields with defaults
    category: str = Field("General", description="Category for organization")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization and search")
    parameters: list[WorkflowParameter] = Field(default_factory=list, description="Workflow parameters")

    # Execution configuration
    execution_mode: Literal["sync", "async"] = Field("sync", description="Execution mode")
    timeout_seconds: int = Field(1800, ge=1, le=7200, description="Max execution time in seconds (default 30 min, max 2 hours)")

    # Retry and scheduling (for future use)
    retry_policy: RetryPolicy | None = Field(None, description="Retry configuration")
    schedule: str | None = Field(None, description="Cron expression for scheduled execution")

    # HTTP Endpoint configuration
    endpoint_enabled: bool = Field(False, description="Whether workflow is exposed as HTTP endpoint")
    allowed_methods: list[str] = Field(default_factory=lambda: ["POST"], description="Allowed HTTP methods")
    disable_global_key: bool = Field(False, description="If true, only workflow-specific API keys work")
    public_endpoint: bool = Field(False, description="If true, skip authentication for webhooks")

    # Source tracking
    source_file_path: str | None = Field(None, description="Full file path to the workflow source code")
    relative_file_path: str | None = Field(None, description="Workspace-relative file path with /workspace/ prefix (e.g., '/workspace/workflows/my_workflow.py')")


class DataProviderMetadata(BaseModel):
    """Data provider metadata from @data_provider decorator (T008)"""
    name: str
    description: str | None = None
    category: str = "General"
    cache_ttl_seconds: int = 300
    parameters: list[WorkflowParameter] = Field(default_factory=list, description="Input parameters from @param decorators")
    source_file_path: str | None = Field(None, description="Full file path to the data provider source code")
    relative_file_path: str | None = Field(None, description="Workspace-relative file path with /workspace/ prefix (e.g., '/workspace/data_providers/my_provider.py')")


class FormDiscoveryMetadata(BaseModel):
    """Lightweight form metadata for discovery endpoint"""
    id: str
    name: str
    workflow_id: str | None = None
    org_id: str
    is_active: bool
    is_global: bool
    access_level: FormAccessLevel | str | None = None
    created_at: datetime
    updated_at: datetime


class MetadataResponse(BaseModel):
    """Response model for /admin/workflow endpoint"""
    workflows: list[WorkflowMetadata] = Field(default_factory=list)
    data_providers: list[DataProviderMetadata] = Field(default_factory=list)
    forms: list[FormDiscoveryMetadata] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


# ==================== WORKFLOW VALIDATION ====================


class ValidationIssue(BaseModel):
    """A single validation error or warning"""
    line: int | None = Field(None, description="Line number where issue occurs (if applicable)")
    message: str = Field(..., description="Human-readable error or warning message")
    severity: Literal["error", "warning"] = Field(..., description="Severity level")


class WorkflowValidationRequest(BaseModel):
    """Request model for workflow validation endpoint"""
    path: str = Field(..., description="Relative workspace path to the workflow file")
    content: str | None = Field(None, description="File content to validate (if not provided, reads from disk)")


class WorkflowValidationResponse(BaseModel):
    """Response model for workflow validation endpoint"""
    valid: bool = Field(..., description="True if workflow is valid and will be discovered")
    issues: list[ValidationIssue] = Field(default_factory=list, description="List of errors and warnings")
    metadata: WorkflowMetadata | None = Field(None, description="Workflow metadata if valid")


# ==================== WORKFLOW API KEYS ====================


class WorkflowKey(BaseModel):
    """Workflow API Key for HTTP access without user authentication"""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()), description="Unique key ID")
    hashed_key: str = Field(..., description="SHA-256 hash of the API key")
    workflow_id: str | None = Field(None, description="Workflow-specific key, or None for global access")
    created_by: str = Field(..., description="User email who created the key")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    revoked: bool = Field(default=False)
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    expires_at: datetime | None = Field(None, description="Optional expiration timestamp")
    description: str | None = Field(None, description="Optional key description")
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")


class WorkflowKeyCreateRequest(BaseModel):
    """Request model for creating a workflow API key"""
    workflow_name: str | None = Field(None, description="Workflow-specific key, or None for global")
    expires_in_days: int | None = Field(None, description="Days until key expires (default: no expiration)")
    description: str | None = Field(None, description="Optional key description")
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")


class WorkflowKeyResponse(BaseModel):
    """Response model for workflow key (includes raw key on creation only)"""
    id: str
    raw_key: str | None = Field(None, description="Raw API key (only returned on creation)")
    masked_key: str | None = Field(None, description="Last 4 characters for display")
    workflow_name: str | None = None
    created_by: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked: bool
    expires_at: datetime | None = None
    description: str | None = None
    disable_global_key: bool = Field(default=False, description="If true, workflow opts out of global API keys")
