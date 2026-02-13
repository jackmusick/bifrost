"""
Maintenance Models

Pydantic models for workspace maintenance operations.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MaintenanceStatus(BaseModel):
    """Current maintenance status of the workspace."""

    total_files: int = Field(
        default=0,
        description="Total number of files in workspace",
    )
    last_reindex: datetime | None = Field(
        default=None,
        description="Timestamp of last reindex operation",
    )


class ReimportJobResponse(BaseModel):
    """Response from a reimport request."""

    status: str = Field(description="Job status: queued")
    job_id: str = Field(description="Job ID for polling via GET /api/jobs/{job_id}")


class DocsIndexResponse(BaseModel):
    """Response from documentation indexing operation."""

    status: str = Field(
        description="Operation status: complete, skipped, failed"
    )
    files_indexed: int = Field(
        default=0,
        description="Number of documentation files that were indexed (new or changed)",
    )
    files_unchanged: int = Field(
        default=0,
        description="Number of files skipped because content was unchanged",
    )
    files_deleted: int = Field(
        default=0,
        description="Number of orphaned documents removed",
    )
    duration_ms: int = Field(
        default=0,
        description="Time taken to complete indexing in milliseconds",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable status message or error description",
    )


class PreflightIssueResponse(BaseModel):
    """A single preflight validation issue."""

    level: str = Field(description="Issue level: 'error' or 'warning'")
    category: str = Field(description="Issue category")
    detail: str = Field(description="Human-readable description")
    path: str | None = Field(default=None, description="File path if applicable")


class PreflightResponse(BaseModel):
    """Response from on-demand preflight validation."""

    valid: bool = Field(description="True if no errors found")
    issues: list[PreflightIssueResponse] = Field(
        default_factory=list, description="Blocking issues"
    )
    warnings: list[PreflightIssueResponse] = Field(
        default_factory=list, description="Non-blocking warnings"
    )
