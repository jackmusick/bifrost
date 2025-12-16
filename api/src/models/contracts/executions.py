"""
Execution and system log contract models for Bifrost.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from src.models.enums import ExecutionStatus

if TYPE_CHECKING:
    pass


# ==================== WORKFLOW EXECUTION MODELS ====================


class ExecutionLogPublic(BaseModel):
    """Single log entry from workflow execution (API response model)"""
    timestamp: str
    level: str  # debug, info, warning, error
    message: str
    data: dict[str, Any] | None = None


class WorkflowExecution(BaseModel):
    """Workflow execution entity"""
    execution_id: str
    workflow_name: str
    org_id: str | None = None  # Organization ID for display/filtering
    form_id: str | None = None
    executed_by: str
    executed_by_name: str  # Display name of user who executed
    status: ExecutionStatus
    input_data: dict[str, Any]
    result: dict[str, Any] | list[Any] | str | None = Field(default=None)  # Can be dict/list (JSON) or str (HTML/text)
    result_type: str | None = None  # How to render result (json, html, text)
    error_message: str | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None  # May be None if not started yet
    completed_at: datetime | None = None
    logs: list[dict[str, Any]] | None = None  # Structured logger output (replaces old ExecutionLog format)
    variables: dict[str, Any] | None = None  # Runtime variables captured from execution scope
    # CLI session tracking
    session_id: str | None = None  # CLI session ID if executed from local runner
    # Resource metrics (admin only, null for non-admins)
    peak_memory_bytes: int | None = None
    cpu_total_seconds: float | None = None


class WorkflowExecutionRequest(BaseModel):
    """Request model for executing a workflow"""
    workflow_id: str | None = Field(default=None, description="UUID of the workflow to execute (required if code not provided)")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Workflow input parameters")
    form_id: str | None = Field(default=None, description="Optional form ID that triggered this execution")
    transient: bool = Field(default=False, description="If true, skip database persistence (for code editor debugging)")
    code: str | None = Field(default=None, description="Optional: Python code to execute as script (base64 encoded). If provided, executes code instead of looking up workflow by ID.")
    script_name: str | None = Field(default=None, description="Optional: Name/identifier for the script (used for logging when code is provided)")

    @model_validator(mode='after')
    def validate_workflow_or_code(self) -> 'WorkflowExecutionRequest':
        """Ensure either workflow_id or code is provided"""
        if not self.workflow_id and not self.code:
            raise ValueError("Either 'workflow_id' or 'code' must be provided")
        return self


class WorkflowExecutionResponse(BaseModel):
    """Response model for workflow execution"""
    execution_id: str
    workflow_id: str | None = None
    workflow_name: str | None = None  # Display name from @workflow decorator
    status: ExecutionStatus
    result: dict[str, Any] | list[Any] | str | None = Field(default=None)  # Can be dict/list (JSON) or str (HTML/text)
    error: str | None = None
    error_type: str | None = None
    details: dict[str, Any] | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Enhanced debugging output for code editor
    logs: list[dict[str, Any]] | None = None  # Structured logger output
    variables: dict[str, Any] | None = None  # Runtime variables from execution scope
    is_transient: bool = False  # Flag for editor executions (no DB persistence)


class ExecutionsListResponse(BaseModel):
    """Response model for listing workflow executions with pagination"""
    executions: list[WorkflowExecution] = Field(..., description="List of workflow executions")
    continuation_token: str | None = Field(default=None, description="Continuation token for next page (opaque, base64-encoded). Presence of token indicates more results available.")


class StuckExecutionsResponse(BaseModel):
    """Response model for stuck executions query"""
    executions: list[WorkflowExecution] = Field(..., description="List of stuck executions")
    count: int = Field(..., description="Number of stuck executions found")


class CleanupTriggeredResponse(BaseModel):
    """Response model for cleanup trigger operation"""
    cleaned: int = Field(..., description="Total number of executions cleaned up")
    pending: int = Field(..., description="Number of pending executions timed out")
    running: int = Field(..., description="Number of running executions timed out")
    failed: int = Field(..., description="Number of executions that failed to clean up")


# CRUD Pattern Models for Execution
class ExecutionBase(BaseModel):
    """Shared execution fields."""
    workflow_name: str = Field(max_length=255)
    workflow_version: str | None = Field(default=None, max_length=50)
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    parameters: dict = Field(default_factory=dict)
    result: dict | None = Field(default=None)
    result_type: str | None = Field(default=None, max_length=50)
    variables: dict | None = Field(default=None)
    error_message: str | None = Field(default=None)


class ExecutionCreate(BaseModel):
    """Input for creating an execution."""
    workflow_name: str
    workflow_version: str | None = None
    parameters: dict = Field(default_factory=dict)
    form_id: UUID | None = None


class ExecutionUpdate(BaseModel):
    """Input for updating an execution (typically status updates)."""
    status: ExecutionStatus | None = None
    result: dict | None = None
    result_type: str | None = None
    variables: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class ExecutionPublic(ExecutionBase):
    """Execution output for API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    executed_by: UUID
    executed_by_name: str
    organization_id: UUID | None
    form_id: UUID | None
    created_at: datetime

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None


# ==================== SYSTEM LOGS MODELS ====================


class SystemLog(BaseModel):
    """System log entry (platform events, not workflow executions)"""
    event_id: str = Field(..., description="Unique event ID (UUID)")
    timestamp: datetime = Field(..., description="When the event occurred (ISO 8601)")
    category: Literal["discovery", "organization", "user", "role", "config", "secret", "form", "oauth", "execution", "system", "error"] = Field(..., description="Event category")
    level: Literal["info", "warning", "error", "critical"] = Field(..., description="Event severity level")
    message: str = Field(..., description="Human-readable event description")
    executed_by: str = Field(..., description="User ID or 'System'")
    executed_by_name: str = Field(..., description="Display name or 'System'")
    details: dict[str, Any] | None = Field(default=None, description="Additional event-specific data")


class SystemLogsListResponse(BaseModel):
    """Response model for listing system logs with pagination"""
    logs: list[SystemLog] = Field(..., description="List of system log entries")
    continuation_token: str | None = Field(default=None, description="Continuation token for next page (opaque, base64-encoded)")
