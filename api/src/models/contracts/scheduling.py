"""
Async execution and scheduling contract models for Bifrost.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    pass


# ==================== ASYNC EXECUTION ====================


class AsyncExecutionStatus(str, Enum):
    """Async execution status values"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AsyncExecution(BaseModel):
    """Async workflow execution tracking"""
    execution_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    workflow_id: str = Field(..., description="Workflow name to execute")
    status: AsyncExecutionStatus = Field(default=AsyncExecutionStatus.QUEUED)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Workflow input parameters")
    context: dict[str, Any] = Field(default_factory=dict, description="Execution context (org scope, user)")
    result: Any | None = Field(None, description="Workflow result (for small results)")
    result_blob_uri: str | None = Field(None, description="Blob URI for large results (>32KB)")
    error: str | None = Field(None, description="Error message if failed")
    error_details: dict[str, Any] | None = Field(None, description="Detailed error information")
    queued_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(None, description="Execution duration in milliseconds")


# ==================== CRON SCHEDULING ====================


class CronSchedule(BaseModel):
    """CRON schedule configuration for automatic workflow execution"""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    workflow_id: str = Field(..., description="Workflow name to execute on schedule")
    cron_expression: str = Field(..., description="Standard CRON expression (e.g., '0 2 * * *')")
    human_readable: str | None = Field(None, description="Human-readable schedule description")
    enabled: bool = Field(default=True)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Default parameters for execution")
    next_run_at: datetime = Field(..., description="Next scheduled execution time")
    last_run_at: datetime | None = None
    last_execution_id: str | None = Field(None, description="ID of last execution")
    created_by: str = Field(..., description="User email who created the schedule")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CronScheduleCreateRequest(BaseModel):
    """Request model for creating a CRON schedule"""
    workflow_id: str = Field(..., description="Workflow name to schedule")
    cron_expression: str = Field(..., description="CRON expression (e.g., '0 2 * * *' for 2am daily)")
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression(cls, v):
        """Validate CRON expression format"""
        from croniter import croniter
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid CRON expression: {v}")
        return v


class CronScheduleUpdateRequest(BaseModel):
    """Request model for updating a CRON schedule"""
    cron_expression: str | None = None
    parameters: dict[str, Any] | None = None
    enabled: bool | None = None


class ScheduleInfo(BaseModel):
    """Information about a scheduled workflow for display"""
    workflow_name: str = Field(..., description="Internal workflow name/identifier")
    workflow_description: str = Field(..., description="Display name of the workflow")
    cron_expression: str = Field(..., description="CRON expression")
    human_readable: str = Field(..., description="Human-readable schedule (e.g., 'Every day at 2:00 AM')")
    next_run_at: datetime | None = Field(None, description="Next scheduled execution time")
    last_run_at: datetime | None = Field(None, description="Last execution time")
    last_execution_id: str | None = Field(None, description="ID of last execution")
    execution_count: int = Field(0, description="Total number of times this schedule has been triggered")
    enabled: bool = Field(True, description="Whether this schedule is currently active")
    validation_status: Literal["valid", "warning", "error"] | None = Field(None, description="Validation status of the CRON expression")
    validation_message: str | None = Field(None, description="Validation message for warning/error statuses")
    is_overdue: bool = Field(False, description="Whether the schedule is overdue by more than 6 minutes")


class SchedulesListResponse(BaseModel):
    """Response model for listing scheduled workflows"""
    schedules: list[ScheduleInfo] = Field(..., description="List of scheduled workflows")
    total_count: int = Field(..., description="Total number of scheduled workflows")


class CronValidationRequest(BaseModel):
    """Request model for CRON validation"""
    expression: str = Field(..., description="CRON expression to validate")


class CronValidationResponse(BaseModel):
    """Response model for CRON validation"""
    valid: bool = Field(..., description="Whether the CRON expression is valid")
    human_readable: str = Field(..., description="Human-readable description")
    next_runs: list[str] | None = Field(None, description="Next 5 execution times (ISO format)")
    interval_seconds: int | None = Field(None, description="Seconds between executions")
    warning: str | None = Field(None, description="Warning message for too-frequent schedules")
    error: str | None = Field(None, description="Error message for invalid expressions")


class ProcessSchedulesResponse(BaseModel):
    """Response model for processing due schedules"""
    total: int = Field(..., description="Total number of scheduled workflows")
    due: int = Field(..., description="Number of schedules that were due")
    executed: int = Field(..., description="Number of schedules successfully executed")
    failed: int = Field(..., description="Number of schedules that failed to execute")
    errors: list[dict[str, str]] = Field(default_factory=list, description="List of error details")
